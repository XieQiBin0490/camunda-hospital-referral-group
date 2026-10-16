@echo off
chcp 65001 >nul
title Camunda 8 Run - 保持此窗口打开 / KEEP THIS WINDOW OPEN
cd /d D:\app\Camunda\c8run-8.10.0-alpha5

echo ============================================================
echo  Starting the local Camunda 8 cluster
echo  正在启动本地 Camunda 集群
echo.
echo  --disable-connectors is REQUIRED on this machine: the bundled
echo  connectors runtime never starts, and c8run then shuts the whole
echo  cluster down.  Must keep this flag or the cluster dies in minutes.
echo  必须带 --disable-connectors，否则 c8run 会等不到 Connectors
echo  而把整个集群停掉（表现为"集群活几分钟就死了"）。
echo ============================================================
echo.

c8run.exe start --disable-connectors

echo.
echo ============================================================
echo  Startup finished.  THE CLUSTER IS NOW RUNNING.
echo  集群已启动完成。
echo.
echo  *** DO NOT CLOSE THIS WINDOW ***
echo  *** 千万不要关闭这个窗口 ***
echo  Closing it kills the cluster. 关闭窗口 = 关闭集群。
echo.
echo  Tasklist : http://localhost:8080/tasklist
echo  Operate  : http://localhost:8080/operate
echo  Login    : demo / demo
echo.
echo  To stop the cluster, press any key below and then run:
echo    c8run.exe stop
echo  要停止集群：按任意键关闭本窗口，再执行 c8run.exe stop
echo ============================================================
pause
