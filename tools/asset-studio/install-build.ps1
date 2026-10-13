$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = 'D:\ProjectHub3D'
$cache = 'C:\ProjectHub3D\cache'
$mutex=New-Object Threading.Mutex($false, 'Local\ProjectHub3DInstall')
if (-not $mutex.WaitOne(0)) { throw 'Blender installation is already running' }
try {
if ((Get-Volume -DriveLetter D).FileSystemLabel -ne 'Expansion') { throw 'Expected Seagate Expansion on D:' }
foreach ($dir in @($root, "$root\apps", "$root\downloads", "$root\jobs", "$root\pipeline", "$root\references", $cache)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}
$base = 'https://download.blender.org/release/Blender4.5/'
$index = (Invoke-WebRequest -UseBasicParsing -Uri $base).Content
$versions = [regex]::Matches($index, 'blender-(4\.5\.\d+)-windows-x64\.zip') | ForEach-Object { [version]$_.Groups[1].Value }
$version = ($versions | Sort-Object -Descending | Select-Object -First 1).ToString()
$name = "blender-$version-windows-x64.zip"
$zip = "$root\downloads\$name"
$hashPath = "$root\downloads\blender-$version.sha256"
Invoke-WebRequest -UseBasicParsing -Uri "${base}blender-$version.sha256" -OutFile $hashPath
$line = Get-Content $hashPath | Where-Object { $_ -match [regex]::Escape($name) } | Select-Object -First 1
if (-not $line) { throw 'Official checksum entry missing' }
$expected = ($line -split '\s+')[0].ToLowerInvariant()
if (-not (Test-Path $zip)) {
    & curl.exe -fL --retry 3 --connect-timeout 20 -o "$zip.partial" "${base}$name"
    if ($LASTEXITCODE -ne 0) { throw 'Blender download failed' }
    Move-Item -LiteralPath "$zip.partial" -Destination $zip
}
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Blender SHA256 mismatch' }
$exe = "$cache\blender-$version-windows-x64\blender.exe"
if (-not (Test-Path "$cache\blender-$version-windows-x64\.projecthub-extracted")) {
    & tar.exe -xmf $zip -C $cache
    if ($LASTEXITCODE -ne 0) { throw 'Blender extraction failed' }
    Set-Content -Encoding ascii "$cache\blender-$version-windows-x64\.projecthub-extracted" $actual
}
$config = @{ schema_version=1; blender=$exe; runtime_cache=$exe; version=$version; root=$root; cache="$cache\temp"; install_layout='SSD runtime; Seagate archive and model packs'; sha256=$actual; downloaded_from="${base}$name"; installed_at=(Get-Date).ToUniversalTime().ToString('o') }
New-Item -ItemType Directory -Force $config.cache | Out-Null
$config | ConvertTo-Json | Set-Content -Encoding utf8 "$root\installation.json"
& $exe --background --factory-startup --python-expr "import bpy; print('PROJECTHUB_BLENDER_OK', bpy.app.version_string)"
if ($LASTEXITCODE -ne 0) { throw 'Blender smoke test failed' }
$config | ConvertTo-Json
$shortcut=(New-Object -ComObject WScript.Shell).CreateShortcut("$root\Blender.lnk")
$shortcut.TargetPath=$exe
$shortcut.WorkingDirectory=$root
$shortcut.Save()
} finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
