# AlgoTrader launcher: one window that starts, watches and stops everything.
#   Start everything : Docker Desktop -> MT5 price bridge (hidden, logged) -> the app -> fills any gap -> opens the browser
#   Status lights    : Docker, MT5, price bridge, app, data freshness (refreshed every few seconds)
#   Stop everything  : price bridge + the app's containers (your stored candles are kept)
# Install the desktop icon once with:  powershell -ExecutionPolicy Bypass -File scripts\windows\install-launcher.ps1

Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase

$Root      = (Resolve-Path "$PSScriptRoot\..\..").Path
$Win       = "$Root\scripts\windows"
$LogDir    = "$Root\logs"
$BridgeLog = "$LogDir\bridge.log"
$StackLog  = "$LogDir\stack.log"
$Settings  = "$Root\config\launcher.json"
$Py        = "$Root\broker-service\.venv-mt5\Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$mode = "demo"
try { if (Test-Path $Settings) { $mode = (Get-Content $Settings -Raw | ConvertFrom-Json).mode } } catch {}

[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="AlgoTrader" Width="460" Height="640" Background="#161a22" ResizeMode="CanMinimize"
        WindowStartupLocation="CenterScreen" FontFamily="Segoe UI">
  <Window.Resources>
    <Style TargetType="Button">
      <Setter Property="Foreground" Value="#e8e8e8"/><Setter Property="Background" Value="#2a3140"/>
      <Setter Property="BorderBrush" Value="#3a4356"/><Setter Property="Height" Value="38"/>
      <Setter Property="FontSize" Value="13"/><Setter Property="Margin" Value="0,0,0,8"/>
      <Setter Property="Cursor" Value="Hand"/>
    </Style>
    <Style TargetType="TextBlock"><Setter Property="Foreground" Value="#d8dbe2"/></Style>
  </Window.Resources>
  <StackPanel Margin="22,18,22,14">
    <TextBlock Text="AlgoTrader" FontSize="24" FontWeight="SemiBold"/>
    <TextBlock Text="ES / NQ charts, indicators and Replay" Foreground="#8a93a6" Margin="0,0,0,14"/>

    <Border Background="#1d2230" CornerRadius="10" Padding="14,10" Margin="0,0,0,14">
      <StackPanel x:Name="Lights"/>
    </Border>

    <StackPanel Orientation="Horizontal" Margin="0,0,0,10">
      <TextBlock Text="MT5 account:" VerticalAlignment="Center" Margin="0,0,10,0" Foreground="#8a93a6"/>
      <RadioButton x:Name="ModeDemo" Content="Demo" Foreground="#d8dbe2" Margin="0,0,14,0" VerticalAlignment="Center"/>
      <RadioButton x:Name="ModeLive" Content="Live (prices only)" Foreground="#d8dbe2" VerticalAlignment="Center"/>
    </StackPanel>

    <Button x:Name="BtnStart" Content="Start everything" Background="#1f6f43" BorderBrush="#2a8a55" FontWeight="SemiBold"/>
    <Button x:Name="BtnOpen"  Content="Open AlgoTrader in the browser"/>
    <Button x:Name="BtnGap"   Content="Fill missing bars (last 7 days)"/>
    <Button x:Name="BtnStop"  Content="Stop everything" Background="#5a2328" BorderBrush="#7a2f35"/>

    <TextBlock Text="Price bridge log (last lines)" Foreground="#8a93a6" Margin="0,6,0,4"/>
    <Border Background="#0f1218" CornerRadius="8" Padding="8">
      <TextBlock x:Name="Log" FontFamily="Consolas" FontSize="11" Foreground="#9fb0c8" TextWrapping="Wrap" Height="120"/>
    </Border>
    <TextBlock x:Name="Status" Foreground="#e9b040" Margin="0,8,0,0" TextWrapping="Wrap"/>
  </StackPanel>
</Window>
"@
$window = [Windows.Markup.XamlReader]::Load((New-Object System.Xml.XmlNodeReader $xaml))
$ui = @{}
foreach ($n in "Lights","ModeDemo","ModeLive","BtnStart","BtnOpen","BtnGap","BtnStop","Log","Status") { $ui[$n] = $window.FindName($n) }
if ($mode -eq "live") { $ui.ModeLive.IsChecked = $true } else { $ui.ModeDemo.IsChecked = $true }

# ---- status lights ---------------------------------------------------------------------------
$lightNames = "Docker", "MT5", "Price bridge", "App", "Today's data"
$lights = @{}
foreach ($n in $lightNames) {
  $row = New-Object Windows.Controls.StackPanel; $row.Orientation = "Horizontal"; $row.Margin = "0,3,0,3"
  $dot = New-Object Windows.Shapes.Ellipse; $dot.Width = 11; $dot.Height = 11; $dot.Margin = "0,0,10,0"; $dot.Fill = "#555"
  $name = New-Object Windows.Controls.TextBlock; $name.Text = $n; $name.Width = 110; $name.Foreground = "#d8dbe2"
  $info = New-Object Windows.Controls.TextBlock; $info.Foreground = "#8a93a6"; $info.TextTrimming = "CharacterEllipsis"; $info.Width = 250
  $row.Children.Add($dot) | Out-Null; $row.Children.Add($name) | Out-Null; $row.Children.Add($info) | Out-Null
  $ui.Lights.Children.Add($row) | Out-Null
  $lights[$n] = @{ dot = $dot; info = $info }
}
function Set-Light($n, $state, $text) {
  $c = @{ ok = "#3fb950"; warn = "#e9b040"; bad = "#e5534b"; off = "#555" }[$state]
  $lights[$n].dot.Fill = $c; $lights[$n].info.Text = $text
}
function Get-Json($url) { try { Invoke-RestMethod $url -TimeoutSec 1 } catch { $null } }
function Test-Url($url) { try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 1 | Out-Null; $true } catch { $false } }

