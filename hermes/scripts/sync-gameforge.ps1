# sync-gameforge.ps1
#
# E:\AI → Mother(~/gameforge/) 동기화 — rsync 없이 tar 스트리밍 기반
#
# 자리 PC PowerShell에서 실행:
#   powershell -ExecutionPolicy Bypass -File sync-gameforge.ps1
#
# Windows Task Scheduler 등록 예시 (5분 주기):
#   schtasks /create /tn "GameForge-Sync" /tr "powershell -ExecutionPolicy Bypass -File E:\AI\hermes\scripts\sync-gameforge.ps1" /sc minute /mo 5
#
# 강제 전체 싱크 원하면 -Full 플래그 전달 (증분 상태 초기화)

param(
    [switch]$Full  # 증분 스냅샷 무시하고 전체 재동기화
)

$ErrorActionPreference = "Stop"

$MotherHost = if ($env:MOTHER_HOST) { $env:MOTHER_HOST } else { "aimed@100.77.190.68" }
$LocalPath = "E:\AI"
$RemotePath = "/home/aimed/gameforge"
$SnapshotFile = "$env:TEMP\gameforge-sync.snar"

if (-not (Test-Path $LocalPath)) {
    Write-Error "Local path not found: $LocalPath"
    exit 1
}

# Git Bash 경로로 변환
$gitBashSource = $LocalPath -replace "\\", "/" -replace "^([A-Z]):", { "/$($matches[1].ToLower())" }

# 제외 패턴 (tar --exclude 플래그 인자)
$Excludes = @(
    "node_modules"
    "sd_models"
    "*.pt"
    "build"
    "dist"
    ".git"
    ".next"
    ".venv"
    "venv"
    "Feedback"
    "History"
    "02-Projects-*"
    "virtual_player"
    "__pycache__"
    "*.spec"
    "hermes"                 # Hermes 메모리는 별도 sync
    "ad_suspects_collage.png"
    "pixelflow_game_data"    # 게임 데이터 대용량
    "projects"                # 작업 산출물 (필요 시 별도)
    ".env"                   # 시크릿
    "*.log"
    "*.tmp"
)

$excludeArgs = @()
foreach ($p in $Excludes) {
    $excludeArgs += "--exclude=$p"
}

# 증분 옵션 (Full 플래그 시 스냅샷 초기화)
if ($Full -and (Test-Path $SnapshotFile)) {
    Remove-Item $SnapshotFile -Force
    Write-Host "[INFO] Full mode: snapshot cleared" -ForegroundColor Yellow
}

# Git Bash 경로로 스냅샷 변환
$gitBashSnar = $SnapshotFile -replace "\\", "/" -replace "^([A-Z]):", { "/$($matches[1].ToLower())" }

Write-Host "==> GameForge sync start ($(Get-Date -Format 'HH:mm:ss'))" -ForegroundColor Cyan
Write-Host "    Source: $LocalPath"
Write-Host "    Target: ${MotherHost}:${RemotePath}"

# bash 셸에서 tar 스트리밍 (Git Bash 의존)
$tarExcludeList = ($Excludes | ForEach-Object { "--exclude='$_'" }) -join " "

$bashCmd = @"
cd '$gitBashSource' && tar -cf - $tarExcludeList --listed-incremental='$gitBashSnar' . 2>/dev/null | ssh $MotherHost "mkdir -p $RemotePath && tar -C $RemotePath -xf - --listed-incremental=/dev/null 2>/dev/null; echo TRANSFERRED"
"@

$result = & bash -c $bashCmd 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "==> Sync complete ($(Get-Date -Format 'HH:mm:ss'))" -ForegroundColor Green
    Write-Host $result
} else {
    Write-Error "Sync failed (exit=$LASTEXITCODE): $result"
    exit $LASTEXITCODE
}
