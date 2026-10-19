import sys
from pathlib import Path

import pytest

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
