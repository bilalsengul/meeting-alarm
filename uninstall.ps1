# Stops and removes the "MeetingAlarm" Scheduled Task.
# Usage: .\uninstall.ps1 [-Purge]    (-Purge also deletes the data dir with credentials and logs)
param([switch]$Purge)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$task = Get-ScheduledTask -TaskName 'MeetingAlarm' -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName 'MeetingAlarm' -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName 'MeetingAlarm' -Confirm:$false
    Write-Host 'MeetingAlarm task removed.'
} else {
    Write-Host 'MeetingAlarm task not found.'
}

if ($Purge) {
    $dir = if ($env:MEETING_ALARM_HOME) { $env:MEETING_ALARM_HOME } else { Join-Path $env:USERPROFILE '.meeting-alarm' }
    if (Test-Path $dir) {
        Remove-Item -Recurse -Force $dir
        Write-Host "Removed $dir"
    }
}
