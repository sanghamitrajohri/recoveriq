"""Filesystem checkpoints of an agent workspace.

Checkpoints are full directory snapshots stored *outside* the workspace (so sandboxed code
cannot tamper with them) together with a SHA-256 manifest. Restoring replaces the workspace
contents and then re-hashes it to prove the restored state matches the snapshot byte for byte.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

IGNORED = {".tmp", "__pycache__", ".junit.xml", ".pytest_cache", "pytest.ini"}


def _files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and not any(part in IGNORED for part in p.relative_to(root).parts)
    )


def manifest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in _files(root)}


@dataclass
class Checkpoint:
    checkpoint_id: str
    label: str
    known_good: bool
    created_at: float
    passed_tests: int
    manifest: dict[str, str]


class CheckpointError(RuntimeError):
    pass


class CheckpointManager:
    def __init__(self, workspace: Path, store: Path) -> None:
        self.workspace = workspace
        self.store = store
        self.store.mkdir(parents=True, exist_ok=True)
        self._checkpoints: list[Checkpoint] = []

    @property
    def checkpoints(self) -> list[Checkpoint]:
        return list(self._checkpoints)

    def save(self, label: str, known_good: bool, passed_tests: int = 0) -> Checkpoint:
        cp_id = f"cp{len(self._checkpoints):02d}"
        dest = self.store / cp_id
        shutil.copytree(self.workspace, dest, ignore=shutil.ignore_patterns(*IGNORED))
        cp = Checkpoint(cp_id, label, known_good, time.time(), passed_tests, manifest(dest))
        (self.store / f"{cp_id}.json").write_text(json.dumps(asdict(cp), indent=2))
        self._checkpoints.append(cp)
        return cp

    def latest_known_good(self) -> Checkpoint | None:
        good = [c for c in self._checkpoints if c.known_good]
        return good[-1] if good else None

    def best_known_good(self) -> Checkpoint | None:
        """Known-good checkpoint with the most passing tests (latest wins ties)."""
        good = [c for c in self._checkpoints if c.known_good]
        return max(reversed(good), key=lambda c: c.passed_tests) if good else None

    def diverged_files(self, cp: Checkpoint) -> list[str]:
        """Files whose contents differ between the workspace and ``cp`` (incl. added/removed)."""
        current = manifest(self.workspace)
        keys = set(current) | set(cp.manifest)
        return sorted(k for k in keys if current.get(k) != cp.manifest.get(k))

    def restore(self, cp: Checkpoint | None = None) -> Checkpoint:
        cp = cp or self.best_known_good()
        if cp is None:
            raise CheckpointError("no known-good checkpoint available")
        src = self.store / cp.checkpoint_id
        for child in self.workspace.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        shutil.copytree(src, self.workspace, dirs_exist_ok=True)
        restored = manifest(self.workspace)
        if restored != cp.manifest:
            raise CheckpointError(f"restore verification failed for {cp.checkpoint_id}")
        return cp
