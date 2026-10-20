"""Terminal demo: one failing task under each strategy, narrated live, step by step.

    python scripts/demo.py                                   # t10_checkout (tax silently changed to 80%)
    python scripts/demo.py --task t7_temperature             # constant silently changed
    python scripts/demo.py --strategies recoveriq            # just RecoverIQ (fast)
    python scripts/demo.py --interactive                     # you answer human escalations
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import Task  # noqa: E402
from benchmark import provenance  # noqa: E402
from config import RUNS_DIR, Budget, Settings  # noqa: E402
from engine import RecoveryRun, console_human, scripted_human  # noqa: E402
from integrity import audit  # noqa: E402
from narrate import ACTION_PLAIN, c, printer, sabotage_diff  # noqa: E402
from strategies import make_strategy  # noqa: E402

LABELS = {"recoveriq": "RecoverIQ (Jev + gate)", "recoveriq_raw": "Jev only (no gate)",
          "rule_based": "Rule-based (hand-written rules)", "fixed_retry": "Fixed retry (always retry)"}


def rule(title: str) -> None:
    print("\n" + c(f"━━━ {title} " + "━" * max(3, 72 - len(title)), "bold"), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="t10_checkout")
    ap.add_argument("--strategies", default="fixed_retry,rule_based,recoveriq")
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()
    settings, task, budget = Settings(), Task.load(args.task), Budget()

    rule("RecoverIQ: what should a coding agent do after it fails?")
    for k, v in provenance(settings).items():
        live = "LIVE" in str(v).upper() or "live" in str(v)
        print(f"  {k:>7}: {c(str(v), 'green' if live else 'yellow')}")
    print(f"  budget : ${budget.max_cost_usd:.2f} and {budget.max_attempts} attempts per strategy")

    rule(f"The task: {task.id}")
    print(f"  {task.title}")
    print(f"  Job: {task.description}")
    print(f"  The agent may only edit: {c(task.target_file, 'bold')}")
    diff = sabotage_diff(task)
    if diff:
        print(c("  The sabotage, injected after attempt 1:", "yellow"))
        for line in diff.splitlines():
            style = "red" if line.startswith("-") else "green" if line.startswith("+") else "dim"
            print("    " + c(line, style))
    else:
        print(f"  What goes wrong: {task.scenario_note}")
    print("  After each failure there are five moves: " + " | ".join(ACTION_PLAIN.values()))

    rows = []
    for name in args.strategies.split(","):
        rule(f"Strategy: {LABELS.get(name, name)}")
        run = RecoveryRun(task, make_strategy(name, settings.jev_mode, settings.jev_model), settings, budget,
                          run_root=RUNS_DIR / "demo")

        def human(payload: dict, _task=task) -> str:
            print(c(f"ASK A PERSON: {payload['question']}", "yellow"), flush=True)
            if args.interactive:
                return console_human(payload)
            print(c(f"   (simulated person replies: {_task.human_hint})", "dim"), flush=True)
            return _task.human_hint

        t0 = time.perf_counter()
        state = run.run(human=human, on_item=printer("  "))
        secs, spent = time.perf_counter() - t0, run.rc.tracker.spent_usd
        ok = state.get("status") == "success"
        check = audit(task, run.rc.workspace) if ok else None
        if ok and check["clean"]:
            verdict = c(f"✅ CLEAN FIX in {secs:.0f}s for ${spent:.4f}", "green", "bold")
        elif ok:
            flags = ", ".join(check["gaming"] + [f"damaged {f}" for f in check["damaged"]])
            verdict = c(f"⚠️  TESTS PASSED BY CHEATING ({flags}) in {secs:.0f}s for ${spent:.4f}", "yellow", "bold")
        else:
            verdict = c(f"❌ NO FIX ({state.get('status')}) after {secs:.0f}s, ${spent:.4f}", "red", "bold")
        print("  " + verdict)
        if ok:
            print(c("  inspector: " + ("nothing gamed or damaged" if check["clean"] else "flagged, does not count"),
                    "dim"))
        rows.append((name, ok and check["clean"], verdict, state.get("attempt", 0), spent, secs,
                     state.get("actions", [])))

    rule("Scoreboard")
    print(f"  {'strategy':<34}{'clean fix':<11}{'attempts':>9}{'cost':>10}{'time':>7}  moves")
    for name, clean, _, attempts, spent, secs, actions in rows:
        mark = c("yes", "green") if clean else c("no ", "red")
        print(f"  {LABELS.get(name, name):<34}{mark:<{11 + (len(mark) - 3)}}{attempts:>9}{spent:>10.4f}{secs:>6.0f}s"
              f"  {' > '.join(actions) or 'none needed'}")
    winners = [r for r in rows if r[1]]
    if winners:
        best = min(winners, key=lambda r: r[4])
        print("\n  " + c(f"Cheapest clean fix: {LABELS.get(best[0], best[0])} at ${best[4]:.4f}", "green", "bold"))


if __name__ == "__main__":
    main()
