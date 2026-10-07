# Registers a per-user Scheduled Task "MeetingAlarm" that starts the daemon at logon.
# Usage: .\install.ps1    (no admin needed; safe to re-run)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = $null
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    $out = & $py.Source -3 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { $python = ($out | Select-Object -First 1).Trim() }
}
if (-not $python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw 'Python 3.11+ not found. Install it from python.org first.' }
    $python = $cmd.Source
}
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$repo\alarm.py`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName 'MeetingAlarm' -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'MeetingAlarm'
Start-Sleep -Seconds 2
$state = (Get-ScheduledTask -TaskName 'MeetingAlarm').State
Write-Host "MeetingAlarm installed ($pythonw). State: $state"
