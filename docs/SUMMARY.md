# RecoverIQ — implementation summary, verified results, limitations

*Status as of 2026-10-19.*

## Bottom line

**On the live benchmark, Jev-guided recovery delivered the most clean successes per dollar of
API spend.** 108 runs with real Claude (Haiku 4.5 / Opus 5) and real Jev (`jev-1.13.0`) cost
$2.41 in total. RecoverIQ cleanly solved 24 of 27 runs for $0.56: 42.9 clean successes per $,
against 25.3 for the rule-based baseline (21/27, $0.83) and 31.3 for fixed retry (12/27,
$0.38). Results: `results/live-2026-10-19/`. Metrics recompute exactly from the raw traces.

Caveats up front: 3 repeats per cell is a small sample; the retry gate was added after seeing
the first live Jev call; and once human time is priced at $0.50 per escalation, fixed retry has
the best ratio, because it never escalates, even though it solves less than half the tasks.

## Implemented

| Requirement | Status | Evidence |
|---|---|---|
| Project structure, venv, pinned deps, git repo | done | `requirements.txt` (Python 3.11 venv); initial commit on `main` |
| Real coding agent (read bug + tests, LLM fix, apply, pytest, report) | done | `agent.py`; `tests/test_agent.py` |
| Sandboxed execution of generated code | done (macOS `sandbox-exec`) | `tests/test_sandbox.py`: network denied (`EPERM`), `$HOME` reads denied, writes outside the workspace denied, env scrubbed, timeout kills runaway code |
| Reproducible buggy tasks with failure conditions | done | 9 tasks in `tasks/`, each with hidden acceptance tests; t7–t9 target the baseline's blind spots |
| JEV via the official SDK, verified against docs | **done, verified live** | First authenticated call: `jev-1.13.0`, 124 ms, 1,066 input tokens, $0.000045 (`results/live_checks.jsonl`); 60 more live Jev decisions in the benchmark (avg 102 ms, $0.0031 total) |
| Labeled offline mock | done | `source="mock"`, `measured=False`, yellow UI badge, manifest provenance |
| JEV decision separated from policy | done | `strategies.RecoverIQ` proposes; `RecoveryPolicy` disposes |
| All five actions with real behavior | done | `tests/test_engine.py`: new LLM call per retry; a different model is invoked on switch; files restored and hash-verified; LangGraph interrupt pauses and resumes with the human's text in the next prompt; terminate stops all calls |
| Limits on attempts, cost and time; reject unaffordable/unsafe/invalid actions | done | `tests/test_policy.py` (12 cases) |
| Cost tracking (tokens, prices, Jev cost, latency, remaining budget) | done | `cost_tracker.py`; Anthropic usage read from `response.usage`, Jev usage from `response.usage.input_tokens` |
| Three strategies on the same tasks and budgets | done (+ a fourth ablation) | `strategies.py`: fixed retry, rule-based, Jev-only (`recoveriq_raw`), Jev + retry gate (`recoveriq`) |
| Result integrity (gaming / damage) | done | `scripts/integrity_audit.py`: a run is a *clean* success only if no helper file is left damaged and no test-gaming signals appear |
| Benchmark metrics, raw traces, reproducibility | done | `benchmark.py --recompute` → `OK`; `tests/test_benchmark.py` also checks that tampering is detected |
| Streamlit dashboard | done | `app.py`; `tests/test_app.py` (headless run + human pause/resume); server boot checked against `/_stcore/health` |
| Demo showing repetition loses | **done, live** | Live `t3_inventory`: Haiku truncated at its 1,024-token cap 3/3 times under fixed retry; switching to Opus passed 3/3. Live `t7_temperature`: Jev restored the checkpoint 3/3 for $0.0024 per run |
| README, architecture diagram, demo script | done | `README.md`, `docs/ARCHITECTURE.md`, `docs/DEMO_SCRIPT.md` |

Test suite: **63 passed** (`.venv/bin/python -m pytest`, about 25 s, offline).

## Live benchmark (MEASURED: real Anthropic + real TypeSafe Jev)

`results/live-2026-10-19/`: 3 repeats × 9 tasks × 4 strategies = 108 runs, $0.25 and 5
attempts per task, scripted human replies (simulated) and injected faults (labeled).
*Clean* = verified (visible + hidden tests pass) AND no damaged helper files AND no
test-gaming signals. Costs are measured API spend.

