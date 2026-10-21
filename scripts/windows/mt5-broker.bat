@echo off
rem Starts the read-only MT5 price bridge on http://localhost:8050.
rem Keep this window open while you use AlgoTrader. Close it (or Ctrl+C) to stop.
setlocal
cd /d "%~dp0\..\..\broker-service"

if not exist ".venv-mt5\Scripts\python.exe" (
  echo Run scripts\windows\mt5-setup.bat first.
  exit /b 1
)

set BROKER_PROVIDER=mt5
set BROKER_REDIS_URL=redis://localhost:6379/0
set BROKER_SERVICE_PORT=8050
rem AlgoTrader name = exact MT5 name. Add more like: ES=@EP,NQ=@ENQ
if "%MT5_SYMBOLS%"=="" set MT5_SYMBOLS=ES=@EP
rem AMP's MT5 server clock is UTC. Change only if your broker's server clock is not.
if "%MT5_SERVER_UTC_OFFSET_MINUTES%"=="" set MT5_SERVER_UTC_OFFSET_MINUTES=0
rem Refuses to start on a real-money account unless you set this to false.
if "%MT5_REQUIRE_DEMO%"=="" set MT5_REQUIRE_DEMO=true

echo Starting the MT5 price bridge (read-only) on http://localhost:8050 ...
".venv-mt5\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8050
