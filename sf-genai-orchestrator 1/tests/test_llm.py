"""Runs the REAL LiteLLM Router with mocked provider responses (no network), so the failover chain
configured in LlmClient is what is actually being tested."""
import asyncio
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import litellm.utils
import pytest
from sf_orchestrator.llm import LlmClient, quiet_litellm
from sf_orchestrator.schemas import ReportError, parse_draft

from helpers import OK, VALID_DRAFT_TEXT, HttpErr, ask, client, make_settings, with_fake_router


quiet_litellm(debug=False)
RATE_LIMIT = "litellm.RateLimitError"  # LiteLLM's built-in mock for a 429
SERVER_ERROR = "litellm.InternalServerError"  # ... and for a 5xx


async def test_primary_model_answers_when_healthy():
    r = await ask(client(OK, OK, OK, OK))
    assert (r.provider, r.model, r.fallbacks) == ("gemini", "gemini-a", 0)
    assert r.value.workstreams[0].id == "W1"


async def test_quota_or_rate_limit_moves_to_the_backup_model_of_the_same_vendor():
    r = await ask(client(RATE_LIMIT, OK, OK, OK))
    assert (r.provider, r.model, r.fallbacks) == ("gemini", "gemini-b", 1)


async def test_both_gemini_models_down_falls_through_to_groq():
    r = await ask(client(RATE_LIMIT, SERVER_ERROR, OK, OK))
    assert (r.provider, r.model, r.fallbacks) == ("groq", "openai/gpt-a", 2)


async def test_last_model_in_the_chain_can_still_answer():
    r = await ask(client(RATE_LIMIT, RATE_LIMIT, SERVER_ERROR, OK))
    assert (r.provider, r.model, r.fallbacks) == ("groq", "openai/gpt-b", 3)


@pytest.mark.parametrize("status,text", [(401, "Incorrect API key"), (402, "insufficient credits"), (400, "bad request")])
async def test_auth_billing_and_bad_request_errors_also_fall_back(status, text):
    r = await ask(client(HttpErr(status, text), OK, OK, OK))
    assert r.model == "gemini-b"


async def test_raises_when_every_model_fails():
    with pytest.raises(Exception):
        await ask(client(RATE_LIMIT, RATE_LIMIT, RATE_LIMIT, RATE_LIMIT))


async def test_single_model_chain_works_without_fallbacks():
    r = await ask(client(OK, llm_chain="gemini/gemini-a"))
    assert r.model == "gemini-a"


# ── schema-validity handling (ours, not LiteLLM's): re-ask once, then give up ──


async def test_a_rejection_raised_by_the_callers_own_check_is_re_asked_too():
    """e.g. internal wording or a broken reference found by brd.build_report."""
    seen = []

    def strict(text: str):
        seen.append(text)
        if len(seen) == 1:
            raise ReportError("the text must not contain internal wording such as \"rootCauseAnalysis\"")
        return parse_draft(text)

    c, router = with_fake_router([(OK, "stop"), (OK, "stop")])
    r = await ask(c, strict)
    assert r.repairs == 1 and "internal wording" in router.calls[1][-1]["content"]


async def test_invalid_json_is_re_asked_with_the_reason_then_accepted():
    c, router = with_fake_router([("not json at all", "stop"), (OK, "stop")])
    r = await ask(c)
    assert r.repairs == 1 and len(router.calls) == 2
    assert "rejected" in router.calls[1][-1]["content"] and router.calls[1][-2]["content"] == "not json at all"


async def test_gives_up_after_the_configured_repair_attempts():
    c, router = with_fake_router([("nope", "stop")], llm_repair_attempts=1)
    with pytest.raises(ReportError):
        await ask(c)
    assert len(router.calls) == 2


async def test_truncated_output_is_not_re_asked():
    c, router = with_fake_router([('{"metricName": "X', "length")])
    with pytest.raises(ReportError, match="token limit"):
        await ask(c)
    assert len(router.calls) == 1


async def test_the_recommended_model_ids_route_correctly_through_litellm():
    chain = "gemini/gemini-3.8-flash,gemini/gemini-3.7-flash,groq/openai/gpt-oss-120b,groq/openai/gpt-oss-20b"
    mocks = [{"mock_response": RATE_LIMIT}, {"mock_response": SERVER_ERROR}, {"mock_response": OK}, {"mock_response": OK}]
    r = await ask(LlmClient(make_settings(llm_chain=chain), mocks))
    assert (r.provider, r.model, r.fallbacks) == ("groq", "openai/gpt-oss-120b", 2)


# ───────────── waiting, retries and the plain-words log (a fake provider over real HTTP) ─────────────
# A tiny local server stands in for the vendors, so the REAL LiteLLM retry/wait logic runs. Waits are set to 1 s.

