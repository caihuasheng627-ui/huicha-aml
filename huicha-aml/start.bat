@echo off
set "PYTHON=%~dp0.venv\Scripts\python.exe"
cd /d "%~dp0backend"
start "循证慧查-API" cmd /k ""%PYTHON%" -m uvicorn app.main:app --reload --port 8000"
cd /d "%~dp0frontend"
start "循证慧查-WEB" cmd /k npm run dev
echo 浏览器打开 http://127.0.0.1:5173
