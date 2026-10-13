param([Parameter(Mandatory=$true)][string]$ScriptPath)
$ErrorActionPreference = 'Stop'
$source = Get-Content -LiteralPath $ScriptPath -Raw -Encoding utf8
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($source))
ssh -o BatchMode=yes -o ConnectTimeout=15 user@100.92.43.9 powershell -NoProfile -NonInteractive -EncodedCommand $encoded
exit $LASTEXITCODE
