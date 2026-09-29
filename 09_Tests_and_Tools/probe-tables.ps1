# Probe how Word actually lays out each table: declared widths vs the widths
# Word needs for the content. A table whose required width exceeds the text
# column is the one that gets cut off on the right in Word/WPS.
param([Parameter(Mandatory=$true)][string]$Path, [switch]$AutoFit)
$ErrorActionPreference='Stop'
$w = New-Object -ComObject Word.Application
$w.Visible=$false; $w.DisplayAlerts=0
$d = $w.Documents.Open((Resolve-Path $Path).Path, $false, $false)
$usable = $d.PageSetup.PageWidth - $d.PageSetup.LeftMargin - $d.PageSetup.RightMargin
"file    : $(Split-Path $Path -Leaf)"
"usable  : {0:N1} pt" -f $usable
$i = 0
foreach ($t in $d.Tables) {
  $i++
  $t.PreferredWidthType = 3          # wdPreferredWidthAuto / keep as authored
  $declared = 0.0
  for ($c=1; $c -le $t.Columns.Count; $c++) { $declared += $t.Columns($c).Width }
  $need = $null
  if ($AutoFit) {
    $t.AutoFitBehavior(1)            # wdAutoFitContent
    $s = 0.0
    for ($c=1; $c -le $t.Columns.Count; $c++) { $s += $t.Columns($c).Width }
    $need = $s
  }
  $flag = ''
  if ($declared -gt $usable + 1) { $flag = '  <== WIDER THAN TEXT COLUMN' }
  if ($need -ne $null -and $need -gt $usable + 1) { $flag += '  <== NEEDS MORE THAN PAGE' }
  "t{0,-3} rows={1,-4} cols={2,-3} declared={3,7:N1}pt  needed={4}" -f `
      $i, $t.Rows.Count, $t.Columns.Count, $declared, `
      $(if ($need -ne $null) { '{0,7:N1}pt' -f $need } else { '   -   ' }) + $flag
}
$d.Close(0); $w.Quit()
