# Convenience wrapper for the hospital external workers (Windows).
#
#   .\run-workers.ps1                      # build if needed, then run
#   $env:REBUILD=1; .\run-workers.ps1      # force a clean rebuild first
#   $env:HPAS_PAYMENT_OUTCOME='DECLINED'; .\run-workers.ps1
#
# Every configuration key in src/main/resources/workers.properties can be
# overridden from the environment as HPAS_<KEY> in upper case with dots replaced
# by underscores - see DEPLOYMENT.md.
[CmdletBinding()]
param(
  [switch]$Rebuild,
  [string]$Config = ''
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$Jar = 'target/hospital-external-workers-1.0.0.jar'
$Mvn = Join-Path $PSScriptRoot '.tools/apache-maven-3.9.9/bin/mvn.cmd'
if (-not (Test-Path $Mvn)) { $Mvn = 'mvn' }   # fall back to a system Maven

if ($Rebuild -or -not (Test-Path $Jar)) {
  Write-Host "==> building $Jar"
  & $Mvn -B -q clean package
  if ($LASTEXITCODE -ne 0) { throw "build failed" }
}

if (-not $env:HPAS_GATEWAY_ADDRESS) {
  Write-Host '==> using the packaged gateway address (127.0.0.1:26500)'
  Write-Host '    set HPAS_GATEWAY_ADDRESS to point somewhere else'
}

# --enable-native-access silences the netty/protobuf warnings on JDK 22+
$jvmArgs = @('--enable-native-access=ALL-UNNAMED')
& java @jvmArgs -jar $Jar
