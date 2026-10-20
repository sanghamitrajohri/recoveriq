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
            out.append(("dim", f"   test output: {item['summary'][:150]}"))
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


_STYLE = {"good": ("green", "bold"), "bad": ("red",), "jev": ("cyan",), "warn": ("yellow",), "dim": ("dim",), "": ()}


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
