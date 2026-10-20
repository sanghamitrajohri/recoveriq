"""Plain-English narration of a recovery run, printed live to the terminal as each step happens.

Used by ``scripts/demo.py`` and by the dashboard's live race (which logs to the Streamlit terminal).
Everything printed comes from the run's own trace and cost ledger; nothing is invented.
"""
from __future__ import annotations

import difflib
import os
import sys

STATUS_PLAIN = {"success": "all tests passed, visible and hidden",
                "test_failure": "the code ran but gave wrong answers",
                "acceptance_failure": "passed the tests it could see, failed the hidden ones",
                "malformed_output": "the reply wasn't usable code",
                "output_truncated": "the answer was cut off mid-code (output limit)",
                "collection_error": "the code is so broken the tests couldn't run",
                "llm_error": "the AI service errored out, no answer",
                "timeout": "the tests took too long"}
ACTION_PLAIN = {"retry": "try again with the same model", "switch_model": "call the bigger model",
                "restore_checkpoint": "roll the files back to the last good snapshot",
                "human_escalation": "ask a person", "terminate": "stop"}
SOURCE_PLAIN = {"jev": "Jev", "jev_mock": "mock Jev (not real)", "rule_based": "the hand-written rules",
                "fixed_retry": "the fixed rule (always retry)"}

_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
_CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "blue": "34", "cyan": "36"}


def keep_awake() -> None:
    """macOS: stop the machine sleeping while this process runs (a sleeping Mac stalls live API calls)."""
    import shutil
    import subprocess
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def c(text: str, *styles: str) -> str:
    if not _COLOR or not styles:
        return text
    return "".join(f"\033[{_CODES[s]}m" for s in styles) + text + "\033[0m"


def sabotage_diff(task) -> str | None:
    """Unified diff of the file a corrupt_file fault overwrites, from the task's own files."""
    fault = task.fault or {}
    if fault.get("type") != "corrupt_file":
        return None
    original = task.dir / "workspace" / fault["file"]
    if not original.exists():
        return None
    return "\n".join(difflib.unified_diff(
        original.read_text().splitlines(), fault["content"].splitlines(),
        f"{fault['file']} (correct)", f"{fault['file']} (after the sabotage)", lineterm="", n=1))


def bug_lines(task) -> set[int]:
    """1-based lines of the target file that differ from the task's reference fix (simulator/fixed.py)."""
    ref = task.dir / "simulator" / "fixed.py"
    if not ref.exists():
        return set()
    src = (task.dir / "workspace" / task.target_file).read_text().splitlines()
    sm = difflib.SequenceMatcher(None, src, ref.read_text().splitlines())
    return {i + 1 for tag, i1, i2, _, _ in sm.get_opcodes() if tag != "equal" for i in range(i1, max(i2, i1 + 1))}


def code_listing(task, max_lines: int = 30) -> list[tuple[str, str]]:
    """The buggy target file with line numbers; long files are cut to the lines around the bug."""
    src = (task.dir / "workspace" / task.target_file).read_text().splitlines()
    bugs = bug_lines(task)
    keep = set(range(1, len(src) + 1)) if len(src) <= max_lines else {
        n for b in bugs for n in range(b - 4, b + 5) if 1 <= n <= len(src)} or set(range(1, max_lines + 1))
    out, last = [], 0
    for n in sorted(keep):
        if n != last + 1:
            out.append(("dim", "      ..."))
        mark = n in bugs
        out.append(("bad" if mark else "", f"{n:>5}  {src[n - 1]}" + ("    <-- the bug" if mark else "")))
        last = n
    return out


def visible_tests(task, max_lines: int = 24) -> list[str]:
    lines: list[str] = []
    for p in sorted((task.dir / "workspace").glob("test_*.py")):
        lines += [f"# {p.name}"] + p.read_text().splitlines()
    return [ln for ln in lines if ln.strip()][:max_lines]


def hidden_test_count(task) -> int:
    return sum(p.read_text().count("\ndef test_") + p.read_text().startswith("def test_")
               for p in (task.dir / "acceptance").glob("*.py"))


