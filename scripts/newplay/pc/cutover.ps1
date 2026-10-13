# cutover.ps1 — NewPlay 서비스를 이 PC 의 WSL 로 전환한다. (관리자 PowerShell)
#   전: Funnel → 127.0.0.1:3000 = aimed-sub 로 가는 SSH 터널
#   후: Funnel → 127.0.0.1:3000 = WSL 안 NewPlay 웹 (localhostForwarding)
#   되돌리기: rollback-cutover.ps1
$ErrorActionPreference = "Continue"
Write-Host "== 1) WSL 서비스 상태"
$svc = (wsl -d Ubuntu-24.04 -u newplay -- bash -lc "systemctl --user is-active projecthub-newteam hermes-newteam | tr '\n' ' '")
Write-Host "   $svc"
if ($svc -notmatch "active active") { Write-Host "WSL 서비스가 살아 있지 않습니다. 중단." -ForegroundColor Red; exit 1 }

Write-Host "== 2) 터널 예약작업 정지·비활성 + ssh 터널 프로세스 종료"
schtasks /end /tn newplay-tunnel 2>$null | Out-Null
schtasks /change /tn newplay-tunnel /disable | Out-Null
Get-Process ssh -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*OpenSSH*" -or $_.Path -like "*ssh.exe" } | ForEach-Object {
  try { $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine } catch { $cl = "" }
  if ($cl -match "3000:127.0.0.1:3000") { Stop-Process -Id $_.Id -Force; Write-Host "   killed tunnel pid $($_.Id)" }
}
Start-Sleep -Seconds 3

Write-Host "== 3) 127.0.0.1:3000 이 WSL 로 가는지"
$code = (curl.exe -s -m 10 -o NUL -w "%{http_code}" http://127.0.0.1:3000/login)
Write-Host "   local:3000 = $code"
if ($code -ne "200") { Write-Host "WSL 포워딩이 안 됩니다. rollback-cutover.ps1 로 되돌리세요." -ForegroundColor Red; exit 1 }

Write-Host "== 4) 공개 주소"
$pub = (curl.exe -s -m 20 -o NUL -w "%{http_code}" https://newplay.tailf6f809.ts.net/login)
Write-Host "   https://newplay.tailf6f809.ts.net/login = $pub"
Write-Host "== 전환 완료. 이제 이 PC 의 WSL 이 NewPlay 서비스 본체입니다." -ForegroundColor Green
