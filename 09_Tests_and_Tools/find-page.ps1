# Find the page number of a heading/text in a .docx, using Word's own layout.
param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)][string]$Find)
$ErrorActionPreference='Stop'
$w = New-Object -ComObject Word.Application
$w.Visible=$false; $w.DisplayAlerts=0
$d = $w.Documents.Open((Resolve-Path $Path).Path, $false, $true)
$total = $d.ComputeStatistics(2)
$hits = 0
foreach ($p in $d.Paragraphs) {
  $t = $p.Range.Text.Trim()
  if ($t -like "*$Find*") {
    $hits++
    "  page {0,-3} of {1}  | {2}" -f $p.Range.Information(3), $total, $t.Substring(0, [Math]::Min(78, $t.Length))
  }
}
if (-not $hits) { "  NOT FOUND in $(Split-Path $Path -Leaf)" }
$d.Close(0); $w.Quit()
