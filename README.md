# RecoverIQ — cost-aware recovery for AI coding agents, guided by Jev

When a coding agent fails, RecoverIQ decides what to do next — **retry**, **switch model**,
**restore checkpoint**, **escalate to a human**, or **terminate** — using TypeSafe's
[Jev](https://docs.typesafe.ai) decision model, with deterministic budget and safety rules
that Jev cannot override.

**Research question:** does Jev-guided recovery deliver more *verified* successful task
completions per dollar than fixed retry or hand-written recovery rules?

```
Successful Task Completions per Dollar = Verified Successful Tasks / Total Execution Cost (USD)
```

A task counts as *verified* only when the visible tests **and** hidden acceptance tests pass
inside the sandbox.

> **Data provenance is always labeled.** `live` modes make real API calls and record measured
> token usage. The offline modes — `scripted` LLM and `mock` Jev — exist for development and
> CI; every record they produce is tagged `measured=False` / `source=mock|scripted`, the
> dashboard shows a yellow **SIMULATED / MOCK** badge, and benchmark manifests carry a
> provenance block. Mock results are **not** Jev results.

---

## Quick start (macOS, Python 3.11+)

```bash
cd recoveriq
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # add keys later; offline modes work without them
.venv/bin/python -m pytest      # 59 tests, ~25 s, fully offline
.venv/bin/streamlit run app.py  # dashboard at http://localhost:8501
```

No GPU required. Generated code runs under macOS `sandbox-exec`, which ships with macOS.

## Going live

1. Create keys: Anthropic at <https://platform.claude.com/settings/keys>, TypeSafe at
   <https://console.typesafe.ai/keys>. Put them in `.env` (git-ignored, and unreadable from the
   sandbox):
   ```
   ANTHROPIC_API_KEY=...
   TYPESAFE_API_KEY=...
   RECOVERIQ_LLM_MODE=live
   RECOVERIQ_JEV_MODE=live
   ```
2. Verify both integrations with real authenticated calls:
   ```bash
   .venv/bin/python scripts/verify_live.py
   ```
   This prints and logs (`results/live_checks.jsonl`) the Jev models visible to your key, the
   full Jev input state, the selected action, per-action probabilities, confidence, failure
   type, latency, billed input tokens, cost and request id. It also runs one real agent
   attempt with the cheap model. Missing keys are reported as `BLOCKED`, never mocked.
3. Run the live benchmark:
   ```bash
   .venv/bin/python benchmark.py --llm-mode live --jev-mode live --repeats 3
   ```
   Rough spend at default settings: 9 tasks × 3 strategies × 3 repeats = 81 runs; most runs
   cost under $0.01, and the truncation task's Opus escalation is about $0.05–0.10, so expect a
   few dollars in total. Jev itself costs about $0.00004 per decision.

You can mix modes, e.g. `--llm-mode live --jev-mode mock` to measure real LLM cost while
developing Jev prompts.

## What's in the box

| File | Role |
|---|---|
| `agent.py` | Coding agent: reads the buggy file + visible tests, asks the LLM for a full-file fix, validates it (fence, `max_tokens`, `ast.parse`), applies it, runs pytest in the sandbox, classifies the outcome |
| `sandbox.py` | `sandbox-exec` profile: no network, no reading file contents under `$HOME` except the workspace and the venv, writes only to the workspace; scrubbed env, CPU/file-size rlimits, wall-clock timeout with process-group kill |
| `llm.py` | `AnthropicLLM` (real usage from `response.usage`), `ScriptedLLM` (offline simulator), `FaultInjectingLLM` |
| `jev_adapter.py` | One `client.system_one()` call per decision: `Choice` over currently-feasible actions, `Choice` failure type, `Noul` "retry would help", `Noul` "task impossible". Plus a labeled mock |
| `strategies.py` | **A** `FixedRetry`, **B** `RuleBased`, **C** `RecoverIQ` (Jev-ranked actions) |
| `recovery_policy.py` | Action definitions, `RecoveryContext`, `RecoveryPolicy` — rejects invalid, infeasible, unsafe or unaffordable proposals for *every* strategy and walks the ranked fallbacks |
| `engine.py` | LangGraph `StateGraph`: `attempt → decide → act / human → attempt`. Human escalation uses `interrupt()` + `Command(resume=...)` |
| `checkpoint_manager.py` | Workspace snapshots stored outside the workspace, restored and verified by SHA-256 manifest |
| `cost_tracker.py` | Per-event ledger (task, model, action, attempt, tokens, USD, latency, outcome, remaining budget, measured, source) → SQLite + JSONL |
| `benchmark.py` | Runs all strategies on the same tasks with the same budgets and seeds; writes raw traces + aggregate metrics; `--recompute` re-derives the metrics from raw traces |
| `app.py` | Streamlit dashboard: live trace, Jev recommendation, policy verdict, budget burn-down, model usage, side-by-side comparison, saved benchmarks |
| `scripts/verify_live.py` | Real authenticated Jev + Anthropic checks |
| `scripts/demo.py` | Terminal side-by-side demo |
| `tasks/` | Six reproducible bug-fix tasks with failure scenarios |
| `docs/` | Architecture diagram, 3-minute demo script, results and limitations summary |

