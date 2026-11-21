@echo off
rem Preloads 1-minute ES / NQ / MES / MNQ history from MT5 into the app, so the chart and Replay
rem can go back. Start the app (and the MT5 price bridge) first. Safe to run again.
rem Default: from January 1 of this year. Further back: import-history.bat 2021-01-01
cd /d "%~dp0..\.."
set START=%1
set PY=.venv-mt5\Scripts\python.exe
if not exist "%PY%" set PY=python
if "%START%"=="" ("%PY%" scripts\import_history.py) else ("%PY%" scripts\import_history.py --start %START%)
pause
