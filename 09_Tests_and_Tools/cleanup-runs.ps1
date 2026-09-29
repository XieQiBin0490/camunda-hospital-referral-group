# Remove the browsers and driver processes left behind by interrupted runs.
# Deliberately narrow: only processes whose command line names this project's own
# drivers, so the harness's own node processes are never touched.
$killed = 0
foreach ($p in Get-CimInstance Win32_Process -Filter "Name='node.exe'") {
  $c = $p.CommandLine
  if ($c -and ($c -like '*tasklist-button*' -or $c -like '*run-all-processes*' -or $c -like '*run-form-tasklist*')) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    $killed++
  }
}
# Edge instances started by puppeteer carry a temporary profile; closing them all is
# safe here because no browser is being used by hand at this moment.
foreach ($p in Get-CimInstance Win32_Process -Filter "Name='msedge.exe'") {
  if ($p.CommandLine -and $p.CommandLine -like '*--remote-debugging-port*') {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    $killed++
  }
}
foreach ($p in Get-CimInstance Win32_Process -Filter "Name='java.exe'") {
  if ($p.CommandLine -and $p.CommandLine -like '*hospital-external-workers*') {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    $killed++
  }
}
Write-Output "cleaned up $killed process(es)"
