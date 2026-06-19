# CIMON SNS Manager — 서버 시작
# 실행: PowerShell에서 .\start.ps1

$PYTHON    = "C:\Users\김태석\AppData\Local\Programs\Python\Python312\python.exe"
$COMPUTER  = $env:COMPUTERNAME   # KK-CIMON
$APP_PORT  = 8000

# 이미 실행 중이면 종료 (Task Scheduler 중복 방지)
$alreadyRunning = netstat -an 2>$null | Select-String ":8000\s+.*LISTENING"
if ($alreadyRunning) {
    Write-Host "서버가 이미 실행 중입니다." -ForegroundColor DarkGray
    exit 0
}

# portproxy 설정 여부 확인
$proxyActive = netsh interface portproxy show all 2>$null | Select-String "0\.0\.0\.0\s+80\s"

Write-Host ""
Write-Host "============================================" -ForegroundColor DarkGray
Write-Host "  CIMON SNS Manager" -ForegroundColor White
Write-Host "============================================" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  [접속 주소]" -ForegroundColor Cyan

if (-not $proxyActive) {
    Write-Host "  [!] 포트 포워딩 미설정 — 관리자 권한으로 setup.ps1을 실행합니다..." -ForegroundColor Yellow
    Write-Host ""
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$PSScriptRoot\setup.ps1`"" -Wait
    $proxyActive = netsh interface portproxy show all 2>$null | Select-String "0\.0\.0\.0\s+80\s"
}

if ($proxyActive) {
    Write-Host "  http://$COMPUTER/" -ForegroundColor Green
    Write-Host ""
    Write-Host "  팀원들은 위 주소로 바로 접속 가능 (별도 설정 불필요)" -ForegroundColor DarkGray
} else {
    $localIP = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.PrefixOrigin -ne 'WellKnown' -and $_.IPAddress -notmatch '^127\.' -and $_.IPAddress -notmatch '^169\.' } |
        Sort-Object InterfaceMetric |
        Select-Object -First 1).IPAddress

    Write-Host "  로컬:     http://localhost:$APP_PORT" -ForegroundColor Green
    if ($localIP) { Write-Host "  네트워크: http://${localIP}:$APP_PORT" -ForegroundColor Green }
    Write-Host ""
    Write-Host "  [!] 포트 포워딩 설정 실패 — UAC를 허용했는지 확인하세요" -ForegroundColor Red
}

Write-Host ""
Write-Host "  [로그인]  ID: cimon  /  PW: cimon2024" -ForegroundColor DarkGray
Write-Host "  [종료]    Ctrl+C" -ForegroundColor DarkGray
Write-Host ""
Write-Host "============================================" -ForegroundColor DarkGray
Write-Host ""

# .env 환경변수 주입 (서버 프로세스에 상속됨)
$envPath = Join-Path $PSScriptRoot "config\.env"
if (Test-Path $envPath) {
    Get-Content $envPath | Where-Object { $_ -match "^[A-Z][A-Z0-9_]+=.+" } | ForEach-Object {
        $parts = $_ -split "=", 2
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
    }
    Write-Host "  [.env]   환경변수 로드 완료 (API_MODE=$env:API_MODE)" -ForegroundColor DarkGray
}

while ($true) {
    & $PYTHON main.py
    Write-Host ""
    Write-Host "  [재시작] 서버가 종료됐습니다. 3초 후 재시작합니다..." -ForegroundColor Yellow
    Write-Host "  (완전히 종료하려면 Ctrl+C)" -ForegroundColor DarkGray
    Start-Sleep 3
    # 재시작 시에도 최신 .env 재로드
    if (Test-Path $envPath) {
        Get-Content $envPath | Where-Object { $_ -match "^[A-Z][A-Z0-9_]+=.+" } | ForEach-Object {
            $parts = $_ -split "=", 2
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
        }
    }
    Write-Host ""
}
