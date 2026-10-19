"""Run pytest against agent-modified code inside a restricted sandbox.

On macOS the test process runs under ``sandbox-exec`` with a profile that
  * denies all network access,
  * denies reading file contents anywhere under $HOME except the workspace and the venv
    (so the project's .env, ~/.ssh, etc. are unreadable),
  * denies writes everywhere except the workspace,
and with a scrubbed environment (no API keys), CPU/file-size rlimits and a wall-clock timeout.
If sandbox-exec is unavailable the run still happens but is recorded as ``isolation="reduced"``.
"""
from __future__ import annotations

import os
import resource
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
ACCEPTANCE_PREFIX = "test_acceptance_"
REPORT_NAME = ".junit.xml"


@dataclass
class TestFailure:
    test: str
    file: str
    message: str
    acceptance: bool


@dataclass
class TestReport:
    exit_code: int
    passed: int
    failed: int
    errors: int
    total: int
    duration_s: float
    timed_out: bool
    collection_error: bool
    isolation: str
    failures: list[TestFailure] = field(default_factory=list)
    output_tail: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and self.total > 0 and not self.failures

    @property
    def visible_failures(self) -> list[TestFailure]:
        return [f for f in self.failures if not f.acceptance]

    @property
    def acceptance_failures(self) -> list[TestFailure]:
        return [f for f in self.failures if f.acceptance]

    def to_dict(self) -> dict:
        return asdict(self)


def _profile(workspace: Path) -> str:
    home = os.path.realpath(Path.home())
    venv = os.path.realpath(sys.prefix)
    ws = os.path.realpath(workspace)
    return f"""(version 1)
(allow default)
(deny network*)
(deny file-read-data (subpath "{home}"))
(allow file-read-data (subpath "{venv}") (subpath "{ws}"))
(deny file-write*)
(allow file-write* (subpath "{ws}") (literal "/dev/null"))
"""


def sandbox_available() -> bool:
    return sys.platform == "darwin" and Path(SANDBOX_EXEC).exists()


def _limits(cpu_seconds: int):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
    return apply


def build_command(workspace: Path, argv: list[str]) -> tuple[list[str], str]:
    """Wrap ``argv`` in the sandbox; returns (command, isolation level)."""
    if sandbox_available():
        return [SANDBOX_EXEC, "-p", _profile(workspace), *argv], "sandbox-exec"
    return argv, "reduced"


def run_sandboxed(workspace: Path, argv: list[str], timeout_s: float) -> tuple[int, str, bool, str]:
    """Run ``argv`` in ``workspace`` under the sandbox. Returns (exit, output, timed_out, isolation)."""
    workspace = Path(os.path.realpath(workspace))
    tmp = workspace / ".tmp"
    tmp.mkdir(exist_ok=True)
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(workspace),
        "TMPDIR": str(tmp),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "LANG": "en_US.UTF-8",
    }
    cmd, isolation = build_command(workspace, argv)
    proc = subprocess.Popen(
        cmd, cwd=workspace, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True, preexec_fn=_limits(int(timeout_s) + 1),
    )
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        return proc.returncode, out.decode(errors="replace"), False, isolation
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return -9, out.decode(errors="replace"), True, isolation


def _parse_junit(path: Path) -> tuple[int, int, int, list[TestFailure], bool]:
    if not path.exists():
        return 0, 0, 0, [], True
    root = ET.parse(path).getroot()
    passed = failed = errors = 0
    failures: list[TestFailure] = []
    collection_error = False
    for case in root.iter("testcase"):
        name = case.get("name", "")
        classname = case.get("classname", "")
        file = (case.get("file") or classname.split(".")[0] + ".py") if classname else name
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is None:
            if case.find("skipped") is None:
                passed += 1
            continue
        message = (problem.get("message") or "") + "\n" + (problem.text or "")
        if problem.tag == "error":
            errors += 1
            if not classname or "collection" in message.lower():
                collection_error = True
        else:
            failed += 1
        failures.append(TestFailure(name, file, message.strip()[-1500:],
                                    acceptance=ACCEPTANCE_PREFIX in file or ACCEPTANCE_PREFIX in classname))
    return passed, failed, errors, failures, collection_error


def run_tests(workspace: Path, timeout_s: float = 30.0) -> TestReport:
    """Run the full test suite (visible + acceptance) for a workspace inside the sandbox."""
    workspace = Path(os.path.realpath(workspace))
    report_path = workspace / REPORT_NAME
    report_path.unlink(missing_ok=True)
    (workspace / "pytest.ini").write_text("[pytest]\n")
    shutil.rmtree(workspace / "__pycache__", ignore_errors=True)
    argv = [sys.executable, "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider",
            f"--junitxml={report_path}", "-o", "junit_family=xunit1", "--tb=short", "."]
    # -I (isolated mode) drops the cwd from sys.path; pytest's rootdir insertion restores it.
    start = time.perf_counter()
    code, output, timed_out, isolation = run_sandboxed(workspace, argv, timeout_s)
    duration = time.perf_counter() - start
    passed, failed, errors, failures, collection_error = _parse_junit(report_path)
    if code == 2 or (code not in (0, 1) and not timed_out):
        collection_error = True
    if timed_out:
        failures.append(TestFailure("<timeout>", "", f"test run exceeded {timeout_s}s", False))
    if collection_error and not failures:
        failures.append(TestFailure("<collection>", "", output[-1500:], False))
    return TestReport(
        exit_code=code, passed=passed, failed=failed, errors=errors, total=passed + failed + errors,
        duration_s=round(duration, 3), timed_out=timed_out, collection_error=collection_error,
        isolation=isolation, failures=failures, output_tail=output[-3000:],
    )
