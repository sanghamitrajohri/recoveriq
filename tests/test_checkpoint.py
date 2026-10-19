import pytest

from checkpoint_manager import CheckpointError, CheckpointManager, manifest


def test_restore_is_byte_identical(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("A = 1\n")
    (ws / "b.py").write_text("B = 2\n")
    cpm = CheckpointManager(ws, tmp_path / "store")
    cp = cpm.save("initial", known_good=True)
    (ws / "a.py").write_text("A = (\n")          # corrupt
    (ws / "b.py").unlink()                        # delete
    (ws / "junk.py").write_text("x")              # add
    assert set(cpm.diverged_files(cp)) == {"a.py", "b.py", "junk.py"}
    cpm.restore()
    assert manifest(ws) == cp.manifest
    assert (ws / "a.py").read_text() == "A = 1\n" and not (ws / "junk.py").exists()


def test_best_known_good_prefers_most_passing(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "f.py").write_text("v0")
    cpm = CheckpointManager(ws, tmp_path / "store")
    cpm.save("initial", True, passed_tests=0)
    (ws / "f.py").write_text("v1")
    cpm.save("better", True, passed_tests=3)
    (ws / "f.py").write_text("v2")
    cpm.save("bad", False, passed_tests=9)
    assert cpm.best_known_good().label == "better"
    cpm.restore()
    assert (ws / "f.py").read_text() == "v1"


def test_restore_without_checkpoint_raises(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(CheckpointError):
        CheckpointManager(ws, tmp_path / "store").restore()


def test_tampered_snapshot_fails_verification(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("A = 1\n")
    cpm = CheckpointManager(ws, tmp_path / "store")
    cp = cpm.save("initial", True)
    (tmp_path / "store" / cp.checkpoint_id / "a.py").write_text("tampered")
    with pytest.raises(CheckpointError):
        cpm.restore()
