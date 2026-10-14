@echo off
setlocal
title Nori AI - Local Job Copilot
cd /d "%~dp0"

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (
  echo A server is already using port 8000.
  echo Close its existing Nori/Tsenta server window, then run this launcher again.
  echo This avoids loading a new interface against an outdated backend.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv. Run: python -m venv .venv
  pause
  exit /b 1
)

pushd "webapp\frontend"
if not exist "node_modules" (
  echo Installing frontend dependencies...
  call npm install
  if errorlevel 1 exit /b 1
)
echo Building Nori AI...
call npm run build
if errorlevel 1 exit /b 1
popd

start "" "http://localhost:8000"
echo Nori AI is running at http://localhost:8000
echo Keep this window open for overnight HiringCafe monitoring.
".venv\Scripts\python.exe" -m uvicorn webapp.server:app --host 127.0.0.1 --port 8000 --no-access-log
