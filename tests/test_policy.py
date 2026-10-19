"""Deterministic policy constraints override any strategy, including Jev."""
from recovery_policy import (HUMAN_ESCALATION, RESTORE_CHECKPOINT, RETRY, SWITCH_MODEL, TERMINATE, Proposal,
                             RecoveryContext, RecoveryPolicy)


def ctx(tiers, budget, **kw):
    base = dict(task_id="t", task_description="d", target_file="f.py", failure_type="test_failure",
                error_summary="e", attempts_made=1, current_tier=0, tiers=tiers, remaining_budget_usd=0.2,
                elapsed_s=1.0, budget=budget)
    base.update(kw)
    return RecoveryContext(**base)


def decide(tiers, budget, action, ranked=(), **kw):
    return RecoveryPolicy(budget).decide(Proposal(action, "test", "", list(ranked)), ctx(tiers, budget, **kw))


def test_each_feasible_action_is_accepted(tiers, budget):
    for action in (RETRY, SWITCH_MODEL, HUMAN_ESCALATION, TERMINATE):
        d = decide(tiers, budget, action)
        assert d.action == action and not d.overridden
    d = decide(tiers, budget, RESTORE_CHECKPOINT, checkpoint_available=True)
    assert d.action == RESTORE_CHECKPOINT


def test_invalid_recommendation_is_rejected(tiers, budget):
    d = decide(tiers, budget, "rm_rf_workspace", ranked=[RETRY])
    assert d.action == RETRY and d.overridden and "invalid" in d.rejected[0][1]


def test_invalid_recommendation_without_fallback_terminates(tiers, budget):
    d = decide(tiers, budget, "launch_missiles")
    assert d.action == TERMINATE and d.overridden


def test_restore_without_checkpoint_is_rejected(tiers, budget):
    d = decide(tiers, budget, RESTORE_CHECKPOINT, ranked=[RETRY], checkpoint_available=False)
    assert d.action == RETRY and "checkpoint" in d.rejected[0][1]


def test_switch_model_on_strongest_tier_is_rejected(tiers, budget):
    d = decide(tiers, budget, SWITCH_MODEL, ranked=[RETRY], current_tier=1)
    assert d.action == RETRY


def test_human_escalation_limit(tiers, budget):
    d = decide(tiers, budget, HUMAN_ESCALATION, ranked=[RETRY], human_escalations_used=budget.max_human_escalations)
    assert d.action == RETRY


def test_human_unavailable_is_unsafe(tiers, budget):
    d = decide(tiers, budget, HUMAN_ESCALATION, human_available=False)
    assert d.action == TERMINATE


def test_unaffordable_switch_falls_back_to_cheaper_action(tiers, budget):
    # Opus attempt costs far more than $0.01; a cheap retry fits.
    d = decide(tiers, budget, SWITCH_MODEL, ranked=[RETRY, TERMINATE], remaining_budget_usd=0.01,
               est_input_tokens=2000, est_source_tokens=1500)
    assert d.action == RETRY and "unaffordable" in d.rejected[0][1]


def test_budget_exhaustion_forces_terminate(tiers, budget):
    d = decide(tiers, budget, RETRY, ranked=[SWITCH_MODEL], remaining_budget_usd=0.00001)
    assert d.action == TERMINATE and all("unaffordable" in r for _, r in d.rejected)


def test_attempt_limit_forces_terminate(tiers, budget):
    d = decide(tiers, budget, RETRY, attempts_made=budget.max_attempts)
    assert d.action == TERMINATE and "attempt limit" in d.reason


def test_time_limit_forces_terminate(tiers, budget):
    d = decide(tiers, budget, RETRY, elapsed_s=budget.max_seconds + 1)
    assert d.action == TERMINATE


def test_observed_cost_overrides_prior(tiers, budget):
    c = ctx(tiers, budget, observed_cost_by_model={"claude-haiku-4-5": 0.5})
    assert c.estimate_attempt_cost(0) == 0.5
