"""The Lab's harness: every cycle, run each agent's next step, record how it went, sleep.

An agent is a folder in ``agents/`` with an ``AGENT.md`` (its rules), a ``step.py`` with
``run(ctx) -> str`` (one step; returns a one-line summary) and its ``memory/`` and
``results/``. An empty ``PAUSE`` file in the folder skips it.

    python harness.py          run forever
    python harness.py --once   one cycle, then exit
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import logging.handlers
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

from labkit.files import now_iso, read_json, write_json  # noqa: E402


@dataclass
class Context:
    lab: Path
    agent: Path
    config: dict
    log: logging.Logger

    @property
    def memory(self) -> Path:
        return self.agent / "memory"

    @property
    def results(self) -> Path:
        return self.agent / "results"

    @property
    def data(self) -> Path:
        return self.lab / "data" / "es_m1"


def make_logger(lab: Path) -> logging.Logger:
    log = logging.getLogger("lab")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    (lab / "logs").mkdir(exist_ok=True)
    fh = logging.handlers.RotatingFileHandler(lab / "logs" / "harness.log", maxBytes=2_000_000, backupCount=3)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
    return log


def load_step(agent_dir: Path):
    spec = importlib.util.spec_from_file_location(f"agent_{agent_dir.name}", agent_dir / "step.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)  # fresh each cycle, so edits apply without a restart
    return mod


def run_cycle(lab: Path, config: dict, log: logging.Logger) -> dict:
    status = read_json(lab / "arena" / "status.json", {}) or {}
    for name in config.get("agents", []):
        agent = lab / "agents" / name
        entry = {"last_run": now_iso()}
        if (agent / "PAUSE").exists():
            entry.update(ok=True, summary="paused")
        else:
            started = time.monotonic()
            try:
                summary = load_step(agent).run(Context(lab, agent, config, log))
                entry.update(ok=True, summary=str(summary)[:500])
            except Exception as e:  # one agent failing never stops the other
                entry.update(ok=False, summary=f"{type(e).__name__}: {e}"[:500])
                (agent / "memory").mkdir(exist_ok=True)
                with (agent / "memory" / "errors.log").open("a") as f:
                    f.write(f"{now_iso()}\n{traceback.format_exc()}\n")
            entry["seconds"] = round(time.monotonic() - started, 1)
        status[name] = entry
        log.info("%s: %s", name, entry["summary"])
    status["harness"] = {"last_cycle": now_iso(), "cycle_minutes": config.get("cycle_minutes", 15)}
    write_json(lab / "arena" / "status.json", status)
    return status


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--lab", default=str(LAB))
    args = ap.parse_args()
    lab = Path(args.lab)
    config = read_json(lab / "config.json", {}) or {}
    log = make_logger(lab)
    try:
        os.nice(int(config.get("nice", 10)))  # stay out of the way of the charts and MT5
    except (AttributeError, OSError):
        pass
    log.info("harness starting (agents: %s)", ", ".join(config.get("agents", [])))
    while True:
        run_cycle(lab, read_json(lab / "config.json", config) or config, log)
        if args.once:
            return
        time.sleep(60 * float(config.get("cycle_minutes", 15)))


if __name__ == "__main__":
    main()