def agent_change(task, workspace) -> str:
    """What the agent actually changed in the target file, as a unified diff."""
    before = (task.dir / "workspace" / task.target_file).read_text().splitlines()
    after_path = workspace / task.target_file
    after = after_path.read_text().splitlines() if after_path.exists() else []
    return "\n".join(difflib.unified_diff(before, after, f"{task.target_file} (buggy)",
                                          f"{task.target_file} (after the AI's fix)", lineterm="", n=1))


def saved_results(task_id: str, results_dir) -> dict[str, dict]:
    """Per-strategy averages for one task from saved LIVE benchmark runs (results/*/runs.csv + integrity.csv)."""
    import csv
    import json
    from pathlib import Path
    out: dict[str, dict] = {}
    for runs_csv in sorted(Path(results_dir).glob("*/runs.csv")):
        d = runs_csv.parent
        try:
            m = json.loads((d / "manifest.json").read_text())
        except (OSError, ValueError):
            continue
        if m.get("llm_mode") != "live" or m.get("jev_mode") != "live":
            continue
        clean = {}
        if (d / "integrity.csv").exists():
            clean = {r["run_id"]: r["clean_success"] == "1" for r in csv.DictReader(open(d / "integrity.csv"))}
        for r in csv.DictReader(open(runs_csv)):
            if r["task_id"] != task_id:
                continue
            s = out.setdefault(r["strategy"], {"runs": 0, "clean": 0, "cost": 0.0, "secs": 0.0, "source": d.name})
            s["runs"] += 1
            s["clean"] += int(clean.get(r["run_id"], r["verified_success"] == "1"))
            s["cost"] += float(r["total_cost_usd"])
            s["secs"] += float(r["latency_s"])
    for s in out.values():
        s["cost"] /= s["runs"]
        s["secs"] /= s["runs"]
    return out


NO_FIX = "RecoverIQ did not get a clean fix this time, so there is no Jev win to claim on this run."


def jev_verdict(with_jev: dict, w: dict) -> tuple[bool, str] | None:
    """(jev_better, sentence) comparing one no-Jev run to the Jev run, or None if not comparable."""
    if not (with_jev["cost"] and with_jev["secs"]) or not with_jev["clean"]:
        return None
    cost_x, time_x = w["cost"] / with_jev["cost"], w["secs"] / with_jev["secs"]
    money = f"spent {cost_x:.1f}x more" if cost_x >= 1 else f"spent {1 / cost_x:.1f}x LESS"
    speed = f"took {time_x:.1f}x longer" if time_x >= 1 else f"was {1 / time_x:.1f}x FASTER"
    result = "and got no clean fix" if not w["clean"] else "for the same result"
    return cost_x >= 1, f"without Jev, {w['label']} {money}, {speed}, {result}"


def jev_vs_without(with_jev: dict, without: list[dict]) -> list[tuple[str, str]]:
    """Rows are dicts with label, fixed (text), clean (bool), cost, secs, note. Returns styled lines."""
    def row(prefix: str, r: dict) -> str:
        return f"{prefix + r['label']:<26}{r['fixed']:<12}{'$' + format(r['cost'], '.4f'):>9}{r['secs']:>6.0f}s  {r.get('note', '')}"
    out = [("bold", f"{'':<26}{'clean fix?':<12}{'cost':>9}{'time':>7}")]
    out.append(("good", row("WITH Jev:    ", with_jev)))
    for w in without:
        out.append(("bad" if not w["clean"] else "", row("without Jev: ", w)))
        v = jev_verdict(with_jev, w)
        if v:
            out.append(("good" if v[0] else "warn", f"{'':<26}-> {v[1]}"))
    if not with_jev["clean"]:
        out.append(("warn", NO_FIX))
    if with_jev.get("jev_cost") is not None:
        share = with_jev["jev_cost"] / with_jev["cost"] * 100 if with_jev["cost"] else 0
        out.append(("jev", f"Jev's own cost: ${with_jev['jev_cost']:.5f} for {with_jev['jev_calls']} decision(s), "
                           f"{share:.1f}% of RecoverIQ's spend. The rest is Claude writing code."))
    return out


