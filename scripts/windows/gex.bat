@echo off
rem GEX levels for the chart (free Yahoo Finance option data). Leave this window open:
rem it refreshes every 15 minutes. Close it to stop. Then turn on "GEX" on the chart.
cd /d "%~dp0..\.."
set PY=.venv-mt5\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" -c "import yfinance" 2>nul || "%PY%" -m pip install --quiet yfinance
"%PY%" scripts\gex.py --loop 15
pause
