# Choose how the models bind their forms: deployment (strict) or latest (convenient).
#
#   pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-form-binding.ps1 show
#   pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-form-binding.ps1 deployment
#   pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-form-binding.ps1 latest
#
# deployment (recommended, and what the delivered models use)
#   An instance renders the form deployed in its OWN deployment. Nobody else's upload can
#   change what a running process shows. The cost: a .bpmn cannot be deployed on its own -
#   the Modeler's Deploy button will fail with "expected to find form with id X in current
#   deployment" - so deploy with 09_Tests_and_Tools/deploy-all.mjs, which sends the model
#   and its forms together.
#
# latest
#   An instance renders whichever version of the form was deployed most recently, by
#   anyone. This is what the models used to do by accident, when they said
#   binding="deployment" - an attribute that does not exist, so the engine ignored it and
#   used this default. It is why the Modeler's Deploy button used to work, and also why a
#   teammate deploying their own copy of the forms made every drop-down disappear. Use it
#   while editing models freely, then switch back before you rely on the behaviour.
#
# Changing this edits all four .bpmn files. Deploy again afterwards:
#   node 09_Tests_and_Tools/deploy-all.mjs

param(
    [Parameter(Position = 0)]
    [ValidateSet('show', 'deployment', 'latest')]
    [string]$Mode = 'show'
)

$ErrorActionPreference = 'Stop'
$models = Join-Path (Split-Path -Parent $PSScriptRoot) '02_BPMN_Models'

$files = Get-ChildItem $models -Filter '*.bpmn'
if (-not $files) { Write-Error "no .bpmn files in $models"; exit 2 }

if ($Mode -eq 'show') {
    Write-Host 'current form binding in the four models:'
    foreach ($f in $files) {
        $t = Get-Content $f.FullName -Raw
        $dep = ([regex]::Matches($t, 'bindingType="deployment"')).Count
        $lat = ([regex]::Matches($t, 'bindingType="latest"')).Count
        $bad = ([regex]::Matches($t, 'formDefinition[^>]*\sbinding="')).Count
        Write-Host ("  {0,-46} deployment={1,-3} latest={2,-3} wrong attribute={3}" -f $f.Name, $dep, $lat, $bad)
    }
    Write-Host ''
    Write-Host '  deployment = strict, deploy with deploy-all.mjs (Modeler Deploy button will fail)'
    Write-Host '  latest     = convenient, Modeler Deploy button works (forms can be hijacked)'
    exit 0
}

$total = 0
foreach ($f in $files) {
    $t = Get-Content $f.FullName -Raw
    $n = ([regex]::Matches($t, 'bindingType="[^"]*"')).Count
    if ($n -eq 0) {
        Write-Warning "  $($f.Name): no bindingType attribute found - run fix-form-binding.py first"
        continue
    }
    $t2 = [regex]::Replace($t, 'bindingType="[^"]*"', "bindingType=`"$Mode`"")
    if ($t2 -ne $t) {
        Set-Content -Path $f.FullName -Value $t2 -NoNewline -Encoding utf8
        $total += $n
    }
    Write-Host ("  {0,-46} {1} attribute(s) -> bindingType=`"{2}`"" -f $f.Name, $n, $Mode)
}

Write-Host ''
Write-Host "$total attribute(s) set to '$Mode'."
if ($Mode -eq 'deployment') {
    Write-Host ''
    Write-Host 'Deploy with the script - the Modeler Deploy button cannot send the forms:' -ForegroundColor Cyan
    Write-Host '  node 09_Tests_and_Tools\deploy-all.mjs'
} else {
    Write-Host ''
    Write-Host 'The Modeler Deploy button will now succeed, but an instance uses whatever form' -ForegroundColor Yellow
    Write-Host 'version was deployed most recently by anyone, so keep 03_Forms as the single' -ForegroundColor Yellow
    Write-Host 'source of truth and never deploy a personal copy.' -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'Deploy again for this to take effect:'
Write-Host '  node 09_Tests_and_Tools\deploy-all.mjs'
