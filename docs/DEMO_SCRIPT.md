# RecoverIQ — 3-minute live demo (AI Tinkerers)

**Setup before going on stage:** `.env` has both keys and both modes set to `live`; run
`python scripts/verify_live.py` once (it should print two `OK` lines); then run
`streamlit run app.py` and keep the tab open. Have a saved live benchmark in `results/`.
Fallback if Wi-Fi dies: switch to `scripted`/`mock` — the badges turn yellow and you say so
out loud.

---

### 0:00–0:25 — The problem
> "Coding agents fail all the time. The default fix is *retry*, which is the most expensive
> way to learn nothing. Sometimes the right move is a bigger model, sometimes rolling back the
> workspace, sometimes asking a human, and sometimes just stopping. RecoverIQ makes that call
> with Jev — TypeSafe's decision model, which returns calibrated probabilities instead of
> prose — and a deterministic policy that Jev can't talk its way past."

Point at the sidebar badges: **LLM: LIVE Anthropic · Jev: LIVE TypeSafe**.

### 0:25–1:15 — Repetition loses: output truncation (`t3_inventory`)
1. Select **t3_inventory · output_truncation**, strategy **Fixed retry**, then **Run**.
   > "The cheap model has a 1K-token output cap. The file is 7 KB. Watch it hit the cap…
   > again… again." Point at the burn-down chart dropping while nothing improves.
2. Switch to **RecoverIQ (Jev)**, then **Run**.
   > "Same failure. Here's the Jev call: one request, four typed questions. Here's the action
   > it picked, the probability over every action, its confidence, and the latency" — *read
   > the actual values on screen* — "and at $0.042 per million input tokens the call cost a
   > few millionths of a dollar. The policy checks it's affordable, we escalate, and the tests
   > pass, including hidden ones the agent never saw."
   *(Rehearse this with live keys first. If Jev picks something else, narrate what it picked
   and how the policy handled it. That's the point of the demo.)*

### 1:15–2:00 — The other recovery actions
3. **t2_duration · workspace_corruption**, RecoverIQ, then **Run**.
   > "Something trashed a helper file. Retrying can't fix it, because the agent may only edit
   > one file. Jev says restore. We restore a real snapshot and verify every file hash, and it
   > passes."
4. **t4_pricing · missing_requirement**, RecoverIQ, then **Run**.
   > "Visible tests pass, hidden finance checks fail. No model can guess an unwritten policy.
   > It pauses — that's a real LangGraph interrupt." Type *"Use Decimal, round half-up to
   > cents"*, then **Resume** → ✅.
5. *(If time allows)* **t5_slugify · contradictory_spec**: two tests contradict each other.
   Show the `impossible` Noul and whether Jev terminates earlier than fixed retry's five
   attempts.

   *(Strongest beat if the live benchmark supports it)* **t7_temperature · silent_corruption**:
   "A helper constant was quietly changed. The error looks like an ordinary failing assertion,
   so the rules keep retrying. Jev is also told which files differ from the last good
   snapshot." Show whether it picks `restore_checkpoint`, and only claim it if it does.

### 2:00–2:45 — The numbers
6. Open the **Benchmark results** tab and select the live run.
   > "Same nine tasks, same budgets, same seeds, multiple repeats. Completion rate, total cost,
   > and the metric that matters: verified successes per dollar."
   Read the three bars **as they are**. If rule-based ties or beats Jev, say so:
   > "Our hand-written rules know these six scenarios because we wrote both. The interesting
   > part is that Jev matches them without being told the rules — and it adapts when the error
   > text doesn't match a regex."
7. Point out zero budget violations and the policy-override count.
   > "Every number here can be recomputed from the raw trace file — `benchmark.py --recompute`."

### 2:45–3:00 — Close
> "Cheap typed decisions on the control path, expensive LLM calls only where they earn their
> keep. Code's on GitHub; the README says exactly what's measured and what's simulated."
