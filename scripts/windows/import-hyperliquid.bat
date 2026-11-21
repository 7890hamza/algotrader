@echo off
rem Loads Hyperliquid 1-minute XYZ100 / SP500 history (from AWS) into the app. Start the app first.
rem Safe to run again. Another file: import-hyperliquid.bat "C:\path\to\file.csv.gz"
cd /d "%~dp0..\.."
set PY=.venv-mt5\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" scripts\import_hyperliquid.py %1
pause