## Tasks and failure scenarios

Each task has a buggy module, visible tests (shown to the agent), hidden acceptance tests (not
shown; the agent is told only their names), and an optional injected fault defined in
`task.json`.

| Task | Scenario | What happens | Best recovery |
|---|---|---|---|
| `t1_median` | transient API error | The first two LLM calls get an injected `529 overloaded` | retry |
| `t2_duration` | workspace corruption | During attempt 1 an injected rogue write truncates `units.py`; the agent may only edit `duration.py` | restore checkpoint |
| `t3_inventory` | output truncation | A 7 KB file; the cheap tier's 1,024-token output cap cuts the full-file rewrite | switch model |
| `t4_pricing` | missing requirement | Hidden tests enforce a finance policy (Decimal, ROUND_HALF_UP) stated nowhere visible | human escalation |
| `t5_slugify` | contradictory spec | Two visible tests demand opposite underscore handling | terminate early |
| `t6_wordcount` | clean control | Plain off-by-one | none (measures overhead) |
| `t7_temperature` | silent corruption | An injected write changes a *value* in `constants.py`; tests fail with assertions, not import errors | restore checkpoint |
| `t8_versions` | capability gap | The cheap model keeps proposing a plausible but wrong fix | switch model early |
| `t9_chunks` | inferable edge case | Hidden tests check validation stated in the description; a stronger model can infer it | switch model (a human also works, but costs more) |

`t1`–`t6` match the hand-written rules. `t7`–`t9` were added afterwards on purpose, so the
rules weren't designed for them: the rules only restore on import errors, retry before
escalating, and always send hidden-test failures to a human.

## Budgets and limits

Defaults in `config.Budget`, overridable on the CLI (`--budget-usd`, `--max-attempts`,
`--max-seconds`) or in the dashboard sidebar:

* `max_attempts=5`, `max_cost_usd=0.25` per task, `max_seconds=300`, `max_human_escalations=1`.
* Before every action the policy estimates the next attempt's cost — from the cost actually
  observed on that model in this run, else a prior based on prompt and file size — and rejects
  actions it can't afford.
* If actual spend still exceeds the cap (the estimate was too low), the run stops with
  `budget_exhausted` and the event is counted as a **budget violation**.

## Benchmark outputs

`results/<id>/` contains `traces.jsonl` (the source of truth), `raw.sqlite`, `runs.csv`,
`metrics.json`, `metrics.csv` and `manifest.json` (modes, provenance labels, budgets, model
tiers, package versions, git commit). `python benchmark.py --recompute results/<id>`
re-derives the metrics from the raw traces and fails on any mismatch.

Reported metrics, per strategy and per strategy × scenario: verified completion rate; total,
LLM and Jev cost; average cost per success; successes per dollar; successes per dollar
*including* the imputed human cost (`RECOVERIQ_HUMAN_COST_USD`, default $0.50, reported
separately); recovery actions; average attempts; average and p95 latency (all runs and
successful runs); human escalations; budget violations; policy overrides.

**Controlling randomness:** the cheap model is called with `temperature=0` (Opus 5 does not
accept sampling parameters). The offline simulator uses *common random numbers*: a given
(task, repeat, attempt, model) draws the same slip for every strategy. Use `--repeats` for
variance, and pin `RECOVERIQ_JEV_MODEL=jev-1.13.0` (rather than the moving `jev-latest` alias)
for comparable runs.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `BLOCKED Jev: TYPESAFE_API_KEY is not set` | Add the key to `.env` (no quotes needed) or `export` it |
| `TypeSafeAuthenticationError` in the trace / `jev_unavailable_fallback` | Key is wrong or revoked. RecoverIQ falls back to rule-based for that decision and labels it as such |
| `TypeSafeRateLimitError` | The per-organization limit is in the TypeSafe console; the SDK retries 429s with backoff |
| `llm_error [auth]` | `ANTHROPIC_API_KEY` is missing or invalid |
| `llm_error [bad_request]` on Opus | Some parameter isn't supported by the chosen model; check `RECOVERIQ_STRONG_EFFORT` |
| Tests show `isolation=reduced` | `sandbox-exec` wasn't found (non-macOS). Generated code then runs without OS-level isolation — don't use live mode there |
| `sandbox-exec: ... Operation not permitted` on everything | The venv must live where the profile allows it to be read (`sys.prefix`). Recreate `.venv` inside the project |
| A plain `pytest` run collects the buggy task tests | Run from the repo root so `pytest.ini` (`testpaths = tests`) applies |
| Streamlit "file watcher" warning | Optional: `pip install watchdog` |
| `KeyError: No price configured for model` | Add the model's prices to `config.LLM_PRICES` |

## Security notes

* Credentials come only from environment variables or `.env`; `.env` is git-ignored.
* Sandboxed test processes cannot read `.env` or anything else under `$HOME` outside the
  workspace and venv, cannot open network connections, cannot write outside the workspace, and
  get no API keys in their environment. `tests/test_sandbox.py` checks each of these.
* The agent only writes the task's target file; checkpoints live outside the sandbox's
  writable area.
* `sandbox-exec` is deprecated by Apple but still functional on macOS 15. For stronger
  isolation, run tests in a container.
