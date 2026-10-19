# ==============================================================================
# Aviation Briefing - Windows Task Scheduler Setup
# Registers a background scheduled task that runs every 2 hours to collect official
# airline posts and analyst signals, and publish them to the GitHub data branch.
# ==============================================================================

$taskName = "AviationBriefingSocialCollector"
$cmdScript = "Q:\DEV\aviation-briefing-app\scripts\run_social_collector.cmd"
$workingDir = "Q:\DEV\aviation-briefing-app"

Write-Host "Configuring Windows Scheduled Task: $taskName..." -ForegroundColor Cyan

# Check if script exists
if (-not (Test-Path $cmdScript)) {
    Write-Error "Runner script not found at $cmdScript"
    exit 1
}

# Define Action (launch cmd silently)
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$cmdScript`"" -WorkingDirectory $workingDir

# Define Triggers:
# 1. At logon of the current user
# 2. Every 2 hours indefinitely
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerInterval = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 2)

# Define Settings (allow running on battery, wake if sleep, hide window)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

# Unregister old task if present
try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}

# Register new scheduled task for the current user
try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($triggerLogon, $triggerInterval) -Settings $settings -Description "Automated airline and aviation analyst social radar collector for the Aviation Briefing App."
    Write-Host "✅ Scheduled Task '$taskName' successfully registered!" -ForegroundColor Green
    Write-Host "   - Frequency: Every 2 hours + at user login" -ForegroundColor Yellow
    Write-Host "   - Script: $cmdScript" -ForegroundColor Yellow
    Write-Host "   - Logs: $workingDir\output\social_collector.log" -ForegroundColor Yellow
} catch {
    Write-Warning "Could not register via PowerShell cmdlet: $($_.Exception.Message)"
    Write-Host "Attempting fallback via schtasks.exe..." -ForegroundColor Cyan
    schtasks /create /tn "$taskName" /tr "cmd.exe /c `"$cmdScript`"" /sc HOURLY /mo 2 /f
}
