# 머신 B 환경 체크 스크립트
# 실행: scp로 머신 B에 올리고 PowerShell로 실행

Write-Host "=== Node.js ==="
try { node --version } catch { Write-Host "not installed" }

Write-Host "=== Git ==="
try { git --version } catch { Write-Host "not installed" }

Write-Host "=== GitHub CLI ==="
try { gh --version 2>&1 | Select-Object -First 1 } catch { Write-Host "not installed" }

Write-Host "=== Unity Hub ==="
$unityHub = "C:\Program Files\Unity Hub\Unity Hub.exe"
if (Test-Path $unityHub) { Write-Host "found at $unityHub" } else { Write-Host "not found" }

Write-Host "=== Claude Code ==="
try { (Get-Command claude -ErrorAction Stop).Path } catch { Write-Host "not installed" }

Write-Host "=== winget ==="
try { winget --version } catch { Write-Host "not available" }

Write-Host "=== Python ==="
try { python --version 2>&1 } catch { Write-Host "not installed" }

Write-Host ""
Write-Host "=== Disk 여유 ==="
Get-PSDrive -PSProvider FileSystem | Where-Object { $null -ne $_.Used } | Select-Object Name, @{N='UsedGB';E={[math]::Round($_.Used/1GB,1)}}, @{N='FreeGB';E={[math]::Round($_.Free/1GB,1)}} | Format-Table -AutoSize

Write-Host "=== Windows 버전 ==="
[System.Environment]::OSVersion.VersionString

Write-Host "=== PATH 내 주요 디렉토리 ==="
$env:PATH -split ';' | Where-Object { $_ -match 'node|git|unity|claude|gh|python' -or $_ -eq $env:USERPROFILE + '\AppData\Local\Programs\Microsoft VS Code\bin' } | ForEach-Object { "  $_" }
