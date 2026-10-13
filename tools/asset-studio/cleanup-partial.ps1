$ErrorActionPreference='Stop'
$partial='D:\ProjectHub3D\apps\_partial_hdd_extraction_20260909'
if(Test-Path -LiteralPath $partial){
  $resolved=(Resolve-Path -LiteralPath $partial).Path
  if($resolved -cne $partial -or -not $resolved.StartsWith('D:\ProjectHub3D\apps\')){throw 'Unexpected cleanup target'}
  Write-Output "Removing interrupted extraction: $resolved"
  Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output 'Partial extraction cleanup complete'
