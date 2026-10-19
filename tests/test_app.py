"""Headless Streamlit smoke tests (offline modes)."""
import pytest
from streamlit.testing.v1 import AppTest

from config import ROOT


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("RECOVERIQ_LLM_MODE", "scripted")
    monkeypatch.setenv("RECOVERIQ_JEV_MODE", "mock")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_run_shows_trace_and_success(app):
    app.sidebar.selectbox[0].select_index(2)
    app.sidebar.button[0].click().run()
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "switch_model" in text and "VERIFIED SUCCESS" in text
    assert any("MOCK" in i.value for i in app.info)


def test_human_escalation_pause_and_resume(app):
    app.sidebar.selectbox[0].select_index(3)
    app.sidebar.button[0].click().run()
    assert any("execution paused" in w.value for w in app.warning)
    app.text_area[0].input("Use Decimal with ROUND_HALF_UP to cents and return a Decimal.")
    next(b for b in app.button if b.label == "Resume with guidance").click().run()
    assert not app.exception
    assert "VERIFIED SUCCESS" in " ".join(m.value for m in app.markdown)


def test_live_race_runs_all_strategies(app):
    # t3 offline: fixed retry gives up (truncation); rule-based and RecoverIQ switch model and solve it.
    app.sidebar.selectbox[0].select_index(2)
    next(b for b in app.button if b.label == "🏁 Start race").click().run(timeout=120)
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "SOLVED" in text and "GAVE UP" in text
    assert any("Cheapest verified fix" in s.value for s in app.success)
