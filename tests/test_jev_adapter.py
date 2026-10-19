"""Exercise the adapter through the real typesafe-sdk client with a fake HTTP transport.

These tests verify request construction and response parsing only. They are not live Jev
results; the live check is scripts/verify_jev.py.
"""
import json

import httpx2
import pytest
from typesafe_sdk import TypeSafeClient

from config import Budget
from jev_adapter import JevAdapter, JevUnavailable
from recovery_policy import RecoveryContext


def make_ctx(tiers, **kw):
    base = dict(task_id="t", task_description="fix it", target_file="f.py", failure_type="output_truncated",
                error_summary="model output hit max_tokens", attempts_made=1, current_tier=0, tiers=tiers,
                remaining_budget_usd=0.2, elapsed_s=1.0, budget=Budget())
    base.update(kw)
    return RecoveryContext(**base)


def fake_client(captured, status=200, action="switch_model"):
    def handler(request):
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        if status != 200:
            return httpx2.Response(status, json={"error": {"type": "authentication_error", "message": "bad key"}})
        opts = list(captured["body"]["questions"]["action"]["criteria"])
        probs = {o: (0.7 if o == action else 0.3 / (len(opts) - 1)) for o in opts}
        return httpx2.Response(200, headers={"x-typesafe-request-id": "req_test"}, json={
            "model": "jev-1.13.0",
            "answers": {
                "action": {"type": "choice", "choice": action, "confidence": 0.62, "probabilities": probs},
                "failure_type": {"type": "choice", "choice": "model_capability_or_output_limit", "confidence": 0.8,
                                 "probabilities": {"model_capability_or_output_limit": 0.9, "ordinary_bug_in_fix": 0.1}},
                "retry_would_help": {"type": "noul", "noul": 0.12},
                "impossible": {"type": "noul", "noul": 0.03},
            },
            "usage": {"input_tokens": 1500, "output_tokens": 40},
        })
    return TypeSafeClient(api_key="test-key", transport=httpx2.MockTransport(handler))


def test_live_mode_request_and_parse(tiers):
    cap = {}
    d = JevAdapter("live", client=fake_client(cap)).decide(make_ctx(tiers), "def test_x(): ...")
    assert cap["url"].endswith("/v1/systemone")
    q = cap["body"]["questions"]
    assert q["action"]["type"] == "choice" and q["retry_would_help"]["type"] == "noul"
    # Only currently-feasible options are offered (no checkpoint -> no restore).
    assert set(q["action"]["criteria"]) == {"retry", "switch_model", "human_escalation", "terminate"}
    assert cap["body"]["state"]["latest_failure_type"] == "output_truncated"
    assert d.action == "switch_model" and d.confidence == 0.62 and d.source == "typesafe" and d.measured
    assert d.request_id == "req_test" and d.model == "jev-1.13.0"
    assert d.cost_usd == pytest.approx(1500 * 0.042 / 1e6)
    assert d.ranked_actions()[0] == "switch_model"


def test_live_mode_api_error_raises_unavailable(tiers):
    with pytest.raises(JevUnavailable):
        JevAdapter("live", client=fake_client({}, status=401)).decide(make_ctx(tiers))


def test_mock_mode_is_labeled(tiers):
    d = JevAdapter("mock").decide(make_ctx(tiers))
    assert d.source == "mock" and not d.measured and d.model == "mock-heuristic" and d.confidence is None
    assert abs(sum(d.probabilities.values()) - 1) < 1e-9


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        JevAdapter("llm")
