@echo off
setlocal
cd /d "C:\Users\Administrator\Desktop\FXTM App\FX_TrendMaster"

set "DB=C:\Users\Administrator\Desktop\FXTM App\trading_gate\app\market_memory.db"
set "SCRIPT=scripts\hard_delete_orphans_sqlite.py"

if not exist "%DB%" (
  echo ERROR: Database not found:
  echo   %DB%
  pause
  exit /b 1
)

if not exist "%SCRIPT%" (
  echo ERROR: Script not found:
  echo   %CD%\%SCRIPT%
  echo Copy FX_TrendMaster repo to VPS or git pull first.
  pause
  exit /b 1
)

echo === Dry run (orphans to delete) ===
python "%SCRIPT%" --db "%DB%" --dry-run
echo.

set /p CONFIRM=Type DELETE and press Enter to permanently remove orphans (Macro 152 tree stays): 
if /I not "%CONFIRM%"=="DELETE" (
  echo Cancelled.
  pause
  exit /b 0
)

echo === Hard delete ===
python "%SCRIPT%" --db "%DB%" --execute
echo.
echo Done. Reload master case in Cockpit.
pause
