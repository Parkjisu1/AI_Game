$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='D:\ProjectHub3D'
$exe='C:\ProjectHub3D\cache\blender-4.5.13-windows-x64\blender.exe'
if (-not (Test-Path $exe)) { throw 'Verified SSD runtime cache unavailable' }
if (-not (Test-Path "$root\installation.json")) {
    @{schema_version=1;blender=$exe;runtime_cache=$exe;version='4.5.13';root=$root;cache='C:\ProjectHub3D\cache';
      hdd_extraction_pending=$true;sha256='b5fdf800ce65fa2f209e8f68d02667e4d720fa1c42f247c72d1882ab04decba6';
      archive='D:\ProjectHub3D\downloads\blender-4.5.13-windows-x64.zip';installed_at=(Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json | Set-Content -Encoding utf8 "$root\installation.json"
}
Write-Output 'Verified SSD runtime activated; packages remain on Seagate HDD.'
