# sync-memory-to-mother.ps1
#
# E:\AI\hermes\memories\ → Mother(~/.hermes/memories/) 동기화
#
# 자리 PC PowerShell에서 실행:
#   powershell -ExecutionPolicy Bypass -File sync-memory-to-mother.ps1
#
# 또는 Windows Task Scheduler에 등록해서 주기 실행 (15분마다 등).

$ErrorActionPreference = "Stop"

$MotherHost = if ($env:MOTHER_HOST) { $env:MOTHER_HOST } else { "aimed@100.77.190.68" }
$LocalPath = "E:\AI\hermes\memories"
$RemotePath = "/home/aimed/.hermes/memories"

if (-not (Test-Path $LocalPath)) {
    Write-Error "Local path not found: $LocalPath"
    exit 1
}

Write-Host "==> Syncing memory from $LocalPath to ${MotherHost}:${RemotePath}" -ForegroundColor Cyan

# 1. 원격 디렉토리 보장
ssh $MotherHost "mkdir -p $RemotePath"

# 2. scp로 재귀 복사 (git bash/WSL의 rsync 없어도 작동)
#    주의: scp는 전체 복사라 rsync 대비 비효율이지만 메모리 파일은 작아서 OK
scp -r -q "$LocalPath\*" "${MotherHost}:$RemotePath/"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Memory sync complete" -ForegroundColor Green
} else {
    Write-Error "scp failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# 3. (선택) Hermes watcher가 캐시 무효화할 수 있게 시그널 파일 갱신
ssh $MotherHost "touch $RemotePath/.sync_marker" 2>$null

Write-Host "완료 시각: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
