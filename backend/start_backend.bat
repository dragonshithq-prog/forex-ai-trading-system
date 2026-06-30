@echo off
cd /d "C:\Users\USER\Desktop\Forex Trading Bot\backend"
start /B "" "C:\Users\USER\Desktop\Forex Trading Bot\.venv312\Scripts\pythonw.exe" -m uvicorn forex_trading.main:app --host 0.0.0.0 --port 8003 > backend_uvicorn.log 2>&1
echo Backend started with PID %ERRORLEVEL%
