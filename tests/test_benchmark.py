"""Benchmark metrics must be reproducible from saved raw traces."""
import json

from agent import Task
from benchmark import aggregate, p95, recompute, run_benchmark
from config import Budget


def test_metrics_reproduce_from_traces(tmp_path, settings, monkeypatch):
    monkeypatch.setattr("benchmark.RUNS_DIR", tmp_path / "runs")
    out = tmp_path / "bench"
    tasks = [Task.load("t1_median"), Task.load("t5_slugify")]
    metrics = run_benchmark(["fixed_retry", "rule_based", "recoveriq"], tasks, 2, Budget(), settings, out,
                            progress=lambda *_: None)
    assert recompute(out)
    runs = [json.loads(l) for l in (out / "traces.jsonl").read_text().splitlines() if '"type": "run"' in l]
    assert len(runs) == 12
    m = metrics["by_strategy"]["rule_based"]
    assert m["successes_per_dollar"] == round(m["verified_successes"] / m["total_cost_usd"], 4)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["provenance"]["jev"].startswith("MOCK") and manifest["provenance"]["llm"].startswith("SIMULATED")


def test_tampered_metrics_detected(tmp_path, settings, monkeypatch):
    monkeypatch.setattr("benchmark.RUNS_DIR", tmp_path / "runs")
    out = tmp_path / "bench"
    run_benchmark(["fixed_retry"], [Task.load("t6_wordcount")], 1, Budget(), settings, out, progress=lambda *_: None)
    m = json.loads((out / "metrics.json").read_text())
    m["by_strategy"]["fixed_retry"]["verified_successes"] += 1
    (out / "metrics.json").write_text(json.dumps(m))
    assert not recompute(out)


def test_aggregate_formula():
    runs = [dict(verified_success=1, total_cost_usd=0.02, llm_cost_usd=0.02, jev_cost_usd=0.0, human_escalations=0,
                 latency_s=1.0, recovery_actions=1, attempts=2, budget_violations=0, policy_overrides=0, all_measured=1),
            dict(verified_success=0, total_cost_usd=0.03, llm_cost_usd=0.03, jev_cost_usd=0.0, human_escalations=1,
                 latency_s=3.0, recovery_actions=3, attempts=4, budget_violations=0, policy_overrides=1, all_measured=1)]
    m = aggregate(runs, human_cost_usd=0.5)
    assert m["successes_per_dollar"] == 20.0 and m["avg_cost_per_success_usd"] == 0.05
    assert m["successes_per_dollar_incl_human"] == round(1 / 0.55, 4)
    assert m["completion_rate"] == 0.5 and m["p95_latency_s"] == 3.0


def test_p95():
    assert p95(list(range(1, 101))) == 95 and p95([]) is None
