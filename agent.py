"""A minimal coding agent: read buggy file + tests, ask an LLM for a fix, apply it, run pytest.

The agent only ever writes the task's target file. Generated code is executed exclusively
through ``sandbox.run_tests``.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import sandbox
from config import TASKS_DIR, ModelTier, llm_cost
from llm import FaultInjectingLLM, LLMError, LLMResponse, SimContext

FENCE = re.compile(r"```(?:python)?\n(.*?)```", re.S)


@dataclass
class Task:
    id: str
    title: str
    description: str
    target_file: str
    scenario: str
    scenario_note: str
    fault: dict
    human_hint: str
    simulator: dict
    dir: Path

    @classmethod
    def load(cls, task_id: str, tasks_dir: Path = TASKS_DIR) -> "Task":
        d = tasks_dir / task_id
        data = json.loads((d / "task.json").read_text())
        return cls(dir=d, **data)


def list_tasks(tasks_dir: Path = TASKS_DIR) -> list[Task]:
    return [Task.load(p.name, tasks_dir) for p in sorted(tasks_dir.iterdir()) if (p / "task.json").exists()]


def prepare_workspace(task: Task, dest: Path) -> Path:
    """Fresh isolated copy of the task: source + visible tests + hidden acceptance tests."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(task.dir / "workspace", dest)
    for f in (task.dir / "acceptance").glob("*.py"):
        shutil.copy(f, dest / f.name)
    return dest


@dataclass
class AttemptResult:
    attempt: int
    model: str
    tier_role: str
    status: str  # success | llm_error | output_truncated | malformed_output | collection_error |
    #              test_failure | acceptance_failure | timeout
    error_summary: str
    patch_applied: bool
    measured: bool
    llm_source: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    llm_latency_s: float = 0.0
    test_latency_s: float = 0.0
    passed_tests: int = 0
    total_tests: int = 0
    report: dict | None = None
    injected_faults: list[str] = field(default_factory=list)
    request_id: str | None = None

    @property
    def success(self) -> bool:
        return self.status == "success"


class FaultPlan:
    """Environment faults declared in task.json. Every injected fault is recorded on the attempt."""

    def __init__(self, fault: dict) -> None:
        self.fault = fault or {"type": "none"}
        self._llm_wrapper: FaultInjectingLLM | None = None

    def wrap_llm(self, llm):
        if self.fault.get("type") == "transient_llm_error":
            if self._llm_wrapper is None:
                self._llm_wrapper = FaultInjectingLLM(llm, int(self.fault.get("calls", 1)))
            return self._llm_wrapper
        return llm

    def before_tests(self, attempt: int, workspace: Path) -> list[str]:
        if self.fault.get("type") == "corrupt_file" and attempt == int(self.fault.get("on_attempt", 1)):
            (workspace / self.fault["file"]).write_text(self.fault["content"])
            return [f"corrupt_file:{self.fault['file']}"]
        return []


def visible_test_files(workspace: Path) -> list[Path]:
    return sorted(p for p in workspace.glob("test_*.py") if not p.name.startswith(sandbox.ACCEPTANCE_PREFIX))


def feedback_from(result: AttemptResult) -> str:
    """What the agent is told about a failed attempt. Acceptance-test details are withheld."""
    lines = [f"Attempt {result.attempt} with {result.model} failed: {result.status}."]
    if result.report:
        for f in result.report["failures"]:
            if f["acceptance"]:
                lines.append(f"- hidden acceptance check failed: {f['test']} (details withheld)")
            else:
                lines.append(f"- {f['test']}: {f['message'][:600]}")
    elif result.error_summary:
        lines.append(result.error_summary[:600])
    return "\n".join(lines)


