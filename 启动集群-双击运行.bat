@echo off
title Camunda 8 Run - KEEP THIS WINDOW OPEN
cd /d D:\app\Camunda\c8run-8.10.0-alpha5

echo ============================================================
echo  Starting the local Camunda 8 cluster
echo.
echo  The flag --disable-connectors is REQUIRED on this machine:
echo  the bundled connectors runtime never starts, and c8run then
echo  shuts the whole cluster down a few minutes after launch.
echo ============================================================
echo.

c8run.exe start --disable-connectors

echo.
echo ============================================================
echo  Startup finished. The cluster is RUNNING.
echo.
echo  *** DO NOT CLOSE THIS WINDOW ***
echo  Closing it stops the cluster, and then Camunda Modeler
echo  reports: Cannot connect to Orchestration Cluster.
echo.
echo  Tasklist : http://localhost:8080/tasklist
echo  Operate  : http://localhost:8080/operate
echo  Login    : demo / demo
echo ============================================================
pause
