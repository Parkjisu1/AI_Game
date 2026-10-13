# Final cleanup: gitignore + untrack secrets/runtime, commit, push.
# Runs after token rotation.

$ErrorActionPreference = 'Continue'
Set-Location C:/projects/balloonflow

# 1. Ensure gitignore has all 4 entries (idempotent)
$marker = '# ProjectHub MCP runtime + secrets (do not commit)'
$gitignore = '.gitignore'
$current = if (Test-Path $gitignore) { Get-Content $gitignore -Raw } else { '' }
if ($current -notmatch [regex]::Escape($marker)) {
    Add-Content -Path $gitignore -Value @(
        '',
        $marker,
        'projecthub-mcp/server/.env',
        'projecthub-mcp/server/mcp.log',
        'projecthub-mcp/server/mcp.err',
        'projecthub-mcp/server/run_mcp.cmd'
    )
    Write-Host "appended .gitignore"
} else {
    Write-Host ".gitignore already has marker"
}

# 2. Untrack the leaked/runtime files
foreach ($f in @(
    'projecthub-mcp/server/.env',
    'projecthub-mcp/server/run_mcp.cmd',
    'projecthub-mcp/server/mcp.log',
    'projecthub-mcp/server/mcp.err'
)) {
    cmd /c "git rm --cached $f 2>NUL"
}
Write-Host "untracked secrets+logs"

# 3. Stage gitignore
git add .gitignore 2>&1 | Out-Null

Write-Host "===STATUS==="
git status --short

Write-Host "===COMMIT==="
git commit -m "chore(mcp): gitignore secrets+runtime, untrack leaked .env/run_mcp.cmd

Token in 2779097 was rotated; new token only on disk (gitignored).
Untracking:
  - .env (PROJECTHUB_MCP_TOKEN)
  - run_mcp.cmd (generated wrapper, also contains token)
  - mcp.log, mcp.err (runtime artifacts)
History scrub (BFG/filter-repo) deferred — see security note." 2>&1 | Out-String

Write-Host "===PUSH==="
git push origin main 2>&1 | Out-String
