"""Per-event cost and usage ledger, persisted to SQLite and JSONL.

Every row carries ``measured`` (True only when token counts came from a real API response)
and ``source`` (anthropic | typesafe | scripted | mock | injected | policy) so simulated rows
can always be filtered out of reported results.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

EVENT_FIELDS = [
    "run_id", "ts", "strategy", "task_id", "kind", "model", "recovery_action", "attempt",
    "input_tokens", "output_tokens", "cost_usd", "latency_s", "outcome", "remaining_budget_usd",
    "measured", "source", "detail",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, ts REAL, strategy TEXT, task_id TEXT, kind TEXT, model TEXT,
    recovery_action TEXT, attempt INTEGER, input_tokens INTEGER, output_tokens INTEGER,
    cost_usd REAL, latency_s REAL, outcome TEXT, remaining_budget_usd REAL,
    measured INTEGER, source TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, benchmark_id TEXT, strategy TEXT, task_id TEXT, scenario TEXT,
    repeat INTEGER, llm_mode TEXT, jev_mode TEXT, outcome TEXT, verified_success INTEGER,
    total_cost_usd REAL, llm_cost_usd REAL, jev_cost_usd REAL, attempts INTEGER,
    recovery_actions INTEGER, human_escalations INTEGER, budget_violations INTEGER,
    policy_overrides INTEGER, latency_s REAL, all_measured INTEGER, actions TEXT
);
"""


@dataclass
class Event:
    run_id: str
    strategy: str
    task_id: str
    kind: str  # llm_attempt | jev_decision | recovery_action | run_end
    model: str = ""
    recovery_action: str = ""
    attempt: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    outcome: str = ""
    remaining_budget_usd: float = 0.0
    measured: bool = False
    source: str = ""
    detail: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class CostTracker:
    """Tracks spend for one run against its dollar budget."""

    def __init__(self, run_id: str, strategy: str, task_id: str, max_cost_usd: float) -> None:
        self.run_id = run_id
        self.strategy = strategy
        self.task_id = task_id
        self.max_cost_usd = max_cost_usd
        self.events: list[Event] = []

    @property
    def spent_usd(self) -> float:
        return sum(e.cost_usd for e in self.events)

    @property
    def remaining_usd(self) -> float:
        return self.max_cost_usd - self.spent_usd

    def spent_by_kind(self, kind: str) -> float:
        return sum(e.cost_usd for e in self.events if e.kind == kind)

    def record(self, kind: str, **kw) -> Event:
        ev = Event(self.run_id, self.strategy, self.task_id, kind, **kw)
        self.events.append(ev)
        ev.remaining_budget_usd = round(self.remaining_usd, 8)
        return ev

    def all_measured(self) -> bool:
        priced = [e for e in self.events if e.kind in ("llm_attempt", "jev_decision") and e.source != "injected"]
        return bool(priced) and all(e.measured for e in priced)


class Store:
    """SQLite store for events and run summaries, plus an append-only JSONL trace."""

    def __init__(self, db_path: Path, trace_path: Path | None = None) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.trace_path = trace_path

    def write_events(self, events: list[Event]) -> None:
        rows = []
        for e in events:
            d = asdict(e)
            d["measured"] = int(d["measured"])
            d["detail"] = json.dumps(d["detail"], default=str)
            rows.append(tuple(d[f] for f in EVENT_FIELDS))
        self.db.executemany(
            f"INSERT INTO events ({','.join(EVENT_FIELDS)}) VALUES ({','.join('?' * len(EVENT_FIELDS))})", rows)
        self.db.commit()
        if self.trace_path:
            with self.trace_path.open("a") as fh:
                for e in events:
                    fh.write(json.dumps({"type": "event", **asdict(e)}, default=str) + "\n")

    def write_run(self, summary: dict) -> None:
        cols = list(summary)
        self.db.execute(
            f"INSERT OR REPLACE INTO runs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [json.dumps(v) if isinstance(v, (list, dict)) else v for v in summary.values()])
        self.db.commit()
        if self.trace_path:
            with self.trace_path.open("a") as fh:
                fh.write(json.dumps({"type": "run", **summary}, default=str) + "\n")
