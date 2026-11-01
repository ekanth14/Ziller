$ErrorActionPreference = 'Stop'
$projectPath = Split-Path $PSScriptRoot -Parent
$pythonPath = (Get-Command python).Source
$logPath = Join-Path $projectPath 'work/autotrader'
New-Item -ItemType Directory -Force -Path $logPath > $null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-B', '-m', 'cryptoscope.autotrader', 'start') -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logPath "engine-$stamp.out.log") -RedirectStandardError (Join-Path $logPath "engine-$stamp.err.log") -PassThru
Write-Output "Laya paper bot launched with PID $($process.Id)."
Write-Output 'Status: python -m cryptoscope.autotrader status'
Write-Output 'Pause entries: python -m cryptoscope.autotrader pause-entries'
Write-Output 'Stop: python -m cryptoscope.autotrader stop'
