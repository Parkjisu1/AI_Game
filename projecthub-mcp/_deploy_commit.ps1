# Deploy + commit MCP source files in one go (atomic).
# Run on build PC after files are in place.

Set-Location C:/projects/balloonflow

# 1. Stop MCP so mcp.log isn't being written
$conn = Get-NetTCPConnection -LocalPort 7900 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    foreach ($processId in ($conn.OwningProcess | Select-Object -Unique)) {
        try { Stop-Process -Id $processId -Force; Write-Host "stopped MCP PID $processId" } catch {}
    }
}
cmd /c "schtasks /End /TN ProjectHubMcp >NUL 2>&1"
cmd /c "schtasks /Delete /TN ProjectHubMcp /F >NUL 2>&1"
Start-Sleep -Seconds 2

# 2. Append to .gitignore (idempotent — only add if missing)
$ignoreLines = @(
    '',
    '# ProjectHub MCP runtime artifacts (added 2026-05-07)',
    'projecthub-mcp/server/mcp.log',
    'projecthub-mcp/server/mcp.err',
    'projecthub-mcp/server/.env',
    'projecthub-mcp/server/run_mcp.cmd'
)
$gitignore = '.gitignore'
$current = if (Test-Path $gitignore) { Get-Content $gitignore -Raw } else { '' }
$needAdd = $false
foreach ($line in $ignoreLines) {
    if ($line.Trim() -and $current -notmatch [regex]::Escape($line.Trim())) { $needAdd = $true; break }
}
if ($needAdd) {
    Add-Content -Path $gitignore -Value $ignoreLines
    Write-Host "appended .gitignore"
} else {
    Write-Host ".gitignore already has entries"
}

# 3. Untrack runtime files (forces removal from index, file stays on disk if exists)
cmd /c "git rm --cached projecthub-mcp/server/mcp.log projecthub-mcp/server/mcp.err 2>NUL"
Write-Host "untracked log files"

# 4. Add source files
git add `
    .gitignore `
    BalloonFlow/Assets/Editor/McpBridge.cs `
    BalloonFlow/Assets/Editor/McpBridge.cs.meta `
    projecthub-mcp/server/index.mjs `
    projecthub-mcp/server/package.json `
    projecthub-mcp/server/start.ps1 `
    projecthub-mcp/server/stop.ps1 `
    projecthub-mcp/server/spawn.vbs `
    projecthub-mcp/server/test/ping.mjs

Write-Host "===STATUS==="
git status --short

Write-Host "===COMMIT==="
git commit -m "chore(mcp): track MCP server source + gitignore runtime logs

- Add Assets/Editor/McpBridge.cs (Unity HTTP bridge for MCP RPC)
- Add projecthub-mcp/server/* (Node.js MCP server, scripts, tests)
- Untrack mcp.log/mcp.err (runtime artifacts, were committed via PR #91)
- gitignore: mcp.log, mcp.err, .env (token), run_mcp.cmd (generated wrapper)"

Write-Host "===PUSH==="
git push origin main
