@echo off
REM One click: start the whole walkthrough.
REM
REM   Double-click this file, then leave it alone. A browser opens on Tasklist,
REM   logs in as demo/demo, and works the real Camunda Forms one after another -
REM   nineteen of them on the operational path - while the automated activities are
REM   done by the Java job workers in the background.
REM
REM The cluster must already be running:
REM   C:\Users\a1620\Desktop\camunda8-getting-started-bundle-8.10.0-alpha5-windows-x86_64\c8run-8.10.0-alpha5\c8run.exe start
title UFCEP4-0-3 run the whole process
cd /d "%~dp0"

REM STEP_DELAY_MS is how long the run pauses on each form, so a person can see it.
if "%STEP_DELAY_MS%"=="" set STEP_DELAY_MS=3500

echo.
echo   Running the whole process.
echo   The browser will open, fill every form and complete every task it can.
echo   Nineteen forms on the operational path; the instance should end COMPLETED.
echo.
echo   Pause between forms: %STEP_DELAY_MS% ms   (set STEP_DELAY_MS to change it)
echo.
node "%~dp0tools\run-form-tasklist.mjs"
echo.
echo   Finished. Evidence is in 05_Test_Evidence\form-demo
echo.
pause
