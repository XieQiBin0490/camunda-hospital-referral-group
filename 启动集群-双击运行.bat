@echo off
title Camunda 8 Run - KEEP THIS WINDOW OPEN
cd /d D:\app\Camunda\c8run-8.10.0-alpha5

echo ============================================================
echo  Starting the local Camunda 8 cluster (DEMONSTRATION mode)
echo.
echo  BOTH overrides below are needed. Role separation needs the API
echo  protected, but the worker fleet needs it open: with
echo  unprotected-api=false the gRPC gateway asks for credentials the
echo  delivered 8.9 client does not send, and every service task parks.
echo  See section 5 of 08_Repository_Documents/running-the-cluster-and-modeler.md
echo ============================================================
echo.
set CAMUNDA_SECURITY_AUTHORIZATIONS_ENABLED=false
set CAMUNDA_SECURITY_AUTHENTICATION_UNPROTECTEDAPI=true

echo ============================================================
echo  Starting the cluster
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
echo  Next, in a second window, start the worker fleet:
echo    cd /d <repository>\04_Java_Worker
echo    "D:\app\Camunda\c8run-8.10.0-alpha5\jre\bin\java.exe" -jar target\hospital-external-workers-1.0.0.jar
echo  It must print: 13 workers subscribed and polling 127.0.0.1:26500
echo.
echo  Tasklist : http://localhost:8080/tasklist
echo  Operate  : http://localhost:8080/operate
echo  Login    : demo / demo
echo ============================================================
pause
