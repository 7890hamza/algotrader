@echo off
rem Loads 5 years of 1-minute ES / NQ / MES / MNQ history from the NinjaTrader exports
rem (C:\Users\<you>\es-sdev\data\processed) into the app's database. Start the app first.
rem Safe to run again. Change the years: import-history.bat 3
cd /d "%~dp0..\.."
set YEARS=%1
if "%YEARS%"=="" set YEARS=5
set PY=.venv-mt5\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" scripts\import_history.py --years %YEARS%
pause
