# RecoverIQ architecture

```mermaid
flowchart TB
    subgraph UI["Interfaces"]
        APP["app.py<br/>Streamlit dashboard"]
        BENCH["benchmark.py<br/>evaluation runner"]
        DEMO["scripts/demo.py<br/>terminal demo"]
    end

    subgraph ENGINE["engine.py — LangGraph state machine"]
        direction LR
        A["attempt"] -->|failed| D["decide"]
        D -->|human_escalation| H["human<br/>(interrupt → pause)"]
        D -->|other action| X["act"]
        H -->|resume with input| A
        X -->|retry / switch / restore| A
        X -->|terminate| END1(("end"))
        A -->|verified success<br/>or overspend| END2(("end"))
    end

    subgraph AGENT["agent.py — coding agent"]
        PROMPT["build prompt<br/>(source + visible tests + feedback + hint)"]
        LLM["llm.py<br/>AnthropicLLM · ScriptedLLM · FaultInjectingLLM"]
        PATCH["validate patch<br/>(fence, max_tokens, ast.parse)"]
        SBX["sandbox.py<br/>pytest under sandbox-exec:<br/>no network · no $HOME reads · writes only workspace"]
        PROMPT --> LLM --> PATCH --> SBX
    end

    subgraph DECIDE["Recovery decision"]
        STRAT["strategies.py<br/>FixedRetry · RuleBased · RecoverIQ"]
        JEV["jev_adapter.py<br/>TypeSafe system_one():<br/>Choice(action) · Choice(failure_type) · Noul×2"]
        POL["recovery_policy.py<br/>feasibility · attempt/time limits ·<br/>affordability · invalid-action rejection"]
        STRAT -->|RecoverIQ only| JEV
        STRAT -->|Proposal + ranked fallbacks| POL
    end

    CP["checkpoint_manager.py<br/>snapshots outside workspace + SHA-256 verify"]
    COST["cost_tracker.py<br/>per-event ledger: tokens · USD · latency · measured flag"]
    STORE[("results/&lt;id&gt;/<br/>traces.jsonl · raw.sqlite · metrics.json/csv · manifest.json")]

    APP --> ENGINE
    BENCH --> ENGINE
    DEMO --> ENGINE
    A --> AGENT
    D --> DECIDE
    X --> CP
    A --> CP
    A --> COST
    D --> COST
    COST --> STORE
```

## Data flow for one failure

1. **attempt** — the agent builds a prompt from the target file, the *visible* tests and
   feedback from earlier attempts (hidden acceptance-test details are withheld), calls the
   current model tier, validates the reply (code fence present, not cut off at `max_tokens`,
   parses with `ast`), writes only the target file, and runs the full suite (visible +
   acceptance) inside the sandbox. The outcome is classified as one of `success`,
   `llm_error`, `output_truncated`, `malformed_output`, `collection_error`, `test_failure`,
   `acceptance_failure`, `timeout`. A known-good checkpoint is saved when a patch applied
   cleanly, more tests pass than ever before, **and** every file other than the target still
   matches the initial snapshot, so silently damaged state is never captured as "good".
2. **decide** — a `RecoveryContext` (failure type, error summary, attempts, model, remaining
   budget, previous actions, damaged files, available options, per-option cost estimates)
   goes to the strategy. RecoverIQ sends it as JSON `state` to Jev with four questions in one
   call; the action Choice offers only currently-feasible actions. The strategy returns a
   proposal plus ranked fallbacks.
3. **policy** — `RecoveryPolicy.decide` independently rejects invalid, infeasible, unsafe or
   unaffordable proposals and walks the fallback ranking; if nothing survives it terminates.
   This applies identically to all three strategies.
4. **act / human** — `retry` re-enters attempt on the same tier; `switch_model` moves to the
   next tier (a different model with a larger output budget); `restore_checkpoint` replaces
   the workspace with the best known-good snapshot and verifies hashes; `human_escalation`
   calls LangGraph `interrupt()` and resumes with the reply as guidance; `terminate` ends.

## Isolation boundaries

| Asset | Who can touch it |
|---|---|
| `.env`, `~/.ssh`, anything under `$HOME` | host process only — sandbox denies `file-read-data` |
| Network | host process only — sandbox denies `network*` |
| Workspace (`runs/<run>/workspace`) | agent writes the target file; sandboxed tests may write here |
| Checkpoints (`runs/<run>/checkpoints`) | host only — outside the sandbox's writable area |
| Environment variables | sandbox gets a scrubbed env (no API keys) |
