@echo off
cd /d "C:\Users\Administrator\Desktop\FXTM App"

set "ROOT=C:\Users\Administrator\Desktop\FXTM App"
set "REPO=%ROOT%\FX_TrendMaster"
set "APP=%ROOT%\trading_gate\app"

if not exist "%REPO%\.git" (
  echo Cloning FX_TrendMaster...
  git clone https://github.com/joshuamoodley06-ux/FX_TrendMaster.git "%REPO%"
) else (
  echo Pulling latest...
  cd /d "%REPO%"
  git pull origin main
  cd /d "%ROOT%"
)

echo Copying updated backend files...
copy /Y "%REPO%\backend\*.py" "%APP%\"
if exist "%REPO%\backend\detector" (
  echo Copying detector package...
  xcopy /E /I /Y "%REPO%\backend\detector" "%APP%\detector\"
)

set "DATABASE_PATH=%APP%\market_memory.db"
set "RAW_MAPPING_DB_PATH=%ROOT%\trading_gate\data\raw_mapping_v159.db"

echo Stopping anything on port 8000...
powershell -NoProfile -Command "$p = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; if ($p) { $p | ForEach-Object { Write-Host ('  Killing PID ' + $_); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } } else { Write-Host '  Port 8000 is free.' }"
timeout /t 3 /nobreak >nul

netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo ERROR: Port 8000 is STILL in use. Do this manually:
  echo   netstat -ano ^| findstr :8000
  echo   taskkill /F /PID ^<number from last column^>
  echo.
  echo Or close the OTHER cmd window that is running the old backend.
  pause
  exit /b 1
)

echo Starting uvicorn...
cd /d "%ROOT%"
python -m uvicorn trading_gate.app.main:app --host 0.0.0.0 --port 8000

pause
