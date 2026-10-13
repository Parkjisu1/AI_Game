# rollback-cutover.ps1 — 전환을 되돌린다: 다시 aimed-sub 터널로. (관리자 PowerShell)
#   aimed-sub 쪽 newteam 서비스가 정지돼 있으면 먼저 거기서 `systemctl --user start projecthub-newteam hermes-newteam` 이 필요하다.
$ErrorActionPreference = "Continue"
Write-Host "== WSL 웹을 3000 에서 비켜 줌 (서비스 정지)"
wsl -d Ubuntu-24.04 -u newplay -- bash -lc "systemctl --user stop projecthub-newteam" | Out-Null
Start-Sleep -Seconds 2
Write-Host "== 터널 예약작업 활성 + 실행"
schtasks /change /tn newplay-tunnel /enable | Out-Null
schtasks /run /tn newplay-tunnel | Out-Null
Start-Sleep -Seconds 8
$code = (curl.exe -s -m 10 -o NUL -w "%{http_code}" http://127.0.0.1:3000/login)
Write-Host "   local:3000 (터널) = $code"
$pub = (curl.exe -s -m 20 -o NUL -w "%{http_code}" https://newplay.tailf6f809.ts.net/login)
Write-Host "   public = $pub"
Write-Host "== 되돌림 완료 (aimed-sub 인스턴스로)." -ForegroundColor Yellow
