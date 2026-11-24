# NinjaTrader DOM bridge

`AlgoTraderDomBridge.cs` streams NinjaTrader 8's order book (market depth) and trades for
one instrument into the memory DOM (`dom-service`, TCP 8060 on this PC). It is read-only:
it never sends, changes or cancels orders.

1. Copy `AlgoTraderDomBridge.cs` to `Documents\NinjaTrader 8\bin\Custom\Indicators\`.
2. NinjaTrader: New > NinjaScript Editor, then press F5 to compile.
3. Open an ES chart (any timeframe) and add the indicator **AlgoTraderDomBridge**.
4. In the app, click **DOM** in the top bar. The dot turns green when the feed is live.

It needs live market depth (Level 2) in NinjaTrader, the same data its own DOM shows, and
the app's Docker stack running (`scripts\windows\mt5-stack-up.bat`). It reconnects by
itself if the app restarts.

Settings (env on `dom-service`): `DOM_MIN_SIZE` (100) and `DOM_FACTOR` (2.5) decide what a
big order is: at least that many contracts and 2.5x the side's median size.
`DOM_HOLD_TICKS` (8) is how far price must move away for a level to count as held.

# Option walls (OiWalls)

`OiWalls.cs` draws the STS option walls (outer call wall, call wall, flip, put wall, outer put
wall) as step lines on an NQ / MNQ or ES / MES chart.

1. Double-click `scripts\windows\oi-walls.bat` and leave it open (refreshes every 5 minutes;
   writes `Documents\AlgoTraderLevels\NQ.csv` and `ES.csv`).
2. Copy `OiWalls.cs` to `Documents\NinjaTrader 8\bin\Custom\Indicators\`, compile with F5.
3. Add **OiWalls** to the chart. It re-reads the file every 20 seconds while live.

# LevelsPlus (midbands + MTF / ALN / TBR bands)

`LevelsPlus.cs` sits on top of the ama Day / Week VWAP (LizardIndicators) and Current Day OHL
without changing them: VWAP midbands (+/-0.5, 1.5, 2.5 SD) read from the ama indicators, MTF
daily band (+/-1 to 1.5 SDEV), ALN session bands (+/-0.5 to 1), TBR bands (+0.25 and -0.25 out to
the stretch median), labels inside the bands and a "price is in" tag. Session math runs on its
own 1-minute series, so it matches on any chart timeframe.

1. Back up: Tools > Export > NinjaScript Add-On.
2. Copy `LevelsPlus.cs` to `Documents\NinjaTrader 8\bin\Custom\Indicators\`, compile with F5.
3. Add **LevelsPlus** to the ES chart. Load 30+ days so 20 full days / sessions exist.
