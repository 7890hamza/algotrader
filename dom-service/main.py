"""Memory DOM service.

* TCP :8060 - NinjaTrader's AlgoTraderDomBridge connects here and streams its DOM and trades.
* HTTP :8030 - ``/ws`` pushes the ladder 4 times a second; ``/events``, ``/stats``, ``/health``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from app.engine import Config, Engine, Event, trading_day
from app.store import Store
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

log = logging.getLogger("dom-service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

FEED_PORT = int(os.environ.get("DOM_FEED_PORT", "8060"))
DB_PATH = os.environ.get("DOM_DB", "/data/dom_memory.sqlite")


class Hub:
    def __init__(self) -> None:
        self.store = Store(DB_PATH)
        self.engine = Engine(
            Config(
                min_size=int(os.environ.get("DOM_MIN_SIZE", "100")),
                factor=float(os.environ.get("DOM_FACTOR", "2.5")),
                hold_ticks=int(os.environ.get("DOM_HOLD_TICKS", "8")),
            ),
            on_event=self._on_event,
        )
        self.feed_at = 0.0  # last message from NinjaTrader (monotonic)
        self.feeds = 0
        self.mem_day = trading_day(int(time.time() * 1000))
        self.mem: dict[float, list[dict[str, Any]]] = defaultdict(list)
        for ev in self.store.day_events(self.mem_day):
            self.mem[ev["price"]].append(ev)
        self._stats: list[dict[str, Any]] = []
        self._stats_at = 0.0

    def _on_event(self, ev: Event, final: bool) -> None:
        self.store.save(ev, final)
        if ev.day != self.mem_day:
            self.mem_day = ev.day
            self.mem.clear()
        row = ev.as_dict()
        lst = self.mem[ev.price]
        for i, old in enumerate(lst):
            if old.get("id") == ev.id and old.get("t") == ev.t:
                lst[i] = row
                break
        else:
            lst.append(row)

    def stats(self) -> list[dict[str, Any]]:
        if time.monotonic() - self._stats_at > 10:
            root = (self.engine.sym or "").split(" ")[0]
            self._stats = self.store.stats(root)
            self._stats_at = time.monotonic()
        return self._stats

    def state(self) -> dict[str, Any]:
        snap = self.engine.snapshot()
        snap["connected"] = self.feeds > 0 and time.monotonic() - self.feed_at < 10
        snap["day"] = self.mem_day
        last = snap["last"]
        snap["memory"] = [
            [p, evs[-12:]]
            for p, evs in self.mem.items()
            if last is None or abs(p - last) <= 60 * self.engine.tick
        ]
        snap["stats"] = self.stats()
        return snap

    async def serve_feed(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info("NinjaTrader connected from %s", peer)
        self.feeds += 1
        try:
            while line := await reader.readline():
                self.feed_at = time.monotonic()
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("k") != "ping":
                    self.engine.handle(msg)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.feeds -= 1
            log.info("NinjaTrader disconnected (%s)", peer)
            writer.close()


hub: Hub | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global hub
    hub = Hub()
    server = await asyncio.start_server(hub.serve_feed, "0.0.0.0", FEED_PORT)
    log.info("Waiting for NinjaTrader on TCP %s", FEED_PORT)
    try:
        yield
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()


app = FastAPI(title="Memory DOM", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    assert hub
    return {"status": "up", "ninjatrader": hub.feeds > 0, "symbol": hub.engine.sym}


@app.get("/state")
def state() -> dict[str, Any]:
    assert hub
    return hub.state()


@app.get("/events")
def events(day: str | None = None) -> list[dict[str, Any]]:
    assert hub
    return hub.store.day_events(day or hub.mem_day)


@app.get("/stats")
def stats() -> list[dict[str, Any]]:
    assert hub
    return hub.stats()


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    assert hub
    await socket.accept()
    try:
        while True:
            await socket.send_text(json.dumps(hub.state()))
            await asyncio.sleep(0.25)
    except (WebSocketDisconnect, RuntimeError):
        pass
