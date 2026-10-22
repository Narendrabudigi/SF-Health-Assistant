"""Shared test setup.

LiteLLM loads the project's .env file into the process the moment it is imported (it searches upwards from its own folder,
which sits inside .venv, inside the project). So on a developer's machine every setting in .env, for example REPORTS_TABLE,
SUPABASE_BUCKET or GEMINI_API_KEY, is silently present in every test. Tests must not depend on that: before each test, every
environment variable the program reads is removed. A test that needs one sets it itself with monkeypatch.setenv.
"""
import pytest

import sf_orchestrator.llm  # noqa: F401  (sets LiteLLM's retry limit before any test file imports litellm itself, so a single test file can be run alone)
from sf_orchestrator.config import Settings


@pytest.fixture(autouse=True)
def _ignore_the_developers_own_settings(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    # The dashboard records runs in Supabase: never in a test (tests of the recording pass their own settings and a fake database).
    monkeypatch.setenv("DASHBOARD_TRACKING", "false")
    monkeypatch.delenv("SF_RUN_ID", raising=False)
    monkeypatch.delenv("SF_TRIGGER", raising=False)