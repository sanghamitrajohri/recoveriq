"""Recovery orchestration as a LangGraph state machine.

    START -> attempt --success/stop--> END
                |
              decide --human_escalation--> human (interrupt: pause for input) --> attempt
                |
               act --terminate--> END
                |
             attempt ...

Non-serializable collaborators (agent, tracker, checkpoints, strategy) live on ``RunContext``;
the graph state holds only JSON-friendly values so LangGraph can checkpoint it for interrupts.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent import AttemptResult, CodingAgent, FaultPlan, Task, build_prompt, feedback_from, prepare_workspace, visible_test_files
from checkpoint_manager import CheckpointError, CheckpointManager
from config import RUNS_DIR, Budget, Settings
from cost_tracker import CostTracker
from llm import make_llm
from recovery_policy import (HUMAN_ESCALATION, RESTORE_CHECKPOINT, SWITCH_MODEL, TERMINATE, RecoveryContext,
                             RecoveryPolicy)


class RunState(TypedDict, total=False):
    attempt: int
    tier: int
    status: str  # running | success | terminated | budget_exhausted
    stop_reason: str
    feedback: list[str]
    last_summary: str
    hint: str | None
    pending_action: str
    actions: list[str]
    failure_history: list[str]
    signature_history: list[str]
    human_escalations: int
    budget_violations: int
    policy_overrides: int
    trace: list[dict]


@dataclass
class RunContext:
    run_id: str
    task: Task
    strategy: object
    settings: Settings
    budget: Budget
    workspace: Path
    agent: CodingAgent
    tracker: CostTracker
    checkpoints: CheckpointManager
    policy: RecoveryPolicy
    repeat: int = 0
    human_available: bool = True
    started_at: float = field(default_factory=time.perf_counter)
    best_passed: int = -1

    @property
    def elapsed_s(self) -> float:
        return time.perf_counter() - self.started_at


def _signature(result: AttemptResult) -> str:
    if result.report:
        return ",".join(sorted(f["test"] for f in result.report["failures"])) or "none"
    return result.status


def _observed_costs(rc: RunContext) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in rc.tracker.events:
        if e.kind == "llm_attempt" and e.cost_usd > 0:
            out[e.model] = e.cost_usd
    return out


def build_context(rc: RunContext, state: RunState, last_status: str, last_summary: str) -> RecoveryContext:
    best = rc.checkpoints.best_known_good()
    all_diverged = rc.checkpoints.diverged_files(best) if best is not None else []
    diverged = [f for f in all_diverged if f != rc.task.target_file]
    prompt = build_prompt(rc.task, rc.workspace, state.get("feedback", []), state.get("hint"))
    return RecoveryContext(
        task_id=rc.task.id, task_description=rc.task.description, target_file=rc.task.target_file,
        failure_type=last_status, error_summary=last_summary, attempts_made=state["attempt"],
        current_tier=state["tier"], tiers=rc.settings.tiers, remaining_budget_usd=rc.tracker.remaining_usd,
        elapsed_s=rc.elapsed_s, budget=rc.budget, previous_actions=list(state.get("actions", [])),
        failure_history=list(state.get("failure_history", [])),
        signature_history=list(state.get("signature_history", [])),
        checkpoint_available=bool(all_diverged),
        diverged_non_target_files=diverged, human_available=rc.human_available,
        human_escalations_used=state.get("human_escalations", 0), has_hint=state.get("hint") is not None,
        est_input_tokens=len(prompt) // 4, est_source_tokens=len((rc.workspace / rc.task.target_file).read_text()) // 4,
        observed_cost_by_model=_observed_costs(rc),
    )


def _tests_excerpt(rc: RunContext) -> str:
    return "\n\n".join(f"# {p.name}\n{p.read_text()}" for p in visible_test_files(rc.workspace))


def build_graph(rc: RunContext):
    def attempt_node(state: RunState) -> RunState:
        n = state["attempt"] + 1
        tier = rc.settings.tiers[state["tier"]]
        result = rc.agent.attempt(rc.task, rc.workspace, tier, n, repeat=rc.repeat,
                                  feedback=state.get("feedback", []), hint=state.get("hint"))
        action = state["actions"][-1] if state.get("actions") else "initial"
        rc.tracker.record("llm_attempt", model=result.model, recovery_action=action, attempt=n,
                          input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                          cost_usd=result.cost_usd, latency_s=result.llm_latency_s + result.test_latency_s,
                          outcome=result.status, measured=result.measured, source=result.llm_source,
                          detail={"summary": result.error_summary, "injected_faults": result.injected_faults,
                                  "passed": result.passed_tests, "total": result.total_tests,
                                  "request_id": result.request_id,
                                  "isolation": (result.report or {}).get("isolation")})
        update: RunState = {
            "attempt": n,
            "failure_history": state.get("failure_history", []) + [result.status],
            "signature_history": state.get("signature_history", []) + [_signature(result)],
            "trace": state.get("trace", []) + [{
                "kind": "attempt", "attempt": n, "model": result.model, "status": result.status,
                "summary": result.error_summary, "cost_usd": result.cost_usd, "measured": result.measured,
                "source": result.llm_source, "injected_faults": result.injected_faults,
                "passed": result.passed_tests, "total": result.total_tests,
                "remaining_usd": rc.tracker.remaining_usd}],
        }
        # Known-good checkpoint: the patch applied cleanly, more tests pass than ever before, and no
        # file other than the target differs from the initial snapshot (the agent only edits the
        # target, so any other change is damage and must never be captured as "good").
        initial = rc.checkpoints.checkpoints[0]
        clean = not [f for f in rc.checkpoints.diverged_files(initial) if f != rc.task.target_file]
        if (result.patch_applied and clean and result.status != "collection_error"
                and result.passed_tests > rc.best_passed):
            rc.best_passed = result.passed_tests
            rc.checkpoints.save(f"after attempt {n}", known_good=True, passed_tests=result.passed_tests)
        if rc.tracker.spent_usd > rc.budget.max_cost_usd:
            update.update(status="budget_exhausted", stop_reason="spend exceeded max_cost_usd",
                          budget_violations=state.get("budget_violations", 0) + 1)
        elif result.success:
            update.update(status="success", stop_reason="all tests passed (visible + acceptance)")
        else:
            update["feedback"] = state.get("feedback", []) + [feedback_from(result)]
            update["last_summary"] = result.error_summary
        return update

    def decide_node(state: RunState) -> RunState:
        last_status = state["failure_history"][-1]
        summary = state.get("last_summary", "")
        ctx = build_context(rc, state, last_status, summary)
        proposal = rc.strategy.propose(ctx, _tests_excerpt(rc))
        jev = getattr(rc.strategy, "last_decision", None) if rc.strategy.uses_jev else None
        trace_items = []
        if jev is not None:
            rc.tracker.record("jev_decision", model=jev.model, recovery_action=jev.action, attempt=state["attempt"],
                              input_tokens=jev.input_tokens, output_tokens=jev.output_tokens, cost_usd=jev.cost_usd,
                              latency_s=jev.latency_s, outcome=jev.failure_type or "", measured=jev.measured,
                              source=jev.source, detail={"probabilities": jev.probabilities, "confidence": jev.confidence,
                                                         "failure_type": jev.failure_type, "retry_would_help": jev.retry_would_help,
                                                         "impossible": jev.impossible, "request_id": jev.request_id,
                                                         "state": jev.state})
            trace_items.append({"kind": "jev", "source": jev.source, "action": jev.action,
                                "probabilities": jev.probabilities, "confidence": jev.confidence,
                                "failure_type": jev.failure_type, "latency_s": jev.latency_s,
                                "cost_usd": jev.cost_usd, "measured": jev.measured,
                                "retry_would_help": jev.retry_would_help, "impossible": jev.impossible})
        decision = rc.policy.decide(proposal, ctx)
        rc.tracker.record("recovery_action", recovery_action=decision.action, attempt=state["attempt"],
                          outcome="override" if decision.overridden else "accepted", source="policy",
                          measured=True, detail={"proposed": decision.proposed, "proposal_source": proposal.source,
                                                 "rationale": proposal.rationale, "policy_reason": decision.reason,
                                                 "rejected": decision.rejected, "est_cost_usd": decision.est_cost_usd,
                                                 "options": ctx.available_options()})
        trace_items.append({"kind": "decision", "proposed": decision.proposed, "action": decision.action,
                            "proposal_source": proposal.source, "rationale": proposal.rationale,
                            "overridden": decision.overridden, "policy_reason": decision.reason,
                            "est_cost_usd": decision.est_cost_usd, "remaining_usd": rc.tracker.remaining_usd})
        return {"pending_action": decision.action, "actions": state.get("actions", []) + [decision.action],
                "policy_overrides": state.get("policy_overrides", 0) + int(decision.overridden),
                "trace": state.get("trace", []) + trace_items}

    def act_node(state: RunState) -> RunState:
        action = state["pending_action"]
        if action == TERMINATE:
            return {"status": "terminated", "stop_reason": "recovery policy chose terminate",
                    "trace": state.get("trace", []) + [{"kind": "action", "action": action, "detail": "workflow stopped"}]}
        detail = "same model, new attempt"
        update: RunState = {}
        if action == SWITCH_MODEL:
            update["tier"] = state["tier"] + 1
            detail = f"switched to {rc.settings.tiers[update['tier']].model}"
        elif action == RESTORE_CHECKPOINT:
            try:
                cp = rc.checkpoints.restore()
                detail = f"restored {cp.checkpoint_id} ({cp.label}); hashes verified"
            except CheckpointError as e:
                detail = f"restore failed: {e}"
        update["trace"] = state.get("trace", []) + [{"kind": "action", "action": action, "detail": detail}]
        return update

    def human_node(state: RunState) -> RunState:
        answer = interrupt({"task_id": rc.task.id, "question": "The agent is stuck. What guidance should it follow?",
                            "last_failure": state.get("last_summary", ""),
                            "attempts": state["attempt"]})
        text = str(answer).strip()
        return {"hint": text or None, "human_escalations": state.get("human_escalations", 0) + 1,
                "trace": state.get("trace", []) + [{"kind": "action", "action": HUMAN_ESCALATION,
                                                     "detail": f"human replied: {text[:200]}"}]}

    g = StateGraph(RunState)
    g.add_node("attempt", attempt_node)
    g.add_node("decide", decide_node)
    g.add_node("act", act_node)
    g.add_node("human", human_node)
    g.add_edge(START, "attempt")
    g.add_conditional_edges("attempt", lambda s: "decide" if s.get("status", "running") == "running" else END)
    g.add_conditional_edges("decide", lambda s: "human" if s["pending_action"] == HUMAN_ESCALATION else "act")
    g.add_conditional_edges("act", lambda s: END if s.get("status") == "terminated" else "attempt")
    g.add_edge("human", "attempt")
    return g.compile(checkpointer=InMemorySaver())


class RecoveryRun:
    """One task, one strategy. Drive it with ``run()`` (blocking) or ``stream()``/``resume()`` (UI)."""

    def __init__(self, task: Task, strategy, settings: Settings | None = None, budget: Budget | None = None,
                 *, llm=None, repeat: int = 0, run_root: Path | None = None, human_available: bool = True,
                 run_id: str | None = None) -> None:
        settings = settings or Settings()
        budget = budget or Budget()
        self.run_id = run_id or f"{strategy.name}-{task.id}-r{repeat}-{uuid.uuid4().hex[:6]}"
        root = (run_root or RUNS_DIR) / self.run_id
        workspace = prepare_workspace(task, root / "workspace")
        checkpoints = CheckpointManager(workspace, root / "checkpoints")
        checkpoints.save("initial task state", known_good=True)
        llm = llm if llm is not None else make_llm(settings.llm_is_live)
        self.rc = RunContext(
            run_id=self.run_id, task=task, strategy=strategy, settings=settings, budget=budget,
            workspace=workspace, agent=CodingAgent(llm, FaultPlan(task.fault), settings.sandbox_timeout_s),
            tracker=CostTracker(self.run_id, strategy.name, task.id, budget.max_cost_usd),
            checkpoints=checkpoints, policy=RecoveryPolicy(budget), repeat=repeat, human_available=human_available,
        )
        self.graph = build_graph(self.rc)
        self.config = {"configurable": {"thread_id": self.run_id}, "recursion_limit": 100}
        self.initial: RunState = {"attempt": 0, "tier": 0, "status": "running", "feedback": [], "hint": None,
                                  "actions": [], "failure_history": [], "signature_history": [],
                                  "human_escalations": 0, "budget_violations": 0, "policy_overrides": 0, "trace": []}
        self.ended_at: float | None = None

    # -- streaming API (Streamlit) ----------------------------------------------------------
    def stream(self, resume_value: str | None = None) -> Iterator[dict]:
        """Yield graph updates. Stops at completion or at a human-escalation interrupt."""
        inp = Command(resume=resume_value) if resume_value is not None else self.initial
        for update in self.graph.stream(inp, self.config, stream_mode="updates"):
            yield update
        if not self.pending_interrupt():
            self.ended_at = self.ended_at or time.perf_counter()

    def pending_interrupt(self) -> dict | None:
        snap = self.graph.get_state(self.config)
        for t in snap.tasks:
            if t.interrupts:
                return t.interrupts[0].value
        return None

    @property
    def state(self) -> RunState:
        return self.graph.get_state(self.config).values

    # -- blocking API (benchmark / CLI) -----------------------------------------------------
    def run(self, human: Callable[[dict], str] | None = None) -> RunState:
        for _ in self.stream():
            pass
        while (payload := self.pending_interrupt()) is not None:
            answer = human(payload) if human else ""
            for _ in self.stream(resume_value=answer):
                pass
        return self.state

    def summary(self, benchmark_id: str = "", human_cost_usd: float = 0.0) -> dict:
        s = self.state
        t = self.rc.tracker
        end = self.ended_at or time.perf_counter()
        return {
            "run_id": self.run_id, "benchmark_id": benchmark_id, "strategy": self.rc.strategy.name,
            "task_id": self.rc.task.id, "scenario": self.rc.task.scenario, "repeat": self.rc.repeat,
            "llm_mode": self.rc.settings.llm_mode, "jev_mode": self.rc.settings.jev_mode if self.rc.strategy.uses_jev else "n/a",
            "outcome": s.get("status", "running"), "verified_success": int(s.get("status") == "success"),
            "total_cost_usd": round(t.spent_usd, 8), "llm_cost_usd": round(t.spent_by_kind("llm_attempt"), 8),
            "jev_cost_usd": round(t.spent_by_kind("jev_decision"), 8), "attempts": s.get("attempt", 0),
            "recovery_actions": len(s.get("actions", [])), "human_escalations": s.get("human_escalations", 0),
            "budget_violations": s.get("budget_violations", 0), "policy_overrides": s.get("policy_overrides", 0),
            "latency_s": round(end - self.rc.started_at, 4), "all_measured": int(t.all_measured()),
            "actions": s.get("actions", []),
        }


def scripted_human(task: Task) -> Callable[[dict], str]:
    """Simulated human for unattended benchmarks: replies with the task's documented hint."""
    return lambda payload: task.human_hint


def console_human(payload: dict) -> str:
    print(f"\n[HUMAN ESCALATION] {payload['question']}\nLast failure: {payload['last_failure']}")
    return input("> ")