| Strategy | Verified | Clean | Gamed | Damaged | Total cost | Clean successes / $ | Avg attempts | Human escalations | Budget violations |
|---|---|---|---|---|---|---|---|---|---|
| Fixed retry | 13/27 | 12 | 0 | 1 | $0.3829 | 31.342 | 3.4074 | 0 | 0 |
| Rule-based | 24/27 | 21 | 3 | 0 | $0.8301 | 25.2977 | 2.0741 | 4 | 0 |
| Jev only (no gate) | 27/27 | 24 | 3 | 0 | $0.6427 | 37.3438 | 2.2593 | 3 | 0 |
| RecoverIQ (Jev + gate) | 25/27 | 24 | 1 | 0 | $0.5589 | 42.9434 | 1.8889 | 4 | 0 |

| Scenario | Fixed retry | Rule-based | Jev only (no gate) | RecoverIQ (Jev + gate) |
|---|---|---|---|---|
| capability_gap | 3/3 · $0.0036 | 3/3 · $0.0036 | 3/3 · $0.0036 | 3/3 · $0.0036 |
| clean | 3/3 · $0.0037 | 3/3 · $0.0037 | 3/3 · $0.0037 | 3/3 · $0.0037 |
| contradictory_spec | 0/3 · $0.0753 | 3/3 · $0.1599 | 3/3 · $0.1541 | 1/3 · $0.0930 |
| inferable_edge_case | 3/3 · $0.0026 | 3/3 · $0.0026 | 3/3 · $0.0026 | 3/3 · $0.0026 |
| missing_requirement | 0/3 · $0.0460 | 3/3 · $0.0079 | 3/3 · $0.1558 | 3/3 · $0.1396 |
| output_truncation | 0/3 · $0.1171 | 3/3 · $0.2688 | 3/3 · $0.2933 | 3/3 · $0.2690 |
| silent_corruption | 0/3 · $0.0620 | 0/3 · $0.3618 | 3/3 · $0.0073 | 3/3 · $0.0073 |
| transient_api_error | 3/3 · $0.0062 | 3/3 · $0.0062 | 3/3 · $0.0065 | 3/3 · $0.0243 |
| workspace_corruption | 1/3 · $0.0663 | 3/3 · $0.0156 | 3/3 · $0.0158 | 3/3 · $0.0158 |


### What happened
* **Silent corruption (t7) is where Jev beat the rules outright.** A helper constant was
  changed to a wrong but valid value. Jev diagnosed `workspace_damaged` (confidence 0.97 in a
  rehearsal run), restored the checkpoint, and succeeded 3/3 for $0.0073 in total. The rule-based
  baseline only restores on import errors: it retried, escalated to Opus, asked a human, and
  failed 3/3 for $0.36.
* **Real models game impossible tests.** On the contradictory task (t5), Opus repeatedly
  returned a `str` subclass whose `__eq__` treats `-` and `_` as equal, so both contradictory
  tests passed (`docs/examples/reward_hack_slugify.py`). The integrity audit flagged 3
  rule-based, 3 Jev-only and 1 gated-RecoverIQ "successes" as gamed. Gated RecoverIQ terminated
  t5 correctly in 2 of 3 runs.
* **Haiku also worked around damage.** On t2, Haiku under fixed retry once passed by copying
  the constants into `duration.py` and leaving `units.py` broken. Counted as damaged, not clean.
* **The retry gate is a trade-off.** It removes Jev's "retry first" on output truncation
  (t3: $0.269 vs $0.293 un-gated) but also overrides retries on transient provider errors,
  where retrying is right (t1: $0.024 vs $0.006, about 4×). Jev rated `retry_would_help` low
  even for 529s.
* **Jev over-escalates before asking a human.** On the missing-requirement task (t4) it tried
  Opus first, costing $0.140 against the rules' $0.008 (which go straight to the human).
* **t8 and t9 didn't discriminate.** Real Haiku solved both on the first try, so they only
  measure overhead. The simulator had assumed Haiku would fail them.
* **Overall:** RecoverIQ spent 33% less than rule-based ($0.56 vs $0.83) for more clean
  successes (24 vs 21). Including human time at $0.50 per escalation, cost per clean success is
  $0.032 fixed retry, $0.089 Jev-only, $0.107 RecoverIQ, $0.135 rule-based.
