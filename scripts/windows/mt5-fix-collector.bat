@echo off
rem Restarts the collector so it fills in missing history and saves live prices.
setlocal
cd /d "%~dp0\..\.."
docker compose --env-file config/.env.shared -f docker-compose.yml -f docker-compose.mt5.yml restart ingestion-service
echo.
echo Done. Wait one minute, then press F5 on the chart.
