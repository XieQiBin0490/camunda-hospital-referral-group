$ErrorActionPreference='Stop'
$files = @($args)
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
foreach ($f in $files) {
  $d = $w.Documents.Open((Resolve-Path $f).Path, $false, $true)
  "{0,-46} pages={1,-4} words={2}" -f (Split-Path $f -Leaf), $d.ComputeStatistics(2), $d.ComputeStatistics(0)
  $d.Close(0)
}
$w.Quit()
