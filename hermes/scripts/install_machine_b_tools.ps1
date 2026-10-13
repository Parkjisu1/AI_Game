# 머신 B 개발 도구 일괄 설치
# Git / Node.js / GitHub CLI / Unity Hub
# 실행: powershell -ExecutionPolicy Bypass -File install_machine_b_tools.ps1

$ErrorActionPreference = "Continue"  # 개별 실패 시 다음으로 계속

$tools = @(
    @{Name="Git"; Id="Git.Git"},
    @{Name="Node.js LTS"; Id="OpenJS.NodeJS.LTS"},
    @{Name="GitHub CLI"; Id="GitHub.cli"},
    @{Name="Unity Hub"; Id="UnityTechnologies.UnityHub"}
)

foreach ($tool in $tools) {
    Write-Host ""
    Write-Host "=== [$($tool.Name)] 설치 시도 ===" -ForegroundColor Cyan

    # 이미 설치된 경우 스킵
    $installed = winget list --id $tool.Id --exact 2>&1 | Select-String $tool.Id
    if ($installed) {
        Write-Host "  이미 설치됨 — 스킵" -ForegroundColor Yellow
        continue
    }

    # 설치
    winget install --id $tool.Id -e --silent --accept-package-agreements --accept-source-agreements 2>&1 |
        Tee-Object -Variable installOut | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 설치 성공" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ 설치 실패 (exit=$LASTEXITCODE)" -ForegroundColor Red
        Write-Host "  마지막 출력:"
        $installOut | Select-Object -Last 5 | ForEach-Object { "    $_" }
    }
}

Write-Host ""
Write-Host "=== 최종 버전 체크 ===" -ForegroundColor Cyan

# PATH 새로고침 (현재 세션만)
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

$checks = @(
    @{Name="git"; Cmd="git --version"},
    @{Name="node"; Cmd="node --version"},
    @{Name="npm"; Cmd="npm --version"},
    @{Name="gh"; Cmd="gh --version"}
)

foreach ($c in $checks) {
    try {
        $ver = Invoke-Expression $c.Cmd 2>&1 | Select-Object -First 1
        Write-Host "  $($c.Name): $ver" -ForegroundColor Green
    } catch {
        Write-Host "  $($c.Name): (not in PATH yet)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Unity Hub (GUI 앱, CLI 아님): C:\Program Files\Unity Hub\Unity Hub.exe" -ForegroundColor White
if (Test-Path "C:\Program Files\Unity Hub\Unity Hub.exe") {
    Write-Host "  ✓ 파일 존재" -ForegroundColor Green
} else {
    Write-Host "  ✗ 파일 없음" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== 설치 완료 ===" -ForegroundColor Cyan
