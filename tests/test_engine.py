"""Each recovery action has real effect inside the LangGraph engine."""
from agent import Task
from config import Budget
from engine import RecoveryRun, scripted_human
from jev_adapter import JevAdapter, JevDecision, JevUnavailable
from llm import ScriptedLLM
from strategies import FixedRetry, RecoverIQ, RuleBased


class RecordingLLM:
    def __init__(self):
        self.inner = ScriptedLLM(cheap_slip=0, strong_slip=0)
        self.models, self.prompts = [], []

    def generate(self, prompt, tier, sim=None):
        self.models.append(tier.model)
        self.prompts.append(prompt)
        return self.inner.generate(prompt, tier, sim)


def run(task_id, strategy, settings, budget, run_root, human=True, **kw):
    llm = RecordingLLM()
    r = RecoveryRun(Task.load(task_id), strategy, settings, budget, llm=llm, run_root=run_root, **kw)
    state = r.run(human=scripted_human(r.rc.task) if human else None)
    return r, state, llm


def test_retry_performs_new_attempts(settings, budget, run_root):
    r, s, llm = run("t1_median", FixedRetry(), settings, budget, run_root)
    assert s["status"] == "success" and s["attempt"] == 3 and s["actions"] == ["retry", "retry"]
    assert len(llm.models) == 1  # first two calls never reached the model (injected 529s)
    events = [e for e in r.rc.tracker.events if e.kind == "llm_attempt"]
    assert [e.outcome for e in events] == ["llm_error", "llm_error", "success"]


def test_switch_model_invokes_different_llm(settings, budget, run_root):
    r, s, llm = run("t3_inventory", RuleBased(), settings, budget, run_root)
    assert s["status"] == "success" and s["actions"] == ["switch_model"]
    assert llm.models == ["claude-haiku-4-5", "claude-opus-5"]


def test_restore_checkpoint_restores_real_files(settings, budget, run_root):
    r, s, llm = run("t2_duration", RuleBased(), settings, budget, run_root)
    assert s["actions"] == ["restore_checkpoint"] and s["status"] == "success"
    original = (r.rc.task.dir / "workspace" / "units.py").read_text()
    assert (r.rc.workspace / "units.py").read_text() == original


def test_fixed_retry_cannot_repair_corruption(settings, budget, run_root):
    r, s, _ = run("t2_duration", FixedRetry(), settings, budget, run_root)
    assert s["status"] == "terminated" and s["attempt"] == budget.max_attempts
    assert (r.rc.workspace / "units.py").read_text().endswith("(\n")


def test_human_escalation_pauses_and_resumes(settings, budget, run_root):
    llm = RecordingLLM()
    r = RecoveryRun(Task.load("t4_pricing"), RuleBased(), settings, budget, llm=llm, run_root=run_root)
    list(r.stream())
    payload = r.pending_interrupt()
    assert payload is not None and payload["task_id"] == "t4_pricing"
    assert r.state["status"] == "running" and r.state["attempt"] == 1  # paused, nothing more ran
    list(r.stream(resume_value="Use Decimal with ROUND_HALF_UP and return a Decimal."))
    assert r.pending_interrupt() is None and r.state["status"] == "success"
    assert "ROUND_HALF_UP" in llm.prompts[-1] and r.state["human_escalations"] == 1


def test_terminate_ends_cleanly(settings, budget, run_root):
    r, s, llm = run("t5_slugify", RecoverIQ(JevAdapter("mock")), settings, budget, run_root)
    assert s["status"] == "terminated" and s["actions"][-1] == "terminate"
    assert len(llm.models) == s["attempt"] == 2


def test_repeated_failures_hit_attempt_limit(settings, budget, run_root):
    r, s, _ = run("t5_slugify", FixedRetry(), settings, budget, run_root)
    assert s["status"] == "terminated" and s["attempt"] == budget.max_attempts and s["policy_overrides"] == 1


def test_budget_exhaustion_terminates(settings, run_root):
    # t5 always fails; one cheap attempt costs ~$0.0008, so $0.001 affords exactly one.
    r, s, _ = run("t5_slugify", FixedRetry(), settings, Budget(max_cost_usd=0.001), run_root)
    assert s["status"] == "terminated" and s["attempt"] == 1 and s["budget_violations"] == 0
    assert r.rc.tracker.spent_usd <= 0.001
    decision = [e for e in r.rc.tracker.events if e.kind == "recovery_action"][-1]
    assert decision.recovery_action == "terminate" and "unaffordable" in decision.detail["policy_reason"]


def test_overspend_is_recorded_as_violation(settings, run_root):
    r, s, _ = run("t3_inventory", RuleBased(), settings, Budget(max_cost_usd=0.001), run_root)
    assert s["status"] == "budget_exhausted" and s["budget_violations"] == 1


class StubAdapter(JevAdapter):
    def __init__(self, action=None, fail=False):
        super().__init__("mock")
        self.action, self.fail = action, fail

    def decide(self, ctx, tests_excerpt=""):
        if self.fail:
            raise JevUnavailable("TypeSafeAuthenticationError: 401")
        return JevDecision(self.action, {self.action: 0.9, "retry": 0.1}, 0.9, "x", {}, None, None,
                           10, 0, 0.0, 0.0, "stub", None, "mock", False)


def test_invalid_jev_recommendation_is_overridden(settings, budget, run_root):
    r, s, _ = run("t6_wordcount", RecoverIQ(StubAdapter("delete_the_repo")), settings, budget, run_root, repeat=1)
    ev = [e for e in r.rc.tracker.events if e.kind == "recovery_action"]
    if ev:  # only reached if the first attempt failed
        assert ev[0].recovery_action == "retry" and ev[0].outcome == "override"
    r, s, _ = run("t1_median", RecoverIQ(StubAdapter("delete_the_repo")), settings, budget, run_root)
    ev = [e for e in r.rc.tracker.events if e.kind == "recovery_action"]
    assert ev[0].detail["proposed"] == "delete_the_repo" and ev[0].recovery_action == "retry"
    assert s["policy_overrides"] >= 1 and s["status"] == "success"


def test_jev_outage_falls_back_with_label(settings, budget, run_root):
    r, s, _ = run("t3_inventory", RecoverIQ(StubAdapter(fail=True)), settings, budget, run_root)
    ev = [e for e in r.rc.tracker.events if e.kind == "recovery_action"]
    assert ev[0].detail["proposal_source"] == "jev_unavailable_fallback"
    assert not [e for e in r.rc.tracker.events if e.kind == "jev_decision"]
    assert s["status"] == "success"


class AlwaysRestore:
    name = "always_restore"
    uses_jev = False

    def propose(self, ctx, tests_excerpt=""):
        from recovery_policy import Proposal
        return Proposal("restore_checkpoint", self.name, "test", ranked=["retry"])


def test_silently_damaged_state_is_never_checkpointed(settings, budget, run_root):
    r, s, _ = run("t7_temperature", RuleBased(), settings, budget, run_root)
    # Rule-based only restores on collection errors, so the value corruption persists...
    assert s["status"] != "success"
    # ...and no checkpoint after the damage was marked known-good.
    assert [c.checkpoint_id for c in r.rc.checkpoints.checkpoints] == ["cp00"]


def test_restore_repairs_silent_corruption(settings, budget, run_root):
    r, s, _ = run("t7_temperature", AlwaysRestore(), settings, budget, run_root)
    assert s["actions"][0] == "restore_checkpoint" and s["status"] == "success"
    assert "F_PER_C = 1.8" in (r.rc.workspace / "constants.py").read_text()
