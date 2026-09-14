@echo off
setlocal
cd /d "%~dp0"

set "PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0backend\.venv\Scripts\python.exe" set "PYTHON=%~dp0backend\.venv\Scripts\python.exe"
if not defined PYTHON (
  where py >nul 2>&1 && set "PYTHON=py -3"
)
if not defined PYTHON (
  where python >nul 2>&1 && set "PYTHON=python"
)
if not defined PYTHON (
  echo [错误] 未找到 Python。请先安装 Python，或在 huicha-aml 下创建：
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\python -m pip install -r backend\requirements-dev.txt
  pause
  exit /b 1
)

echo 使用解释器: %PYTHON%
cd /d "%~dp0backend"
start "循证慧查-API" cmd /k %PYTHON% -m uvicorn app.main:app --reload --port 8000
cd /d "%~dp0frontend"
if not exist "node_modules\" (
  echo 前端依赖未安装，正在 npm install ...
  call npm install
)
start "循证慧查-WEB" cmd /k npm run dev
echo.
echo 后端 http://127.0.0.1:8000
echo 前端 http://127.0.0.1:5173
echo 若 API 窗口报 ModuleNotFoundError，在 backend 目录执行：
echo   %PYTHON% -m pip install -r requirements-dev.txt
endlocal
