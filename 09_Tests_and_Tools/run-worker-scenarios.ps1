# Drive the worker fleet through every demonstration scenario.
#
#   powershell -File 09_Tests_and_Tools/run-worker-scenarios.ps1
#   powershell -File tools/run-worker-scenarios.ps1        (team workspace)
#
# For each scenario the fleet is restarted with that scenario's environment, a
# worker-driven instance is run (the script plays only the human tasks), and the
# result is written to evidence/worker-run/.
#
# It works both in the team workspace (workers/ next to tools/) and in the
# delivered package (04_Java_Worker/ next to 09_Tests_and_Tools/), and it
# builds the worker jar if it is not there yet.
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

if (Test-Path (Join-Path $here '..\workers\pom.xml')) {
  $root = (Resolve-Path (Join-Path $here '..')).Path
  $workerDir = Join-Path $root 'workers'
} elseif (Test-Path (Join-Path $here '..\04_Java_Worker\pom.xml')) {
  $root = (Resolve-Path (Join-Path $here '..')).Path
  $workerDir = Join-Path $root '04_Java_Worker'
} else {
  throw "cannot locate the worker project from $here"
}
$jar = Join-Path $workerDir 'target\hospital-external-workers-1.0.0.jar'
if (-not (Test-Path $jar)) {
  # the delivered package ships a prebuilt jar, so the scenarios can run without
  # a build toolchain; building from source is the fallback, not the requirement
  $prebuilt = Join-Path $workerDir 'prebuilt\hospital-external-workers-1.0.0.jar'
  if (Test-Path $prebuilt) { $jar = $prebuilt }
}
if (-not (Test-Path $jar)) {
  Write-Host '==> no jar found; building from source'
  $mvn = Join-Path $workerDir '.tools\apache-maven-3.9.9\bin\mvn.cmd'
  if (-not (Test-Path $mvn)) { $mvn = 'mvn' }
  if (-not (Get-Command $mvn -ErrorAction SilentlyContinue)) {
    throw "no worker jar and no Maven. Either build it (mvn -f `"$workerDir\pom.xml`" package) "
      + "or place hospital-external-workers-1.0.0.jar in $workerDir\prebuilt\"
  }
  & $mvn -B -q -f (Join-Path $workerDir 'pom.xml') package
}
if (-not (Test-Path $jar)) { throw "worker jar not found at $jar" }
Write-Host "==> worker jar: $jar"

# evidence lives in evidence/ in the workspace and in 05_Test_Evidence/ in
# the delivered package; either layout must work
$logDir = Join-Path $root 'evidence\worker-run'
if (-not (Test-Path (Join-Path $root 'evidence'))) {
  $logDir = Join-Path $root '05_Test_Evidence\worker-run'
}
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$demo = Join-Path $here 'run-worker-demo.mjs'
if (-not (Test-Path $demo)) { throw "run-worker-demo.mjs is not next to this script ($here)" }

$scenarios = [ordered]@{
  'happy'                = @{}
  'capacity-unavailable' = @{ HPAS_CAPACITY_UNAVAILABLEONCE = 'true' }
  'payment-declined'     = @{ HPAS_PAYMENT_OUTCOME = 'DECLINED' }
  'transient-retry'      = @{ HPAS_FAILURE_MODE = 'rules'; HPAS_FAILURE_PREFIX = 'query-available-appointment-slots' }
  'aftercare-cycles'     = @{}
  'enquiry'              = @{}
}

function Stop-Fleet {
  Get-CimInstance Win32_Process -Filter "Name='java.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*hospital-external-workers*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 2
}

$results = @()
foreach ($name in $scenarios.Keys) {
  Write-Host ""
  Write-Host ("######## {0} ########" -f $name)
  Stop-Fleet

  # clear any scenario variables inherited from the previous iteration
  foreach ($k in @('HPAS_CAPACITY_UNAVAILABLEONCE', 'HPAS_PAYMENT_OUTCOME', 'HPAS_FAILURE_MODE', 'HPAS_FAILURE_PREFIX')) {
    Remove-Item ("Env:" + $k) -ErrorAction SilentlyContinue
  }
  foreach ($kv in $scenarios[$name].GetEnumerator()) { Set-Item ("Env:" + $kv.Key) $kv.Value }

  $out = "$logDir\workers-$name.log"
  $err = "$logDir\workers-$name.err"
  $proc = Start-Process -FilePath 'java' `
    -ArgumentList '--enable-native-access=ALL-UNNAMED', '-jar', $jar `
    -WorkingDirectory $workerDir `
    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden

  # wait until the fleet reports every subscription
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    if ((Test-Path $out) -and (Select-String -Path $out -Pattern 'workers subscribed and polling' -Quiet)) { $ready = $true; break }
  }
  if (-not $ready) { Write-Host "  !! the fleet did not report ready; see $out" }
  else { Write-Host "  fleet up (pid $($proc.Id))" }

  Push-Location $root
  $json = & node $demo $name 2>&1
  $json | ForEach-Object { Write-Host ("  " + $_) }
  $results += $json
  Pop-Location
}

Stop-Fleet
Write-Host ""
Write-Host "=== scenario summaries ==="
Get-ChildItem "$logDir\worker-demo-*.json" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime |
  Select-Object -Last 6 | ForEach-Object {
    $d = Get-Content $_.FullName -Raw | ConvertFrom-Json
    foreach ($r in $d.results) {
      "{0,-5} {1,-22} state={2,-10} instance={3}" -f $r.status, $r.scenario, $r.state, $r.processInstanceKey
    }
  }


