$ErrorActionPreference='Stop'
$jobId='000000000000000000000003'
$jobDir="D:/ProjectHub3D/jobs/$jobId"
New-Item -ItemType Directory -Force $jobDir | Out-Null
@{mode='image';profile='pc';source='D:/ProjectHub3D/references/wind-ronin-shape.glb';front='D:/ProjectHub3D/references/wind-ronin-front.png';back='D:/ProjectHub3D/references/wind-ronin-back.png';rig_template='D:/ProjectHub3D/pipeline/rig-template.blend';output="$jobDir/output"} | ConvertTo-Json | Set-Content -LiteralPath "$jobDir/job.json" -Encoding UTF8
Set-ExecutionPolicy -Scope Process Bypass -Force
& D:/ProjectHub3D/pipeline/run-job.ps1 -JobId $jobId