def describe(item: dict, jev_state: dict | None = None) -> list[tuple[str, str]]:
    """One trace item as (style, text) lines. Style is '', 'good', 'bad', 'jev', 'warn' or 'dim'."""
    kind, out = item["kind"], []
    if kind == "attempt":
        ok = item["status"] == "success"
        counts = f"{item['passed']}/{item['total']} tests passed, " if item.get("total") else ""
        out.append(("good" if ok else "bad",
                    f"ATTEMPT {item['attempt']} with {item['model']}: "
                    f"{STATUS_PLAIN.get(item['status'], item['status'])} ({counts}${item['cost_usd']:.4f})"))
        if not ok and item.get("summary"):
            head, _, rest = item["summary"].partition(". ")
            parts = rest.split(" | ") if rest else []
            visible = [p for p in parts if not p.startswith("[acceptance]")]
            hidden = len(parts) - len(visible)
            if visible or hidden:
                for p in visible[:2]:
                    out.append(("dim", f"   failing test: {p[:150]}"))
                if hidden:
                    out.append(("dim", f"   + {hidden} hidden test(s) failed (details withheld from the agent)"))
            else:
                out.append(("dim", f"   output: {item['summary'][:150]}"))
        for f in item.get("injected_faults", []):
            kind_, _, what = f.partition(":")
            out.append(("warn", "   injected on purpose: "
                        + (f"{what} was quietly edited while the agent worked" if kind_ == "corrupt_file" else f)))
    elif kind == "jev":
        src = "LIVE" if item["source"] == "typesafe" else "MOCK, not real Jev"
        out.append(("jev", f"ASK JEV ({src}, {item['latency_s'] * 1000:.0f} ms, ${item['cost_usd']:.5f})"))
        if jev_state:
            damaged = jev_state.get("files_damaged_since_last_good_checkpoint") or []
            out.append(("dim", f"   Jev sees: failure={jev_state.get('latest_failure_type')}, "
                               f"files changed that the agent may not touch={', '.join(damaged) or 'none'}, "
                               f"budget left=${jev_state.get('remaining_budget_usd', 0):.4f}"))
        probs = "  ".join(f"{a} {p:.2f}" for a, p in sorted(item["probabilities"].items(), key=lambda kv: -kv[1]))
        out.append(("jev", f"   Q1 what should we do?   {probs}"))
        out.append(("jev", f"   Q2 why did it fail?     {item['failure_type']}"))
        if item.get("retry_would_help") is not None:
            out.append(("jev", f"   Q3 will a retry help?   {item['retry_would_help']:.2f}"))
        if item.get("impossible") is not None:
            out.append(("jev", f"   Q4 is it impossible?    {item['impossible']:.2f}"))
    elif kind == "decision":
        who = SOURCE_PLAIN.get(item["proposal_source"], item["proposal_source"])
        if item["overridden"]:
            out.append(("warn", f"DECIDE: {who} proposed {item['proposed']}; budget policy OVERRODE it -> "
                                f"{item['action']} ({item['policy_reason']})"))
        else:
            out.append(("", f"DECIDE: {who} proposed {item['proposed']}; budget policy approved "
                            f"(est ${item['est_cost_usd']:.4f}, ${item['remaining_usd']:.4f} left)"))
        if item.get("rationale"):
            out.append(("dim", f"   reason: {item['rationale'][:160]}"))
    elif kind == "action":
        out.append(("", f"DO: {ACTION_PLAIN.get(item['action'], item['action'])} -> {item['detail']}"))
    return out


_STYLE = {"good": ("green", "bold"), "bad": ("red",), "jev": ("cyan",), "warn": ("yellow",), "dim": ("dim",),
          "bold": ("bold",), "": ()}


def styled(style: str, text: str) -> str:
    return c(text, *_STYLE[style])


def printer(prefix: str = ""):
    """Return an ``on_item(run, item)`` callback for ``RecoveryRun.run`` that prints each step live."""
    def on_item(run, item: dict) -> None:
        state = None
        if item["kind"] == "jev":
            seen = [e.detail.get("state", {}) for e in run.rc.tracker.events if e.kind == "jev_decision"]
            state = seen[-1] if seen else None
        for style, text in describe(item, state):
            print(f"{prefix}{c(text, *_STYLE[style])}", flush=True)
    return on_item
