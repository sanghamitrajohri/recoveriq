# RecoverIQ — implementation summary, verified results, limitations

*Status as of 2026-10-19.*

## Bottom line

The full system is built and tested offline. **The research question is not answered yet:**
no `ANTHROPIC_API_KEY` or `TYPESAFE_API_KEY` was available in the build environment, so no
real Jev or Claude call has been made. Every benchmark number below comes from the scripted
LLM and the mock Jev heuristic, and says nothing about Jev's real quality. To get real
results, add the keys and run `scripts/verify_live.py`, then
`benchmark.py --llm-mode live --jev-mode live`.

## Implemented

| Requirement | Status | Evidence |
|---|---|---|
| Project structure, venv, pinned deps, git repo | done | `requirements.txt` (Python 3.11 venv); initial commit on `main` |
| Real coding agent (read bug + tests, LLM fix, apply, pytest, report) | done | `agent.py`; `tests/test_agent.py` |
| Sandboxed execution of generated code | done (macOS `sandbox-exec`) | `tests/test_sandbox.py`: network denied (`EPERM`), `$HOME` reads denied, writes outside the workspace denied, env scrubbed, timeout kills runaway code |
| Reproducible buggy tasks with failure conditions | done | 9 tasks in `tasks/`, each with hidden acceptance tests; t7–t9 target the baseline's blind spots |
| JEV via the official SDK, verified against docs | done in code; **not exercised live** | `jev_adapter.py`, written against `typesafe-sdk` 0.7.5 and docs.typesafe.ai; `tests/test_jev_adapter.py` runs the *real SDK client* against a fake HTTP transport to check the request/response wire format |
| Labeled offline mock | done | `source="mock"`, `measured=False`, yellow UI badge, manifest provenance |
| JEV decision separated from policy | done | `strategies.RecoverIQ` proposes; `RecoveryPolicy` disposes |
| All five actions with real behavior | done | `tests/test_engine.py`: new LLM call per retry; a different model is invoked on switch; files restored and hash-verified; LangGraph interrupt pauses and resumes with the human's text in the next prompt; terminate stops all calls |
| Limits on attempts, cost and time; reject unaffordable/unsafe/invalid actions | done | `tests/test_policy.py` (12 cases) |
| Cost tracking (tokens, prices, Jev cost, latency, remaining budget) | done | `cost_tracker.py`; Anthropic usage read from `response.usage`, Jev usage from `response.usage.input_tokens` |
| Three strategies on the same tasks and budgets | done | `strategies.py`, `benchmark.py` |
| Benchmark metrics, raw traces, reproducibility | done | `benchmark.py --recompute` → `OK`; `tests/test_benchmark.py` also checks that tampering is detected |
| Streamlit dashboard | done | `app.py`; `tests/test_app.py` (headless run + human pause/resume); server boot checked against `/_stcore/health` |
| Demo showing repetition loses | done (offline) | `scripts/demo.py` on `t3_inventory`: fixed retry fails 5/5 attempts; rule-based and RecoverIQ succeed after one model switch |
| README, architecture diagram, demo script | done | `README.md`, `docs/ARCHITECTURE.md`, `docs/DEMO_SCRIPT.md` |

Test suite: **59 passed** (`.venv/bin/python -m pytest`, about 25 s, offline).

## Offline benchmark (SIMULATED LLM + MOCK Jev — not real measurements)

`results/offline-scripted-mock/`: 5 repeats × 9 tasks × 3 strategies = 135 runs, $0.25 and
5 attempts per task. Costs use real list prices applied to *estimated* token counts. Metrics
recompute exactly from the raw traces (`--recompute` → OK).

| Strategy | Verified | Total cost | Cost/success | Successes per $ | incl. human time | Avg attempts | Human escalations | Budget violations |
|---|---|---|---|---|---|---|---|---|
| Fixed retry | 10/45 | $0.342 | $0.0342 | 29.3 | 29.3 | 4.38 | 0 | 0 |
| Rule-based | 35/45 | $0.457 | $0.0131 | **76.6** | 7.85 | 2.42 | 8 | 0 |
| RecoverIQ (mock Jev) | 35/45 | $0.478 | $0.0136 | 73.3 | 7.82 | 2.47 | 8 | 0 |

What this does and doesn't show:

* **It validates the harness**: each scenario produces its intended failure, each recovery
  action works, the policy holds the budget (zero violations), and metrics recompute exactly.
* **It does not evaluate Jev.** The mock is a keyword heuristic with the same blind spots as
  the rules, and here it does slightly *worse* than rule-based. It escalates to the expensive
  model more eagerly, and that costs more than terminating the contradictory task early saves.
* **The new scenarios (t7–t9) are where real Jev has room to differ.** Neither the rules nor
  the mock ever restored on `t7_temperature` (0/5 each): the failures look like ordinary
  assertion errors, even though the state sent to Jev lists `constants.py` under
  `files_damaged_since_last_good_checkpoint`. On `t9_chunks` both sent 3 of 5 runs to a human
  when a stronger model would have done. On `t8_versions` both retried once before escalating.
* **Human time dominates the true cost.** At an imputed $0.50 per escalation, successes per $
  drop from ~75 to ~7.8 for both adaptive strategies. A strategy that avoids unnecessary
  escalations has the most to gain on this metric.
* Fixed retry can never repair corruption, truncation, a capability gap, or a missing
  requirement, which is the "repeating the same action is less effective" case.

## Limitations and open risks

1. **No live verification.** The Anthropic and Jev code paths are checked against the
   installed SDK signatures and fake-transport tests, not real responses. The first live run
   may surface issues, e.g. Opus 5 rejecting an `effort` value or Jev's latency or answers
   differing from expectations.
2. **The rule-based baseline is partly scenario-aware.** It was written alongside t1–t6, so
   it's probably optimistic on those. t7–t9 were added afterwards to probe its blind spots, but
   they were still designed by the same author.
3. **Small, synthetic task set.** Nine single-file tasks with injected faults. They are
   reproducible, but not representative of real agent workloads.
4. **Simulated human.** Benchmarks answer escalations with the task's documented hint, so
   escalation always works. Its cost is reported separately (`successes_per_dollar_incl_human`,
   at an imputed $0.50).
5. **Injected faults.** The transient 529s and the file corruption are injected by the harness
   (labeled in every trace), not organic failures.
6. **Cost estimates for the affordability check** are priors until a model has been observed
   in the run. A run can therefore overspend once, which is counted as a budget violation and
   stops the run.
10. **Known-good checkpoints are conservative.** A snapshot only counts as good if every
    non-target file is unchanged, so legitimate multi-file fixes, which this agent doesn't
    make, would never be checkpointed.
7. **Sandbox scope.** `sandbox-exec` is deprecated by Apple (but works on macOS 15.7). It
   doesn't limit memory (RLIMIT_AS isn't enforced on macOS) or process count. Non-macOS
   machines fall back to `isolation=reduced`, which is recorded per attempt.
8. **Refusal fallbacks are not enabled.** Anthropic recommends server-side refusal fallbacks
   for Opus 5. They were left off on purpose so each attempt's cost maps to exactly one model;
   a refusal is treated as a failed attempt that the recovery policy handles.
9. **Model aliases move.** `jev-latest` currently points at `jev-1.13.0`. Pin a version for
   comparable runs.
