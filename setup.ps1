# CIMON SNS Manager - Server Setup (Run as Administrator, once)

$APP_PORT  = 8000
$HTTP_PORT = 80
$COMPUTER  = $env:COMPUTERNAME

Write-Host ""
Write-Host "CIMON SNS Manager - Network Setup" -ForegroundColor White
Write-Host "--------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# Step 1: Port forwarding 80 -> 8000
Write-Host "[1/3] Port forwarding 80 -> $APP_PORT ..." -ForegroundColor Cyan
netsh interface portproxy delete v4tov4 listenport=$HTTP_PORT listenaddress=0.0.0.0 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenport=$HTTP_PORT listenaddress=0.0.0.0 connectport=$APP_PORT connectaddress=127.0.0.1
if ($LASTEXITCODE -eq 0) {
    Write-Host "         OK" -ForegroundColor Green
} else {
    Write-Host "         FAILED - Run as Administrator" -ForegroundColor Red
}

# Step 2: Firewall rules
Write-Host "[2/3] Firewall rules (port 80, $APP_PORT) ..." -ForegroundColor Cyan

$ruleName1 = "CIMON-SNS-HTTP"
$ruleName2 = "CIMON-SNS-APP"

$existing1 = Get-NetFirewallRule -DisplayName $ruleName1 -ErrorAction SilentlyContinue
if (-not $existing1) {
    New-NetFirewallRule -DisplayName $ruleName1 -Direction Inbound -Protocol TCP -LocalPort $HTTP_PORT -Action Allow | Out-Null
    Write-Host "         Port $HTTP_PORT rule added" -ForegroundColor Green
} else {
    Write-Host "         Port $HTTP_PORT rule already exists" -ForegroundColor DarkGray
}

$existing2 = Get-NetFirewallRule -DisplayName $ruleName2 -ErrorAction SilentlyContinue
if (-not $existing2) {
    New-NetFirewallRule -DisplayName $ruleName2 -Direction Inbound -Protocol TCP -LocalPort $APP_PORT -Action Allow | Out-Null
    Write-Host "         Port $APP_PORT rule added" -ForegroundColor Green
} else {
    Write-Host "         Port $APP_PORT rule already exists" -ForegroundColor DarkGray
}

# Step 3: Task Scheduler — 로그인 시 자동 시작
Write-Host "[3/3] 자동 시작 Task Scheduler 등록 ..." -ForegroundColor Cyan
$taskName   = "CIMON-SNS-Manager"
$startScript = Join-Path $PSScriptRoot "start.ps1"
$action   = New-ScheduledTaskAction -Execute "powershell.exe" `
                -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`"" `
                -WorkingDirectory $PSScriptRoot
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -RunLevel Limited -Force | Out-Null
if ($?) {
    Write-Host "         OK (다음 로그인부터 자동 시작)" -ForegroundColor Green
} else {
    Write-Host "         FAILED" -ForegroundColor Red
}

# Done
Write-Host ""
Write-Host "--------------------------------------------" -ForegroundColor DarkGray
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Team access URL (no setup needed on their PC):" -ForegroundColor White
Write-Host ""
Write-Host "  http://$COMPUTER/" -ForegroundColor Green
Write-Host ""
Write-Host "  Login: ID cimon / PW cimon2024" -ForegroundColor DarkGray
Write-Host "  Start server: .\start.ps1" -ForegroundColor DarkGray
Write-Host ""
