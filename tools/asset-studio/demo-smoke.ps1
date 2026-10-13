$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
New-Item -ItemType Directory -Force 'D:/ProjectHub3D/jobs/00000000000001a08526dee4' | Out-Null
@'
{"mode":"demo","profile":"pc","output":"D:/ProjectHub3D/jobs/00000000000001a08526dee4/output"}
'@ | Set-Content -Encoding utf8 'D:/ProjectHub3D/jobs/00000000000001a08526dee4/job.json'
& 'C:/ProjectHub3D/cache/blender-4.5.13-windows-x64/blender.exe' --background --factory-startup --disable-autoexec --threads 8 --python-exit-code 1 --python D:/ProjectHub3D/pipeline/blender_pipeline.py -- 'D:/ProjectHub3D/jobs/00000000000001a08526dee4/job.json'
exit $LASTEXITCODE
