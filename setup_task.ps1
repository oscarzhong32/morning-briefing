# Morning Briefing — Windows Task Scheduler Setup Script
# Run this in PowerShell as Administrator to install the daily briefing automation

$ErrorActionPreference = "Stop"
$ScriptPath = "C:\Users\ZhuanZ\Documents\Codex\2026-06-19\new-chat-2\outputs\morning_briefing\morning_briefing.py"
$PythonPath = "C:\Users\ZhuanZ\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$TaskName = "MorningFinancialBriefing"
$WorkingDir = "C:\Users\ZhuanZ\Documents\Codex\2026-06-19\new-chat-2\outputs\morning_briefing"

Write-Host "===========================================" -ForegroundColor Yellow
Write-Host "  MORNING BRIEFING — TASK SCHEDULER SETUP" -ForegroundColor Yellow
Write-Host "===========================================" -ForegroundColor Yellow
Write-Host ""

# Check if running as admin
$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Host "[WARNING] Not running as Administrator." -ForegroundColor Red
    Write-Host "Please run this script in an Administrator PowerShell window." -ForegroundColor Red
    Write-Host ""
    Write-Host "Right-click PowerShell → Run as Administrator" -ForegroundColor Cyan
    exit 1
}

# Create scheduled task
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`"" -WorkingDirectory $WorkingDir
$Trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force

Write-Host "[OK] Scheduled Task '$TaskName' created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Schedule: Daily at 07:00 (HK Time)" -ForegroundColor Cyan
Write-Host "Script:   $ScriptPath" -ForegroundColor Cyan
Write-Host "Python:   $PythonPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANT: Before this works, configure your Gmail App Password:" -ForegroundColor Yellow
Write-Host "  1. Go to https://myaccount.google.com/security" -ForegroundColor White
Write-Host "  2. Enable 2-Step Verification if not already on" -ForegroundColor White
Write-Host "  3. Go to https://myaccount.google.com/apppasswords" -ForegroundColor White
Write-Host "  4. Create an App Password for 'Mail'" -ForegroundColor White
Write-Host "  5. Edit config.json and set sender_password to the 16-char password" -ForegroundColor White
Write-Host ""
Write-Host "To test immediately, run:" -ForegroundColor Cyan
Write-Host "  python `"$ScriptPath`"" -ForegroundColor White
Write-Host ""
Write-Host "To remove the automation later:" -ForegroundColor Cyan
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor White
