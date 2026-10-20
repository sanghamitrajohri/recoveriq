"""Headless Streamlit smoke tests (offline modes)."""
import pytest
from streamlit.testing.v1 import AppTest

from config import ROOT


def pick_task(app, task_id):
    box = app.sidebar.selectbox[0]
    box.select_index(next(i for i, o in enumerate(box.options) if o.startswith(task_id)))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("RECOVERIQ_LLM_MODE", "scripted")
    monkeypatch.setenv("RECOVERIQ_JEV_MODE", "mock")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_run_shows_trace_and_success(app):
    pick_task(app, "t3_inventory")
    app.sidebar.button[0].click().run()
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "switch_model" in text and "VERIFIED SUCCESS" in text
    assert any("MOCK" in i.value for i in app.info)


def test_human_escalation_pause_and_resume(app):
    pick_task(app, "t4_pricing")
    app.sidebar.button[0].click().run()
    assert any("execution paused" in w.value for w in app.warning)
    app.text_area[0].input("Use Decimal with ROUND_HALF_UP to cents and return a Decimal.")
    next(b for b in app.button if b.label == "Resume with guidance").click().run()
    assert not app.exception
    assert "VERIFIED SUCCESS" in " ".join(m.value for m in app.markdown)


def test_live_race_runs_all_strategies(app):
    # t3 offline: fixed retry gives up (truncation); rule-based and RecoverIQ switch model and solve it.
    pick_task(app, "t3_inventory")
    next(b for b in app.button if b.label == "🏁 Start race").click().run(timeout=120)
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "SOLVED" in text and "GAVE UP" in text
    assert any("Cheapest clean fix" in s.value for s in app.success)


def test_race_flags_cheated_success(tmp_path):
    """A workspace that passes tests by rewriting another file is shown as cheating, not solved."""
    import shutil
    from agent import Task
    from integrity import audit
    t = Task.load("t10_checkout")
    ws = tmp_path / "ws"
    shutil.copytree(t.dir / "workspace", ws)
    (ws / "checkout.py").write_text((ws / "checkout.py").read_text()
                                    + "\nimport pricing_config\npricing_config.TAX_RATE = 0.08\n")
    (ws / "pricing_config.py").write_text(t.fault["content"])
    result = audit(t, ws)
    assert not result["clean"] and "patches_other_modules" in result["gaming"]
    assert result["damaged"] == ["pricing_config.py"]
