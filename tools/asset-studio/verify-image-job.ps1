param([ValidatePattern('^[a-f0-9]{24}$')][string]$JobId='6aa118aab4e9da5eb64d438e')
$ErrorActionPreference='Stop'
$cfg=Get-Content D:/ProjectHub3D/installation.json -Raw | ConvertFrom-Json
& $cfg.blender --background --factory-startup --disable-autoexec --threads 8 --python-exit-code 1 --python D:/ProjectHub3D/pipeline/verify_pack.py -- "D:/ProjectHub3D/jobs/$JobId/output"
exit $LASTEXITCODE
