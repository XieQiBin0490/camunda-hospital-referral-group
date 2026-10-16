# Turn API protection on or off in the local Camunda 8 Run configuration.
#
#   pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-api-protection.ps1 on
#   pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-api-protection.ps1 off
#   pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-api-protection.ps1 show
#
# on   authorization is enforced. Camunda Modeler and the worker fleet must send
#      credentials (demo / demo). This is what makes role-based access control real, and it
#      is what the RBAC evidence was recorded with.
# off  the REST and gRPC APIs skip permission checks, so anything can connect. Role
#      separation stops being enforced - useful while modelling, not while demonstrating it.
#
# Changing this file needs a cluster restart to take effect:
#   cd D:\app\Camunda\c8run-8.10.0-alpha5
#   .\c8run.exe stop
#   .\c8run.exe start --disable-connectors
#
# --disable-connectors matters: the bundled connectors runtime does not start on this
# machine, and c8run stops the whole cluster when it gives up waiting for it.

param(
    [Parameter(Position = 0)]
    [ValidateSet('on', 'off', 'show')]
    [string]$Mode = 'show'
)

$ErrorActionPreference = 'Stop'
$config = 'D:\app\Camunda\c8run-8.10.0-alpha5\configuration\application.yaml'

if (-not (Test-Path $config)) {
    Write-Error "not found: $config"
    exit 2
}

$text = Get-Content $config -Raw

# Show the two lines that matter.
$show = {
    foreach ($n in 25, 27) {
        $line = ($text -split "`r?`n")[$n - 1]
        if ($line) { Write-Host ("  line {0}: {1}" -f $n, $line.Trim()) }
    }
}

if ($Mode -eq 'show') {
    Write-Host "current settings in $config"
    & $show
    Write-Host ''
    Write-Host '  on  = authorization enforced (Modeler and workers need demo / demo)'
    Write-Host '  off = permission checks skipped (anything can connect)'
    exit 0
}

$backup = "$config.bak-before-rbac"
if (-not (Test-Path $backup)) {
    Copy-Item $config $backup
    Write-Host "  kept a backup at $(Split-Path $backup -Leaf)"
}

$want = if ($Mode -eq 'on') { 'false' } else { 'true' }   # unprotected-api: false = protection ON
$old = if ($Mode -eq 'on') { 'true' } else { 'false' }

if ($text -notmatch '(?m)^\s*unprotected-api:\s*(true|false)\s*$') {
    Write-Error 'could not find the unprotected-api line; edit the file by hand'
    exit 2
}
$current = [regex]::Match($text, '(?m)^\s*unprotected-api:\s*(true|false)\s*$').Groups[1].Value
if ($current -eq $want) {
    Write-Host "  already set for '$Mode' (unprotected-api: $current) - nothing changed"
} else {
    $text = [regex]::Replace($text, '(?m)^(\s*unprotected-api:\s*)(true|false)(\s*)$',
                             "`${1}$want`${3}")
    Set-Content -Path $config -Value $text -NoNewline -Encoding utf8
    Write-Host "  unprotected-api: $old -> $want"
    Write-Host "  authorizations stays enabled: $(if ($text -match '(?m)^\s*enabled:\s*true') { 'true' } else { 'check the file' })"
}

Write-Host ''
Write-Host 'Restart the cluster for this to take effect:'
Write-Host '  cd D:\app\Camunda\c8run-8.10.0-alpha5'
Write-Host '  .\c8run.exe stop'
Write-Host '  .\c8run.exe start --disable-connectors'
Write-Host ''
if ($Mode -eq 'off') {
    Write-Host 'With protection off, role separation is no longer enforced.' -ForegroundColor Yellow
    Write-Host 'Show the RBAC evidence from 05_Test_Evidence/rbac/task-visibility.json instead.' -ForegroundColor Yellow
}
