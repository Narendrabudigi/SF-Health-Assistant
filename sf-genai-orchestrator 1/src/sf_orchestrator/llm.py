"""LLM access through LiteLLM.

LiteLLM's Router owns everything infrastructure-related. Per failure type:
  - 503 "high demand", 5xx, timeouts: wait, then retry the SAME model (LLM_NUM_RETRIES times, LLM_RETRY_WAIT_SECONDS apart)
  - 429 rate limit / tokens per minute: wait as long as the provider says (up to 60 s), then retry once
  - quota exhausted, bad key, bad request, anything else: no retry, go straight to the next model of the chain
  - a model that keeps failing is put on cooldown for the rest of the run
This module builds that Router from LLM_CHAIN, logs every failed attempt in plain words, and re-asks the model when its
answer is rejected by the caller's `parse` function (invalid JSON, wrong structure, internal wording, broken references, ...).
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")  # no network call at import time
# LiteLLM never waits longer than this between retries (its own default is 8 s). Read when litellm is imported.
os.environ.setdefault("MAX_RETRY_DELAY", "60")

import litellm  # noqa: E402
from litellm import RetryPolicy, Router  # noqa: E402
from litellm.integrations.custom_logger import CustomLogger  # noqa: E402

from . import dashboard  # noqa: E402
from .config import VENDOR_KEY_FIELDS, Settings  # noqa: E402
from .schemas import ReportError  # noqa: E402

log = logging.getLogger(__name__)

litellm.drop_params = True  # silently drop params a given model does not support

_NO_RETRY_MESSAGE = "Giving up on this model."


@dataclass
class LlmResult:
    value: Any  # whatever `parse` returned
    provider: str
    model: str
    fallbacks: int  # how many models were skipped before this one answered
    retries: int  # how many times the answering model was retried before it answered
    repairs: int  # how many times the model was re-asked after a rejected answer
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


def _cached_tokens(usage: Any) -> int | None:
    """How many of the input tokens the provider served from its prompt cache (billed at a discount). None when it does not say."""
    details = getattr(usage, "prompt_tokens_details", None)
    value = getattr(details, "cached_tokens", None) if details is not None else None
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def quiet_litellm(debug: bool) -> None:
    """LiteLLM logs ERROR lines while it works through a fallback that then succeeds; hide them unless debugging."""
    level = logging.DEBUG if debug else logging.CRITICAL
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        logging.getLogger(name).setLevel(level)


def _reason(exc: BaseException | None) -> str:
    """'503 UNAVAILABLE: This model is currently experiencing high demand...' from a provider error."""
    if exc is None:
        return "unknown error"
    text = str(exc)
    match = re.search(r'"message"\s*:\s*"(.+?)"\s*[,}]', text)
    message = match.group(1) if match else text
    code = getattr(exc, "status_code", None)
    return f"{code or type(exc).__name__}: {' '.join(message.split())[:140]}"


def _retry_after_seconds(exc: BaseException | None) -> float | None:
    headers = getattr(exc, "litellm_response_headers", None) or getattr(getattr(exc, "response", None), "headers", None)
    try:
        value = float(headers.get("retry-after")) if headers else None
    except (TypeError, ValueError):
        return None
    return value if value and 0 < value <= 60 else None


class _AttemptLog(CustomLogger):
    """Plain-words log of every FAILED attempt: which model, why, and whether a retry follows.
    One shared instance per process (LiteLLM keeps only one logger of a kind), re-configured by each LlmClient.
    It never raises, because logging must not be able to break a run."""

    def __init__(self) -> None:
        super().__init__()
        self._secrets: list[str] = []
        self._retries = self._rl_retries = self._wait = 0
        self._failed: dict[str, dict[str, int]] = {}  # run_key -> model -> failed attempts so far
        self._round: dict[str, int] = {}  # run_key -> how many times the model was re-asked so far

    def configure(self, secrets: Sequence[str], retries: int, rate_limit_retries: int, wait_seconds: int) -> None:
        self._secrets = [s for s in secrets if s]
        self._retries, self._rl_retries, self._wait = retries, rate_limit_retries, wait_seconds

    def begin(self, run_key: str, round: int = 0) -> None:
        self._failed[run_key] = {}
        self._round[run_key] = round

    def _budget(self, exc: BaseException | None) -> int:
        name = type(exc).__name__
        if name == "RateLimitError":
            return self._rl_retries
        if name in {"Timeout", "InternalServerError", "ServiceUnavailableError"}:
            return self._retries
        return 0

    async def async_log_failure_event(self, kwargs: dict[str, Any], response_obj: Any, start_time: Any, end_time: Any) -> None:
        try:
            meta = (kwargs.get("litellm_params") or {}).get("metadata") or {}
            key = str(meta.get("run_key") or "-")
            provider = kwargs.get("custom_llm_provider") or ""
            model = f"{provider}/{kwargs.get('model')}" if provider else str(kwargs.get("model"))
            exc = kwargs.get("exception")
            failed = self._failed.setdefault(key, {})
            failed[model] = n = failed.get(model, 0) + 1
            budget = self._budget(exc)
            if n <= budget:
                wait = _retry_after_seconds(exc) or self._wait
                follow = f"Retry {n} of {budget} in about {wait:.0f}s."
            else:
                follow = _NO_RETRY_MESSAGE
            line = f"{key}: {model} failed ({_reason(exc)}). {follow}"
            for secret in self._secrets:
                line = line.replace(secret, "[REDACTED]")
            log.warning(line)
            module, _, metric = key.partition("/")
            seconds = None
            try:
                seconds = int((end_time - start_time).total_seconds() * 1000)
            except Exception:  # noqa: BLE001
                pass
            dashboard.current().llm_call(
                module=module if metric else None, metric=metric or None, outcome="error", provider=provider or None,
                model=str(kwargs.get("model")), round=self._round.get(key, 0), status_code=getattr(exc, "status_code", None),
                error_class=type(exc).__name__, error_message=_reason(exc) + " | " + str(exc)[:1500], retry_info=follow,
                latency_ms=seconds, messages=kwargs.get("messages"),
            )
        except Exception:  # noqa: BLE001
            pass


_ATTEMPT_LOG = _AttemptLog()


def _install_attempt_log() -> None:
    if not any(c is _ATTEMPT_LOG for c in litellm.callbacks):
        litellm.callbacks.append(_ATTEMPT_LOG)


MAX_ECHO_CHARS = 1500


def _shortened(text: str) -> str:
    """A rejected answer is sent back so the model sees what to fix, but only its beginning: the whole answer would make the
    request too large for a provider with a per-minute token limit (Groq allows 8,000 tokens a minute)."""
    return text if len(text) <= MAX_ECHO_CHARS else text[:MAX_ECHO_CHARS] + " ...[the rest of the reply is left out]"


class LlmClient:
    def __init__(self, settings: Settings, deployment_overrides: Sequence[dict[str, Any]] | None = None):
        """`deployment_overrides[i]` is merged into the i-th model's litellm_params (test hook, e.g. mock_response)."""
        chain = settings.chain
        if not chain:
            raise ValueError("LLM_CHAIN is empty")
        names = [f"llm-{i + 1}" for i in range(len(chain))]

        model_list = []
        for i, (name, entry) in enumerate(zip(names, chain)):
            vendor = entry.split("/", 1)[0]
            key = getattr(settings, VENDOR_KEY_FIELDS[vendor])
            params: dict[str, Any] = {
                "model": entry,
                "api_key": key.get_secret_value() if key else None,
                "timeout": settings.llm_timeout_seconds,
            }
            if deployment_overrides:
                params.update(deployment_overrides[i])
            model_list.append({"model_name": name, "litellm_params": params})

        # group name -> (vendor, model) so results report exactly which chain entry answered
        self._answered_by = {n: tuple(e.split("/", 1)) for n, e in zip(names, chain)}

        retries = settings.llm_num_retries
        self._router = Router(
            model_list=model_list,
            # names[0] is the entry point; on failure LiteLLM tries names[1], names[2], ... in order
            fallbacks=[{names[0]: names[1:]}] if len(names) > 1 else [],
            num_retries=0,
            retry_policy=RetryPolicy(
                TimeoutErrorRetries=retries,
                InternalServerErrorRetries=retries,
                ServiceUnavailableErrorRetries=retries,  # the 503 "model is currently experiencing high demand"
                RateLimitErrorRetries=settings.llm_rate_limit_retries,  # waits as long as the provider asks (up to 60 s)
                # Retrying the same model cannot fix these; go straight to the next one.
                AuthenticationErrorRetries=0,
                BadRequestErrorRetries=0,
                ContentPolicyViolationErrorRetries=0,
                DefaultRetries=0,
            ),
            retry_after=settings.llm_retry_wait_seconds,  # minimum wait before retrying the same model
            allowed_fails=settings.llm_allowed_fails,
            cooldown_time=settings.llm_cooldown_seconds,
        )
        self._entry = names[0]
        self._settings = settings
        # Limits the hidden "thinking" tokens; drop_params makes a model without that setting ignore it instead of failing.
        effort = (settings.llm_reasoning_effort or "").strip().lower()
        self._thinking: dict[str, Any] = {"reasoning_effort": effort, "drop_params": True} if effort else {}
        _ATTEMPT_LOG.configure(settings.secret_values(), retries, settings.llm_rate_limit_retries, settings.llm_retry_wait_seconds)
        _install_attempt_log()
        self._attempts = _ATTEMPT_LOG

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        parse: Callable[[str], Any],
        *,
        run_key: str = "",
    ) -> LlmResult:
        """Ask the model; `parse` turns its text into the result or raises ReportError (then the model is re-asked)."""
        s = self._settings
        base = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        messages = base
        started = time.monotonic()
        repairs = 0

        last_rejection = ""
        module, _, metric = run_key.partition("/")
        while True:
            self._attempts.begin(run_key, repairs)
            attempt_started = time.monotonic()
            try:
                resp = await self._router.acompletion(
                    model=self._entry,
                    messages=messages,
                    temperature=s.llm_temperature,
                    max_tokens=s.llm_max_tokens,
                    response_format={"type": "json_object"},
                    metadata={"run_key": run_key},
                    **self._thinking,
                )
            except Exception as exc:
                if not last_rejection:
                    raise
                # The model had answered but the answer was rejected, and then the re-ask met a provider problem. Say both,
                # so the log shows what was actually wrong with the answer and not only the provider message.
                raise ReportError(f"the answer was rejected ({last_rejection}) and the re-ask failed: {str(exc)[:300]}") from exc
            choice = resp.choices[0]
            text = choice.message.content or ""
            hidden = getattr(resp, "_hidden_params", None) or {}
            headers = hidden.get("additional_headers") or {}
            usage = getattr(resp, "usage", None)
            vendor, model = self._answered_by.get(
                str(headers.get("x-litellm-model-group")),
                (hidden.get("custom_llm_provider") or "unknown", getattr(resp, "model", None) or "unknown"),
            )

            def record(outcome: str, why: str | None = None) -> None:
                dashboard.current().llm_call(
                    module=module if metric else None, metric=metric or None, outcome=outcome, provider=str(vendor), model=str(model),
                    round=repairs, error_message=why, input_tokens=getattr(usage, "prompt_tokens", None), cached_tokens=_cached_tokens(usage),
                    output_tokens=getattr(usage, "completion_tokens", None), latency_ms=int((time.monotonic() - attempt_started) * 1000),
                    messages=messages, response=text,
                )

            try:
                if choice.finish_reason == "length":
                    # Re-asking would only make a truncated answer worse.
                    raise ReportError("the reply was cut off (token limit); raise LLM_MAX_TOKENS")
                value = parse(text)
            except ReportError as err:
                record("rejected", str(err))
                if repairs >= s.llm_repair_attempts or choice.finish_reason == "length":
                    raise
                repairs += 1
                last_rejection = str(err)
                log.warning("%s: the answer was rejected (%s). Asking again (%d of %d).", run_key, err, repairs, s.llm_repair_attempts)
                messages = base + [
                    {"role": "assistant", "content": _shortened(text)},
                    {"role": "user", "content": f"Your previous reply was rejected: {err}. Return the corrected JSON object only."},
                ]
                continue

            record("success")
            return LlmResult(
                value=value,
                provider=str(vendor),
                model=str(model),
                fallbacks=int(headers.get("x-litellm-attempted-fallbacks") or 0),
                retries=int(headers.get("x-litellm-attempted-retries") or 0),
                repairs=repairs,
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
                latency_ms=int((time.monotonic() - started) * 1000),
            )