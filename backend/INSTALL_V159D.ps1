# Backend v159d FastAPI Raw Mapping Root Patch Installer
# Run this from inside: C:\Users\Administrator\Desktop\FXTM App\trading_gate\app

$ErrorActionPreference = "Stop"

$appDir = Get-Location
$dataDir = Join-Path $appDir.Parent.FullName "data"
$dbPath = Join-Path $dataDir "raw_mapping_v159.db"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "App folder: $appDir"
Write-Host "Data folder: $dataDir"
Write-Host "DB path: $dbPath"

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

if (Test-Path ".\main.py") {
  Copy-Item ".\main.py" ".\main_backup_before_v159d_$stamp.py" -Force
  Write-Host "Backed up main.py"
}
if (Test-Path ".\candle_store.py") {
  Copy-Item ".\candle_store.py" ".\candle_store_backup_before_v159d_$stamp.py" -Force
  Write-Host "Backed up candle_store.py"
}

# Assumes this script is run from the extracted patch folder OR app folder with patch files beside it.
# If running from patch folder, pass app folder manually instead. Easiest method: copy main.py/candle_store.py from this patch into app root.
Write-Host ""
Write-Host "MANUAL COPY NOTE:"
Write-Host "Copy main.py and candle_store.py from this patch folder into your app root:"
Write-Host "  C:\Users\Administrator\Desktop\FXTM App\trading_gate\app"
Write-Host "Then run the restart commands below."
Write-Host ""

setx DATABASE_PATH $dbPath | Out-Null
$env:DATABASE_PATH = $dbPath
Write-Host "DATABASE_PATH set for this session and future sessions."

Write-Host ""
Write-Host "Now restart backend manually:"
Write-Host "  netstat -ano | findstr :8000"
Write-Host "  taskkill /PID <PID> /F"
Write-Host "  python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug"
