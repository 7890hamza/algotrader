# Running AlgoTrader with MetaTrader 5 (Windows)

The MT5 provider replaces cTrader as the source of prices. It is **read-only**:
it reads Candles and Ticks from a running MT5 terminal and never places, changes
or closes orders (those endpoints answer `403`).

```
 Windows                                   Docker Desktop
 ┌─────────────────────┐                   ┌──────────────────────────────────┐
 │ MT5 terminal (demo) │                   │ redis  ingestion  timescaledb    │
 │        ▲            │   prices (Redis)  │ webserver  indicator-api         │
 │ MT5 bridge :8050 ───┼──────────────────►│ database-accessor-api  frontend  │
 │ (broker-service,    │◄──────────────────┼ history + stream requests (HTTP) │
 │  BROKER_PROVIDER=mt5)                   └──────────────────────────────────┘
 └─────────────────────┘
```

The `MetaTrader5` Python package only exists for Windows and talks to the terminal on
the same PC, so the bridge runs natively; everything else runs in Docker as usual.

## One-time setup

1. Install Python 3.12 and Docker Desktop (with WSL 2).
2. From the repository folder run `scripts\windows\mt5-setup.bat`.
   It creates `broker-service\.venv-mt5`, writes `config\.env.secrets.local` with
   placeholder cTrader values (unused) and `ACCOUNT_ID=1`, and generates the Docker
   config files.

## Every time

1. Open MT5 and log in to a **demo** account.
2. Double-click `scripts\windows\mt5-broker.bat` and leave the window open.
3. Run `scripts\windows\mt5-stack-up.bat` (Docker Desktop must say "Engine running").
4. Open <http://localhost:5173>.

Stop with `scripts\windows\mt5-stack-down.bat` and by closing the bridge window.

## First run: add the ES Market

In the chart's symbol menu add symbol `ES`, exchange `CME`, min move `0.25`. Then
restart ingestion once so it picks up the new Market and backfills history:

```
docker compose --env-file config/.env.shared -f docker-compose.yml -f docker-compose.mt5.yml restart ingestion-service
```

## Settings (environment variables for the bridge)

| Variable | Default | Meaning |
| --- | --- | --- |
| `BROKER_PROVIDER` | `ctrader` | `mt5` selects this adapter |
| `MT5_SYMBOLS` | `ES=@EP` | AlgoTrader name = exact MT5 name, comma separated |
| `MT5_REQUIRE_DEMO` | `true` | refuse to start on a real-money account |
| `MT5_SERVER_UTC_OFFSET_MINUTES` | `0` | MT5 server clock minus UTC (AMP's server is UTC) |
| `MT5_VOLUME_SOURCE` | `real` | `real` exchange volume or `tick` count |
| `MT5_POLL_INTERVAL_SECONDS` | `0.25` | how often live prices are read |
| `MT5_TERMINAL_PATH` | empty | path to `terminal64.exe` if several MT5s are installed |

Aliases exist because MT5 names like `@EP` are awkward in URLs and stream names.

## How it maps to the shared contracts

- History: `copy_rates_range`, requested in bounded windows and repeated while the
  terminal is still downloading, then delivered with the normal NDJSON completion
  record ([HISTORY.md](HISTORY.md)). A failed MT5 call produces the error record.
- Live Candles: the forming bar is published whenever it changes; when a new bar
  opens, the final version of the closed bar is published first. Losing the terminal
  connection rotates publication continuity so ingestion recovers the gap.
- Ticks: every bid/ask change since the last poll (`copy_ticks_from`), no duplicates,
  published as `b`/`a`/`t` on `ticks:{account_id}:{symbol}`.
- Timestamps are converted from the MT5 server clock to UTC epoch milliseconds.
