# hyperliquid-service (read-only)

Brings Hyperliquid's trade.xyz index perps into AlgoTrader next to the MT5 futures:

| Hyperliquid coin | Chart symbol (exchange `HYPERLIQUID`) | Compared with |
|---|---|---|
| `xyz:XYZ100` (Nasdaq-100) | `XYZ100` | `NQ` |
| `xyz:SP500` (S&P 500) | `SP500` | `ES` |

* Backfills the last `HL_BACKFILL_DAYS` (default 3) of 1-minute candles, then keeps them current
  every `HL_POLL_SECONDS` (default 20) through the public `info` API.
* Creates the two markets in the database on first start, so they show up in the chart's market list
  and every indicator (SEIZ picks the NQ table for XYZ100, the ES table for SP500) works on them.
* `GET :8040/compare` - Hyperliquid mid / mark / oracle / hourly funding vs the latest NQ / ES close.
* `GET :8040/markets`, `GET :8040/health`.

It has **no keys and no order endpoints**. trade.xyz's terms prohibit access by US persons and
from the United States; any order-sending side is deliberately not built.

Change coins with `HL_COINS`, e.g. `xyz:XYZ100=XYZ100>NQ, xyz:SP500=SP500>ES`.
