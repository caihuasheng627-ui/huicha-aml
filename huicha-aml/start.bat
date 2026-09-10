@echo off
cd /d "%~dp0backend"
start "慧查AML-API" cmd /k py -m uvicorn app.main:app --reload --port 8000
cd /d "%~dp0frontend"
start "慧查AML-WEB" cmd /k npm run dev
echo 浏览器打开 http://127.0.0.1:5173
