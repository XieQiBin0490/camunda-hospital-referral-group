@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Deploy every model and form to the local Camunda 8 cluster
echo ============================================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js was not found on PATH.
  echo         Install Node.js 18 or later and run this again.
  echo.
  pause
  exit /b 1
)

node deploy-all.mjs
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo [ERROR] deploy-all.mjs reported a failure. The messages above say why.
) else (
  echo Look for the line:  PR_ReferringOrganisation  v3  ...
  echo If it says v3, the fixed model is now live.
)
echo.
pause
