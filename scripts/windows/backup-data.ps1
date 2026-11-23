# Saves ALL of AlgoTrader's stored candles and settings (the database) to one file, to copy to another computer.
#   powershell -ExecutionPolicy Bypass -File scripts\windows\backup-data.ps1
# The app must be running (Start everything). Output: backups\algotrader-YYYY-MM-DD.dump
$Root = (Resolve-Path "$PSScriptRoot\..\..").Path
$Out = "$Root\backups"; New-Item -ItemType Directory -Force -Path $Out | Out-Null
$File = "algotrader-$(Get-Date -Format yyyy-MM-dd).dump"
Write-Host "Backing up the database (a few minutes for a big history)..."
docker exec timescaledb sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/backup.dump'
if ($LASTEXITCODE -ne 0) { Write-Host "Backup failed. Is the app running?" -ForegroundColor Red; exit 1 }
docker cp "timescaledb:/tmp/backup.dump" "$Out\$File"
docker exec timescaledb rm -f /tmp/backup.dump
Write-Host "Saved: $Out\$File  ($([math]::Round((Get-Item "$Out\$File").Length / 1MB)) MB)" -ForegroundColor Green
Write-Host "Copy that file to the other computer and run restore-data.ps1 there."
