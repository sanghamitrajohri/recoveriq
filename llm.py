"""LLM backends for the coding agent.

* ``AnthropicLLM`` — real Claude API calls; token usage comes from ``response.usage`` (measured).
* ``ScriptedLLM`` — offline simulator for development and tests. It replays per-task reference
  outputs with seeded stochastic slips. Its token counts are *estimates* (chars/4) and every
  response is flagged ``measured=False`` so it can never be mistaken for a real measurement.
* ``FaultInjectingLLM`` — wraps another backend and raises injected transient errors.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from config import ModelTier

SYSTEM_PROMPT = (
    "You are a careful Python engineer fixing a bug. You are given one source file, its unit "
    "tests, and possibly feedback from earlier attempts. Reply with the COMPLETE corrected "
    "contents of the source file in a single ```python fenced block and nothing else. "
    "Do not modify tests. Keep the public API unchanged."
)

# Models that still honour temperature (newer models return a 400 for it). anthropic>=1.0 removed
# temperature from the messages.create() signature, so it is sent via extra_body for these models.
SAMPLING_SUPPORTED = {"claude-haiku-4-5"}


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    latency_s: float
    measured: bool
    source: str  # "anthropic" | "scripted"
    request_id: str | None = None


class LLMError(RuntimeError):
    def __init__(self, kind: str, message: str, *, injected: bool = False, model: str = "") -> None:
        super().__init__(message)
        self.kind = kind  # transient | auth | bad_request | refusal | other
        self.injected = injected
        self.model = model


@dataclass
class SimContext:
    """Information only the offline simulator uses (the live backend ignores it)."""

    task_dir: Path
    target_file: str
    attempt: int
    repeat: int
    has_hint: bool
    profile: dict = field(default_factory=dict)


class AnthropicLLM:
    def __init__(self, client=None) -> None:
        import anthropic

        self._anthropic = anthropic
        # Retries are the recovery controller's job, so SDK auto-retry is disabled.
        self.client = client or anthropic.Anthropic(max_retries=0, timeout=120.0)
        self.deadline_s = 90.0

    def _create_with_deadline(self, kwargs: dict, model: str):
        """messages.create with a hard wall-clock limit. The SDK timeout only bounds the gap between bytes,
        and we have seen a live call hang for 30+ minutes; past the deadline it counts as a transient error."""
        box: dict = {}

        def call() -> None:
            try:
                box["resp"] = self.client.messages.create(**kwargs)
            except BaseException as e:  # re-raised in the caller's thread
                box["err"] = e

        worker = threading.Thread(target=call, daemon=True)
        worker.start()
        worker.join(self.deadline_s)
        if worker.is_alive():
            raise LLMError("transient", f"no response from the API within {self.deadline_s:.0f}s (hard deadline)",
                           model=model)
        if "err" in box:
            raise box["err"]
        return box["resp"]

    def generate(self, prompt: str, tier: ModelTier, sim: SimContext | None = None) -> LLMResponse:
        a = self._anthropic
        kwargs: dict = {
            "model": tier.model,
            "max_tokens": tier.max_output_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        if tier.model in SAMPLING_SUPPORTED:
            kwargs["extra_body"] = {"temperature": 0.0}  # reduce run-to-run variance
        if tier.effort:
            kwargs["output_config"] = {"effort": tier.effort}
        start = time.perf_counter()
        try:
            resp = self._create_with_deadline(kwargs, tier.model)
        except (a.RateLimitError, a.APIConnectionError, a.APITimeoutError, a.InternalServerError) as e:
            raise LLMError("transient", f"{type(e).__name__}: {e}", model=tier.model) from e
        except a.AuthenticationError as e:
            raise LLMError("auth", f"AuthenticationError: {e}", model=tier.model) from e
        except a.BadRequestError as e:
            raise LLMError("bad_request", f"BadRequestError: {e}", model=tier.model) from e
        except a.APIStatusError as e:
            kind = "transient" if e.status_code >= 500 or e.status_code == 429 else "other"
            raise LLMError(kind, f"APIStatusError {e.status_code}: {e}", model=tier.model) from e
        latency = time.perf_counter() - start
        text = "".join(b.text for b in resp.content if b.type == "text")
        return LLMResponse(
            text=text, model=resp.model, input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens, stop_reason=resp.stop_reason or "",
            latency_s=latency, measured=True, source="anthropic", request_id=resp.id,
        )


class ScriptedLLM:
    """Deterministic offline stand-in for an LLM. NOT a real model; outputs are labeled simulated."""

    def __init__(self, cheap_slip: float = 0.10, strong_slip: float = 0.03) -> None:
        self.cheap_slip = cheap_slip
        self.strong_slip = strong_slip

    def generate(self, prompt: str, tier: ModelTier, sim: SimContext | None = None) -> LLMResponse:
        if sim is None:
            raise ValueError("ScriptedLLM requires a SimContext")
        start = time.perf_counter()
        is_cheap = tier.role == "cheap"
        behavior = sim.profile.get(tier.role, "fixed")
        simdir = sim.task_dir / "simulator"
        original = (sim.task_dir / "workspace" / sim.target_file).read_text()
        # Common random numbers: the same (task, repeat, attempt, tier) draws the same slip for
        # every strategy, which reduces variance when comparing strategies.
        rng = random.Random(f"{sim.task_dir.name}|{sim.repeat}|{sim.attempt}|{tier.model}")
        slip = rng.random() < (self.cheap_slip if is_cheap else self.strong_slip)
        stop = "end_turn"
        if sim.has_hint and "with_hint" in sim.profile:
            body = (simdir / f"{sim.profile['with_hint']}.py").read_text()
        elif behavior == "fixed":
            body = (simdir / "fixed.py").read_text()
        elif behavior == "naive":
            body = (simdir / "naive.py").read_text()
        elif behavior == "alternate":
            body = (simdir / ("fixed_a.py" if sim.attempt % 2 else "fixed_b.py")).read_text()
        elif behavior == "truncate":
            body = (simdir / "fixed.py").read_text()
        else:
            raise ValueError(f"unknown simulator behavior {behavior!r}")
        if slip and behavior != "truncate":
            body = original  # a plausible failure: the model "fixes" nothing
        text = f"```python\n{body}```"
        if len(text) // 4 > tier.max_output_tokens:
            text = text[: tier.max_output_tokens * 4]
            stop = "max_tokens"
        return LLMResponse(
            text=text, model=tier.model, input_tokens=len(prompt) // 4 + len(SYSTEM_PROMPT) // 4,
            output_tokens=len(text) // 4, stop_reason=stop,
            latency_s=time.perf_counter() - start, measured=False, source="scripted",
        )


class FaultInjectingLLM:
    """Raises an injected transient error for the first ``fail_calls`` calls, then delegates."""

    def __init__(self, inner, fail_calls: int) -> None:
        self.inner = inner
        self.remaining = fail_calls

    def generate(self, prompt: str, tier: ModelTier, sim: SimContext | None = None) -> LLMResponse:
        if self.remaining > 0:
            self.remaining -= 1
            raise LLMError("transient", "injected fault: 529 overloaded_error (provider busy)",
                           injected=True, model=tier.model)
        return self.inner.generate(prompt, tier, sim)


def make_llm(live: bool):
    return AnthropicLLM() if live else ScriptedLLM()
