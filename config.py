"""Central configuration. All secrets come from environment variables (.env supported)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
TASKS_DIR = ROOT / "tasks"
RUNS_DIR = ROOT / "runs"
RESULTS_DIR = ROOT / "results"

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float


# Anthropic first-party list prices (USD per 1M tokens), from the Claude API model table
# cached 2026-06-24. Verify at https://platform.claude.com/docs/en/about-claude/pricing before quoting.
LLM_PRICES: dict[str, ModelPrice] = {
    "claude-haiku-4-5": ModelPrice(1.00, 5.00),
    "claude-sonnet-5": ModelPrice(2.00, 10.00),
    "claude-opus-5": ModelPrice(5.00, 25.00),
}

# TypeSafe Jev pricing from https://docs.typesafe.ai/models (checked 2026-10-19):
# $0.042 per 1M input tokens; output tokens are free.
JEV_PRICE = ModelPrice(0.042, 0.0)


@dataclass(frozen=True)
class ModelTier:
    role: str  # "cheap" | "strong"
    model: str
    max_output_tokens: int  # per-call output cap (a cost guard on the cheap tier)
    effort: str | None = None  # output_config.effort for models that support it


def _tiers_from_env() -> tuple[ModelTier, ...]:
    cheap = os.getenv("RECOVERIQ_CHEAP_MODEL", "claude-haiku-4-5")
    strong = os.getenv("RECOVERIQ_STRONG_MODEL", "claude-opus-5")
    return (
        ModelTier("cheap", cheap, int(os.getenv("RECOVERIQ_CHEAP_MAX_TOKENS", "1024"))),
        ModelTier("strong", strong, int(os.getenv("RECOVERIQ_STRONG_MAX_TOKENS", "8000")),
                  effort=os.getenv("RECOVERIQ_STRONG_EFFORT", "medium")),
    )


@dataclass(frozen=True)
class Budget:
    max_attempts: int = 5
    max_cost_usd: float = 0.25
    max_seconds: float = 300.0
    max_human_escalations: int = 1


@dataclass(frozen=True)
class Settings:
    llm_mode: str = field(default_factory=lambda: os.getenv("RECOVERIQ_LLM_MODE", "scripted"))
    jev_mode: str = field(default_factory=lambda: os.getenv("RECOVERIQ_JEV_MODE", "mock"))
    jev_model: str = field(default_factory=lambda: os.getenv("RECOVERIQ_JEV_MODEL", "jev-latest"))
    tiers: tuple[ModelTier, ...] = field(default_factory=_tiers_from_env)
    sandbox_timeout_s: float = 30.0
    # Imputed cost of one human escalation, reported separately from API spend.
    human_cost_usd: float = field(default_factory=lambda: float(os.getenv("RECOVERIQ_HUMAN_COST_USD", "0.50")))

    @property
    def llm_is_live(self) -> bool:
        return self.llm_mode == "live"

    @property
    def jev_is_live(self) -> bool:
        return self.jev_mode == "live"


def llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = LLM_PRICES.get(model)
    if price is None:
        raise KeyError(f"No price configured for model {model!r}; add it to config.LLM_PRICES")
    return (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000


def jev_cost(input_tokens: int) -> float:
    return input_tokens * JEV_PRICE.input_per_mtok / 1_000_000
