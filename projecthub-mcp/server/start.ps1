# Start MCP via Windows Task Scheduler (survives SSH disconnect — separate session, no Job Object).
$ErrorActionPreference = 'Continue'   # native cmds emit to stderr legitimately
Set-Location $PSScriptRoot
$taskName = 'ProjectHubMcp'
$workdir  = $PSScriptRoot
$wrapper  = Join-Path $PSScriptRoot 'run_mcp.cmd'

# Wrapper batch (so the task points to a stable single command line)
# Token loaded from .env if present
$tokenLine = ''
$envFile = Join-Path $PSScriptRoot '.env'
if (Test-Path $envFile) {
    $tokenMatch = (Get-Content $envFile) | Where-Object { $_ -match '^PROJECTHUB_MCP_TOKEN=' } | Select-Object -First 1
    if ($tokenMatch) { $tokenLine = "set $tokenMatch" }
}
@"
@echo off
cd /d $workdir
$tokenLine
node index.mjs > mcp.log 2> mcp.err
"@ | Out-File -Encoding ascii $wrapper

# Kill existing
Get-NetTCPConnection -LocalPort 7900 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }
cmd /c "schtasks /End /TN $taskName >NUL 2>&1"
cmd /c "schtasks /Delete /TN $taskName /F >NUL 2>&1"
Start-Sleep -Milliseconds 500
Remove-Item mcp.log,mcp.err -ErrorAction SilentlyContinue

# Register one-shot task scheduled 2s in future, then explicitly Run
$startTime = (Get-Date).AddSeconds(2).ToString('HH:mm:ss')
$out = cmd /c "schtasks /Create /TN $taskName /TR `"$wrapper`" /SC ONCE /ST $startTime /F 2>&1"
Write-Host "schtasks create: $out"
cmd /c "schtasks /Run /TN $taskName >NUL 2>&1"
Start-Sleep -Seconds 3

# Verify
$conn = Get-NetTCPConnection -LocalPort 7900 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "OK :7900 listening (PID $($conn.OwningProcess | Select-Object -First 1))"
} else {
    Write-Host "FAIL :7900 not listening"
    if (Test-Path mcp.err) { Get-Content mcp.err | Select-Object -First 10 | ForEach-Object { Write-Host "  err> $_" } }
    if (Test-Path mcp.log) { Get-Content mcp.log | Select-Object -First 10 | ForEach-Object { Write-Host "  log> $_" } }
}
