$ErrorActionPreference = "Continue"

# Install Chocolatey if missing
$choco = Get-Command choco -ErrorAction SilentlyContinue
if (-not $choco) {
    Write-Host "--- Installing Chocolatey ---"
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    Write-Host "--- Chocolatey installed ---"
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
} else {
    Write-Host "Chocolatey already installed"
}

Write-Host ""
Write-Host "--- Installing packages ---"

$packages = @("git", "nodejs-lts", "gh", "unity-hub")

foreach ($pkg in $packages) {
    Write-Host ""
    Write-Host "=== $pkg ==="
    choco install -y $pkg --no-progress --limit-output 2>&1 | Select-Object -Last 3
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK: $pkg"
    } else {
        Write-Host "  FAIL: $pkg (exit=$LASTEXITCODE)"
    }
}

Write-Host ""
Write-Host "--- Verification ---"
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "git:  $(git --version 2>&1 | Select-Object -First 1)"
Write-Host "node: $(node --version 2>&1)"
Write-Host "npm:  $(npm --version 2>&1)"
Write-Host "gh:   $(gh --version 2>&1 | Select-Object -First 1)"

if (Test-Path "C:\Program Files\Unity Hub\Unity Hub.exe") {
    Write-Host "Unity Hub: installed"
} else {
    Write-Host "Unity Hub: NOT FOUND"
}

Write-Host ""
Write-Host "--- Done ---"
