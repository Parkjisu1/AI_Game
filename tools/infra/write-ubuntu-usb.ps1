# write-ubuntu-usb.ps1 — Ubuntu ISO를 USB에 원본 그대로(raw/DD) 쓰고 검증한다.
#
# 왜 이 스크립트인가:
#   Rufus의 "ISO 모드"는 ISO 안의 파일을 FAT32로 풀어 복사하는 방식이라
#   부트 체인이 미묘하게 깨질 수 있다. 실제로 이번 USB가 그 상태였고
#   (initrd 로드 실패 → `VFS: Cannot open root device ""` 커널 패닉),
#   게다가 다른 용도로 쓴 잔재 파일까지 섞여 있었다.
#   raw 쓰기는 ISO를 바이트 단위 그대로 복사하므로 그런 변수가 아예 없다.
#
#   추가로, 쓰기 후 **읽어서 해시를 대조**한다. 이번처럼 부팅할 때마다
#   다른 지점에서 깨지는 증상은 매체 불량 신호인데, 검증 없이는 알 수 없다.
#
# 실행: PowerShell을 **관리자 권한으로** 열고
#         powershell -ExecutionPolicy Bypass -File E:\AI\tools\infra\write-ubuntu-usb.ps1
#
# ⚠️ 대상 디스크의 데이터는 전부 사라진다. 안전장치로 USB 버스가 아니거나
#    시스템/부팅 디스크면 실행을 거부한다.

[CmdletBinding()]
param(
  [string]$IsoPath      = "E:\ISO\ubuntu-24.04.4-live-server-amd64.iso",
  # 공식 SHA256 (releases.ubuntu.com/24.04/SHA256SUMS)
  [string]$ExpectedHash = "e907d92eeec9df64163a7e454cbc8d7755e8ddc7ed42f99dbc80c40f1a138433",
  [int]   $DiskNumber   = -1,   # 미지정 시 USB 디스크를 자동 탐색
  [switch]$SkipVerify           # 검증 생략 (권장하지 않음)
)

$ErrorActionPreference = "Stop"
function Say($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "!! $m" -ForegroundColor Yellow }
function Die($m) { Write-Host "`nXX $m" -ForegroundColor Red; exit 1 }

# ── 0. 관리자 권한 확인 ────────────────────────────────────────
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Die "관리자 권한이 필요하다. PowerShell을 '관리자 권한으로 실행'해서 다시 시도할 것."
}

# ── 1. ISO 확인 ────────────────────────────────────────────────
Say "ISO 확인"
if (-not (Test-Path $IsoPath)) { Die "ISO를 찾을 수 없다: $IsoPath" }
$iso = Get-Item $IsoPath
"{0}  ({1:N2} GB)" -f $iso.FullName, ($iso.Length / 1GB)

Write-Host "SHA256 계산 중... (1~2분)" -NoNewline
$isoHash = (Get-FileHash -Path $IsoPath -Algorithm SHA256).Hash.ToLower()
Write-Host " 완료"
"  계산값: $isoHash"
"  공식값: $($ExpectedHash.ToLower())"
if ($isoHash -ne $ExpectedHash.ToLower()) {
  Die "ISO 해시 불일치 — 파일이 손상됐거나 버전이 다르다. 다시 받을 것."
}
Write-Host "  → 일치. ISO 무결함." -ForegroundColor Green

# ── 2. 대상 디스크 특정 ────────────────────────────────────────
Say "대상 USB 디스크 탐색"
if ($DiskNumber -lt 0) {
  $cands = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsSystem -and -not $_.IsBoot })
  if ($cands.Count -eq 0) { Die "USB 디스크를 찾을 수 없다. USB를 꽂았는지 확인할 것." }
  if ($cands.Count -gt 1) {
    $cands | Format-Table Number, FriendlyName, @{n='GB';e={[math]::Round($_.Size/1GB,2)}}, BusType -AutoSize
    Die "USB 디스크가 여러 개다. -DiskNumber <번호> 로 명시할 것."
  }
  $disk = $cands[0]
} else {
  $disk = Get-Disk -Number $DiskNumber
}

# ── 3. 안전장치 — 실수로 내장 디스크를 밀지 않도록 ─────────────
if ($disk.BusType -ne 'USB') { Die "디스크 $($disk.Number)는 USB가 아니다 (BusType=$($disk.BusType)). 중단." }
if ($disk.IsSystem)          { Die "디스크 $($disk.Number)는 시스템 디스크다. 중단." }
if ($disk.IsBoot)            { Die "디스크 $($disk.Number)는 부팅 디스크다. 중단." }
if ($disk.Size -lt $iso.Length) {
  Die ("USB 용량({0:N2}GB)이 ISO({1:N2}GB)보다 작다. 중단." -f ($disk.Size/1GB), ($iso.Length/1GB))
}
if ($disk.Size -gt 128GB) { Warn "디스크가 $([math]::Round($disk.Size/1GB))GB로 크다. USB가 맞는지 다시 확인할 것." }

Say "지울 대상"
$disk | Format-Table Number, FriendlyName, @{n='GB';e={[math]::Round($_.Size/1GB,2)}}, BusType, PartitionStyle -AutoSize
Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue |
  Format-Table PartitionNumber, DriveLetter, @{n='GB';e={[math]::Round($_.Size/1GB,2)}} -AutoSize

