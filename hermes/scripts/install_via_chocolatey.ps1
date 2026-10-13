# Chocolatey 기반 도구 일괄 설치
# SSH non-interactive 세션에서 winget 이슈 회피용

$ErrorActionPreference = "Continue"

# 1. Chocolatey 설치 확인
$choco = Get-Command choco -ErrorAction SilentlyContinue
if (-not $choco) {
    Write-Host "=== Chocolatey 설치 ===" -ForegroundColor Cyan
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    try {
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        Write-Host "Chocolatey 설치 완료" -ForegroundColor Green
    } catch {
        Write-Host "Chocolatey 설치 실패: $_" -ForegroundColor Red
        exit 1
    }
    # PATH 새로고침
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
else {
    Write-Host "Chocolatey 이미 설치됨: $($choco.Version)" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 도구 설치 시작 ===" -ForegroundColor Cyan

$packages = @(
    @{Name="Git"; Package="git"},
    @{Name="Node.js LTS"; Package="nodejs-lts"},
    @{Name="GitHub CLI"; Package="gh"},
    @{Name="Unity Hub"; Package="unity-hub"}
)

foreach ($p in $packages) {
    Write-Host ""
    Write-Host "--- [$($p.Name)] ---" -ForegroundColor Cyan
    $installed = choco list --local-only --exact $p.Package 2>&1 | Select-String $p.Package
    if ($installed) {
        Write-Host "이미 설치됨 — 스킵" -ForegroundColor Yellow
        continue
    }
    choco install -y $p.Package --no-progress --limit-output 2>&1 | Select-Object -Last 5
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ $($p.Name) 설치 성공" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ $($p.Name) 실패 (exit=$LASTEXITCODE)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== 설치 후 검증 ===" -ForegroundColor Cyan

# PATH 새로고침
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

function Test-Cmd {
    param($name, $cmd)
    try {
        $v = Invoke-Expression "$cmd 2>&1" | Select-Object -First 1
        Write-Host "  ✓ $name : $v" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ $name : 미확인" -ForegroundColor Yellow
    }
}

Test-Cmd "git"  "git --version"
Test-Cmd "node" "node --version"
Test-Cmd "npm"  "npm --version"
Test-Cmd "gh"   "gh --version"

if (Test-Path "C:\Program Files\Unity Hub\Unity Hub.exe") {
    Write-Host "  ✓ Unity Hub: C:\Program Files\Unity Hub\Unity Hub.exe" -ForegroundColor Green
} else {
    Write-Host "  ✗ Unity Hub: 미확인" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== 완료 ===" -ForegroundColor Cyan
