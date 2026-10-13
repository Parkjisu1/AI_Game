param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{24}$')][string]$JobId)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='D:\ProjectHub3D'
$cfg=Get-Content "$root\installation.json" -Raw | ConvertFrom-Json
$blender=if ($cfg.runtime_cache -and (Test-Path $cfg.runtime_cache)) { $cfg.runtime_cache } else { $cfg.blender }
$jobDir="$root\jobs\$JobId"
$mutex=New-Object Threading.Mutex($false, 'Local\ProjectHub3DBlender')
$locked=$false
try {
    $locked=$mutex.WaitOne(0)
    if (-not $locked) { throw 'BUSY: another Blender job is running' }
    if (Get-Process Unity -ErrorAction SilentlyContinue) { throw 'BUSY: Unity is running on the build computer' }
    if (-not (Test-Path "$jobDir\job.json")) { throw 'Job input missing' }
    $env:TEMP=$cfg.cache
    $env:TMP=$cfg.cache
    $proc=Start-Process -FilePath $blender -ArgumentList @('--background','--factory-startup','--disable-autoexec','--threads','8','--python-exit-code','1','--python',"$root\pipeline\blender_pipeline.py",'--',"$jobDir\job.json") -WindowStyle Hidden -PassThru -RedirectStandardOutput "$jobDir\blender.log" -RedirectStandardError "$jobDir\blender-error.log"
    $processHandle=$proc.Handle
    if (-not $proc.WaitForExit(2700000)) { $proc.Kill(); throw 'Blender exceeded 45 minute job timeout' }
    $proc.WaitForExit()
    if ($proc.ExitCode -ne 0) {
        Get-Content "$jobDir\blender.log" -Tail 25
        Get-Content "$jobDir\blender-error.log" -Tail 25
        throw "Blender failed: $($proc.ExitCode)"
    }
    Get-Content "$jobDir\output\report.json" -Raw
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
