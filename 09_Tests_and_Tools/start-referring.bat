@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Start one referring-organisation instance
echo ============================================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js was not found on PATH.
  echo.
  pause
  exit /b 1
)

if "%~1"=="" (
  node start-referring.mjs
) else (
  node start-referring.mjs %1 %2
)

echo.
pause
