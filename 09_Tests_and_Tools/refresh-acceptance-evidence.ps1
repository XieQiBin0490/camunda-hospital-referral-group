# Refresh the acceptance evidence against the currently deployed models.
#
#   pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\refresh-acceptance-evidence.ps1
#
# The script is not code-signed, so a machine with the default execution policy needs the
# bypass above; from an already open session, `Set-ExecutionPolicy -Scope Process Bypass`
# does the same thing.
#
# Why this exists
# ---------------
# 05_Test_Evidence/acceptance-run.json is the acceptance evidence the plan and the
# portfolio cite. It was produced on 27 September against the models as they were then,
# and item 3 of the review list has since changed three BPMN models and added a 69th form,
# so that file no longer describes what is deployed. Running run-acceptance.mjs alone is
# not enough either: without the worker fleet the process instances park on their first
# service task, and the recorded results would be failures that say nothing about the
# model.
#
# So this script does the whole sequence, in the right order, and checks that each step
# actually happened instead of assuming it:
#
#   1. the cluster answers, or is started and waited for
#   2. the models and forms are deployed (deploy-all.mjs)
#   3. the worker database is cleared, so the fleet can write to it
#   4. the worker fleet is running and subscribed
#   5. run-acceptance.mjs executes the cases and writes the evidence in place
#   6. PersistenceCheck dump shows what the fleet stored during those runs
#
# Step 3 is not cosmetic: H2 cannot acquire its file lock in every environment, and where
# it cannot, an existing database file is opened read-only, so a fleet that was already
# running would fail every store call. See 08_Repository_Documents/database-integration.md.

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$C8 = 'D:\app\Camunda\c8run-8.10.0-alpha5'
$auth = @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes('demo:demo')) }
$java = if (Get-Command java -ErrorAction SilentlyContinue) { 'java' }
        elseif (Test-Path 'C:\Users\86137\.jdks\valhalla-ea-23\bin\java.exe') { 'C:\Users\86137\.jdks\valhalla-ea-23\bin\java.exe' }
        else { 'java' }
$node = if (Get-Command node -ErrorAction SilentlyContinue) { 'node' }
        elseif (Test-Path 'C:\Users\86137\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe') { 'C:\Users\86137\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe' }
        else { 'node' }
$jar = Join-Path $root '04_Java_Worker\target\hospital-external-workers-1.0.0.jar'
$evidence = Join-Path $root '05_Test_Evidence'

function Test-Cluster {
    try {
        return (Invoke-WebRequest -Uri 'http://127.0.0.1:8080/v2/topology' -TimeoutSec 5 `
                -UseBasicParsing -Headers $auth).StatusCode -eq 200
    } catch { return $false }
}

Write-Host '### 1. cluster' -ForegroundColor Cyan
if (-not (Test-Cluster)) {
    Write-Host '  not answering; starting c8run'
    # c8run resolves configuration/application.yaml relative to its own directory, so it has
    # to be launched from there.
    #
    # Its output goes to a file, NOT down a pipeline. The Java processes c8run launches
    # inherit its stdout, so `c8run start | Select-Object -Last 3` does not return when
    # c8run exits - the pipeline stays open until those children close it, which is when
    # the cluster stops. Piping it hangs this script until the cluster is gone.
    Push-Location $C8
    try { & (Join-Path $C8 'c8run.exe') start *> (Join-Path $C8 'c8run-start.log') }
    finally { Pop-Location }
    for ($i = 1; $i -le 50 -and -not (Test-Cluster); $i++) { Start-Sleep -Seconds 6 }
}
if (-not (Test-Cluster)) {
    Write-Error 'the cluster did not come up on http://127.0.0.1:8080'
    exit 2
}
Write-Host '  cluster is up'

Write-Host '### 2. deploy models and forms' -ForegroundColor Cyan
& node (Join-Path $root '09_Tests_and_Tools\deploy-all.mjs') 2>&1 | Select-Object -First 5

Write-Host '### 3. clear the worker database' -ForegroundColor Cyan
Remove-Item -Recurse -Force (Join-Path $root 'data') -ErrorAction SilentlyContinue
Write-Host "  data/ exists: $(Test-Path (Join-Path $root 'data'))"

Write-Host '### 4. start the worker fleet' -ForegroundColor Cyan
if (-not (Test-Path $jar)) {
    Write-Error "build the workers first: mvn -o -f 04_Java_Worker/pom.xml package"
    exit 2
}
# A detached Node spawn is used rather than Start-Process or Start-Job: neither of those
# reliably produces a running child in a confined environment, and a shell job would tie
# the fleet to this script's process tree so that stopping the script stops the fleet.
& $node (Join-Path $root '09_Tests_and_Tools\spawn-workers.mjs') --wait 40
$pidFile = Join-Path $evidence 'worker-fleet.pid'
$fleetPid = if (Test-Path $pidFile) { [int](Get-Content $pidFile -Raw).Trim() } else { 0 }
Write-Host "  fleet pid: $fleetPid"

Write-Host '### 5. run the acceptance cases' -ForegroundColor Cyan
& node (Join-Path $root '09_Tests_and_Tools\run-acceptance.mjs') *>&1 |
    Tee-Object -FilePath (Join-Path $evidence 'acceptance-rerun.log') | Select-Object -Last 12

Write-Host '### 6. what the fleet stored' -ForegroundColor Cyan
& $java -cp $jar uk.ac.uwe.hospital.PersistenceCheck dump 2>&1 |
    Tee-Object -FilePath (Join-Path $evidence 'persistence\run-4-acceptance-dump.txt') | Select-Object -First 20

Write-Host '### 7. stop the fleet (the cluster is left running)' -ForegroundColor Cyan
if ($fleetPid -gt 0) {
    Stop-Process -Id $fleetPid -Force -ErrorAction SilentlyContinue
    Write-Host "  stopped fleet pid $fleetPid"
}
Write-Host "  cluster still up: $(Test-Cluster)"
Write-Host ''
Write-Host 'Evidence refreshed:'
Write-Host "  $evidence\acceptance-run.json"
Write-Host "  $evidence\acceptance-run.log"
Write-Host "  $evidence\acceptance-rerun.log"