def build_prompt(task: Task, workspace: Path, feedback: list[str], hint: str | None) -> str:
    parts = [f"## Task\n{task.description}\n", f"## File to fix: {task.target_file}\n```python\n"
             f"{(workspace / task.target_file).read_text()}```\n"]
    for t in visible_test_files(workspace):
        parts.append(f"## Tests: {t.name}\n```python\n{t.read_text()}```\n")
    if feedback:
        parts.append("## Feedback from previous attempts\n" + "\n\n".join(feedback[-3:]) + "\n")
    if hint:
        parts.append(f"## Guidance from a human reviewer\n{hint}\n")
    parts.append(f"Return the complete corrected {task.target_file}.")
    return "\n".join(parts)


def summarize_report(report: sandbox.TestReport) -> str:
    if report.timed_out:
        return "test run timed out"
    msgs = []
    for f in report.failures[:4]:
        detail = "details withheld" if f.acceptance else f.message.splitlines()[0][:200] if f.message else ""
        msgs.append(f"{'[acceptance] ' if f.acceptance else ''}{f.test}: {detail}")
    return f"{report.passed}/{report.total} passed. " + " | ".join(msgs)


def classify(report: sandbox.TestReport) -> str:
    if report.success:
        return "success"
    if report.timed_out:
        return "timeout"
    if report.collection_error:
        return "collection_error"
    if report.visible_failures:
        return "test_failure"
    return "acceptance_failure"


class CodingAgent:
    def __init__(self, llm, faults: FaultPlan, sandbox_timeout_s: float = 30.0) -> None:
        self.llm = faults.wrap_llm(llm)
        self.faults = faults
        self.sandbox_timeout_s = sandbox_timeout_s

    def attempt(self, task: Task, workspace: Path, tier: ModelTier, attempt: int, *,
                repeat: int = 0, feedback: list[str] | None = None, hint: str | None = None) -> AttemptResult:
        prompt = build_prompt(task, workspace, feedback or [], hint)
        sim = SimContext(task.dir, task.target_file, attempt, repeat, hint is not None, task.simulator)
        base = dict(attempt=attempt, model=tier.model, tier_role=tier.role)
        try:
            resp: LLMResponse = self.llm.generate(prompt, tier, sim)
        except LLMError as e:
            return AttemptResult(**base, status="llm_error", error_summary=f"[{e.kind}] {e}",
                                 patch_applied=False, measured=not e.injected,
                                 llm_source="injected" if e.injected else "anthropic",
                                 injected_faults=["transient_llm_error"] if e.injected else [])
        cost = llm_cost(tier.model, resp.input_tokens, resp.output_tokens)
        usage = dict(input_tokens=resp.input_tokens, output_tokens=resp.output_tokens, cost_usd=cost,
                     llm_latency_s=resp.latency_s, measured=resp.measured, llm_source=resp.source,
                     request_id=resp.request_id)
        if resp.stop_reason == "max_tokens":
            return AttemptResult(**base, **usage, status="output_truncated", patch_applied=False,
                                 error_summary=f"model output hit max_tokens={tier.max_output_tokens}; "
                                               "patch incomplete and not applied")
        if resp.stop_reason == "refusal":
            return AttemptResult(**base, **usage, status="malformed_output", patch_applied=False,
                                 error_summary="model refused the request")
        blocks = FENCE.findall(resp.text)
        if not blocks:
            return AttemptResult(**base, **usage, status="malformed_output", patch_applied=False,
                                 error_summary="no ```python block in model output")
        code = max(blocks, key=len)
        try:
            ast.parse(code)
        except SyntaxError as e:
            return AttemptResult(**base, **usage, status="malformed_output", patch_applied=False,
                                 error_summary=f"proposed patch has a syntax error: {e}")
        (workspace / task.target_file).write_text(code)
        injected = self.faults.before_tests(attempt, workspace)
        start = time.perf_counter()
        report = sandbox.run_tests(workspace, self.sandbox_timeout_s)
        test_latency = time.perf_counter() - start
        return AttemptResult(**base, **usage, status=classify(report), error_summary=summarize_report(report),
                             patch_applied=True, test_latency_s=test_latency, passed_tests=report.passed,
                             total_tests=report.total, report=report.to_dict(), injected_faults=injected)
