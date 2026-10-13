# wipe-usb.ps1 — USB 스틱을 완전히 밀고, 실제로 쓰기가 되는지 검증한다.
#
# 목적 2가지:
#   1) ISO를 원본(raw)으로 구운 USB는 Windows가 인식할 파티션이 없어 탐색기에서 포맷이 안 된다.
#      diskpart clean으로 파티션 테이블째 지우고 새로 만든다.
#   2) "디스크가 쓰기 금지되어 있습니다" 증상의 정체를 확정한다.
#      readonly 속성을 지우고 실제로 파일을 써보면 소프트웨어 플래그인지 하드웨어 고장인지 갈린다.
#
# 실행: 관리자 권한 PowerShell
#         powershell -ExecutionPolicy Bypass -File E:\AI\tools\infra\wipe-usb.ps1

[CmdletBinding()]
param(
  [int]$DiskNumber = -1,
  [ValidateSet('FAT32','exFAT','NTFS')]
  [string]$FileSystem = 'FAT32',
  [string]$Label = 'USB'
)

$ErrorActionPreference = "Stop"
function Say($m)  { Write-Host "`n== $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "!! $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "`nXX $m" -ForegroundColor Red; exit 1 }

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Die "관리자 권한이 필요하다."
}

# ── 대상 특정 + 안전장치 ──────────────────────────────────────
# 64GB 상한이 핵심 안전장치다. 데이터가 든 931GB 외장하드를 실수로 잡지 않기 위한 것.
Say "대상 탐색"
if ($DiskNumber -lt 0) {
  $cands = @(Get-Disk | Where-Object {
    $_.BusType -eq 'USB' -and -not $_.IsSystem -and -not $_.IsBoot -and $_.Size -lt 64GB
  })
  if ($cands.Count -eq 0) { Die "조건에 맞는 USB 스틱이 없다 (USB 버스 / 64GB 미만 / 시스템·부팅 아님)." }
  if ($cands.Count -gt 1) {
    $cands | Format-Table Number, FriendlyName, @{n='GB';e={[math]::Round($_.Size/1GB,2)}} -AutoSize
    Die "후보가 여러 개다. -DiskNumber 로 명시할 것."
  }
  $disk = $cands[0]
} else {
  $disk = Get-Disk -Number $DiskNumber
}

if ($disk.BusType -ne 'USB') { Die "디스크 $($disk.Number)는 USB가 아니다 (BusType=$($disk.BusType))." }
if ($disk.IsSystem)          { Die "시스템 디스크다. 중단." }
if ($disk.IsBoot)            { Die "부팅 디스크다. 중단." }
if ($disk.Size -ge 64GB)     { Die "64GB 이상이다 — 외장하드일 수 있다. 중단." }

$disk | Format-Table Number, FriendlyName, @{n='GB';e={[math]::Round($_.Size/1GB,2)}}, BusType, PartitionStyle, IsReadOnly -AutoSize
$n = $disk.Number

# ── diskpart — readonly 해제 + clean ──────────────────────────
Say "readonly 해제 + 파티션 테이블 삭제"
$dpScript = Join-Path $env:TEMP "wipe_usb_$n.txt"
@"
select disk $n
attributes disk clear readonly noerr
clean
convert mbr
create partition primary
select partition 1
active noerr
exit
"@ | Set-Content -Path $dpScript -Encoding ASCII

$out = & diskpart.exe /s $dpScript 2>&1
Remove-Item $dpScript -Force -ErrorAction SilentlyContinue
$out | ForEach-Object { "  $_" }

if ($out -match "쓰기 금지|write.protect|write protected") {
  Die "쓰기 금지가 풀리지 않는다 — 컨트롤러 수준 고장이다. 이 스틱은 폐기할 것."
}

Start-Sleep -Seconds 3

