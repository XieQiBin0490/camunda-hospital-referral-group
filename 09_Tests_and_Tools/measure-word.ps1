# Measure real Calibri advance widths in Word so the TTF model can be checked.
$ErrorActionPreference = 'Stop'
$tests = @('Verdict', 'Measurability', 'REQ-01',
           'S2_Strategic_Referral_To_Authorisation.bpmn')
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
$out = @()
foreach ($bold in @($false, $true)) {
  foreach ($t in $tests) {
    $d = $w.Documents.Add()
    $d.PageSetup.LeftMargin = $w.CentimetersToPoints(2)
    $r = $d.Range()
    $r.Font.Name = 'Calibri'
    $r.Font.Size = 10.5
    $r.Font.Bold = $(if ($bold) { 1 } else { 0 })
    $r.InsertAfter($t)
    $end = $d.Range($t.Length, $t.Length)
    $pos = $end.Information(5)          # wdHorizontalPositionRelativeToPage
    $left = $d.PageSetup.LeftMargin
    $tw = ($pos - $left) * 20
    $out += [pscustomobject]@{ bold = $bold; text = $t; twips = [math]::Round($tw) }
    $d.Close(0)
  }
}
$w.Quit()
$out | Format-Table -AutoSize
