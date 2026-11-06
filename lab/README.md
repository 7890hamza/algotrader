# The Lab: two self-improving trading agents made of folders, files and a harness

No paid AI: every "agent" here is a folder of instructions and memory files plus a small
program the harness runs on a timer. It all runs in one capped Docker container on your PC
(1 CPU core, 1 GB) whenever the stack is up.

```
lab/
  harness.py            the loop: every cycle, run each agent's next step
  config.json           cycle length, which agents run, how much CPU
  labkit/               shared tools (data loading, feed updates, files)
  agents/
    researcher/
      AGENT.md          its job and rules (read this first)
      step.py           what it does each cycle
      memory/           what it has tried, its idea queue, lessons (not in git)
      results/          published strategy cards (not in git)
    trader/
      AGENT.md
      step.py
      memory/           positions, journal (not in git)
      results/          daily results, live vs backtest (not in git)
  arena/                status.json and leaderboard.csv (what the app's Arena page will show)
  data/es_m1/           ES 1-minute history 2008-2026 (ES_YYYY.npz) + your feed (FEED_YYYY.npz)
  logs/                 harness.log
```

## Build steps

1. **Foundation (this step):** folders, harness, capped container, 19 years of data, daily
   top-up from your MT5 feed.
2. **Simulator:** fast 1-minute backtests with your indicator code, MES costs and anti-luck gates.
3. **Researcher loop:** combine indicator signals into rules, test, publish what passes, remember what failed.
4. **Trader:** play published strategies forward on unseen data, then on the DEMO account.
5. **Arena page** in the app.

## Controls

- Pause an agent: create an empty file `agents/<name>/PAUSE`. Delete it to resume.
- Run one cycle by hand: `docker compose ... run --rm lab python harness.py --once`.
- The Trader never sends orders to a real account. Demo only, through the MT5 bridge, and
  only after step 4 and your go-ahead.
