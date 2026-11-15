"""Pretend to be NinjaTrader: stream a simulated ES book and trades to dom-service.

    python dom-service/tools/fake_ninjatrader.py [--host 127.0.0.1] [--port 8060] [--speed 20]

For testing the memory DOM without NinjaTrader. Price random-walks; now and then a big
order shows up near price and is pulled, eaten or holds.
"""

from __future__ import annotations

import argparse
import json
import random
import socket
import time


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8060)
    ap.add_argument("--speed", type=float, default=20.0, help="simulated seconds per real second")
    ap.add_argument("--minutes", type=float, default=30.0, help="simulated minutes to run")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    s = socket.create_connection((a.host, a.port))

    def send(m: dict) -> None:
        s.sendall((json.dumps(m) + "\n").encode())

    send({"k": "hello", "sym": "ES 12-26", "tick": 0.25})
    send({"k": "reset"})
    t = int(time.time() * 1000)
    end = t + int(a.minutes * 60_000)
    mid = 7443.5
    walls: dict[tuple[str, float], dict] = {}
    shown: dict[tuple[str, float], int] = {}

    def depth() -> None:
        want: dict[tuple[str, float], int] = {}
        for i in range(10):
            bp, ap_ = mid - 0.25 - i * 0.25, mid + i * 0.25
            want[("b", bp)] = 15 + (hash((bp, t // 4000)) % 40)
            want[("a", ap_)] = 15 + (hash((ap_, t // 4000)) % 40)
        for (side, p), w in walls.items():
            if (side, p) in want:
                want[(side, p)] = w["size"]
        for key, v in want.items():
            if shown.get(key) != v:
                send({"k": "d", "t": t, "s": key[0], "p": key[1], "v": v})
        for key in list(shown):
            if key not in want:
                send({"k": "d", "t": t, "s": key[0], "p": key[1], "v": 0})
        shown.clear()
        shown.update(want)
        send({"k": "q", "t": t, "b": mid - 0.25, "a": mid})

    drift = 0.0
    while t < end:
        t += 250
        # a new wall now and then, 3-8 ticks from price
        if rnd.random() < 0.01 and len(walls) < 4:
            side = rnd.choice("ba")
            off = rnd.randint(3, 8) * 0.25
            p = mid - 0.25 - off if side == "b" else mid + off
            walls[(side, p)] = {
                "size": rnd.choice([250, 400, 600, 900]),
                "fate": rnd.choice(["pull", "hold", "eat"]),
            }
        # price walk, pushed away by walls that hold
        step = rnd.choice([-0.25, 0, 0, 0.25]) + (
            0.25 if drift > 0.6 else -0.25 if drift < -0.6 else 0
        )
        drift = drift * 0.9 + rnd.uniform(-0.3, 0.3)
        new = mid + step
        for (side, p), w in list(walls.items()):
            if side == "b" and new - 0.25 <= p or side == "a" and new >= p:
                trade_side = "sell" if side == "b" else "buy"
                if w["fate"] == "hold":
                    hit = rnd.randint(20, 80)
                    send({"k": "x", "t": t, "p": p, "v": hit, "s": trade_side})
                    new = mid + (0.5 if side == "b" else -0.5)
                    w["fate"] = "hold-done"
                elif w["fate"] == "eat":
                    send({"k": "x", "t": t, "p": p, "v": w["size"], "s": trade_side})
                    w["size"] = 0
                elif w["fate"] == "pull":
                    w["size"] = 0
            elif w["fate"] == "pull" and abs(new - p) <= 0.75 and rnd.random() < 0.3:
                w["size"] = 0
            if w["size"] == 0 or abs(new - p) > 3:
                del walls[(side, p)]
        mid = new
        depth()
        if rnd.random() < 0.6:
            buy = rnd.random() < 0.5
            send(
                {
                    "k": "x",
                    "t": t,
                    "p": mid if buy else mid - 0.25,
                    "v": rnd.randint(1, 12),
                    "s": "buy" if buy else "sell",
                }
            )
        time.sleep(0.25 / a.speed)
    s.close()


if __name__ == "__main__":
    main()
