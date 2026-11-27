@echo off
rem One STS levels refresh (NQ from QQQ, ES from SPY), no window to keep open.
rem Run by the Windows schedule at 5:00, 6:30, 8:00 and 10:00 AM PT, Monday-Friday
rem (install it once with install-sts-schedule.ps1). Every refresh is saved for backtests in
rem data\sts_levels\levels_NQ.csv / levels_ES.csv (plus the raw option chains in data\sts_levels\raw).
rem Log of each run: data\sts_levels\schedule.log
cd /d "%~dp0..\.."
if not exist data\sts_levels mkdir data\sts_levels
set PY=.venv-mt5\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" -c "import yfinance" 2>nul || "%PY%" -m pip install --quiet yfinance
echo ==== %date% %time% >> data\sts_levels\schedule.log
"%PY%" scripts\oi_walls.py --once >> data\sts_levels\schedule.log 2>&1
