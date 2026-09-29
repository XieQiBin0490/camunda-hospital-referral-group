param(
  [string]$Root = "C:\Users\a1620\Desktop\UFCEP4-0-3_Final"
)
# Regenerate the validation evidence as clean UTF-8 text for the portfolio appendices.
Set-Location $Root
$work = Join-Path $Root "work"
$extract = Join-Path $Root "extract"

$originals = @(
  "..\source\bpmn1.bpmn",
  "..\source\bpmn2_dup.bpmn",
  "..\source\bpmn3.bpmn"
)
$delivered = @(
  "..\output\bpmn\O1_Operational_Merged.bpmn",
  "..\output\bpmn\S1_Strategic_Landscape.bpmn",
  "..\output\bpmn\S2_Strategic_Referral_To_Authorisation.bpmn",
  "..\output\bpmn\S3_Strategic_Treatment_To_Aftercare.bpmn"
)

Push-Location $work
& node --import ./register.mjs check.mjs @originals |
  Out-File -Encoding utf8 -FilePath (Join-Path $extract "audit_originals_raw.txt")
& node --import ./register.mjs check.mjs @delivered |
  Out-File -Encoding utf8 -FilePath (Join-Path $extract "audit_final_raw.txt")
Pop-Location

# PowerShell 5.1 writes UTF-16LE for Out-File -Encoding utf8; normalise to UTF-8.
foreach ($f in @("audit_originals_raw.txt", "audit_final_raw.txt")) {
  $path = Join-Path $extract $f
  $bytes = [System.IO.File]::ReadAllBytes($path)
  if ($bytes.Length -eq 0) { Write-Host "WARNING: $f is empty"; continue }
  if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
    $txt = [System.Text.Encoding]::Unicode.GetString($bytes)
  } else {
    $txt = [System.Text.Encoding]::UTF8.GetString($bytes)
  }
  [System.IO.File]::WriteAllText($path, $txt, (New-Object System.Text.UTF8Encoding($false)))
  Write-Host ("normalised {0} ({1} chars)" -f $f, $txt.Length)
}
Write-Host "done"
