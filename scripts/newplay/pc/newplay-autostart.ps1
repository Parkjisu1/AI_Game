# newplay-autostart.ps1 — Windows 부팅 시 WSL(Ubuntu-24.04) 을 User 계정으로 깨워 systemd 서비스가 올라오게 한다.
#   관리자 PowerShell 에서:  powershell -ExecutionPolicy Bypass -File C:\newplay\newplay-autostart.ps1
#   User 계정 비밀번호를 물어본다(예약작업에 저장 — "로그온 여부와 관계없이 실행"). 비밀번호를 바꾸면 다시 실행.
#   ⚠ SYSTEM 계정으로 wsl 을 띄우면 안 된다 — WSL 배포판은 User 계정에 등록돼 있고, SYSTEM 에서 띄우면 User 의 WSL 이 끊긴다(실측 2026-09-14).
$ErrorActionPreference = "Stop"
$cfg = "[wsl2]`nvmIdleTimeout=-1`nmemory=20GB`nlocalhostForwarding=true`n"
Set-Content -Path "C:\Users\User\.wslconfig" -Value $cfg -Encoding ASCII
Set-Content -Path "C:\newplay\wsl-keep.cmd" -Value "@echo off`r`nC:\Windows\System32\wsl.exe -d Ubuntu-24.04 -u newplay --exec sleep infinity`r`n" -Encoding ASCII
$sec = Read-Host "User 계정 비밀번호" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
try { $pw = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
schtasks /delete /tn newplay-wsl /f 2>$null | Out-Null
schtasks /create /f /tn newplay-wsl /sc onstart /delay 0000:30 /ru "$env:COMPUTERNAME\User" /rp $pw /rl highest /tr "C:\newplay\wsl-keep.cmd" | Out-Null
$pw = $null
schtasks /query /tn newplay-wsl /fo list | Select-String "TaskName|Status|Run As"
Write-Host "등록 완료. 지금 바로 띄우려면:  schtasks /run /tn newplay-wsl   (이미 WSL 이 떠 있으면 실행하지 않아도 됨)"
