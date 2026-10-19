"""The sandbox must block network, secret reads and out-of-workspace writes."""
import sys
from pathlib import Path

import pytest

import sandbox

pytestmark = pytest.mark.skipif(not sandbox.sandbox_available(), reason="requires macOS sandbox-exec")
ROOT = Path(__file__).resolve().parents[1]


def _run(ws: Path, code: str, timeout: float = 20):
    (ws / "probe.py").write_text(code)
    return sandbox.run_sandboxed(ws, [sys.executable, "-I", "probe.py"], timeout)


@pytest.fixture
def ws():
    # Workspace under the project (inside $HOME) to mirror real runs.
    d = ROOT / "runs" / "_pytest_sandbox"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_network_is_blocked(ws):
    code, out, _, iso = _run(ws, "import socket\ns=socket.create_connection(('1.1.1.1', 80), timeout=3)\nprint('CONNECTED')")
    assert iso == "sandbox-exec"
    assert "CONNECTED" not in out and code != 0


def test_cannot_read_secrets_in_home(ws):
    secret = ROOT / ".env.sandbox-test"
    secret.write_text("ANTHROPIC_API_KEY=sk-should-not-leak")
    try:
        code, out, _, _ = _run(ws, f"print(open({str(secret)!r}).read())")
        assert "sk-should-not-leak" not in out and code != 0
    finally:
        secret.unlink()


def test_cannot_write_outside_workspace(ws):
    target = ROOT / "sandbox_escape.txt"
    code, out, _, _ = _run(ws, f"open({str(target)!r}, 'w').write('x')")
    assert code != 0 and not target.exists()


def test_can_write_inside_workspace(ws):
    code, out, _, _ = _run(ws, "open('inside.txt','w').write('ok'); print('WROTE')")
    assert code == 0 and "WROTE" in out


def test_environment_is_scrubbed(ws, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-secret")
    code, out, _, _ = _run(ws, "import os; print(sorted(k for k in os.environ if 'KEY' in k or 'TOKEN' in k))")
    assert "sk-env-secret" not in out and "[]" in out


def test_timeout_kills_runaway_code(ws):
    code, out, timed_out, _ = _run(ws, "while True: pass", timeout=2)
    assert timed_out and code == -9


def test_run_tests_detects_pass_and_fail(tmp_path):
    (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
    (tmp_path / "test_mod.py").write_text("from mod import f\n\ndef test_ok():\n    assert f() == 1\n\ndef test_bad():\n    assert f() == 2\n")
    (tmp_path / "test_acceptance_mod.py").write_text("from mod import f\n\ndef test_acc():\n    assert f() == 3\n")
    r = sandbox.run_tests(tmp_path)
    assert (r.passed, r.failed, r.success) == (1, 2, False)
    assert [f.test for f in r.acceptance_failures] == ["test_acc"]
    assert [f.test for f in r.visible_failures] == ["test_bad"]


def test_run_tests_flags_collection_errors(tmp_path):
    (tmp_path / "test_broken.py").write_text("import does_not_exist\n\ndef test_x():\n    pass\n")
    r = sandbox.run_tests(tmp_path)
    assert r.collection_error and not r.success
