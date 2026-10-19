"""Print markdown result tables for a benchmark directory (after integrity_audit.py).

    python scripts/report.py results/<benchmark_id>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LABELS = {"fixed_retry": "Fixed retry", "rule_based": "Rule-based", "recoveriq_raw": "Jev only (no gate)",
          "recoveriq": "RecoverIQ (Jev + gate)"}
ORDER = ["fixed_retry", "rule_based", "recoveriq_raw", "recoveriq"]


def main() -> None:
    d = Path(sys.argv[1])
    m = json.loads((d / "metrics.json").read_text())
    integ = json.loads((d / "integrity.json").read_text()) if (d / "integrity.json").exists() else {}
    print("| Strategy | Verified | Clean | Gamed | Damaged | Total cost | Clean successes / $ | "
          "Avg attempts | Human escalations | Budget violations |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in [x for x in ORDER if x in m["by_strategy"]]:
        a, i = m["by_strategy"][s], integ.get(s, {})
        print(f"| {LABELS[s]} | {a['verified_successes']}/{a['runs']} | {i.get('clean_successes', '-')} | "
              f"{i.get('successes_with_gaming_signals', '-')} | {i.get('successes_with_damaged_workspace', '-')} | "
              f"${a['total_cost_usd']:.4f} | {i.get('clean_successes_per_dollar', '-')} | {a['avg_attempts']} | "
              f"{a['human_escalations']} | {a['budget_violations']} |")
    scen = sorted({sc for by in m["by_strategy_scenario"].values() for sc in by})
    print("\n| Scenario | " + " | ".join(LABELS[s] for s in ORDER if s in m["by_strategy"]) + " |")
    print("|---|" + "---|" * len([s for s in ORDER if s in m["by_strategy"]]))
    for sc in scen:
        cells = []
        for s in [x for x in ORDER if x in m["by_strategy"]]:
            v = m["by_strategy_scenario"][s].get(sc)
            cells.append(f"{v['verified_successes']}/{v['runs']} · ${v['total_cost_usd']:.4f}" if v else "-")
        print(f"| {sc} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
