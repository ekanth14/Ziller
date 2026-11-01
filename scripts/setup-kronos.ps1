$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Test-Path -LiteralPath 'work/environments/kronos/Scripts/python.exe')) {
        python -m venv work/environments/kronos
        if ($LASTEXITCODE -ne 0) { throw 'Could not create Kronos environment' }
    }
    & './work/environments/kronos/Scripts/python.exe' -m pip install --cache-dir work/package-cache -r requirements-kronos-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Kronos dependency installation failed' }
    & './work/environments/kronos/Scripts/python.exe' -m cryptoscope.forecasting download
    if ($LASTEXITCODE -ne 0) { throw 'Kronos model download failed' }
    & './work/environments/kronos/Scripts/python.exe' -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Kronos dependencies are inconsistent' }
} finally { Pop-Location }
