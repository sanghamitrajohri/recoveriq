"""The agent really edits code, runs tests in the sandbox and classifies outcomes."""
from agent import CodingAgent, FaultPlan, Task, feedback_from, prepare_workspace
from llm import LLMResponse, ScriptedLLM


class FixedTextLLM:
    def __init__(self, text, stop="end_turn"):
        self.text, self.stop, self.calls = text, stop, 0

    def generate(self, prompt, tier, sim=None):
        self.calls += 1
        self.prompt = prompt
        return LLMResponse(self.text, tier.model, 100, 50, self.stop, 0.01, False, "test")


def test_agent_fixes_bug_and_verifies(tmp_path, tiers):
    task = Task.load("t1_median")
    ws = prepare_workspace(task, tmp_path / "ws")
    fixed = (task.dir / "simulator" / "fixed.py").read_text()
    r = CodingAgent(FixedTextLLM(f"```python\n{fixed}```"), FaultPlan({"type": "none"})).attempt(task, ws, tiers[0], 1)
    assert r.status == "success" and r.patch_applied
    assert (ws / "stats.py").read_text() == fixed
    assert r.passed_tests == r.total_tests == 6


def test_agent_reports_visible_failure_for_bad_fix(tmp_path, tiers):
    task = Task.load("t1_median")
    ws = prepare_workspace(task, tmp_path / "ws")
    original = (ws / "stats.py").read_text()
    r = CodingAgent(FixedTextLLM(f"```python\n{original}```"), FaultPlan({})).attempt(task, ws, tiers[0], 1)
    assert r.status == "test_failure" and r.passed_tests == 4


def test_truncated_output_is_not_applied(tmp_path, tiers):
    task = Task.load("t1_median")
    ws = prepare_workspace(task, tmp_path / "ws")
    before = (ws / "stats.py").read_text()
    r = CodingAgent(FixedTextLLM("```python\ndef median(", stop="max_tokens"), FaultPlan({})).attempt(task, ws, tiers[0], 1)
    assert r.status == "output_truncated" and not r.patch_applied
    assert (ws / "stats.py").read_text() == before


def test_syntax_error_patch_is_rejected(tmp_path, tiers):
    task = Task.load("t1_median")
    ws = prepare_workspace(task, tmp_path / "ws")
    r = CodingAgent(FixedTextLLM("```python\ndef broken(:\n```"), FaultPlan({})).attempt(task, ws, tiers[0], 1)
    assert r.status == "malformed_output" and not r.patch_applied


def test_corruption_fault_causes_collection_error(tmp_path, tiers):
    task = Task.load("t2_duration")
    ws = prepare_workspace(task, tmp_path / "ws")
    r = CodingAgent(ScriptedLLM(cheap_slip=0), FaultPlan(task.fault)).attempt(task, ws, tiers[0], 1)
    assert r.status == "collection_error"
    assert r.injected_faults == ["corrupt_file:units.py"]


def test_acceptance_details_are_withheld_from_agent(tmp_path, tiers):
    task = Task.load("t4_pricing")
    ws = prepare_workspace(task, tmp_path / "ws")
    r = CodingAgent(ScriptedLLM(cheap_slip=0), FaultPlan({})).attempt(task, ws, tiers[0], 1)
    assert r.status == "acceptance_failure"
    fb = feedback_from(r)
    assert "details withheld" in fb and "1.01" not in fb


def test_prompt_excludes_hidden_acceptance_tests(tmp_path, tiers):
    task = Task.load("t4_pricing")
    ws = prepare_workspace(task, tmp_path / "ws")
    llm = FixedTextLLM("no code here")
    CodingAgent(llm, FaultPlan({})).attempt(task, ws, tiers[0], 1)
    assert "test_acceptance" not in llm.prompt and "test_pricing.py" in llm.prompt


def test_transient_fault_injection(tmp_path, tiers):
    task = Task.load("t1_median")
    ws = prepare_workspace(task, tmp_path / "ws")
    agent = CodingAgent(ScriptedLLM(cheap_slip=0), FaultPlan(task.fault))
    statuses = [agent.attempt(task, ws, tiers[0], n).status for n in (1, 2, 3)]
    assert statuses == ["llm_error", "llm_error", "success"]
