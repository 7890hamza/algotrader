# Sets up the STS levels refresh in Windows Task Scheduler: Monday-Friday at
# 5:00, 6:30, 8:00 and 10:00 AM (this PC's clock, Pacific time).
# Run once:   powershell -ExecutionPolicy Bypass -File scripts\windows\install-sts-schedule.ps1
# Remove:     powershell -ExecutionPolicy Bypass -File scripts\windows\install-sts-schedule.ps1 -Remove
# The PC must be on and you must be logged in at those times. If the PC was asleep, the run
# happens as soon as it wakes up (StartWhenAvailable).
param([switch]$Remove)
$Name = 'AlgoTrader STS levels'
if ($Remove) {
  Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed '$Name'."
  return
}
$bat = (Resolve-Path (Join-Path $PSScriptRoot 'sts-refresh.bat')).Path
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$bat`"" -WorkingDirectory $repo
$days = 'Monday','Tuesday','Wednesday','Thursday','Friday'
$triggers = @('5:00AM','6:30AM','8:00AM','10:00AM') | ForEach-Object { New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $_ }
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $Name -Action $action -Trigger $triggers -Settings $settings -Description 'STS walls, flip, pin from QQQ/SPY open interest; saved to data\sts_levels' -Force | Out-Null
Write-Host "Installed '$Name': Mon-Fri 5:00, 6:30, 8:00, 10:00 AM."
Write-Host "Running one refresh now so today's levels show up..."
Start-ScheduledTask -TaskName $Name
Write-Host "Done. Log: $repo\data\sts_levels\schedule.log   Saved levels: $repo\data\sts_levels\levels_NQ.csv / levels_ES.csv"
