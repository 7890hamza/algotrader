# MT5 CHECK: finds out why prices aren't moving. Reads only - changes nothing.
#   powershell -ExecutionPolicy Bypass -File scripts\windows\mt5-check.ps1          (ES)
#   powershell -ExecutionPolicy Bypass -File scripts\windows\mt5-check.ps1 NQ
param([string]$Symbol = "ES")

$bridge = "http://localhost:8050"
$db = "http://localhost:8000"
$problems = @()
function Ok($t)   { Write-Host "  OK    $t" -ForegroundColor Green }
function Bad($t)  { Write-Host "  FAIL  $t" -ForegroundColor Red; $script:problems += $t }
function Info($t) { Write-Host "        $t" -ForegroundColor Gray }
function NowMs    { [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() }
function Age($ms) { [math]::Round(((NowMs) - $ms) / 60000, 1) }

Write-Host "`n1) Is MetaTrader 5 running?"
$term = Get-Process terminal64 -ErrorAction SilentlyContinue
if ($term) { Ok "MT5 is open ($($term.MainWindowTitle))" } else { Bad "MT5 is not open. Open AMP MetaTrader 5 and log into the demo." }

Write-Host "`n2) Is the MT5 price bridge running and connected to MT5?"
try {
  $h = Invoke-RestMethod "$bridge/health" -TimeoutSec 5
  $c = $h.components.ctrader.status
  if ($c -eq "up") { Ok "Bridge is up and connected to MT5" } else { Bad "Bridge is running but NOT connected to MT5 (status: $c). MT5 closed, logged out, or algo trading off." }
} catch { Bad "Bridge not answering on port 8050. Start scripts\windows\mt5-broker.bat." }

Write-Host "`n3) Is MT5 sending new $Symbol bars right now?"
$headers = @{ "X-Account-Id" = "1" }
function LastBar {
  $to = NowMs; $from = $to - 30 * 60000
  $bars = Invoke-RestMethod "$bridge/symbols/$Symbol/trendbars?timeframe=M1&fromTs=$from&toTs=$to" -Headers $headers -TimeoutSec 15
  if ($bars) { $bars | Sort-Object { [long]$_.t } | Select-Object -Last 1 } else { $null }
}
try {
  $b1 = LastBar
  if (-not $b1) { Bad "MT5 has NO $Symbol bars in the last 30 minutes. Market Watch symbol not updating (feed stalled, or wrong/expired contract)." }
  else {
    $age = Age ([long]$b1.t)
    Info "newest bar: $(([DateTimeOffset]::FromUnixTimeMilliseconds([long]$b1.t)).ToLocalTime().ToString('ddd h:mm tt'))  close $($b1.c)  ($age min ago)"
    Info "waiting 20 seconds to see if the price moves..."
    Start-Sleep -Seconds 20
    $b2 = LastBar
    $moved = ($b2.t -ne $b1.t) -or ($b2.c -ne $b1.c)
    if ($age -le 3 -and $moved) { Ok "MT5 price is moving ($($b1.c) -> $($b2.c))" }
    elseif ($age -le 3) { Ok "Bars are current; price didn't change in 20 s (quiet market is possible)" }
    else { Bad "Newest $Symbol bar is $age minutes old: MT5's data feed is stalled. Close MT5 completely and reopen it." }
  }
} catch { Bad "Couldn't ask the bridge for $Symbol bars ($($_.Exception.Message))." }

Write-Host "`n4) Is the app saving new $Symbol bars to its database?"
try {
  $last = Invoke-RestMethod "$db/candles/$Symbol/latest" -TimeoutSec 5
  $ts = if ($last.timestamp_ms) { [long]$last.timestamp_ms } elseif ($last.t) { [long]$last.t } else { [long]$last.timestamp }
  $age = Age $ts
  if ($age -le 5) { Ok "Database has $Symbol up to $age min ago" } else { Bad "Database's newest $Symbol bar is $age minutes old: the app's ingestion isn't pulling from the bridge." }
} catch { Bad "App database not answering on port 8000. Start scripts\windows\mt5-stack-up.bat (Docker must be running)." }

Write-Host "`n5) App containers"
try {
  $rows = docker ps --format "{{.Names}}|{{.Status}}" 2>$null
  if (-not $rows) { Bad "Docker isn't running, or no app containers are up." }
  foreach ($r in $rows) {
    $n, $s = $r -split '\|', 2
    if ($s -match "^Up" -and $s -notmatch "unhealthy") { Ok "$n  ($s)" } else { Bad "$n  ($s)" }
  }
} catch { Bad "Couldn't ask Docker for containers." }

Write-Host ""
if ($problems.Count -eq 0) { Write-Host "Everything looks fine. If the chart still looks frozen, press Ctrl+F5 on the page." -ForegroundColor Green }
else { Write-Host "Found $($problems.Count) problem(s). Fix the FIRST one above, then run this again." -ForegroundColor Yellow }
