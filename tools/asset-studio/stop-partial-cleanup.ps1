$ErrorActionPreference='Stop'
foreach($candidate in Get-CimInstance Win32_Process -Filter "Name='powershell.exe'") {
  if($candidate.ProcessId -eq $PID){continue}
  if($candidate.CommandLine -match '-EncodedCommand\s+([A-Za-z0-9+/=]+)') {
    $decoded=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($Matches[1]))
    if($decoded.Contains("Write-Output 'Partial extraction cleanup complete'") -and $decoded.Contains("Remove-Item -LiteralPath `$resolved -Recurse -Force")) {
      Stop-Process -Id $candidate.ProcessId -Force
      Write-Output "Stopped slow task-owned partial cleanup process $($candidate.ProcessId)"
    }
  }
}
Write-Output ('Partial extraction remains: '+(Test-Path -LiteralPath 'D:\ProjectHub3D\apps\_partial_hdd_extraction_20260909'))
