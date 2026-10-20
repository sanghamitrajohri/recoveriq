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
from config import RESULTS_DIR, RUNS_DIR, Budget, Settings  # noqa: E402
from engine import RecoveryRun, console_human, scripted_human  # noqa: E402
from integrity import audit  # noqa: E402
from narrate import (ACTION_PLAIN, agent_change, c, code_listing, hidden_test_count, printer,  # noqa: E402
                     jev_vs_without, keep_awake, sabotage_diff, saved_results, styled, visible_tests)  # noqa: E402
from strategies import make_strategy  # noqa: E402

LABELS = {"recoveriq": "RecoverIQ (Jev + gate)", "recoveriq_raw": "Jev only (no gate)",
          "rule_based": "Rule-based (hand-written rules)", "fixed_retry": "Fixed retry (always retry)"}
INTRO_RECOVERIQ = [
    "RecoverIQ is a cost-aware recovery controller for AI coding agents.",
    "When a Claude agent fails a task, TypeSafe's Jev decides whether to retry, switch models,",
    "restore a checkpoint, escalate to a human or stop. Fixed budget and safety rules can veto",
    "that choice, so you get more verified fixes per dollar than with blind retries.",
]
INTRO_JEV = [
    "Jev is TypeSafe's decision model, called through their \"System One\" API.",
    "It doesn't write code or text. You give it a JSON description of a situation plus a few",
    "structured questions, and it sends back answers with probabilities.",
    "It costs $0.042 per million input tokens and output is free, so each decision costs a",
    "fraction of a cent. In RecoverIQ it acts as the \"kitchen manager\" that picks the recovery move.",
]
SHORT = {"recoveriq": "RecoverIQ", "recoveriq_raw": "Jev only", "rule_based": "Rule-based", "fixed_retry": "Fixed retry"}


def wait(enabled: bool, prompt: str) -> None:
    if enabled:
        input("\n" + c(prompt + "⏎", "yellow"))


