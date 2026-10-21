@echo off
rem One-time setup for running AlgoTrader with MetaTrader 5 on Windows.
rem Creates the Python environment for the MT5 bridge and the config files.
setlocal
cd /d "%~dp0\..\.."

echo.
echo [1/3] Creating the Python environment for the MT5 bridge (broker-service\.venv-mt5)...
if not exist "broker-service\.venv-mt5\Scripts\python.exe" (
  python -m venv broker-service\.venv-mt5 || goto :fail
)
pushd broker-service
".venv-mt5\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv-mt5\Scripts\python.exe" -m pip install -r requirements-mt5-windows.txt pyyaml || (popd & goto :fail)
popd

echo.
echo [2/3] Creating config\.env.secrets.local (only if it does not exist yet)...
if not exist "config\.env.secrets.local" (
  > "config\.env.secrets.local" (
    echo TIMESCALEDB_PASSWORD=change-me-local-only
    echo ACCOUNT_ID=1
    echo CTRADER_CLIENT_ID=unused-mt5
    echo CTRADER_SECRET=unused-mt5
    echo CTRADER_ACCESS_TOKEN=unused-mt5
    echo CTRADER_REFRESH_TOKEN=unused-mt5
    echo CTRADER_HOST_TYPE=demo
  )
)

echo.
echo [3/3] Generating Docker config files...
"broker-service\.venv-mt5\Scripts\python.exe" scripts\generate_env.py --force || goto :fail

echo.
echo Setup finished.
exit /b 0

:fail
echo.
echo Setup FAILED. Copy the red or error lines above and send them to Claude.
exit /b 1
