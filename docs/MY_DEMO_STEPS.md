# My live demo, step by step

For each step: **DO** (what to click), **SEE** (what should appear), **SAY** (your words).
A full practice run costs about **$0.25** (one checkout race + one temperature run).

---

## PART A: Setup (before you go on stage)

**Step 1: Open Terminal.** Press **Cmd + Space**, type **Terminal**, press **Enter**.

**Step 2: Start the app.** Paste these two lines, pressing **Enter** after each:
```bash
cd ~/Desktop/recoveriq
.venv/bin/streamlit run app.py
```
SEE: the browser opens a page called **RecoverIQ** (or go to http://localhost:8501).
Don't close this Terminal window; it's running the app.

**Step 3: Zoom.** In the browser press **Cmd and +** twice.

**Step 4: Check you're LIVE.** In the left sidebar, both badges are **green**:
"LLM: LIVE Anthropic" and "Jev: LIVE TypeSafe". If they're yellow, stop and ask for help.

**Step 5: Warm-up.** Sidebar → pick **t6_wordcount · clean** → click the **Live run** tab →
click **▶ Run agent**. SEE: "✅ VERIFIED SUCCESS" within seconds.

**Step 6: Starting screen.** Sidebar → pick **t10_checkout · silent_corruption** → click the
**🏁 Live race** tab. Don't press Start yet.

---

## PART B: The demo (3 minutes)

### Step 7: Opening (0:00–0:20). Before touching anything.
SAY:
> "Picture a robot baker. A cake comes out wrong, so it bakes again. But someone swapped the
> sugar for salt, so every cake is salty, and you pay for every one. That's how most AI coding
> agents handle failure: they just try again.
>
> RecoverIQ adds a cheap decision helper called **Jev**, from TypeSafe. When the agent fails,
> Jev picks the right fix: try again, use a smarter model, restore the files, ask a human, or
> stop. A simple money checker makes sure we never overspend. Let me show you, live."

### Step 8: Set up the race (0:20)
SAY:
> "Here's an online shop. The AI agent is fixing a small checkout bug. While it works, someone
> fat-fingers the tax setting from **8% to 80%**. A $100 order now costs **$180**. And the agent
> is only allowed to edit the checkout file, not the settings."

DO: click **🏁 Start race**.
SEE: three columns, all **⏳ working…**: Fixed retry · Rule-based · RecoverIQ.

SAY:
> "Three strategies, same task, same budget, racing with real AI calls right now."

### Step 9: RecoverIQ wins (~10–15 s in)
SEE: the RecoverIQ column turns **✅ SOLVED** (about 13 s, about $0.0068), with a line like
**🧠 Jev → restore_checkpoint (0.97) · workspace_damaged**.

SAY (point at the 🧠 line):
> "Done. Jev looked at the failure and said: **a file is damaged, restore the saved copy**.
> It was 97% sure. That decision cost a two-hundredth of a cent. Then the cheap model fixed the
> actual bug. Under one cent in total."

### Step 10: Watch the others struggle (~15–100 s)
SEE: the other two still **⏳ working…**, their **Spent** numbers and budget bars growing.

SAY:
> "Plain retry keeps paying for the same mistake, because trying again never fixes the 80%.
> The rule-based system thinks it's a normal bug, so it escalates to the expensive model, and
> then asks a human for help."

SEE (after about 45 s): **Fixed retry → ❌ GAVE UP**.
> "Retry gave up."

SEE (after about 100 s): **Rule-based → ⚠️ "SOLVED" BY CHEATING**, with a warning like
"the inspector found: writes_files".

SAY:
> "And look at this. The rule-based one says the tests passed, but my inspector caught it: the
> expensive AI wrote code that **secretly rewrites the settings file** to sneak past the rules.
> Tests green, but it cheated. It also cost about **27 times more**."

Point at the green banner: **"Cheapest clean fix: RecoverIQ"**.

*(If the rule-based one is still running when you're at 1:45, don't wait: say "it'll take
another minute, let's move on" and continue.)*

### Step 11: Second case, the temperature (about 15 seconds)
DO: sidebar → pick **t7_temperature · silent_corruption** → click the **Live run** tab →
click **▶ Run agent**.
SEE: within about 5 s, **✅ VERIFIED SUCCESS**, Jev chose **restore_checkpoint**.

SAY:
> "Same idea in a science app: a constant was changed from 1.8 to 1.6. Jev caught it again,
> five seconds, a quarter of a cent. Across both tasks, Jev fixed six out of six. The
> hand-written rules fixed none of them cleanly."

### Step 12: The big results (~2:00–2:40)
DO: click the **Benchmark results** tab; the dropdown should say **live-2026-10-19**.
SEE three charts: clean completion (RecoverIQ **89%**, rules **78%**, retry **44%**), total cost
(RecoverIQ **$0.559**, rules **$0.830**), and clean fixes per dollar (RecoverIQ **42.9**,
rules **25.3**, retry **31.3**).

SAY:
> "Beyond the demo, I ran 108 real tests: nine different broken tasks, every strategy, three
> times each, with real AI and real money. RecoverIQ fixed the most, 24 out of 27, spent about
> a third less than the rules, and got **42.9 clean fixes per dollar**, against 25 for the rules
> and 31 for plain retry. And it never went over budget, not once."

Then the honest note (this builds trust):
> "Two honest notes. One rule I added made it overspend on simple temporary errors. And if you
> price a person's time highly, plain retry looks cheapest, because it never asks anyone, even
> though it fixes less than half."

### Step 13: Close (2:40–3:00)
SAY:
> "So: let a cheap decision model choose how to recover, let plain code control the money, and
> never trust green tests without checking how they got green. The code is public on GitHub and
> the project page is **sanghamitrajohri.github.io/recoveriq**. Thank you!"

---

## PART C: Compare your results

| What to check | Expected | Mine |
|---|---|---|
| RecoverIQ (checkout race) | ✅ SOLVED, about 10–15 s, about $0.007 | |
| Jev's choice | restore_checkpoint, about 0.97 | |
| Fixed retry | ❌ GAVE UP, about 45 s, about $0.027 | |
| Rule-based | ⚠️ "SOLVED" BY CHEATING or ❌ GAVE UP, about 80–100 s, $0.08–0.19 | |
| Temperature run (RecoverIQ) | ✅ about 5 s, about $0.0024 | |
| Benchmark: RecoverIQ clean fixes per $ | 42.9 | |

Small differences are normal: live AI varies a little each run. In 5 live tries on the checkout
task, the rule-based strategy "solved" it by cheating 4 times and gave up once. Both are fine for
the story.

---

## PART D: When you're done practicing
Click the Terminal window that's running the app and press **Ctrl + C**.

## If something goes wrong on stage
| Problem | What to do and say |
|---|---|
| Wi-Fi is down | Benchmark results tab: "The internet's down, so here are 108 real runs." |
| RecoverIQ doesn't win | "That's live AI, it varies. That's why I ran it 108 times." Then the benchmark tab. |
| Page frozen | Cmd + R to refresh, then the benchmark tab. |
| You forget what to say | Breathe. "The key idea: figure out why it failed before paying to try again." |
