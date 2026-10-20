import time

import pytest

from config import ModelTier
from llm import AnthropicLLM, LLMError


class _HangingMessages:
    def create(self, **kwargs):
        time.sleep(5)


class _HangingClient:
    messages = _HangingMessages()


def test_hung_api_call_becomes_transient_error_at_deadline():
    llm = AnthropicLLM(client=_HangingClient())
    llm.deadline_s = 0.2
    start = time.perf_counter()
    with pytest.raises(LLMError) as e:
        llm.generate("fix it", ModelTier(model="claude-haiku-4-5", role="cheap", max_output_tokens=10))
    assert e.value.kind == "transient"
    assert time.perf_counter() - start < 2
