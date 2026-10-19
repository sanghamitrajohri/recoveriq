"""AnthropicLLM request shape and usage parsing, via the real SDK with a fake HTTP transport.

Not a live call; scripts/verify_live.py makes the real one.
"""
import json

import anthropic
import httpx2
import pytest

from config import ModelTier
from llm import AnthropicLLM, LLMError, ScriptedLLM, SimContext


def client(captured, status=200, stop="end_turn"):
    def handler(request):
        captured.append(json.loads(request.content))
        if status != 200:
            return httpx2.Response(status, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})
        body = captured[-1]
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": "```python\nx = 1\n```"}],
            "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 321, "output_tokens": 45}})
    return anthropic.Anthropic(api_key="test", max_retries=0, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_cheap_tier_request_and_usage():
    cap = []
    r = AnthropicLLM(client(cap)).generate("fix it", ModelTier("cheap", "claude-haiku-4-5", 1024))
    body = cap[0]
    assert body["model"] == "claude-haiku-4-5" and body["max_tokens"] == 1024 and body["temperature"] == 0.0
    assert "output_config" not in body and body["messages"][0]["content"] == "fix it"
    assert (r.input_tokens, r.output_tokens, r.measured, r.source, r.request_id) == (321, 45, True, "anthropic", "msg_test")
    assert r.text == "```python\nx = 1\n```"  # thinking blocks excluded


def test_strong_tier_uses_effort_and_no_sampling_params():
    cap = []
    AnthropicLLM(client(cap)).generate("fix it", ModelTier("strong", "claude-opus-5", 8000, "medium"))
    assert cap[0]["output_config"] == {"effort": "medium"} and "temperature" not in cap[0]


def test_overloaded_maps_to_transient():
    with pytest.raises(LLMError) as e:
        AnthropicLLM(client([], status=529)).generate("x", ModelTier("cheap", "claude-haiku-4-5", 1024))
    assert e.value.kind == "transient" and not e.value.injected


def test_scripted_llm_is_labeled_simulated(tmp_path):
    from agent import Task
    task = Task.load("t6_wordcount")
    r = ScriptedLLM().generate("p", ModelTier("cheap", "claude-haiku-4-5", 1024),
                               SimContext(task.dir, task.target_file, 1, 0, False, task.simulator))
    assert r.measured is False and r.source == "scripted"
