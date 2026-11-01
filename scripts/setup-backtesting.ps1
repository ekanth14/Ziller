$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $projectRoot 'work/environments/backtesting'
$pythonPath = Join-Path $environmentPath 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv $environmentPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create backtesting environment.' }
}
& $pythonPath -m pip install -r (Join-Path $projectRoot 'requirements-backtest.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backtesting dependencies could not be installed.' }
& $pythonPath -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Backtesting dependency validation failed.' }
Write-Host "Backtesting Python: $pythonPath"
