@echo off
rem Stops the Docker part of AlgoTrader. Your stored candles are kept.
setlocal
cd /d "%~dp0\..\.."
docker compose --env-file config/.env.shared -f docker-compose.yml -f docker-compose.mt5.yml down
