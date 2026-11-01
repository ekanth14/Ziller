$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -B -m cryptoscope.risk_tools --demo
    if ($LASTEXITCODE -ne 0) { throw 'Clodds risk installation verification failed.' }
    node --test (Join-Path $projectRoot 'integrations/clodds-risk/tests/risk.test.mjs')
    if ($LASTEXITCODE -ne 0) { throw 'Clodds risk tests failed.' }
} finally {
    Pop-Location
}
