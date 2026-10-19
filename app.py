"""RecoverIQ dashboard — run:  streamlit run app.py"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from agent import list_tasks
from benchmark import aggregate
from config import RESULTS_DIR, RUNS_DIR, Budget, Settings
from engine import RecoveryRun, scripted_human
from strategies import STRATEGY_NAMES, make_strategy

st.set_page_config(page_title="RecoverIQ", page_icon="🛟", layout="wide")

# Categorical slots 1-3 of the validated reference palette; color follows the strategy, never rank.
COLORS = {"recoveriq": "#2a78d6", "rule_based": "#eb6834", "fixed_retry": "#1baf7a", "recoveriq_raw": "#eda100"}
LABELS = {"recoveriq": "RecoverIQ (Jev + gate)", "rule_based": "Rule-based", "fixed_retry": "Fixed retry",
          "recoveriq_raw": "Jev only (no gate)"}
ACTION_ICONS = {"retry": "🔁", "switch_model": "⬆️", "restore_checkpoint": "⏪", "human_escalation": "🙋",
                "terminate": "⛔"}
STATUS_ICONS = {"success": "✅", "llm_error": "🌩️", "output_truncated": "✂️", "malformed_output": "🧩",
                "collection_error": "💥", "test_failure": "❌", "acceptance_failure": "🔒", "timeout": "⏱️"}

st.markdown("""
<style>
.badge {display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.8rem;font-weight:600;margin-right:6px}
.live {background:#1baf7a22;color:inherit;border:1px solid #1baf7a}
.sim {background:#eda10022;color:inherit;border:1px solid #eda100}
</style>""", unsafe_allow_html=True)


def badge(text: str, live: bool) -> str:
    return f'<span class="badge {"live" if live else "sim"}">{"● " if live else "◌ "}{text}</span>'


settings = Settings()
tasks = {t.id: t for t in list_tasks()}

# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🛟 RecoverIQ")
    st.caption("Cost-aware recovery for AI coding agents, guided by TypeSafe Jev.")
    st.markdown(badge("LLM: LIVE Anthropic" if settings.llm_is_live else "LLM: SIMULATED", settings.llm_is_live)
                + "<br>" + badge("Jev: LIVE TypeSafe" if settings.jev_is_live else "Jev: MOCK heuristic",
                                 settings.jev_is_live), unsafe_allow_html=True)
    if not settings.llm_is_live or not settings.jev_is_live:
        st.caption("Simulated/mock values are illustrative, not measurements. Set RECOVERIQ_LLM_MODE=live and "
                   "RECOVERIQ_JEV_MODE=live in .env for real API calls.")
    task_id = st.selectbox("Task & failure scenario", list(tasks),
                           format_func=lambda t: f"{t} · {tasks[t].scenario}")
    strategy_name = st.selectbox("Recovery strategy", STRATEGY_NAMES, index=3, format_func=LABELS.get)
    with st.expander("Budget limits"):
        max_cost = st.number_input("Max cost per task (USD)", 0.001, 5.0, Budget.max_cost_usd, 0.01, format="%.3f")
        max_attempts = st.slider("Max attempts", 1, 10, Budget.max_attempts)
        human_ok = st.checkbox("Human available for escalation", True)
    budget = Budget(max_attempts=max_attempts, max_cost_usd=max_cost)
    start = st.button("▶ Run agent", type="primary", width="stretch")

task = tasks[task_id]

tab_race, tab_run, tab_compare, tab_bench = st.tabs(["🏁 Live race", "Live run", "Side-by-side on this task", "Benchmark results"])


# ----------------------------------------------------------------------------- live run
def render_trace(container, trace: list[dict]) -> None:
    with container.container():
        for item in trace:
            if item["kind"] == "attempt":
                icon = STATUS_ICONS.get(item["status"], "•")
                tag = "measured" if item["measured"] else ("injected fault" if item["source"] == "injected" else "simulated")
                st.markdown(f"**{icon} Attempt {item['attempt']}** · `{item['model']}` · **{item['status']}** · "
                            f"${item['cost_usd']:.5f} *({tag})*")
                st.caption(item["summary"][:300] + (f"  ·  injected: {', '.join(item['injected_faults'])}"
                                                    if item["injected_faults"] else ""))
            elif item["kind"] == "jev":
                conf = f"{item['confidence']:.2f}" if item["confidence"] is not None else "n/a"
                src = "LIVE Jev" if item["source"] == "typesafe" else "MOCK (not Jev)"
                st.info(f"🧠 **Jev recommendation [{src}]**: `{item['action']}` · confidence {conf} · "
                        f"failure type *{item['failure_type']}* · {item['latency_s'] * 1000:.0f} ms")
            elif item["kind"] == "decision":
                verdict = "⚠️ policy override" if item["overridden"] else "✔ accepted"
                st.markdown(f"&nbsp;&nbsp;↳ proposed `{item['proposed']}` by *{item['proposal_source']}* → "
                            f"**{ACTION_ICONS.get(item['action'], '')} {item['action']}** ({verdict}) · "
                            f"est. ${item['est_cost_usd']:.5f} · remaining ${item['remaining_usd']:.5f}")
                st.caption(f"{item['rationale']} — {item['policy_reason']}")
            elif item["kind"] == "action":
                st.markdown(f"&nbsp;&nbsp;{ACTION_ICONS.get(item['action'], '•')} *{item['detail']}*")


def burn_chart(run: RecoveryRun) -> alt.Chart | None:
    rows, spent = [{"step": 0, "event": "start", "remaining": run.rc.budget.max_cost_usd}], 0.0
    for i, e in enumerate((e for e in run.rc.tracker.events if e.kind in ("llm_attempt", "jev_decision")), 1):
        spent += e.cost_usd
        rows.append({"step": i, "event": f"{e.kind} ({e.model})", "remaining": run.rc.budget.max_cost_usd - spent})
    df = pd.DataFrame(rows)
    line = alt.Chart(df).mark_line(strokeWidth=2, color=COLORS[run.rc.strategy.name], point=alt.OverlayMarkDef(size=64)).encode(
        x=alt.X("step:O", title="Billed call"), y=alt.Y("remaining:Q", title="Remaining budget (USD)", scale=alt.Scale(zero=True)),
        tooltip=["event", alt.Tooltip("remaining:Q", format="$.5f")])
    return line.properties(height=220)


with tab_run:
    st.subheader(f"{task.title}")
    st.caption(f"**Scenario — {task.scenario}:** {task.scenario_note}")
    if start:
        st.session_state.run = RecoveryRun(task, make_strategy(strategy_name, settings.jev_mode, settings.jev_model),
                                           settings, budget, run_root=RUNS_DIR / "dashboard", human_available=human_ok)
        st.session_state.resume = None
        st.session_state.started = False
    run: RecoveryRun | None = st.session_state.get("run")
    if run is None:
        st.write("Pick a task and strategy, then press **Run agent**.")
    else:
        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"#### Execution trace · {LABELS[run.rc.strategy.name]} on `{run.rc.task.id}`")
            trace_box = st.empty()
            if not st.session_state.started or st.session_state.resume is not None:
                resume = st.session_state.resume
                st.session_state.started, st.session_state.resume = True, None
                with st.spinner("Agent running…"):
                    for _ in run.stream(resume_value=resume):
                        render_trace(trace_box, run.state.get("trace", []))
            render_trace(trace_box, run.state.get("trace", []))
            payload = run.pending_interrupt()
            if payload:
                st.warning(f"🙋 **Human escalation — execution paused.** {payload['question']}\n\n"
                           f"Last failure: {payload['last_failure']}")
                hint = st.text_area("Your guidance", value="", placeholder=run.rc.task.human_hint)
                c1, c2 = st.columns(2)
                if c1.button("Resume with guidance", type="primary"):
                    st.session_state.resume = hint or run.rc.task.human_hint
                    st.rerun()
                if c2.button("Resume with no guidance"):
                    st.session_state.resume = ""
                    st.rerun()
        with right:
            s = run.state
            status = s.get("status", "running")
            if payload:
                status = "paused for human"
            t = run.rc.tracker
            st.markdown(f"#### Outcome: {'✅ VERIFIED SUCCESS' if status == 'success' else status.upper()}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Spent", f"${t.spent_usd:.5f}")
            m2.metric("Remaining", f"${t.remaining_usd:.5f}")
            m3.metric("Attempts", s.get("attempt", 0))
            st.caption("Costs are " + ("**measured** from API usage." if t.all_measured() else
                                       "**simulated/estimated** — not real API measurements."))
            chart = burn_chart(run)
            st.altair_chart(chart, width="stretch")
            usage = pd.DataFrame([{"model": e.model, "kind": e.kind, "in_tok": e.input_tokens, "out_tok": e.output_tokens,
                                   "cost_usd": round(e.cost_usd, 6), "measured": e.measured, "source": e.source}
                                  for e in t.events if e.kind in ("llm_attempt", "jev_decision")])
            if not usage.empty:
                st.markdown("**Model usage & cost**")
                st.dataframe(usage.groupby(["model", "kind", "measured", "source"], as_index=False).sum(),
                             hide_index=True, width="stretch")
            jev = [x for x in s.get("trace", []) if x["kind"] == "jev"]
            if jev:
                last = jev[-1]
                st.markdown("**Latest Jev action distribution** " +
                            ("(LIVE)" if last["source"] == "typesafe" else "(MOCK — not Jev)"))
                pdf = pd.DataFrame([{"action": k, "p": v} for k, v in last["probabilities"].items()])
                st.altair_chart(alt.Chart(pdf).mark_bar(cornerRadiusEnd=4, color=COLORS["recoveriq"], height=14).encode(
                    y=alt.Y("action:N", sort="-x", title=None), x=alt.X("p:Q", title="probability", scale=alt.Scale(domain=[0, 1])),
                    tooltip=["action", alt.Tooltip("p:Q", format=".3f")]).properties(height=150), width="stretch")


# ----------------------------------------------------------------------------- comparison charts
def metric_bars(df: pd.DataFrame, field: str, title: str, fmt: str) -> alt.Chart:
    base = alt.Chart(df).encode(
        y=alt.Y("label:N", title=None, sort=[LABELS[s] for s in STRATEGY_NAMES]),
        x=alt.X(f"{field}:Q", title=title, scale=alt.Scale(zero=True)),
        color=alt.Color("label:N", scale=alt.Scale(domain=[LABELS[s] for s in COLORS], range=list(COLORS.values())),
                        legend=None),
        tooltip=["label", alt.Tooltip(f"{field}:Q", format=fmt)])
    bars = base.mark_bar(cornerRadiusEnd=4, height=18)
    text = base.mark_text(align="left", dx=4).encode(text=alt.Text(f"{field}:Q", format=fmt), color=alt.value("gray"))
    return (bars + text).properties(height=160, title=title)


def comparison_charts(metrics: dict, integrity: dict | None = None) -> None:
    """Bars per strategy. With an integrity audit, rates use *clean* successes (no gaming, no damage)."""
    rows = []
    for s, m in metrics.items():
        row = {"strategy": s, "label": LABELS.get(s, s), **m}
        if integrity and s in integrity:
            i = integrity[s]
            row.update(clean_successes=i["clean_successes"], clean_rate=i["clean_successes"] / m["runs"],
                       clean_per_dollar=i["clean_successes_per_dollar"], gamed=i["successes_with_gaming_signals"],
                       damaged=i["successes_with_damaged_workspace"])
        rows.append(row)
    df = pd.DataFrame(rows)
    clean = integrity is not None and "clean_rate" in df
    c1, c2, c3 = st.columns(3)
    c1.altair_chart(metric_bars(df, "clean_rate" if clean else "completion_rate",
                                "Clean completion rate" if clean else "Verified completion rate", ".0%"), width="stretch")
    c2.altair_chart(metric_bars(df, "total_cost_usd", "Total API cost (USD)", "$.3f"), width="stretch")
    c3.altair_chart(metric_bars(df.fillna(0), "clean_per_dollar" if clean else "successes_per_dollar",
                                "Clean successes per $" if clean else "Verified successes per $", ",.1f"), width="stretch")
    if clean:
        st.caption("**Clean** = all tests pass (visible + hidden) AND no helper file left damaged AND no test-gaming "
                   "signals (e.g. overriding `__eq__`). See `scripts/integrity_audit.py`.")
    cols = ["label", "runs", "verified_successes", "clean_successes", "gamed", "damaged", "completion_rate",
            "total_cost_usd", "avg_cost_per_success_usd",
            "successes_per_dollar", "successes_per_dollar_incl_human", "avg_attempts", "human_escalations",
            "budget_violations", "policy_overrides", "avg_latency_s", "p95_latency_s", "all_measured"]
    st.dataframe(df[[c for c in cols if c in df]], hide_index=True, width="stretch")


with tab_compare:
    st.subheader(f"All three strategies on `{task.id}` with the same budget")
    st.caption("Uses the scripted human (replies with the task's documented hint) so runs are unattended.")
    if st.button("Run side-by-side comparison"):
        rows, traces = [], {}
        prog = st.progress(0.0)
        for i, name in enumerate(STRATEGY_NAMES):
            r = RecoveryRun(task, make_strategy(name, settings.jev_mode, settings.jev_model), settings, budget,
                            run_root=RUNS_DIR / "dashboard-compare", human_available=human_ok)
            r.run(human=scripted_human(task))
            rows.append(r.summary())
            traces[name] = r.state.get("trace", [])
            prog.progress((i + 1) / len(STRATEGY_NAMES))
        st.session_state.compare = (task.id, rows, traces)
    if st.session_state.get("compare") and st.session_state.compare[0] == task.id:
        _, rows, traces = st.session_state.compare
        comparison_charts({r["strategy"]: aggregate([r], settings.human_cost_usd) for r in rows})
        cols = st.columns(len(STRATEGY_NAMES))
        for col, name in zip(cols, STRATEGY_NAMES):
            r = next(x for x in rows if x["strategy"] == name)
            col.markdown(f"**{LABELS[name]}** — {r['outcome']} · {r['attempts']} attempts · ${r['total_cost_usd']:.5f}")
            col.caption(" → ".join(ACTION_ICONS.get(a, a) + " " + a for a in r["actions"]) or "no recovery needed")
            render_trace(col, traces[name])


# ----------------------------------------------------------------------------- saved benchmarks
with tab_bench:
    def _rank(p: Path):
        m = json.loads((p.parent / "manifest.json").read_text())
        return (m["llm_mode"] == "live" and m["jev_mode"] == "live", p.stat().st_mtime)
    dirs = sorted(RESULTS_DIR.glob("*/metrics.json"), key=_rank, reverse=True)
    if not dirs:
        st.write("No benchmark results yet. Run `python benchmark.py --repeats 3`.")
    else:
        choice = st.selectbox("Benchmark run", dirs, format_func=lambda p: p.parent.name + ("" if _rank(p)[0] else "  (SIMULATED)"))
        manifest = json.loads((choice.parent / "manifest.json").read_text())
        metrics = json.loads(choice.read_text())
        live = manifest["llm_mode"] == "live" and manifest["jev_mode"] == "live"
        (st.success if live else st.warning)(
            "  \n".join(f"**{k}**: {v}" for k, v in manifest["provenance"].items()))
        st.caption(f"{manifest['repeats']} repeats × {len(manifest['tasks'])} tasks × {len(manifest['strategies'])} "
                   f"strategies · budget ${manifest['budget']['max_cost_usd']}/task, {manifest['budget']['max_attempts']} attempts"
                   f" · commit {manifest.get('git_commit')}")
        integ_path = choice.parent / "integrity.json"
        comparison_charts(metrics["by_strategy"], json.loads(integ_path.read_text()) if integ_path.exists() else None)
        st.markdown("**By scenario**")
        rows = [{"strategy": LABELS.get(s, s), "scenario": sc, **{k: m[k] for k in
                ("verified_successes", "runs", "total_cost_usd", "successes_per_dollar", "avg_attempts", "human_escalations")}}
                for s, by in metrics["by_strategy_scenario"].items() for sc, m in by.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        runs_csv = choice.parent / "runs.csv"
        if runs_csv.exists():
            with st.expander("Raw runs"):
                st.dataframe(pd.read_csv(runs_csv), hide_index=True, width="stretch")


# ----------------------------------------------------------------------------- live race
RACERS = ("fixed_retry", "rule_based", "recoveriq")


def render_racer(box, name: str, run: RecoveryRun, finished_s: float | None, elapsed_s: float, error: str | None) -> None:
    """Draw one racer from its cost ledger (append-only, safe to read while the run's thread works)."""
    events = list(run.rc.tracker.events)
    attempts = [e for e in events if e.kind == "llm_attempt"]
    spent = sum(e.cost_usd for e in events)
    status = (run.state.get("status", "running") if finished_s is not None else "running")
    with box.container(border=True):
        st.markdown(f"<span style='color:{COLORS[name]};font-size:1.3rem'>●</span> **{LABELS[name]}**",
                    unsafe_allow_html=True)
        if error:
            st.error(f"crashed: {error}")
        elif finished_s is None:
            st.markdown(f"### ⏳ working… {elapsed_s:.0f}s")
        elif status == "success":
            st.markdown(f"### ✅ SOLVED in {finished_s:.0f}s")
        else:
            st.markdown(f"### ❌ GAVE UP after {finished_s:.0f}s")
        m1, m2 = st.columns(2)
        m1.metric("Attempts", len(attempts))
        m2.metric("Spent", f"${spent:.4f}")
        st.progress(min(spent / run.rc.budget.max_cost_usd, 1.0), text=f"budget used of ${run.rc.budget.max_cost_usd:.2f}")
        for e in events[-7:]:
            if e.kind == "llm_attempt":
                st.caption(f"{STATUS_ICONS.get(e.outcome, '•')} attempt {e.attempt} · `{e.model}` · {e.outcome}")
            elif e.kind == "jev_decision":
                conf = e.detail.get("confidence")
                st.caption(f"🧠 Jev → **{e.recovery_action}**" + (f" ({conf:.2f})" if conf is not None else "")
                           + f" · {e.detail.get('failure_type')}")
            elif e.kind == "recovery_action":
                flag = " (override)" if e.outcome == "override" else ""
                st.caption(f"{ACTION_ICONS.get(e.recovery_action, '•')} {e.recovery_action}{flag}")


with tab_race:
    st.subheader(f"🏁 Live race on `{task.id}`")
    st.caption(f"**{task.scenario}:** {task.scenario_note}")
    st.caption("Same task, same budget, all strategies at once. Each press makes real API calls when the "
               "badges are LIVE (about $0.05–0.25 per race). Human escalations get the simulated reply.")
    if st.button("🏁 Start race", type="primary"):
        runs = {n: RecoveryRun(task, make_strategy(n, settings.jev_mode, settings.jev_model), settings, budget,
                               run_root=RUNS_DIR / "race", human_available=human_ok) for n in RACERS}
        errors: dict[str, str] = {}

        def _go(name: str, run: RecoveryRun) -> None:
            try:
                run.run(human=scripted_human(task))
            except Exception as e:  # shown in the racer's card; never hidden
                errors[name] = f"{type(e).__name__}: {e}"

        threads = {n: threading.Thread(target=_go, args=(n, r), daemon=True) for n, r in runs.items()}
        start = time.perf_counter()
        for t in threads.values():
            t.start()
        boxes = dict(zip(RACERS, (c.empty() for c in st.columns(len(RACERS)))))
        finished: dict[str, float] = {}
        while True:
            now = time.perf_counter() - start
            for n, r in runs.items():
                if not threads[n].is_alive() and n not in finished:
                    finished[n] = now
                render_racer(boxes[n], n, r, finished.get(n), now, errors.get(n))
            if len(finished) == len(runs):
                break
            time.sleep(0.5)
        st.session_state.race = (task.id, runs, finished, errors)
        st.rerun()
    if st.session_state.get("race") and st.session_state.race[0] == task.id:
        _, runs, finished, errors = st.session_state.race
        for box, n in zip((c.empty() for c in st.columns(len(RACERS))), RACERS):
            render_racer(box, n, runs[n], finished[n], finished[n], errors.get(n))
        winners = [n for n in RACERS if runs[n].state.get("status") == "success"]
        if winners:
            best = min(winners, key=lambda n: runs[n].rc.tracker.spent_usd)
            st.success(f"Cheapest verified fix: **{LABELS[best]}** at ${runs[best].rc.tracker.spent_usd:.4f}"
                       + ("" if runs[best].rc.tracker.all_measured() else "  (simulated costs)"))
