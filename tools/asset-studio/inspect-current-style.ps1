$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$taskRoot='D:/ProjectHub3D/jobs/6aa1374ec1c98766b7b44ece'
Get-ChildItem -LiteralPath $taskRoot | Select-Object Name,Length,LastWriteTime
Get-ChildItem -LiteralPath "$taskRoot/output" -Recurse -File | Select-Object FullName,Length | ConvertTo-Json -Compress
Get-CimInstance Win32_Process -Filter "name='blender.exe'" | Select-Object ProcessId,CommandLine,ReadTransferCount,WriteTransferCount | ConvertTo-Json -Compress
if(Test-Path -LiteralPath "$taskRoot/blender.log"){Get-Content -LiteralPath "$taskRoot/blender.log" -Tail 12}
if(Test-Path -LiteralPath "$taskRoot/blender-error.log"){Get-Content -LiteralPath "$taskRoot/blender-error.log" -Tail 5}
