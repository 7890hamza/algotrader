@echo off
rem PRICES ONLY from a LIVE (real-money) MT5 login. Same read-only price bridge as mt5-broker.bat,
rem but it doesn't refuse a live account. It can NEVER send orders here:
rem   - order sending is forced off below, and
rem   - every order is also refused by the bridge unless MT5 is logged into a DEMO account.
rem Keep MT5's "Algo Trading" button OFF while logged into live.
setlocal
set MT5_REQUIRE_DEMO=false
set MT5_TRADING_ENABLED=false
echo.
echo   LIVE MT5 LOGIN - PRICES ONLY. No orders can be sent from AlgoTrader.
echo.
call "%~dp0mt5-broker.bat"
