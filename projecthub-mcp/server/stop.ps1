$conn = Get-NetTCPConnection -LocalPort 7900 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    foreach ($pid in ($conn.OwningProcess | Select-Object -Unique)) {
        try { Stop-Process -Id $pid -Force; Write-Host "stopped PID $pid" } catch {}
    }
} else { Write-Host "no listener on :7900" }
cmd /c "schtasks /End /TN ProjectHubMcp >NUL 2>&1"
cmd /c "schtasks /Delete /TN ProjectHubMcp /F >NUL 2>&1"
Start-Sleep -Seconds 1
$still = Get-NetTCPConnection -LocalPort 7900 -State Listen -ErrorAction SilentlyContinue
if ($still) { Write-Host "WARN still listening" } else { Write-Host "OK :7900 free" }
