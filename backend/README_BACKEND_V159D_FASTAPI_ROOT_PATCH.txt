Backend v159d FastAPI Raw Mapping Root Patch

Purpose:
- This patch is for the ACTUAL VPS backend structure, which is Python/FastAPI.
- It must be copied into the APP ROOT:
  C:\Users\Administrator\Desktop\FXTM App\trading_gate\app
- Do NOT copy into lifecycle_engine. That was the previous folder trap.

Files:
- main.py
- candle_store.py
- INSTALL_V159D.ps1
- QUICK_TEST_V159D.ps1

What it includes:
- /api/v1/raw-mapping/cases
- /api/v1/raw-mapping/events
- /api/v1/raw-mapping/events/batch
- /api/v1/raw-mapping/events/delete
- /api/v1/raw-mapping/events?case_id=...
- /api/v1/raw-mapping/events/export?case_id=...

DB path:
- Uses DATABASE_PATH when provided.
- Intended path on your VPS:
  C:\Users\Administrator\Desktop\FXTM App\trading_gate\data\raw_mapping_v159.db

Install simple steps:
1. Extract this zip somewhere temporary, like Desktop\backend_v159d_patch.
2. Copy main.py and candle_store.py into:
   C:\Users\Administrator\Desktop\FXTM App\trading_gate\app
   replacing the files there.
3. In PowerShell:
   cd "C:\Users\Administrator\Desktop\FXTM App\trading_gate\app"
   $env:DATABASE_PATH="C:\Users\Administrator\Desktop\FXTM App\trading_gate\data\raw_mapping_v159.db"
   netstat -ano | findstr :8000
   taskkill /PID <PID> /F
   python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug

4. In a second PowerShell window, test:
   cd "C:\Users\Administrator\Desktop\FXTM App\trading_gate\app"
   .\QUICK_TEST_V159D.ps1

Expected:
- POST /api/v1/raw-mapping/cases returns ok true and a case object/id.
