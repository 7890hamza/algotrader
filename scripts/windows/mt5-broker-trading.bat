@echo off
rem Same MT5 price bridge, but with order sending ON (demo accounts only).
rem AlgoTrader's Buy / Sell and "Send to MT5" buttons place real orders on your MT5 demo.
rem The bridge refuses to send anything if MT5 is logged in to a real-money account.
rem Use scripts\windows\mt5-broker.bat instead to keep it read-only.
setlocal
set MT5_TRADING_ENABLED=true
set MT5_REQUIRE_DEMO=true
echo ORDER SENDING IS ON (demo accounts only).
call "%~dp0mt5-broker.bat"
