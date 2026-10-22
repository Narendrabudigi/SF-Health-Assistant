import pytest
from sf_orchestrator.config import ConfigError, load_settings

from helpers import CHAIN


ENV_NAMES = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "LLM_CHAIN", "INSIGHTS_TABLE", "REPORTS_TABLE"]
BASE = dict(
    _env_file=None,
    supabase_url="https://abc.supabase.co",
    supabase_service_role_key="service-role-key-0123456789",
    gemini_api_key="gemini-key-1234567890",
    groq_api_key="groq-key-1234567890",
    llm_chain=CHAIN,
    insights_table="ML_Notebook_Insights",
    reports_table="LLM_Reports",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_chain_keeps_order_and_drops_duplicates():
    s = load_settings(**{**BASE, "llm_chain": "groq/openai/a, gemini/b ,groq/openai/a,gemini/c"})
    assert s.chain == ["groq/openai/a", "gemini/b", "gemini/c"]


def test_missing_vendor_key_is_named():
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        load_settings(**{**BASE, "groq_api_key": None})


def test_the_recommended_chain_is_valid_and_keeps_the_slash_inside_groq_model_ids():
    s = load_settings(**{**BASE, "llm_chain": "gemini/gemini-3.8-flash,gemini/gemini-3.7-flash,groq/openai/gpt-oss-120b,groq/openai/gpt-oss-20b"})
    assert s.chain[2] == "groq/openai/gpt-oss-120b" and len(s.chain) == 4


def test_unknown_vendor_or_missing_model_is_rejected():
    with pytest.raises(ConfigError, match="must look like"):
        load_settings(**{**BASE, "llm_chain": "xai/grok-x"})  # a vendor that is not supported
    with pytest.raises(ConfigError, match="must look like"):
        load_settings(**{**BASE, "llm_chain": "gemini/"})


def test_placeholder_model_ids_from_the_template_are_rejected():
    with pytest.raises(ConfigError, match="placeholder"):
        load_settings(**{**BASE, "llm_chain": "gemini/<gemini-primary-model-id>"})


def test_empty_chain_is_rejected():
    with pytest.raises(ConfigError, match="LLM_CHAIN is empty"):
        load_settings(**{**BASE, "llm_chain": ""})


def test_supabase_settings_are_required():
    with pytest.raises(ConfigError, match="SUPABASE_URL"):
        load_settings(**{k: v for k, v in BASE.items() if k != "supabase_url"})


def test_a_pipeline_run_without_the_llm_step_needs_no_supabase_settings():
    s = load_settings(require_supabase=False, **{k: v for k, v in BASE.items() if not k.startswith("supabase")})
    assert s.supabase_url is None and s.chain


def test_dry_run_needs_no_llm_keys():
    s = load_settings(require_llm=False, **{k: v for k, v in BASE.items() if k not in ("gemini_api_key", "groq_api_key", "llm_chain")})
    assert s.chain == []


def test_empty_env_values_count_as_unset(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        load_settings(**{k: v for k, v in BASE.items() if k != "groq_api_key"})


def test_errors_never_echo_secret_values():
    with pytest.raises(ConfigError) as exc:
        load_settings(**{**BASE, "gemini_api_key": "tooshort"})
    assert "tooshort" not in str(exc.value)
    assert "GEMINI_API_KEY" in str(exc.value)


def test_defaults_wait_for_the_model_and_run_one_metric_at_a_time():
    s = load_settings(**BASE)
    assert (s.llm_num_retries, s.llm_rate_limit_retries, s.llm_retry_wait_seconds) == (2, 1, 10)
    assert (s.orchestrator_concurrency, s.llm_cooldown_seconds) == (1, 120)

# ── the tables of the industry standards ──


def test_both_tables_are_required_and_the_message_names_them():
    for missing in ("insights_table", "reports_table"):
        with pytest.raises(ConfigError, match="INSIGHTS_TABLE and REPORTS_TABLE are required"):
            load_settings(**{k: v for k, v in BASE.items() if k != missing})


def test_the_dashboard_and_a_custom_only_run_do_not_need_the_industry_tables():
    no_tables = {k: v for k, v in BASE.items() if not k.endswith("_table")}
    assert load_settings(require_tables=False, **no_tables).insights_table is None
    custom = dict(no_tables, custom_insights_table="ML_Notebook_Custom_Insights", custom_reports_table="LLM_Reports_Custom")
    assert load_settings(require_custom=True, **custom).custom_configured


@pytest.mark.parametrize("name", ["LLM_Reports", "llm_reports", "Reports2", " LLM_Reports "])
def test_plain_table_names_are_accepted_exactly_as_written(name):
    assert load_settings(**{**BASE, "reports_table": name}).reports_table == name.strip()


@pytest.mark.parametrize("name", ["LLM Reports", "LLM-Reports", "public.LLM_Reports", 'LLM_Reports"; drop table x; --', "1reports"])
def test_names_with_spaces_dots_quotes_or_a_leading_digit_are_rejected(name):
    with pytest.raises(ConfigError, match="REPORTS_TABLE"):
        load_settings(**{**BASE, "reports_table": name})
