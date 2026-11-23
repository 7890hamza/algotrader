# Loads a backup made by backup-data.ps1 into THIS computer's AlgoTrader. Replaces what's stored here.
#   powershell -ExecutionPolicy Bypass -File scripts\windows\restore-data.ps1 C:\path\algotrader-2026-11-23.dump
# The app must be running (Start everything) so the database exists.
param([Parameter(Mandatory = $true)][string]$DumpFile)
if (-not (Test-Path $DumpFile)) { Write-Host "File not found: $DumpFile" -ForegroundColor Red; exit 1 }
$ok = Read-Host "This REPLACES the candles stored on this computer with the backup. Type yes to continue"
if ($ok -ne "yes") { Write-Host "Cancelled."; exit 0 }
docker cp $DumpFile "timescaledb:/tmp/restore.dump"
docker exec timescaledb sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT timescaledb_pre_restore();" &&
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /tmp/restore.dump;
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT timescaledb_post_restore();"'
docker exec timescaledb rm -f /tmp/restore.dump
docker restart database-accessor-api indicator-api ingestion-service | Out-Null
Write-Host "Restored. Press Ctrl+F5 on the chart page." -ForegroundColor Green
