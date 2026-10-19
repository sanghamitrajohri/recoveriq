"""Terminal demo: the same failing task under each strategy, side by side.

    python scripts/demo.py                       # t3_inventory (output truncation)
    python scripts/demo.py --task t2_duration    # workspace corruption
    python scripts/demo.py --interactive         # you answer human escalations
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import Task  # noqa: E402
from benchmark import provenance  # noqa: E402
from config import RUNS_DIR, Budget, Settings  # noqa: E402
from engine import RecoveryRun, console_human, scripted_human  # noqa: E402
from strategies import STRATEGY_NAMES, make_strategy  # noqa: E402


def show(trace: list[dict]) -> None:
    for t in trace:
        if t["kind"] == "attempt":
            tag = "measured" if t["measured"] else ("injected" if t["source"] == "injected" else "simulated")
            print(f"  attempt {t['attempt']}  {t['model']:<18} {t['status']:<19} ${t['cost_usd']:.5f} ({tag})  "
                  f"{t['summary'][:70]}")
        elif t["kind"] == "jev":
            conf = f"{t['confidence']:.2f}" if t["confidence"] is not None else "n/a"
            print(f"    jev[{t['source']}] -> {t['action']}  conf={conf}  type={t['failure_type']}")
        elif t["kind"] == "decision":
            flag = " OVERRIDE" if t["overridden"] else ""
            print(f"    decide: {t['proposed']} -> {t['action']}{flag}  (remaining ${t['remaining_usd']:.5f})")
        elif t["kind"] == "action":
            print(f"    act: {t['detail']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="t3_inventory")
    ap.add_argument("--strategies", default=",".join(STRATEGY_NAMES))
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()
    settings, task = Settings(), Task.load(args.task)
    for k, v in provenance(settings).items():
        print(f"{k:>7}: {v}")
    print(f"\nTASK {task.id}: {task.title}\nSCENARIO {task.scenario}: {task.scenario_note}\n")
    rows = []
    for name in args.strategies.split(","):
        run = RecoveryRun(task, make_strategy(name, settings.jev_mode, settings.jev_model), settings, Budget(),
                          run_root=RUNS_DIR / "demo")
        run.run(human=console_human if args.interactive else scripted_human(task))
        s = run.summary()
        rows.append(s)
        print(f"== {name} ==")
        show(run.state.get("trace", []))
        print()
    print(f"{'strategy':<13}{'outcome':<18}{'attempts':>9}{'cost USD':>11}  actions")
    for s in rows:
        print(f"{s['strategy']:<13}{s['outcome']:<18}{s['attempts']:>9}{s['total_cost_usd']:>11.5f}  {' > '.join(s['actions'])}")


if __name__ == "__main__":
    main()
