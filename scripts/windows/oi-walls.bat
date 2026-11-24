@echo off
rem Option walls for NQ (from QQQ) and ES (from SPY), STS method, free Yahoo data.
rem Leave this window open: it refreshes every 5 minutes. Feeds the app chart ("GEX" button,
rem Walls) and the NinjaTrader indicator OiWalls (Documents\AlgoTraderLevels\NQ.csv / ES.csv).
cd /d "%~dp0..\.."
set PY=.venv-mt5\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" -c "import yfinance" 2>nul || "%PY%" -m pip install --quiet yfinance
"%PY%" scripts\oi_walls.py %*
pause
