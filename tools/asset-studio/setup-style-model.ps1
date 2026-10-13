$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='C:\ProjectHub3D\cache\trellis2'
if(-not(Test-Path "$root\.git")){
  git clone --depth 1 https://github.com/IgorAherne/TRELLIS.2-stableprojectorz.git $root
  if($LASTEXITCODE -ne 0){throw 'Repository download failed'}
}
$pythonRoot='C:\ProjectHub3D\cache\python311-style'
New-Item -ItemType Directory -Force $pythonRoot | Out-Null
if(-not(Test-Path "$pythonRoot\python.exe")){
  curl.exe -fL --retry 3 https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip -o "$pythonRoot\python.zip"
  if($LASTEXITCODE -ne 0){throw 'Python download failed'}
  Expand-Archive -LiteralPath "$pythonRoot\python.zip" -DestinationPath $pythonRoot -Force
  @('python311.zip','.','Lib/site-packages','import site') | Set-Content -LiteralPath "$pythonRoot\python311._pth" -Encoding ASCII
}
if(-not(Test-Path "$pythonRoot\Lib\site-packages\pip")){
  curl.exe -fL --retry 3 https://bootstrap.pypa.io/get-pip.py -o "$pythonRoot\get-pip.py"
  & "$pythonRoot\python.exe" "$pythonRoot\get-pip.py"
  if($LASTEXITCODE -ne 0){throw 'pip bootstrap failed'}
}
Get-ChildItem "$root\whl" | Select-Object Name,Length
& "$pythonRoot\python.exe" --version
