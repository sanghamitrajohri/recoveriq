"""Verify the live integrations with real, authenticated API calls.

    python scripts/verify_live.py            # checks both Jev and Anthropic
    python scripts/verify_live.py --jev      # only Jev
    python scripts/verify_live.py --llm      # only Anthropic

Each check appends a record to results/live_checks.jsonl. Missing keys are reported as
blockers; nothing is mocked here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import CodingAgent, FaultPlan, Task, prepare_workspace  # noqa: E402
from config import RESULTS_DIR, RUNS_DIR, Budget, Settings  # noqa: E402
from jev_adapter import JevAdapter  # noqa: E402
from recovery_policy import RecoveryContext  # noqa: E402

LOG = RESULTS_DIR / "live_checks.jsonl"


def log(record: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with LOG.open("a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def check_jev(settings: Settings) -> bool:
    if not os.getenv("TYPESAFE_API_KEY"):
        print("BLOCKED  Jev: TYPESAFE_API_KEY is not set. Create a key at https://console.typesafe.ai/keys "
              "and add it to .env")
        log({"check": "jev", "status": "blocked", "reason": "TYPESAFE_API_KEY not set"})
        return False
    from typesafe_sdk import TypeSafeClient

    with TypeSafeClient() as client:
        models = [m.name for m in client.models.list().models]
    print(f"Jev models available to this key: {models}")
    ctx = RecoveryContext(
        task_id="t3_inventory", task_description=Task.load("t3_inventory").description, target_file="inventory.py",
        failure_type="output_truncated",
        error_summary="model output hit max_tokens=1024; patch incomplete and not applied",
        attempts_made=1, current_tier=0, tiers=settings.tiers, remaining_budget_usd=0.24, elapsed_s=4.0,
        budget=Budget(), failure_history=["output_truncated"], signature_history=["output_truncated"],
        est_input_tokens=2200, est_source_tokens=1800,
    )
    d = JevAdapter("live", settings.jev_model).decide(ctx)
    print(f"OK       Jev [{d.model}] action={d.action} confidence={d.confidence} failure_type={d.failure_type} "
          f"latency={d.latency_s:.3f}s input_tokens={d.input_tokens} cost=${d.cost_usd:.8f} request_id={d.request_id}")
    print(f"         probabilities={json.dumps({k: round(v, 3) for k, v in d.probabilities.items()})}")
    log({"check": "jev", "status": "ok", "models": models, **d.to_dict()})
    return True


def check_llm(settings: Settings) -> bool:
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("ANTHROPIC_AUTH_TOKEN"):
        print("BLOCKED  Anthropic: ANTHROPIC_API_KEY is not set. Add it to .env")
        log({"check": "anthropic", "status": "blocked", "reason": "ANTHROPIC_API_KEY not set"})
        return False
    from llm import AnthropicLLM

    task = Task.load("t6_wordcount")
    ws = prepare_workspace(task, RUNS_DIR / "_live_check" / "workspace")
    r = CodingAgent(AnthropicLLM(), FaultPlan({})).attempt(task, ws, settings.tiers[0], 1)
    print(f"{'OK      ' if r.measured else 'FAILED  '} Anthropic [{r.model}] status={r.status} "
          f"tokens={r.input_tokens}/{r.output_tokens} cost=${r.cost_usd:.6f} llm_latency={r.llm_latency_s:.2f}s "
          f"tests={r.passed_tests}/{r.total_tests} request_id={r.request_id}")
    if r.status == "llm_error":
        print(f"         {r.error_summary}")
    log({"check": "anthropic", "status": "ok" if r.measured else "error", "result": r.__dict__})
    return r.measured


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jev", action="store_true")
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()
    both = not (args.jev or args.llm)
    settings = Settings()
    ok = True
    if args.jev or both:
        ok &= check_jev(settings)
    if args.llm or both:
        ok &= check_llm(settings)
    print(f"\nlog: {LOG}")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