class _Provider:
    """Fake chat-completions endpoint. The behaviour is chosen by the model name in the request."""

    calls: dict[str, int] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            model = body["model"].split("/")[-1]
            n = _Provider.calls[model] = _Provider.calls.get(model, 0) + 1

            def send(code, obj, headers=None):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            busy = {"error": {"code": 503, "message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}}
            if model == "flaky503" and n <= 2:
                return send(503, busy)
            if model == "dead503":
                return send(503, busy)
            if model == "limit429" and n == 1:
                return send(429, {"error": {"message": "Rate limit reached on tokens per minute (TPM). Please try again in 1s."}}, {"retry-after": "1"})
            if model == "auth401":
                return send(401, {"error": {"message": "Invalid API Key groq-key-1234567890"}})  # a provider that echoes the key
            send(200, {
                "id": "x", "object": "chat.completion", "created": 1, "model": body["model"], "service_tier": "on_demand",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": VALID_DRAFT_TEXT}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
            })


@pytest.fixture(scope="module")
def provider_url():
    server = HTTPServer(("127.0.0.1", 0), _Provider.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/openai/v1"
    server.shutdown()


async def ask_first(first: str, base: str, **settings_over):
    """Chain: <first> then a model that always works. Returns (result, seconds)."""
    _Provider.calls.clear()
    settings = make_settings(
        llm_chain=f"groq/openai/{first},groq/openai/good",
        llm_num_retries=2, llm_rate_limit_retries=1, llm_retry_wait_seconds=1,
        **settings_over,
    )
    client = LlmClient(settings, [{"api_base": base}, {"api_base": base}])
    started = time.monotonic()
    result = await client.generate("system", "user", parse_draft, run_key="RCM/TimeToHire")
    await asyncio.sleep(0.4)  # let the log lines of the last attempt arrive
    return result, time.monotonic() - started


async def test_a_503_high_demand_is_retried_on_the_same_model_after_waiting(provider_url, caplog):
    with caplog.at_level(logging.INFO):
        r, seconds = await ask_first("flaky503", provider_url)
    assert (r.model, r.fallbacks, r.retries) == ("openai/flaky503", 0, 2)
    assert _Provider.calls == {"flaky503": 3}
    assert seconds >= 2  # it really waited between the attempts
    assert "RCM/TimeToHire: groq/openai/flaky503 failed (503: This model is currently experiencing high demand.). Retry 1 of 2" in caplog.text
    assert "Retry 2 of 2" in caplog.text


async def test_a_rate_limit_waits_as_long_as_the_provider_says_then_retries_the_same_model(provider_url, caplog):
    with caplog.at_level(logging.INFO):
        r, seconds = await ask_first("limit429", provider_url)
    assert (r.model, r.fallbacks, r.retries) == ("openai/limit429", 0, 1)
    assert _Provider.calls == {"limit429": 2} and seconds >= 1
    assert "Retry 1 of 1 in about 1s" in caplog.text


async def test_a_model_that_stays_unavailable_is_retried_then_given_up_on(provider_url, caplog):
    with caplog.at_level(logging.INFO):
        r, _ = await ask_first("dead503", provider_url)
    assert (r.model, r.fallbacks) == ("openai/good", 1)
    assert _Provider.calls == {"dead503": 3, "good": 1}
    assert "Giving up on this model." in caplog.text


async def test_a_bad_key_is_not_retried_and_the_secret_is_not_logged(provider_url, caplog):
    with caplog.at_level(logging.INFO):
        r, seconds = await ask_first("auth401", provider_url)
    assert (r.model, r.fallbacks) == ("openai/good", 1)
    assert _Provider.calls == {"auth401": 1, "good": 1} and seconds < 2
    assert "failed (401" in caplog.text and "Giving up on this model." in caplog.text
    assert "groq-key-1234567890" not in caplog.text and "[REDACTED]" in caplog.text


def test_litellm_may_wait_longer_than_its_default_of_8_seconds():
    """A 30-60 s Retry-After (for example Groq's tokens-per-minute limit) must not be cut short."""
    assert litellm.utils.MAX_RETRY_DELAY >= 60

def test_the_thinking_limit_is_sent_with_every_call_and_can_be_switched_off():
    from sf_orchestrator.config import Settings

    base = {"gemini_api_key": "k" * 30, "llm_chain": "gemini/gemini-a"}
    assert LlmClient(Settings(_env_file=None, **base))._thinking == {"reasoning_effort": "low", "drop_params": True}
    assert LlmClient(Settings(_env_file=None, llm_reasoning_effort="MEDIUM", **base))._thinking["reasoning_effort"] == "medium"
    assert LlmClient(Settings(_env_file=None, llm_reasoning_effort="", **base))._thinking == {}


def test_cached_tokens_are_read_from_the_usage_when_the_provider_reports_them():
    from sf_orchestrator.llm import _cached_tokens

    assert _cached_tokens(SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens=4096))) == 4096
    assert _cached_tokens(SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens=None))) is None
    assert _cached_tokens(SimpleNamespace(prompt_tokens_details=None)) is None and _cached_tokens(None) is None
