"""Benchmark the three recovery strategies on the same tasks and budgets.

    python benchmark.py --repeats 3                    # offline (scripted LLM + mock Jev)
    python benchmark.py --llm-mode live --jev-mode live --repeats 2
    python benchmark.py --recompute results/<benchmark_id>   # re-derive metrics from raw traces

Outputs under results/<benchmark_id>/:
    traces.jsonl   raw per-event and per-run records (source of truth)
    raw.sqlite     the same records in SQLite (tables: events, runs)
    runs.csv       one row per run
    metrics.json   aggregate metrics per strategy and per strategy x scenario
    metrics.csv    per-strategy aggregate table
    manifest.json  configuration, modes, package versions, data-provenance labels
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from agent import Task, list_tasks
from config import RESULTS_DIR, RUNS_DIR, Budget, Settings
from cost_tracker import Store
from engine import RecoveryRun, scripted_human
from strategies import STRATEGY_NAMES, make_strategy


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def aggregate(runs: list[dict], human_cost_usd: float) -> dict:
    """Aggregate metrics for a group of run summaries. Pure function of the run records."""
    n = len(runs)
    successes = sum(r["verified_success"] for r in runs)
    cost = sum(r["total_cost_usd"] for r in runs)
    escalations = sum(r["human_escalations"] for r in runs)
    cost_with_human = cost + escalations * human_cost_usd
    latencies = [r["latency_s"] for r in runs]
    ok_latencies = [r["latency_s"] for r in runs if r["verified_success"]]
    return {
        "runs": n,
        "verified_successes": successes,
        "completion_rate": round(successes / n, 6) if n else 0.0,
        "total_cost_usd": round(cost, 8),
        "llm_cost_usd": round(sum(r["llm_cost_usd"] for r in runs), 8),
        "jev_cost_usd": round(sum(r["jev_cost_usd"] for r in runs), 8),
        "avg_cost_per_success_usd": round(cost / successes, 8) if successes else None,
        "successes_per_dollar": round(successes / cost, 4) if cost > 0 else None,
        "successes_per_dollar_incl_human": round(successes / cost_with_human, 4) if cost_with_human > 0 else None,
        "recovery_actions": sum(r["recovery_actions"] for r in runs),
        "avg_attempts": round(sum(r["attempts"] for r in runs) / n, 4) if n else 0.0,
        "avg_latency_s": round(sum(latencies) / n, 4) if n else None,
        "p95_latency_s": round(p95(latencies), 4) if latencies else None,
        "avg_success_latency_s": round(sum(ok_latencies) / len(ok_latencies), 4) if ok_latencies else None,
        "p95_success_latency_s": round(p95(ok_latencies), 4) if ok_latencies else None,
        "human_escalations": escalations,
        "budget_violations": sum(r["budget_violations"] for r in runs),
        "policy_overrides": sum(r["policy_overrides"] for r in runs),
        "all_measured": all(r["all_measured"] for r in runs) if runs else False,
    }


def compute_metrics(runs: list[dict], human_cost_usd: float) -> dict:
    by_strategy: dict = {}
    by_scenario: dict = {}
    for s in sorted({r["strategy"] for r in runs}):
        group = [r for r in runs if r["strategy"] == s]
        by_strategy[s] = aggregate(group, human_cost_usd)
        by_scenario[s] = {sc: aggregate([r for r in group if r["scenario"] == sc], human_cost_usd)
                          for sc in sorted({r["scenario"] for r in group})}
    return {"by_strategy": by_strategy, "by_strategy_scenario": by_scenario}


def load_runs(trace_path: Path) -> list[dict]:
    runs = []
    for line in trace_path.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") == "run":
            rec.pop("type")
            runs.append(rec)
    return runs


def provenance(settings: Settings) -> dict:
    return {
        "llm": "MEASURED: real Anthropic API usage" if settings.llm_is_live else
               "SIMULATED: scripted offline LLM; token counts are chars/4 estimates, not measurements",
        "jev": "MEASURED: real TypeSafe Jev API" if settings.jev_is_live else
               "MOCK: offline heuristic stand-in for Jev; NOT Jev results",
        "human": "SIMULATED: scripted human replies with each task's documented hint",
        "faults": "INJECTED: transient provider errors and file corruption are injected by the harness (see task.json)",
    }


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def run_benchmark(strategies: list[str], tasks: list[Task], repeats: int, budget: Budget,
                  settings: Settings, out_dir: Path, llm_factory=None, progress=print) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    bench_id = out_dir.name
    trace = out_dir / "traces.jsonl"
    trace.unlink(missing_ok=True)
    store = Store(out_dir / "raw.sqlite", trace)
    summaries = []
    for rep in range(repeats):
        for task in tasks:
            for name in strategies:
                strategy = make_strategy(name, settings.jev_mode, settings.jev_model)
                run = RecoveryRun(task, strategy, settings, budget, repeat=rep,
                                  llm=llm_factory() if llm_factory else None,
                                  run_root=RUNS_DIR / bench_id, run_id=f"{name}-{task.id}-r{rep}")
                run.run(human=scripted_human(task))
                summary = run.summary(bench_id)
                store.write_events(run.rc.tracker.events)
                store.write_run(summary)
                summaries.append(summary)
                progress(f"[{rep}] {task.id:14} {name:12} {summary['outcome']:17} "
                         f"attempts={summary['attempts']} cost=${summary['total_cost_usd']:.5f} "
                         f"actions={summary['actions']}")
    metrics = compute_metrics(summaries, settings.human_cost_usd)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    fields = ["strategy"] + list(next(iter(metrics["by_strategy"].values())).keys())
    with (out_dir / "metrics.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for s, m in metrics["by_strategy"].items():
            w.writerow({"strategy": s, **m})
    with (out_dir / "runs.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summaries[0].keys()))
        w.writeheader()
        for s in summaries:
            w.writerow({**s, "actions": json.dumps(s["actions"])})
    manifest = {
        "benchmark_id": bench_id, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "strategies": strategies, "tasks": [t.id for t in tasks], "repeats": repeats,
        "budget": asdict(budget), "llm_mode": settings.llm_mode, "jev_mode": settings.jev_mode,
        "jev_model": settings.jev_model, "tiers": [asdict(t) for t in settings.tiers],
        "human_cost_usd": settings.human_cost_usd, "provenance": provenance(settings),
        "git_commit": git_commit(), "python": sys.version.split()[0], "platform": platform.platform(),
        "packages": {p: version(p) for p in ("anthropic", "typesafe-sdk", "langgraph", "streamlit")},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return metrics


def recompute(out_dir: Path) -> bool:
    """Re-derive metrics from traces.jsonl and compare with the saved metrics.json."""
    manifest = json.loads((out_dir / "manifest.json").read_text())
    fresh = compute_metrics(load_runs(out_dir / "traces.jsonl"), manifest["human_cost_usd"])
    saved = json.loads((out_dir / "metrics.json").read_text())
    return fresh == saved


def print_table(metrics: dict) -> None:
    cols = ["runs", "verified_successes", "completion_rate", "total_cost_usd", "avg_cost_per_success_usd",
            "successes_per_dollar", "avg_attempts", "human_escalations", "budget_violations", "p95_latency_s"]
    print("\n" + "strategy".ljust(13) + " ".join(c[:14].rjust(14) for c in cols))
    for s, m in metrics["by_strategy"].items():
        print(s.ljust(13) + " ".join(str(m[c] if m[c] is not None else "-")[:14].rjust(14) for c in cols))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategies", default=",".join(STRATEGY_NAMES))
    ap.add_argument("--tasks", default="all", help="comma-separated task ids or 'all'")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--budget-usd", type=float, default=Budget.max_cost_usd)
    ap.add_argument("--max-attempts", type=int, default=Budget.max_attempts)
    ap.add_argument("--max-seconds", type=float, default=Budget.max_seconds)
    ap.add_argument("--llm-mode", choices=["live", "scripted"])
    ap.add_argument("--jev-mode", choices=["live", "mock"])
    ap.add_argument("--out", help="output directory (default results/<timestamp>)")
    ap.add_argument("--recompute", help="re-derive metrics from a saved benchmark directory")
    args = ap.parse_args()

    if args.recompute:
        ok = recompute(Path(args.recompute))
        print("metrics reproduced from raw traces: " + ("OK" if ok else "MISMATCH"))
        sys.exit(0 if ok else 1)

    import os
    if args.llm_mode:
        os.environ["RECOVERIQ_LLM_MODE"] = args.llm_mode
    if args.jev_mode:
        os.environ["RECOVERIQ_JEV_MODE"] = args.jev_mode
    settings = Settings()
    budget = Budget(max_attempts=args.max_attempts, max_cost_usd=args.budget_usd, max_seconds=args.max_seconds)
    tasks = list_tasks() if args.tasks == "all" else [Task.load(t) for t in args.tasks.split(",")]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else RESULTS_DIR / f"{stamp}-{settings.llm_mode}-{settings.jev_mode}"
    for k, v in provenance(settings).items():
        print(f"{k:>7}: {v}")
    metrics = run_benchmark(args.strategies.split(","), tasks, args.repeats, budget, settings, out)
    print_table(metrics)
    print(f"\nresults: {out}\nreproducible: {recompute(out)}")


if __name__ == "__main__":
    main()
