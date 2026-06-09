@echo off
cd /d "C:\Users\Administrator\Desktop\FXTM App"

set DATABASE_PATH=C:\Users\Administrator\Desktop\FXTM App\trading_gate\app\market_memory.db
set RAW_MAPPING_DB_PATH=C:\Users\Administrator\Desktop\FXTM App\trading_gate\data\raw_mapping_v159.db

python -m uvicorn trading_gate.app.main:app --host 0.0.0.0 --port 8000

pause
