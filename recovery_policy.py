"""Recovery actions, the context a strategy sees, and the deterministic safety/budget policy.

Strategies (fixed retry, rule-based, JEV-guided) only *propose* an action. ``RecoveryPolicy``
then decides what actually happens: it rejects actions that are invalid, infeasible (e.g. no
checkpoint to restore), unsafe (e.g. human escalation when no human is available) or
unaffordable given the remaining budget — regardless of who proposed them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import Budget, ModelTier, llm_cost

RETRY = "retry"
SWITCH_MODEL = "switch_model"
RESTORE_CHECKPOINT = "restore_checkpoint"
HUMAN_ESCALATION = "human_escalation"
TERMINATE = "terminate"
ALL_ACTIONS = (RETRY, SWITCH_MODEL, RESTORE_CHECKPOINT, HUMAN_ESCALATION, TERMINATE)

ACTION_DESCRIPTIONS = {
    RETRY: "Repeat the attempt with the same model and the same workspace. Good for transient "
           "provider errors or a one-off sloppy answer.",
    SWITCH_MODEL: "Escalate to a different, more capable (and more expensive) model with a larger "
                  "output limit. Good when the current model is not capable enough or its output was cut off.",
    RESTORE_CHECKPOINT: "Restore the workspace files to the last known-good snapshot, then try again. "
                        "Good when files other than the one being fixed are damaged or broken.",
    HUMAN_ESCALATION: "Pause and ask a human for guidance. Good when a requirement is missing or "
                      "hidden and cannot be inferred from the code and tests.",
    TERMINATE: "Stop working on this task. Good when the task is impossible (e.g. contradictory "
               "tests), keeps failing the same way, or more attempts are not worth the cost.",
}


@dataclass
class RecoveryContext:
    task_id: str
    task_description: str
    target_file: str
    failure_type: str
    error_summary: str
    attempts_made: int
    current_tier: int
    tiers: tuple[ModelTier, ...]
    remaining_budget_usd: float
    elapsed_s: float
    budget: Budget
    previous_actions: list[str] = field(default_factory=list)
    failure_history: list[str] = field(default_factory=list)  # one status per attempt
    signature_history: list[str] = field(default_factory=list)  # failing-test signature per attempt
    checkpoint_available: bool = False
    diverged_non_target_files: list[str] = field(default_factory=list)
    human_available: bool = True
    human_escalations_used: int = 0
    has_hint: bool = False
    est_input_tokens: int = 1000
    est_source_tokens: int = 300
    observed_cost_by_model: dict[str, float] = field(default_factory=dict)

    @property
    def current_model(self) -> str:
        return self.tiers[self.current_tier].model

    def available_options(self) -> list[str]:
        """Actions that are feasible right now (before budget checks)."""
        opts = [RETRY]
        if self.current_tier + 1 < len(self.tiers):
            opts.append(SWITCH_MODEL)
        if self.checkpoint_available:
            opts.append(RESTORE_CHECKPOINT)
        if self.human_available and self.human_escalations_used < self.budget.max_human_escalations:
            opts.append(HUMAN_ESCALATION)
        opts.append(TERMINATE)
        return opts

    def tier_after(self, action: str) -> int:
        return self.current_tier + 1 if action == SWITCH_MODEL else self.current_tier

    def estimate_attempt_cost(self, tier_index: int) -> float:
        """Expected cost of one more agent attempt on ``tier_index``.

        Uses the observed cost on that model in this run when available, otherwise a prior:
        prompt tokens in, ~1.2x the source file out, plus a thinking allowance for effort tiers.
        """
        tier = self.tiers[tier_index]
        if tier.model in self.observed_cost_by_model:
            return self.observed_cost_by_model[tier.model]
        out = min(tier.max_output_tokens, int(self.est_source_tokens * 1.2) + (1500 if tier.effort else 0))
        return llm_cost(tier.model, self.est_input_tokens, out)


@dataclass
class Proposal:
    action: str
    source: str  # fixed_retry | rule_based | jev | jev_mock
    rationale: str
    ranked: list[str] = field(default_factory=list)  # fallbacks in preference order
    confidence: float | None = None
    detail: dict = field(default_factory=dict)


@dataclass
class PolicyDecision:
    action: str
    proposed: str
    overridden: bool
    reason: str
    est_cost_usd: float
    rejected: list[tuple[str, str]] = field(default_factory=list)


class RecoveryPolicy:
    def __init__(self, budget: Budget) -> None:
        self.budget = budget

    def _reject_reason(self, action: str, ctx: RecoveryContext) -> str | None:
        if action not in ALL_ACTIONS:
            return f"invalid action {action!r}"
        if action == TERMINATE:
            return None
        if action not in ctx.available_options():
            return {
                SWITCH_MODEL: "no stronger model configured",
                RESTORE_CHECKPOINT: "no known-good checkpoint available",
                HUMAN_ESCALATION: "human escalation unavailable or limit reached",
            }.get(action, "action not available")
        if ctx.attempts_made >= self.budget.max_attempts:
            return f"attempt limit reached ({self.budget.max_attempts})"
        if ctx.elapsed_s >= self.budget.max_seconds:
            return f"time limit reached ({self.budget.max_seconds}s)"
        cost = ctx.estimate_attempt_cost(ctx.tier_after(action))
        if cost > ctx.remaining_budget_usd:
            return f"unaffordable: est ${cost:.4f} > remaining ${ctx.remaining_budget_usd:.4f}"
        return None

    def decide(self, proposal: Proposal, ctx: RecoveryContext) -> PolicyDecision:
        rejected: list[tuple[str, str]] = []
        candidates = [proposal.action] + [a for a in proposal.ranked if a != proposal.action]
        for action in candidates:
            reason = self._reject_reason(action, ctx)
            if reason is None:
                est = 0.0 if action == TERMINATE else ctx.estimate_attempt_cost(ctx.tier_after(action))
                overridden = action != proposal.action
                why = (f"policy override: {rejected[0][0]} rejected ({rejected[0][1]}); using {action}"
                       if overridden else f"accepted {action}")
                return PolicyDecision(action, proposal.action, overridden, why, est, rejected)
            rejected.append((action, reason))
        why = "; ".join(f"{a}: {r}" for a, r in rejected)
        return PolicyDecision(TERMINATE, proposal.action, proposal.action != TERMINATE,
                              f"policy forced terminate ({why})", 0.0, rejected)
