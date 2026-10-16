# Deploy the corrected models and prove the forms resolve as intended.
#
#   pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\fix-and-verify-binding.ps1
#
# The models used to say binding="deployment", an attribute zeebe:formDefinition does not
# have, so the engine ignored it and used the default binding `latest`. An instance then
# rendered whichever version of a form had been deployed most recently by anyone, which is
# how a teammate's older text-box forms replaced the drop-downs, and why a task whose form
# was not in that latest set could not open.
#
# The attribute is corrected to bindingType="deployment". This script puts the corrected
# models and all their forms into one deployment and then checks, through the engine, that
# a real task resolves to the form that has the typed controls.
#
# Everything runs inside this one process: c8run's Java children inherit its stdout, so a
# pipeline would hang until the cluster stopped, and a cluster started in one shell job is
# reaped when that job ends.

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$C8 = 'D:\app\Camunda\c8run-8.10.0-alpha5'
$auth = @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes('demo:demo')) }
$node = if (Get-Command node -ErrorAction SilentlyContinue) { 'node' }
        elseif (Test-Path 'C:\Users\86137\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe') { 'C:\Users\86137\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe' }
        else { 'node' }

function Test-Cluster {
    try {
        return (Invoke-WebRequest -Uri 'http://127.0.0.1:8080/v2/topology' -TimeoutSec 5 `
                -UseBasicParsing -Headers $auth).StatusCode -eq 200
    } catch { return $false }
}

Write-Host '### 1. cluster' -ForegroundColor Cyan
if (-not (Test-Cluster)) {
    Write-Host '  not running; starting c8run (about two minutes)'
    # --disable-connectors is not optional on a machine where the bundled connectors
    # runtime will not start. c8run waits for it, gives up, and then stops the whole
    # cluster - which presents as "Camunda keeps stopping after a few minutes". These
    # processes use job workers, not connectors, so skipping it costs nothing.
    Push-Location $C8
    try { & (Join-Path $C8 'c8run.exe') start --disable-connectors *> (Join-Path $C8 'c8run-start.log') }
    finally { Pop-Location }
    for ($i = 1; $i -le 60 -and -not (Test-Cluster); $i++) { Start-Sleep -Seconds 5 }
}
if (-not (Test-Cluster)) {
    Write-Error 'the cluster did not come up on http://127.0.0.1:8080 - see c8run-start.log'
    exit 2
}
Write-Host '  cluster is up'

Write-Host '### 2. deploy the corrected models with all 69 forms' -ForegroundColor Cyan
& $node (Join-Path $root '09_Tests_and_Tools\deploy-all.mjs') 2>&1 | Select-Object -First 6

Write-Host '### 3. verify that a task resolves to its own form' -ForegroundColor Cyan
& $node (Join-Path $root '09_Tests_and_Tools\verify-form-binding.mjs')
$verdict = $LASTEXITCODE

Write-Host ''
if ($verdict -eq 0) {
    Write-Host 'The drop-downs are back: a task now resolves to the form deployed with its model.' -ForegroundColor Green
} else {
    Write-Host 'The check did not pass - read the FAIL lines above.' -ForegroundColor Yellow
}
Write-Host 'The cluster is left running so you can open Tasklist.'
exit $verdict