# ── 포맷 ──────────────────────────────────────────────────────
Say "포맷 ($FileSystem)"
$part = Get-Partition -DiskNumber $n | Where-Object { $_.Size -gt 100MB } | Select-Object -First 1
if (-not $part) { Die "파티션 생성 실패." }
if (-not $part.DriveLetter) {
  $part | Add-PartitionAccessPath -AssignDriveLetter
  Start-Sleep -Seconds 2
  $part = Get-Partition -DiskNumber $n -PartitionNumber $part.PartitionNumber
}
$letter = $part.DriveLetter
Format-Volume -DriveLetter $letter -FileSystem $FileSystem -NewFileSystemLabel $Label -Confirm:$false | Out-Null
Get-Volume -DriveLetter $letter |
  Format-Table DriveLetter, FileSystemLabel, FileSystem, @{n='GB';e={[math]::Round($_.Size/1GB,2)}} -AutoSize

# ── 실제 쓰기 검증 — 이게 스틱 생사를 가른다 ──────────────────
# 포맷이 성공해도 컨트롤러가 맛이 간 스틱은 실제 데이터 쓰기에서 드러난다.
# 200MB를 쓰고 되읽어 해시를 대조하며, 속도도 함께 잰다(느리면 수명 끝물).
Say "쓰기 검증 (200MB 쓰고 되읽어 대조)"
$testFile = "${letter}:\__write_test.bin"
$size = 200MB
$rnd = New-Object byte[] (4MB)
(New-Object Random 1234).NextBytes($rnd)

try {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $fs = [IO.File]::Open($testFile, 'Create', 'Write')
  for ($i = 0; $i -lt ($size / 4MB); $i++) { $fs.Write($rnd, 0, 4MB) }
  $fs.Flush(); $fs.Close()
  $sw.Stop()
  $wMbps = [math]::Round($size / 1MB / $sw.Elapsed.TotalSeconds, 2)
  "  쓰기: {0:N0} MB / {1:N1}초 = {2} MB/s" -f ($size/1MB), $sw.Elapsed.TotalSeconds, $wMbps

  $sw2 = [Diagnostics.Stopwatch]::StartNew()
  $hash = (Get-FileHash -Path $testFile -Algorithm SHA256).Hash
  $sw2.Stop()
  $rMbps = [math]::Round($size / 1MB / $sw2.Elapsed.TotalSeconds, 2)
  "  읽기: {0:N1}초 = {1} MB/s" -f $sw2.Elapsed.TotalSeconds, $rMbps

  # 같은 데이터를 메모리에서 해시해 대조
  $sha = [Security.Cryptography.SHA256]::Create()
  for ($i = 0; $i -lt ($size / 4MB); $i++) { $sha.TransformBlock($rnd, 0, 4MB, $null, 0) | Out-Null }
  $sha.TransformFinalBlock((New-Object byte[] 0), 0, 0) | Out-Null
  $expect = ($sha.Hash | ForEach-Object { $_.ToString("x2") }) -join ""

  Remove-Item $testFile -Force -ErrorAction SilentlyContinue

  if ($hash.ToLower() -ne $expect) {
    Die "데이터 불일치 — 쓴 내용과 읽은 내용이 다르다. 스틱 불량 확정. 폐기할 것."
  }
  Write-Host "  → 데이터 일치." -ForegroundColor Green

  Say "판정"
  if ($wMbps -lt 5) {
    Warn "쓰기 $wMbps MB/s — 매우 느리다. 정상 USB 2.0도 8~15 MB/s는 나온다."
    Warn "포맷은 됐지만 수명 끝물로 보인다. 부팅 미디어로는 쓰지 말 것."
  } elseif ($wMbps -lt 15) {
    Warn "쓰기 $wMbps MB/s — USB 2.0 수준. 동작은 하나 설치 미디어로는 느리다."
  } else {
    Write-Host "쓰기 $wMbps MB/s — 정상. 설치 미디어로 사용 가능." -ForegroundColor Green
  }
} catch {
  Remove-Item $testFile -Force -ErrorAction SilentlyContinue
  Die "쓰기 검증 실패: $($_.Exception.Message)`n스틱 불량 확정. 폐기할 것."
}

Say "완료"
"드라이브 ${letter}: 로 사용 가능하다."