* Zero budget violations, zero crashes; p95 latency 31 s (RecoverIQ) vs 68 s (rule-based).

## Added later: checkout task (MEASURED, reported separately)

`results/live-t10-checkout/`: a 10th task added after the main benchmark to make the effect
easy to see in a demo. An online store's tax setting is changed from 0.08 to 0.80 while the
agent fixes a shipping bug, so a $100 order totals $180.

| Strategy | Clean fixes (3 runs) | Avg cost per run | What happened |
|---|---|---|---|
| RecoverIQ | 3/3 | $0.0068 | Jev chose restore checkpoint every time |
| Jev only | 3/3 | $0.0068 | Same |
| Rule-based | 0/3 | $0.140 | Retry → Opus → human; 2 passes came from code that rewrote or patched the settings at runtime |
| Fixed retry | 0/3 | $0.026 | Gave up after 5 attempts |

Across 5 live tries on this task (3 benchmark runs + 2 dashboard races), the rule-based strategy
passed the tests by gaming 4 times and gave up once. The integrity audit gained two checks for
this (`writes_files`, `patches_other_modules`); re-auditing the main benchmark with them changed
none of its numbers. The dashboard race now runs the same inspector live and labels such runs
"SOLVED BY CHEATING".

## Offline benchmark (SIMULATED LLM + MOCK Jev — not real measurements)

Kept as the no-network fallback. Re-run with four strategies, where the mock Jev-only and gated
rows are identical (the mock returns no Noul values, so the gate never fires).
`results/offline-scripted-mock/`: 5 repeats × 9 tasks × 4 strategies = 180 runs, $0.25 and
5 attempts per task. Costs use real list prices applied to *estimated* token counts. Metrics
recompute exactly from the raw traces (`--recompute` → OK).

| Strategy | Verified | Total cost | Cost/success | Successes per $ | incl. human time | Avg attempts | Human escalations | Budget violations |
|---|---|---|---|---|---|---|---|---|
| Fixed retry | 10/45 | $0.342 | $0.0342 | 29.3 | 29.3 | 4.38 | 0 | 0 |
| Rule-based | 35/45 | $0.457 | $0.0131 | **76.6** | 7.85 | 2.42 | 8 | 0 |
| Jev-only / RecoverIQ (mock Jev, identical) | 35/45 each | $0.478 | $0.0136 | 73.3 | 7.82 | 2.47 | 8 | 0 |

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

1. **Small sample.** 3 repeats × 9 tasks per strategy. The t7 result (3/3 vs 0/3) is clear;
   most other differences are a few runs or cents and could move with more repeats.
2. **Post-hoc tuning.** The retry gate was added after the first live Jev call showed retry
   chosen while `retry_would_help` was 0.19. The un-gated `recoveriq_raw` row is the
   pre-registered behavior, and it also beats both baselines on clean successes per $ (37.3).
3. **The baseline and tasks share an author.** The rules were written alongside t1–t6, and
   t7–t9 were added to probe their blind spots. That's fair to Jev on t7, but it isn't an
   independent task set.
4. **The integrity audit is a heuristic.** It catches comparison-dunder overrides, test-runner
   tampering and early exits, plus damaged helper files. Other gaming tricks could slip through.
   Stronger option: acceptance tests that check `type(result) is str` and similar invariants.
5. **Simulated human and injected faults.** Escalations always receive the documented hint
   (cost imputed at $0.50, reported separately). Transient 529s and file corruption are injected.
6. **The cost of the affordability check is estimated** until a model has been observed in the
   run, so an overspend is possible (counted as a violation; none occurred).
7. **Conservative known-good checkpoints.** Only snapshots with every non-target file unchanged
   count, so multi-file fixes (which this agent never makes) would never be checkpointed.
8. **Sandbox scope.** `sandbox-exec` is deprecated by Apple but works on macOS 15.7. No memory or
   process-count limits. Non-macOS hosts fall back to `isolation=reduced` (recorded).
9. **Refusal fallbacks are off** so each attempt's cost maps to one model.
10. **Model aliases move.** `jev-latest` was `jev-1.13.0` during these runs (recorded per
    decision). Pin it for comparable reruns.
11. **Credentials were pasted into a chat session.** Rotate both keys after the event.
