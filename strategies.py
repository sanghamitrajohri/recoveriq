"""The three recovery strategies compared by the benchmark.

All three only *propose* actions; ``recovery_policy.RecoveryPolicy`` enforces the same budget
and safety constraints on every one of them.
"""
from __future__ import annotations

from jev_adapter import JevAdapter, JevDecision, JevUnavailable
from recovery_policy import (HUMAN_ESCALATION, RESTORE_CHECKPOINT, RETRY, SWITCH_MODEL, TERMINATE,
                             Proposal, RecoveryContext)


class FixedRetry:
    """A. Retry the same thing until the attempt limit."""

    name = "fixed_retry"
    uses_jev = False

    def propose(self, ctx: RecoveryContext, tests_excerpt: str = "") -> Proposal:
        return Proposal(RETRY, self.name, "fixed policy: always retry", ranked=[TERMINATE])


class RuleBased:
    """B. Deterministic failure classification -> recovery rules."""

    name = "rule_based"
    uses_jev = False

    def propose(self, ctx: RecoveryContext, tests_excerpt: str = "") -> Proposal:
        opts = ctx.available_options()
        ft = ctx.failure_type
        consecutive = 0
        for f in reversed(ctx.failure_history):
            if f != ft:
                break
            consecutive += 1

        def first(*actions: str) -> str:
            return next(a for a in actions if a in opts)

        if ft == "llm_error":
            action, why = (first(RETRY) if consecutive < 3 else first(SWITCH_MODEL, TERMINATE),
                           f"provider error #{consecutive}: retry up to 3 times")
        elif ft in ("output_truncated", "malformed_output"):
            action, why = first(SWITCH_MODEL, RETRY), "bad/truncated output: escalate model"
        elif ft == "collection_error":
            action, why = (first(RESTORE_CHECKPOINT, RETRY) if ctx.diverged_non_target_files else first(RETRY),
                           "import/collection error: restore workspace if other files changed")
        elif ft == "acceptance_failure":
            action, why = first(HUMAN_ESCALATION, SWITCH_MODEL, TERMINATE), "visible tests pass, hidden fail: ask human"
        elif ft == "timeout":
            action, why = (first(RETRY) if consecutive < 2 else TERMINATE), "test timeout"
        else:  # test_failure
            if consecutive >= 2:
                action, why = first(SWITCH_MODEL, TERMINATE), "repeated test failures: escalate, else stop"
            else:
                action, why = first(RETRY), "first test failure: retry with feedback"
        return Proposal(action, self.name, why, ranked=[RETRY, TERMINATE])


class RecoverIQ:
    """C. Jev-guided recovery. Jev ranks the available actions; the policy enforces constraints."""

    name = "recoveriq"
    uses_jev = True

    def __init__(self, adapter: JevAdapter) -> None:
        self.adapter = adapter
        self._fallback = RuleBased()
        self.last_decision: JevDecision | None = None

    def propose(self, ctx: RecoveryContext, tests_excerpt: str = "") -> Proposal:
        try:
            d = self.adapter.decide(ctx, tests_excerpt)
        except JevUnavailable as e:
            # Explicit, logged fallback; never presented as a Jev result.
            self.last_decision = None
            p = self._fallback.propose(ctx)
            return Proposal(p.action, "jev_unavailable_fallback", f"Jev call failed ({e}); used rule-based",
                            ranked=p.ranked, detail={"jev_error": str(e)})
        self.last_decision = d
        why = (f"Jev[{d.source}] chose {d.action}"
               + (f" (confidence {d.confidence:.2f})" if d.confidence is not None else "")
               + f"; failure type: {d.failure_type}")
        return Proposal(d.action, "jev" if d.source == "typesafe" else "jev_mock", why,
                        ranked=d.ranked_actions(), confidence=d.confidence, detail=d.to_dict())


def make_strategy(name: str, jev_mode: str = "mock", jev_model: str = "jev-latest"):
    if name == "fixed_retry":
        return FixedRetry()
    if name == "rule_based":
        return RuleBased()
    if name == "recoveriq":
        return RecoverIQ(JevAdapter(jev_mode, jev_model))
    raise ValueError(f"unknown strategy {name!r}")


STRATEGY_NAMES = ("fixed_retry", "rule_based", "recoveriq")
