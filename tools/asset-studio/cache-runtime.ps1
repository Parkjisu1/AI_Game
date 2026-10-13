$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$zip='D:\ProjectHub3D\downloads\blender-4.5.13-windows-x64.zip'
$target='C:\ProjectHub3D\cache'
$expected='b5fdf800ce65fa2f209e8f68d02667e4d720fa1c42f247c72d1882ab04decba6'
if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Checksum mismatch' }
& tar.exe -xmf $zip -C $target
if ($LASTEXITCODE -ne 0) { throw 'SSD runtime cache extraction failed' }
& "$target\blender-4.5.13-windows-x64\blender.exe" --background --factory-startup --python-expr "import bpy; print('SSD_CACHE_BLENDER_OK', bpy.app.version_string)"
if ($LASTEXITCODE -ne 0) { throw 'Blender cache failed smoke check' }
