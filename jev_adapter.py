"""Adapter between RecoverIQ and TypeSafe's Jev decision model (System One API).

Verified against the official docs (docs.typesafe.ai, 2026-10-19) and the installed
``typesafe-sdk`` 0.7.5:
  * ``TypeSafeClient(api_key=None -> reads TYPESAFE_API_KEY, model=...)``
  * ``client.system_one(state=..., questions={id: Choice(...) | Noul(...) | Score(...)})``
  * ``response.choices[id].choice / .probabilities / .confidence``, ``response.nouls[id].noul``
  * ``response.usage.input_tokens``, ``response.model``, ``response.request_id``
  * Pricing: $0.042 per 1M input tokens, output free.

Modes:
  * ``live`` — real authenticated Jev request. Results are tagged ``source="typesafe"``.
  * ``mock`` — an offline keyword heuristic for development. It is NOT Jev; results are tagged
    ``source="mock"`` and ``measured=False`` everywhere they are stored or displayed.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field

from config import jev_cost
from recovery_policy import (ACTION_DESCRIPTIONS, HUMAN_ESCALATION, RESTORE_CHECKPOINT, RETRY,
                             SWITCH_MODEL, TERMINATE, RecoveryContext)

FAILURE_TYPES = {
    "transient_provider_error": "The LLM provider or network failed temporarily (rate limit, overload, timeout); the code was not evaluated.",
    "model_capability_or_output_limit": "The model's answer was cut off, malformed, or not good enough; a more capable model would likely do better.",
    "workspace_damaged": "Files other than the one being fixed are broken or corrupted (syntax/import errors in helper modules).",
    "missing_or_hidden_requirement": "Visible tests pass but hidden acceptance checks fail; the needed requirement is not stated anywhere the agent can see.",
    "contradictory_or_impossible_spec": "The tests or requirements contradict each other, so no implementation can satisfy all of them.",
    "ordinary_bug_in_fix": "The proposed fix has a normal mistake that another attempt could correct.",
}


class JevUnavailable(RuntimeError):
    pass


@dataclass
class JevDecision:
    action: str
    probabilities: dict[str, float]
    confidence: float | None
    failure_type: str | None
    failure_type_probabilities: dict[str, float]
    retry_would_help: float | None
    impossible: float | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float
    model: str
    request_id: str | None
    source: str  # "typesafe" | "mock"
    measured: bool
    state: dict = field(default_factory=dict)

    def ranked_actions(self) -> list[str]:
        return [a for a, _ in sorted(self.probabilities.items(), key=lambda kv: -kv[1])]

    def to_dict(self) -> dict:
        return asdict(self)


def build_state(ctx: RecoveryContext, tests_excerpt: str = "") -> dict:
    """The JSON state Jev evaluates. Kept compact: Jev bills per input token."""
    return {
        "situation": "An AI coding agent attempted to fix a bug and the attempt failed. Choose how to recover.",
        "task": ctx.task_description,
        "file_being_fixed": ctx.target_file,
        "latest_failure_type": ctx.failure_type,
        "latest_error_summary": ctx.error_summary[:1200],
        "attempts_made": ctx.attempts_made,
        "max_attempts": ctx.budget.max_attempts,
        "failure_history": ctx.failure_history,
        "failing_test_signatures_per_attempt": ctx.signature_history,
        "previous_recovery_actions": ctx.previous_actions,
        "current_model": ctx.current_model,
        "stronger_model_available": ctx.current_tier + 1 < len(ctx.tiers),
        "files_damaged_since_last_good_checkpoint": ctx.diverged_non_target_files,
        "human_guidance_already_received": ctx.has_hint,
        "remaining_budget_usd": round(ctx.remaining_budget_usd, 4),
        "estimated_cost_usd_per_option": {
            opt: round(ctx.estimate_attempt_cost(ctx.tier_after(opt)), 5) if opt != TERMINATE else 0.0
            for opt in ctx.available_options()
        },
        "visible_tests": tests_excerpt[:4000],
    }


def build_questions(options: list[str]):
    from typesafe_sdk import Choice, Noul

    return {
        "action": Choice(
            instructions=("Which recovery action should the controller take next? Prefer the cheapest "
                          "action that is likely to lead to a verified fix; stop if success is unlikely."),
            criteria={opt: ACTION_DESCRIPTIONS[opt] for opt in options},
        ),
        "failure_type": Choice(instructions="What best explains the latest failure?", criteria=FAILURE_TYPES),
        "retry_would_help": Noul(
            instructions="Repeating the same attempt with the same model and unchanged workspace is likely to succeed."),
        "impossible": Noul(
            instructions="The task is impossible as specified, for example because tests contradict each other."),
    }


class JevAdapter:
    def __init__(self, mode: str = "mock", model: str = "jev-latest", client=None) -> None:
        if mode not in ("live", "mock"):
            raise ValueError("mode must be 'live' or 'mock'")
        self.mode = mode
        self.model = model
        self._client = client

    @property
    def source(self) -> str:
        return "typesafe" if self.mode == "live" else "mock"

    def _get_client(self):
        if self._client is None:
            from typesafe_sdk import TypeSafeClient

            self._client = TypeSafeClient(model=self.model)  # reads TYPESAFE_API_KEY
        return self._client

    def decide(self, ctx: RecoveryContext, tests_excerpt: str = "") -> JevDecision:
        options = ctx.available_options()
        state = build_state(ctx, tests_excerpt)
        if self.mode == "mock":
            return self._mock(ctx, options, state)
        import typesafe_sdk

        start = time.perf_counter()
        try:
            resp = self._get_client().system_one(state=state, questions=build_questions(options))
        except typesafe_sdk.TypeSafeError as e:
            raise JevUnavailable(f"{type(e).__name__}: {e}") from e
        latency = time.perf_counter() - start
        action = resp.choices["action"]
        ftype = resp.choices["failure_type"]
        in_tok = resp.usage.input_tokens or 0
        return JevDecision(
            action=action.choice, probabilities=dict(action.probabilities), confidence=action.confidence,
            failure_type=ftype.choice, failure_type_probabilities=dict(ftype.probabilities),
            retry_would_help=resp.nouls["retry_would_help"].noul, impossible=resp.nouls["impossible"].noul,
            input_tokens=in_tok, output_tokens=resp.usage.output_tokens or 0, cost_usd=jev_cost(in_tok),
            latency_s=latency, model=resp.model, request_id=resp.request_id, source="typesafe",
            measured=resp.usage.input_tokens is not None, state=state,
        )

    # ------------------------------------------------------------------ mock
    def _mock(self, ctx: RecoveryContext, options: list[str], state: dict) -> JevDecision:
        """Offline heuristic stand-in. NOT Jev. Produces a softmax over hand-set scores."""
        start = time.perf_counter()
        err = ctx.error_summary.lower()
        scores = {opt: 0.0 for opt in options}
        ftype = "ordinary_bug_in_fix"
        alternating = len(set(ctx.signature_history[-3:])) >= 2 and ctx.failure_history[-2:] == ["test_failure"] * 2
        if ctx.failure_type == "llm_error" and ("overload" in err or "rate" in err or "transient" in err):
            ftype, scores[RETRY] = "transient_provider_error", 3.0
        elif ctx.failure_type in ("output_truncated", "malformed_output"):
            ftype = "model_capability_or_output_limit"
            scores[SWITCH_MODEL if SWITCH_MODEL in scores else RETRY] = 3.0
        elif ctx.failure_type == "collection_error" and ctx.diverged_non_target_files:
            ftype = "workspace_damaged"
            scores[RESTORE_CHECKPOINT if RESTORE_CHECKPOINT in scores else TERMINATE] = 3.0
        elif ctx.failure_type == "acceptance_failure" and not ctx.has_hint:
            ftype = "missing_or_hidden_requirement"
            scores[HUMAN_ESCALATION if HUMAN_ESCALATION in scores else SWITCH_MODEL if SWITCH_MODEL in scores else TERMINATE] = 3.0
        elif alternating:
            ftype, scores[TERMINATE] = "contradictory_or_impossible_spec", 3.0
        else:
            scores[RETRY] = 1.5
            if SWITCH_MODEL in scores:
                scores[SWITCH_MODEL] = 1.0 + 0.5 * ctx.attempts_made
        z = sum(math.exp(s) for s in scores.values())
        probs = {k: math.exp(v) / z for k, v in scores.items()}
        best = max(probs, key=probs.get)
        return JevDecision(
            action=best, probabilities=probs, confidence=None, failure_type=ftype,
            failure_type_probabilities={ftype: 1.0}, retry_would_help=None,
            impossible=1.0 if ftype == "contradictory_or_impossible_spec" else None,
            # Estimated (unmeasured) cost at Jev's list price, so mock benchmarks include JEV overhead.
            input_tokens=len(json.dumps(state)) // 4, output_tokens=0,
            cost_usd=jev_cost(len(json.dumps(state)) // 4),
            latency_s=time.perf_counter() - start, model="mock-heuristic", request_id=None,
            source="mock", measured=False, state=state,
        )
