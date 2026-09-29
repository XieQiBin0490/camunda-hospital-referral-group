@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Hospital external workers - build and start
echo ============================================================
echo.

where mvn >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Maven not found on PATH.
  echo         Install Maven, or add its bin folder to PATH, then run this again.
  echo.
  pause
  exit /b 1
)

echo [1/2] Building the worker jar ^(mvn clean package^) ...
echo.
call mvn -B clean package
if errorlevel 1 (
  echo.
  echo [ERROR] The build FAILED. The red messages above say why - send them on.
  echo.
  pause
  exit /b 1
)

echo.
echo [2/2] Starting the worker fleet. LEAVE THIS WINDOW OPEN.
echo       You want to see: 13 workers subscribed and polling 127.0.0.1:26500
echo       Press Ctrl+C to stop.
echo.
java --enable-native-access=ALL-UNNAMED -jar "target\hospital-external-workers-1.0.0.jar"

echo.
echo The worker fleet has stopped.
pause