Write-Host "이 디스크의 데이터가 전부 사라진다." -ForegroundColor Red
$ans = Read-Host "계속하려면 정확히 'YES' 입력"
if ($ans -cne 'YES') { Die "취소됨." }

# ── 4. 디스크 초기화 ───────────────────────────────────────────
Say "디스크 초기화"
Clear-Disk -Number $disk.Number -RemoveData -RemoveOEM -Confirm:$false
Start-Sleep -Seconds 2
Write-Host "  파티션 제거 완료" -ForegroundColor Green

# ── 5. raw 쓰기 ────────────────────────────────────────────────
Say "ISO 원본 쓰기 (raw)"
Warn "쓰는 동안 Windows가 '디스크를 포맷하시겠습니까?' 창을 띄울 수 있다 — 반드시 [취소]를 누를 것."

$devPath = "\\.\PhysicalDrive$($disk.Number)"
$bufSize = 4MB
$buffer  = New-Object byte[] $bufSize
$written = 0L
$sw      = [System.Diagnostics.Stopwatch]::StartNew()

$src = [System.IO.File]::Open($IsoPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
try {
  $dst = New-Object System.IO.FileStream($devPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
} catch {
  $src.Close()
  Die "디스크를 열 수 없다: $($_.Exception.Message)`n다른 프로그램이 USB를 쓰고 있을 수 있다. 탐색기 창을 모두 닫고 재시도할 것."
}

try {
  while ($true) {
    $read = $src.Read($buffer, 0, $bufSize)
    if ($read -le 0) { break }
    # 물리 디스크는 섹터(512B) 단위로만 쓸 수 있다. 마지막 조각은 0으로 채워 맞춘다.
    $chunk = $read
    if ($chunk % 512 -ne 0) {
      $pad = 512 - ($chunk % 512)
      [Array]::Clear($buffer, $chunk, $pad)
      $chunk += $pad
    }
    $dst.Write($buffer, 0, $chunk)
    $written += $read
    $pct = [math]::Round($written * 100 / $src.Length, 1)
    $mbps = if ($sw.Elapsed.TotalSeconds -gt 0) { [math]::Round($written / 1MB / $sw.Elapsed.TotalSeconds, 1) } else { 0 }
    Write-Progress -Activity "USB에 쓰는 중" -Status "$pct%  ($([math]::Round($written/1MB))MB / $mbps MB/s)" -PercentComplete $pct
  }
  $dst.Flush()
} finally {
  $dst.Close(); $src.Close()
  Write-Progress -Activity "USB에 쓰는 중" -Completed
}
$sw.Stop()
Write-Host ("  쓰기 완료: {0:N2} GB / {1:N0}초" -f ($written/1GB), $sw.Elapsed.TotalSeconds) -ForegroundColor Green

# ── 6. 검증 — 되읽어서 해시 대조 ───────────────────────────────
# 이 단계가 핵심이다. 이번 USB처럼 부팅마다 다른 지점에서 깨지는 매체는
# 쓰기는 성공한 것처럼 보여도 되읽으면 값이 다르다.
if ($SkipVerify) {
  Warn "검증을 건너뛴다 (-SkipVerify)."
} else {
  Say "검증 (되읽기 해시 대조)"
  Start-Sleep -Seconds 3
  $vs = New-Object System.IO.FileStream($devPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
  try {
    $sha  = [System.Security.Cryptography.SHA256]::Create()
    $left = $iso.Length
    $vbuf = New-Object byte[] $bufSize
    $done = 0L
    while ($left -gt 0) {
      # 섹터 정렬 유지: 항상 bufSize로 읽고, ISO 길이만큼만 해시에 넣는다.
      # (raw 쓰기는 마지막 조각을 0으로 패딩했으므로 그 뒤는 대조 대상이 아니다)
      $got = $vs.Read($vbuf, 0, $bufSize)
      if ($got -le 0) { break }
      $use = [Math]::Min([long]$got, $left)
      $sha.TransformBlock($vbuf, 0, [int]$use, $null, 0) | Out-Null
      $left -= $use; $done += $use
      Write-Progress -Activity "검증 중" -PercentComplete ([math]::Round($done * 100 / $iso.Length, 1))
    }
    $sha.TransformFinalBlock((New-Object byte[] 0), 0, 0) | Out-Null
    $usbHash = ($sha.Hash | ForEach-Object { $_.ToString("x2") }) -join ""
  } finally {
    $vs.Close(); Write-Progress -Activity "검증 중" -Completed
  }

  "  USB 해시: $usbHash"
  "  ISO 해시: $isoHash"
  if ($usbHash -ne $isoHash) {
    Die "검증 실패 — USB에 쓰인 내용이 ISO와 다르다.`n이 USB는 불량이다. **다른 USB를 사용할 것.**"
  }
  Write-Host "  → 일치. USB 정상." -ForegroundColor Green
}

Say "완료"
@"
USB 준비 끝. 이제 새 PC에 꽂고 부팅하면 된다.

  · 부팅 메뉴에서 'Try or Install Ubuntu Server' 선택
  · Windows 탐색기가 이 USB를 '포맷하라'고 해도 무시할 것
    (ISO 원본 방식이라 Windows가 못 읽는 게 정상이다)

설치 중 잊지 말 것:
  1) SSH Setup → Install OpenSSH server 체크
                 → Import SSH identity: from GitHub → jisupark-tech
  2) Storage → ubuntu-lv 크기가 디스크 전체인지 확인
"@
