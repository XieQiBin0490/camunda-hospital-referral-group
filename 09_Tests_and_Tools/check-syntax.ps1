# Parse every PowerShell script we ship, without running it. Catches the class of
# error that PowerShell 5.1 accepts at load time but rejects at parse time (a
# string concatenation across lines inside a hash literal, for one).
$files = @(
  'verify-all.ps1', 'run-worker-scenarios.ps1', 'measure-word.ps1',
  'probe-tables.ps1', 'pages.ps1', 'find-page.ps1'
)
$bad = 0
foreach ($f in $files) {
  $path = Join-Path $PSScriptRoot $f
  if (-not (Test-Path $path)) { Write-Host "  missing  $f" -ForegroundColor Yellow; continue }
  $errors = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errors)
  if ($errors -and $errors.Count) {
    $bad++
    Write-Host ("  FAIL     {0}  ({1} parse error(s))" -f $f, $errors.Count) -ForegroundColor Red
    $errors | Select-Object -First 3 | ForEach-Object {
      Write-Host ("             line {0}: {1}" -f $_.Extent.StartLineNumber, $_.Message) -ForegroundColor Red
    }
  } else {
    Write-Host ("  ok       {0}" -f $f) -ForegroundColor Green
  }
}
Write-Host ''
Write-Host ("  {0} of {1} script(s) parsed cleanly" -f ($files.Count - $bad), $files.Count)
exit $(if ($bad -eq 0) { 0 } else { 1 })
