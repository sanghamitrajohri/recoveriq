# Demo day cheat sheet

## Night before (10 min)
- [ ] Laptop charged; notifications off (Focus mode); close Slack/email.
- [ ] `cd ~/Desktop/recoveriq && .venv/bin/python scripts/verify_live.py` prints two `OK` lines.
- [ ] Check credit at platform.claude.com → Billing (keep $5 or more).
- [ ] Do a full dry run with the timer: `docs/DEMO_SCRIPT.md`.

## 30 minutes before
```bash
cd ~/Desktop/recoveriq
.venv/bin/streamlit run app.py
```
- [ ] Browser opens at http://localhost:8501. Zoom to 125% (Cmd +) so the back row can read it.
- [ ] Sidebar badges are **green**: "LLM: LIVE Anthropic" and "Jev: LIVE TypeSafe".
- [ ] Warm-up: pick **t6_wordcount**, press **Run agent** on the Live run tab (seconds, about $0.001).
- [ ] Then set the sidebar to **t7_temperature** and open the **🏁 Live race** tab. That's your starting screen.
- [ ] Open the **Benchmark results** tab once and check that `live-2026-10-19` is selected.

## If something breaks on stage
| Problem | Do this (and say it out loud) |
|---|---|
| Wi-Fi is down or an API errors | Stop Streamlit (Ctrl-C) and run `RECOVERIQ_LLM_MODE=scripted RECOVERIQ_JEV_MODE=mock .venv/bin/streamlit run app.py`. Say: *"Offline mode now, so these numbers are simulated; the real ones are in the benchmark tab."* |
| A run is slow (Opus takes ~20–30 s) | Talk through the Jev box and the probabilities while it runs |
| The race shows a different winner or Jev picks another action | Narrate what happened honestly, then show the benchmark tab: 108 runs matter more than one |
| The page freezes | Refresh the browser tab; the saved benchmark tab still works |
| The laptop dies | Show `docs/SUMMARY.md` on another device |

## Terminal backup demo
```bash
.venv/bin/python scripts/demo.py --task t3_inventory
```

## After the event
- **Rotate both API keys**, since they were pasted into a chat: delete them in console.typesafe.ai/keys and platform.claude.com, create new ones, and update `.env`.
