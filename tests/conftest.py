import os
import sys
from pathlib import Path

import pytest

# The test suite must never make paid API calls, even when .env holds live keys. These are set
# before config.py runs load_dotenv(), which does not override variables that already exist.
os.environ["RECOVERIQ_LLM_MODE"] = "scripted"
os.environ["RECOVERIQ_JEV_MODE"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["TYPESAFE_API_KEY"] = ""

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Budget, ModelTier, Settings  # noqa: E402


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("RECOVERIQ_LLM_MODE", "scripted")
    monkeypatch.setenv("RECOVERIQ_JEV_MODE", "mock")
    return Settings()


@pytest.fixture
def budget():
    return Budget(max_attempts=5, max_cost_usd=0.25, max_seconds=120)


@pytest.fixture
def tiers():
    return (ModelTier("cheap", "claude-haiku-4-5", 1024), ModelTier("strong", "claude-opus-5", 8000, "medium"))


@pytest.fixture
def run_root(tmp_path):
    return tmp_path / "runs"
