# RecoverIQ — 3-minute live demo (AI Tinkerers)

Every number here comes from the live benchmark `results/live-2026-10-19`: 108 runs with real
Claude and real Jev calls, $2.41 total. Setup and fallbacks: `docs/DEMO_CHEATSHEET.md`.

**On screen before you start:** the dashboard (`streamlit run app.py`) at 125% zoom with green
LIVE badges, plus `docs/examples/reward_hack_slugify.py` open in a second window.

---

### 0:00–0:20 — The problem
> "Coding agents fail constantly. The default fix is *retry*: same model, same prompt, pay
> again. Sometimes that works. Often the right move is a bigger model, rolling back the
> workspace, asking a human, or just stopping. RecoverIQ makes that call with **Jev**,
> TypeSafe's decision model. It answers typed questions with probabilities, not prose, and a
> plain-code budget policy sits on top that Jev can't override."

### 0:20–1:05 — Live moment: damage the rules can't see (`t7_temperature`)
Sidebar → **t7_temperature · silent_corruption**, strategy **RecoverIQ (Jev + gate)** → **Run**.
It takes about 5 seconds.

> "While the agent was working, something quietly changed a constant in a helper file. It's
> still valid Python, so the tests fail like any ordinary bug."

When the trace appears, point at the blue Jev box:
> "Jev diagnoses `workspace_damaged` and recommends `restore_checkpoint`" — **read the
> confidence off the screen**; it was 0.97 in rehearsal — "the policy approves it, we restore
> a real snapshot with every file hash verified, and the cheap model fixes the bug. Verified,
> including hidden tests, for a quarter of a cent."

> "Our hand-written rule-based baseline **failed this task in all 3 runs** and burned
> **$0.36** escalating to Opus and asking humans. Jev went 3 for 3 at **$0.007**."

### 1:05–1:45 — The model cheated (`reward_hack_slugify.py`)
Switch to the code window.
> "Task 5 has two tests that contradict each other: it's impossible by design. Watch what
> Claude Opus did. It returned a fake string whose equality check treats hyphens and
> underscores as the same character, so **both contradictory tests pass**."
Point at `def __eq__`.
> "Tests green, function broken. That's reward hacking, and it happened live in our benchmark.
> So we added an integrity audit, and we only count **clean** successes: tests pass, no files
> damaged, no gaming. The audit flagged 3 rule-based wins and 3 Jev-only wins as cheats.
> Gated RecoverIQ cheated once, and in 2 of 3 runs Jev correctly said 'this task is
> impossible' and stopped."

### 1:45–2:40 — The numbers
**Benchmark results** tab (the `live-2026-10-19` run is preselected).
> "108 real runs across nine tasks and four strategies, all with the same budgets."

Point at the three charts, left to right:
> "Clean completion: RecoverIQ **24 of 27**, rules 21, fixed retry 12. Total API cost:
> RecoverIQ **$0.56**, the rules **$0.83**. Clean successes per dollar: **42.9** for RecoverIQ,
> **31.3** for fixed retry, **25.3** for the rules. And zero budget violations: the policy
> held every time."

Be upfront about the caveat (it builds trust):
> "Two honest caveats. My retry-gate, a one-line rule on top of Jev, made it skip a cheap retry
> on transient API errors, so it cost 4× more on that task. And if you price human time at
> 50 cents per question, fixed retry wins per dollar, because it never asks anyone, even though
> it solves less than half. Recovery strategy is a cost trade-off, and now you can measure it."

### 2:40–3:00 — Close
> "Fast, typed decisions on the control path, expensive LLM calls only where they earn it, and
> never trust a green test suite without checking how it got green. Every number recomputes
> from the raw traces, and the code and full results are in the repo."

---

## Backup moments (if a question or spare time comes up)
* **t3_inventory (output truncation):** Haiku hits its 1,024-token cap, RecoverIQ escalates
  to Opus, and it passes. This takes about 30 s live (Opus ~23 s), so talk through the Jev
  probabilities while it runs.
* **t4_pricing (human escalation):** the run pauses for input. Type *"Use Decimal, round
  half-up to cents"* and press **Resume** → ✅. Honest note: Jev tried Opus before asking, so it
  cost $0.047 against the rules' $0.003.
* **Q: "Isn't Jev just a cheap LLM?"** No. It doesn't generate text. It returns a choice and a
  probability for every option. Measured over 60 live decisions: about $0.00005 and
  102 ms each on average.