function Update-Status {
  $docker = Get-Process "com.docker.backend" -ErrorAction SilentlyContinue
  if ($docker) { Set-Light "Docker" ok "running" } else { Set-Light "Docker" bad "Docker Desktop is closed" }

  $mt5 = Get-Process terminal64 -ErrorAction SilentlyContinue
  if ($mt5) { Set-Light "MT5" ok ($mt5[0].MainWindowTitle -replace " - AMP Global Clearing LLC.*", "") }
  else { Set-Light "MT5" bad "not open - open AMP MT5 and log in" }

  $h = Get-Json "http://localhost:8050/health"
  if (-not $h) { Set-Light "Price bridge" bad "not running" }
  elseif ($h.components.ctrader.status -eq "up") { Set-Light "Price bridge" ok "connected to MT5" }
  else { Set-Light "Price bridge" warn "running, waiting for MT5 to log in" }

  if (Test-Url "http://localhost:5173") { Set-Light "App" ok "http://localhost:5173" } else { Set-Light "App" off "not running" }

  $last = Get-Json "http://localhost:8000/candles/ES/latest"
  if ($last -and $last.timestamp_ms) {
    $age = [math]::Round(([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - [long]$last.timestamp_ms) / 60000)
    $when = [DateTimeOffset]::FromUnixTimeMilliseconds([long]$last.timestamp_ms).ToLocalTime().ToString("ddd h:mm tt")
    if ($age -le 5) { Set-Light "Today's data" ok "ES up to date ($when)" }
    else { Set-Light "Today's data" warn "ES last bar $when - market closed, or press Fill missing bars" }
  } else { Set-Light "Today's data" off "-" }

  if (Test-Path $BridgeLog) {
    try { $ui.Log.Text = ((Get-Content $BridgeLog -Tail 7 -ErrorAction Stop) -join "`n") } catch {}
  }
}

function Say($t) { $ui.Status.Text = $t; $window.Dispatcher.Invoke([action]{}, "Render") }
function Save-Mode { $m = if ($ui.ModeLive.IsChecked) { "live" } else { "demo" }; (@{ mode = $m } | ConvertTo-Json) | Set-Content $Settings; $m }

# ---- actions ---------------------------------------------------------------------------------
function Stop-Bridge {
  $pids = Get-NetTCPConnection -LocalPort 8050 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique
  foreach ($p in $pids) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
}

function Start-Everything {
  $m = Save-Mode
  if (-not (Get-Process terminal64 -ErrorAction SilentlyContinue)) {
    Say "Open AMP MT5 and log in first (it isn't running)."; return
  }
  if (-not (Get-Process "com.docker.backend" -ErrorAction SilentlyContinue)) {
    Say "Starting Docker Desktop..."
    $dd = @("$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe", "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($dd) { Start-Process $dd }
    for ($i = 0; $i -lt 60; $i++) { docker info *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep 2; $window.Dispatcher.Invoke([action]{}, "Background") }
  }
  Say "Starting the MT5 price bridge ($m)..."
  Stop-Bridge
  $bat = if ($m -eq "live") { "mt5-broker-live.bat" } else { "mt5-broker.bat" }
  Start-Process cmd -ArgumentList "/c", "`"$Win\$bat`" > `"$BridgeLog`" 2>&1" -WindowStyle Hidden
  for ($i = 0; $i -lt 20; $i++) { Start-Sleep 1; if (Get-Json "http://localhost:8050/health") { break } }
  if (-not (Get-Json "http://localhost:8050/health")) {
    Say "The price bridge didn't start. Read the log below (the lines above 'startup failed')."; Update-Status; return
  }
  Say "Starting the app (database, charts, indicators)... about a minute."
  $p = Start-Process cmd -ArgumentList "/c", "`"$Win\mt5-stack-up.bat`" > `"$StackLog`" 2>&1" -WindowStyle Hidden -PassThru
  while (-not $p.HasExited) { Start-Sleep 1; $window.Dispatcher.Invoke([action]{}, "Background") }
  if ($p.ExitCode -ne 0) { Say "The app didn't start. See logs\stack.log. Is Docker Desktop running?"; return }
  docker restart ingestion-service *> $null      # pulls any bars missed while things were off
  for ($i = 0; $i -lt 60; $i++) { if (Test-Url "http://localhost:5173") { break }; Start-Sleep 2; $window.Dispatcher.Invoke([action]{}, "Background") }
  Start-Process "http://localhost:5173"
  Say "Running. Keep this window open (minimise it); closing it does not stop anything."
  Update-Status
}

function Fill-Gap {
  if (-not (Get-Json "http://localhost:8050/health")) { Say "Start everything first (the price bridge isn't running)."; return }
  $from = (Get-Date).AddDays(-7).ToString("yyyy-MM-dd")
  Say "Loading bars since $from from MT5... (a minute or two)"
  $p = Start-Process $Py -ArgumentList "`"$Root\scripts\import_history.py`"", "--start", $from -WindowStyle Hidden -PassThru `
       -RedirectStandardOutput "$LogDir\import.log" -RedirectStandardError "$LogDir\import-err.log"
  while (-not $p.HasExited) { Start-Sleep 1; $window.Dispatcher.Invoke([action]{}, "Background") }
  Say "Done. Press Ctrl+F5 on the chart page."
  Update-Status
}

function Stop-Everything {
  Say "Stopping..."
  Stop-Bridge
  $p = Start-Process cmd -ArgumentList "/c", "`"$Win\mt5-stack-down.bat`" > `"$StackLog`" 2>&1" -WindowStyle Hidden -PassThru
  while (-not $p.HasExited) { Start-Sleep 1; $window.Dispatcher.Invoke([action]{}, "Background") }
  Say "Stopped. Your stored candles are kept."
  Update-Status
}

$ui.BtnStart.Add_Click({ $ui.BtnStart.IsEnabled = $false; try { Start-Everything } finally { $ui.BtnStart.IsEnabled = $true } })
$ui.BtnOpen.Add_Click({ Start-Process "http://localhost:5173" })
$ui.BtnGap.Add_Click({ Fill-Gap })
$ui.BtnStop.Add_Click({ Stop-Everything })
$ui.ModeDemo.Add_Checked({ Save-Mode | Out-Null })
$ui.ModeLive.Add_Checked({ Save-Mode | Out-Null })

$timer = New-Object Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromSeconds(5)
$timer.Add_Tick({ Update-Status })
$timer.Start()
$window.Add_ContentRendered({ Update-Status })
$window.ShowDialog() | Out-Null