def rule(title: str) -> None:
    print("\n" + c(f"━━━ {title} " + "━" * max(3, 72 - len(title)), "bold"), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="t10_checkout")
    ap.add_argument("--strategies", default="fixed_retry,recoveriq",
                    help="comma list; add rule_based for the hand-written rules")
    ap.add_argument("--pause", action="store_true", help="wait for Enter between sections (for presenting)")
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()
    settings, task, budget = Settings(), Task.load(args.task), Budget()
    keep_awake()

    rule("RecoverIQ: what should a coding agent do after it fails?")
    for k, v in provenance(settings).items():
        live = "LIVE" in str(v).upper() or "live" in str(v)
        print(f"  {k:>7}: {c(str(v), 'green' if live else 'yellow')}")
    print(f"  budget : ${budget.max_cost_usd:.2f} and {budget.max_attempts} attempts per strategy")

    rule("What is RecoverIQ?")
    for line in INTRO_RECOVERIQ:
        print("  " + line)
    rule("What is Jev?")
    for line in INTRO_JEV:
        print("  " + c(line, "cyan"))

    rule(f"The task: {task.id}")
    print(f"  {task.title}")
    print(f"  Job: {task.description}")
    print(f"  The agent may only edit: {c(task.target_file, 'bold')}")

    wait(args.pause, "Press Enter to show the buggy code ")
    rule(f"The buggy code: {task.target_file}")
    for style, text in code_listing(task):
        print("  " + c(text, *({"bad": ("red", "bold"), "dim": ("dim",)}.get(style, ()))))
    rule("The tests it must pass")
    for line in visible_tests(task):
        print("  " + c(line, "dim" if line.startswith("#") else "cyan"))
    print(f"  + {hidden_test_count(task)} hidden tests the agent never sees (a fix counts only if those pass too)")

    rule("What runs on every attempt")
    print("  1. Claude gets the task, the code and the last test output, and returns a new "
          f"{task.target_file}")
    print("  2. We run pytest in a sandbox: no network, no API keys, only this workspace")
    print("  3. If tests fail, a strategy picks one of five moves; a budget policy in plain code can veto it")

    wait(args.pause, "Press Enter to show what goes wrong mid-run ")
    rule("What goes wrong mid-run")
    diff = sabotage_diff(task)
    if diff:
        print(c("  The sabotage, injected after attempt 1:", "yellow"))
        for line in diff.splitlines():
            style = "red" if line.startswith("-") else "green" if line.startswith("+") else "dim"
            print("    " + c(line, style))
    else:
        print(f"  What goes wrong: {task.scenario_note}")
    print("  After each failure there are five moves: " + " | ".join(ACTION_PLAIN.values()))

    rows, outcome = [], {}
    for i, name in enumerate(args.strategies.split(",")):
        uses_jev = name.startswith("recoveriq")
        wait(args.pause, f"Press Enter to run {'WITH' if uses_jev else 'WITHOUT'} Jev: {LABELS.get(name, name)} ")
        rule(f"PART {i + 1}: {'WITH' if uses_jev else 'WITHOUT'} Jev · {LABELS.get(name, name)}")
        run = RecoveryRun(task, make_strategy(name, settings.jev_mode, settings.jev_model), settings, budget,
                          run_root=RUNS_DIR / "demo")

        def human(payload: dict, _task=task) -> str:
            print(c(f"ASK A PERSON: {payload['question']}", "yellow"), flush=True)
            if args.interactive:
                return console_human(payload)
            print(c(f"   (simulated person replies: {_task.human_hint})", "dim"), flush=True)
            return _task.human_hint

        t0 = time.perf_counter()
        state = run.run(human=human, on_item=printer("  ", show_code=True))
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
        change = agent_change(task, run.rc.workspace)
        if change:
            print(c(f"  What the AI changed in {task.target_file}:", "bold"))
            for line in change.splitlines()[:30]:
                style = "red" if line.startswith("-") else "green" if line.startswith("+") else "dim"
                print("    " + c(line, style))
        print("  " + verdict)
        print("  " + c(f"TOTAL {'WITH' if uses_jev else 'WITHOUT'} JEV: {state.get('attempt', 0)} attempts · "
                       f"{secs:.0f} seconds · ${spent:.4f}", "bold"))
        if ok:
            print(c("  inspector: " + ("nothing gamed or damaged" if check["clean"] else "flagged, does not count"),
                    "dim"))
        rows.append((name, ok and check["clean"], verdict, state.get("attempt", 0), spent, secs,
                     state.get("actions", [])))
        outcome[name] = {"label": SHORT.get(name, name), "clean": bool(ok and check["clean"]), "cost": spent,
                         "secs": secs, "fixed": "yes" if ok and check["clean"] else ("CHEATED" if ok else "no fix"),
                         "note": "live, just now", "jev_cost": run.rc.tracker.spent_by_kind("jev_decision"),
                         "jev_calls": sum(e.kind == "jev_decision" for e in run.rc.tracker.events)}

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

    wait(args.pause, "Press Enter for the with-vs-without-Jev comparison ")
    print_jev_comparison(task, outcome)


def print_jev_comparison(task, outcome: dict) -> None:
    """With Jev (RecoverIQ) vs without Jev (fixed retry, rules): cost and time, live where we have it."""
    saved = saved_results(task.id, RESULTS_DIR)

    def from_saved(name: str) -> dict | None:
        s = saved.get(name)
        if not s:
            return None
        return {"label": SHORT.get(name, name), "clean": s["clean"] == s["runs"], "cost": s["cost"],
                "secs": s["secs"], "fixed": f"{s['clean']}/{s['runs']} clean",
                "note": f"avg of {s['runs']} saved live runs ({s['source']})"}

    with_jev = outcome.get("recoveriq") or from_saved("recoveriq")
    without = [outcome.get(n) or from_saved(n) for n in ("fixed_retry", "rule_based")]
    without = [w for w in without if w]
    if not with_jev or not without:
        return
    rule("With Jev vs without Jev")
    for style, text in jev_vs_without(with_jev, without):
        print("  " + styled(style, text))
    if any("saved" in w.get("note", "") for w in without):
        print(styled("dim", "  Saved runs are real live runs from the benchmark; rerun without --strategies to race them now."))


if __name__ == "__main__":
    main()
