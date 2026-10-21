@echo off
rem Starts everything except the broker in Docker (database, charts, indicators...).
setlocal
cd /d "%~dp0\..\.."
"broker-service\.venv-mt5\Scripts\python.exe" scripts\generate_env.py --force || exit /b 1
docker compose --env-file config/.env.shared -f docker-compose.yml -f docker-compose.mt5.yml up -d --build
if errorlevel 1 (
  echo.
  echo Docker could not start the stack. Is Docker Desktop open and "Engine running"?
  exit /b 1
)
echo.
echo AlgoTrader is starting. Open http://localhost:5173 in your browser in a minute or two.
