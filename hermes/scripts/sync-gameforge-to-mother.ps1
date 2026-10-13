# sync-gameforge-to-mother.ps1
#
# E:\AI\ → Mother(~/gameforge/) 동기화
# GameForge 전체 소스 코드를 Mother로 배포 (Hermes가 `claude -p` 호출 시 사용).
#
# 자리 PC PowerShell에서 실행:
#   powershell -ExecutionPolicy Bypass -File sync-gameforge-to-mother.ps1
#
# Task Scheduler에 등록해서 5분 주기 sync 권장 (많이 바뀔 때).

$ErrorActionPreference = "Stop"

$MotherHost = if ($env:MOTHER_HOST) { $env:MOTHER_HOST } else { "aimed@100.77.190.68" }
$LocalPath = "E:\AI"
$RemotePath = "/home/aimed/gameforge"

# 제외 패턴 (node_modules, build 산출물, 대용량 바이너리, Hermes 자체)
$ExcludePatterns = @(
    "node_modules",
    "__pycache__",
    ".git",
    "build",
    "dist",
    "*.pt",               # YOLO 모델
    "*.spec",             # PyInstaller spec
    "sd_models",          # Stable Diffusion 모델
    "tools/projecthub-web/node_modules",
    "tools/projecthub-web/.next",
    "hermes"              # Hermes 자체는 memories를 별도로 sync
)

Write-Host "==> Syncing GameForge from $LocalPath to ${MotherHost}:${RemotePath}" -ForegroundColor Cyan

# 원격 디렉토리 보장
ssh $MotherHost "mkdir -p $RemotePath"

# Windows 환경에서는 rsync.exe가 없을 수 있으니 Git Bash의 rsync를 쓰거나 scp
# 가장 호환성 좋은 방법: WSL의 rsync 또는 Git Bash가 설치돼 있어야 함
# 여기선 간단한 로봇카피(robocopy)로 스테이징 + scp 조합 — 생략, rsync 기준 가이드

# 옵션 A: Git Bash의 rsync 사용 (권장)
$rsyncAvailable = $false
try {
    $null = Get-Command rsync -ErrorAction Stop
    $rsyncAvailable = $true
} catch {
    Write-Warning "rsync not found in PATH. Install Git for Windows or WSL."
}

if ($rsyncAvailable) {
    $excludeArgs = @()
    foreach ($pattern in $ExcludePatterns) {
        $excludeArgs += "--exclude=$pattern"
    }
    # 경로 변환: E:\AI → /e/AI (Git Bash 경로)
    $gitBashPath = $LocalPath -replace "\\", "/" -replace "^([A-Z]):", "/$($_.ToLower())"
    $gitBashPath = $LocalPath -replace "\\", "/" -replace "^([A-Z]):", { "/$($matches[1].ToLower())" }

    rsync -avz --delete @excludeArgs "$gitBashPath/" "${MotherHost}:${RemotePath}/"

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ GameForge sync complete (rsync)" -ForegroundColor Green
    } else {
        Write-Error "rsync failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
} else {
    # 옵션 B: scp fallback (느림, 전체 복사)
    Write-Warning "Falling back to scp (slower). Install rsync for incremental sync."
    # node_modules 등 큰 폴더를 먼저 원격에서 skip하기 어려워, 로컬에서 임시 tar 생성
    Write-Host "Creating temporary archive..."
    $tempTar = "$env:TEMP\gameforge-sync.tar"
    tar -cf $tempTar --exclude='node_modules' --exclude='build' --exclude='dist' --exclude='.git' `
        --exclude='*.pt' --exclude='sd_models' --exclude='hermes' -C "$LocalPath" .

    scp $tempTar "${MotherHost}:/tmp/gameforge-sync.tar"
    ssh $MotherHost "mkdir -p $RemotePath && tar -xf /tmp/gameforge-sync.tar -C $RemotePath && rm /tmp/gameforge-sync.tar"
    Remove-Item $tempTar -Force

    Write-Host "✅ GameForge sync complete (scp fallback)" -ForegroundColor Green
}

Write-Host "완료 시각: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
