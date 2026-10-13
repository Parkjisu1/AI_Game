$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='D:\ProjectHub3D'
$partial='D:\ProjectHub3D\apps\blender-4.5.13-windows-x64'
$archived='D:\ProjectHub3D\apps\_partial_hdd_extraction_20260909'
foreach ($target in @($partial,$archived)) {
    $resolved=[IO.Path]::GetFullPath($target)
    if (-not $resolved.StartsWith('D:\ProjectHub3D\apps\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid extraction target' }
}
Get-CimInstance Win32_Process -Filter "Name='tar.exe'" | Where-Object { $_.CommandLine -like '*D:\ProjectHub3D\downloads\blender-4.5.13-windows-x64.zip*' -and $_.CommandLine -like '*D:\ProjectHub3D\apps*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
if ((Test-Path $partial) -and -not (Test-Path $archived)) {
    try { Move-Item -LiteralPath $partial -Destination $archived }
    catch { Write-Output 'Unused HDD extraction retained; SSD runtime is the active installation.' }
}
# Keep the already verified runtime at its current path while existing test jobs finish.
$exe='C:\ProjectHub3D\cache\blender-4.5.13-windows-x64\blender.exe'
if (-not (Test-Path $exe)) { throw 'Verified SSD runtime missing' }
$cfg=@{schema_version=1;blender=$exe;runtime_cache=$exe;version='4.5.13';root=$root;cache='C:\ProjectHub3D\cache\temp';
  install_layout='SSD runtime; Seagate archive and model packs';hdd_extraction_pending=$false;
  sha256='b5fdf800ce65fa2f209e8f68d02667e4d720fa1c42f247c72d1882ab04decba6';
  archive='D:\ProjectHub3D\downloads\blender-4.5.13-windows-x64.zip';installed_at=(Get-Date).ToUniversalTime().ToString('o')}
New-Item -ItemType Directory -Force $cfg.cache | Out-Null
$cfg | ConvertTo-Json | Set-Content -Encoding utf8 "$root\installation.json"
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut("$root\Blender.lnk")
$shortcut.TargetPath=$exe
$shortcut.WorkingDirectory=$root
$shortcut.Save()
$cfg | ConvertTo-Json
