<#
.SYNOPSIS
  newplay-hub.ps1 — NewPlay Hub(플랫폼)를 PowerShell 에서 수정·배포한다.

.DESCRIPTION
  SSH 없이 동작한다. 모든 것이 플랫폼 API 하나를 통과하며, 서버 쪽에서
  범위 검사와 자동 복구(빌드 실패·무응답 시 되돌리기)가 강제된다.
  게임팀 ProjectHub 는 다른 서버라 이 도구로는 닿지 않는다.

  대상 (-Target):
    platform (기본) — 플랫폼 웹(화면·API·스타일). 범위 src/·public/. 로컬 .\newplay-hub
    watcher          — AI 워처(역할 분배·라우팅·실행·검수 로직, *.py). 로컬 .\newplay-hub-ai
                       배포 = 컴파일·import 검사 → 재기동 → 생존 확인. 결과가 바로 온다.

  준비 (최초 1회):
    1. 토큰을 환경변수로 저장:  setx NEWPLAY_TOKEN "nph_..."   (새 창부터 적용)
    2. 소스 받기:               .\newplay-hub.ps1 pull
       → .\newplay-hub\ 에 git 저장소가 생긴다. 여기서 코드를 고친다.

  일상 작업:
    코드 수정 후 →  .\newplay-hub.ps1 check    (배포 없이 판정만)
                →  .\newplay-hub.ps1 deploy -Title "무엇을 바꿨는지"
    문제 생기면 →  .\newplay-hub.ps1 history   (커밋 확인)
                →  .\newplay-hub.ps1 rollback <커밋>

.NOTES
  deploy 는 서버에서 빌드+재기동까지 한다(30초~2분). 실패하면 서버가 스스로 되돌린다.
  서버까지 죽는 최악의 경우는 이 도구로 복구할 수 없다 — 지수님께 연락한다(프로토콜 문서 참조).
#>
[CmdletBinding()]
param(
  [Parameter(Position = 0)] [string]$Command = "help",
  [Parameter(Position = 1)] [string]$Arg = "",
  [string]$Title = "",
  [string]$BaseUrl = "https://newplay.tailf6f809.ts.net",
  [string]$Token = $env:NEWPLAY_TOKEN,
  [ValidateSet("platform", "watcher")] [string]$Target = "platform",
  [string]$RepoDir = ""
)
# 대상마다 로컬 저장소를 따로 둔다 — 두 트리는 서로 다른 git 이력이라 섞이면 diff 가 깨진다.
if (-not $RepoDir) { $RepoDir = if ($Target -eq "watcher") { ".\newplay-hub-ai" } else { ".\newplay-hub" } }

$ErrorActionPreference = "Stop"
# PS 5.1 기본이 TLS1.0 이라 최신 TLS 를 명시해야 Funnel 에 붙는다.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# 첫 실행에서 가장 자주 터지는 것부터 미리 확인한다 — 에러 스택보다 안내가 낫다.
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "git 이 설치돼 있지 않습니다. https://git-scm.com 에서 설치 후 새 창에서 다시 실행하세요." -ForegroundColor Yellow
  exit 1
}

$Api = "$BaseUrl/api/platform/apply"

function Need-Token {
  if (-not $Token) {
    Write-Host "토큰이 없습니다. 지수님께 발급받아 아래처럼 저장하세요:" -ForegroundColor Yellow
    Write-Host '  setx NEWPLAY_TOKEN "nph_..."   (저장 후 새 PowerShell 창에서 사용)'
    exit 1
  }
}

function Invoke-Api {
  param([string]$Method = "GET", [string]$Query = "", $Body = $null)
  Need-Token
  $headers = @{ Authorization = "Bearer $Token" }
  $uri = $Api + $Query
  # 보내는 쪽: 한글이 깨지지 않게 UTF-8 바이트로 보낸다.
  # 받는 쪽: PS 5.1 은 charset 선언이 없는 JSON 을 ISO-8859-1 로 읽어 한글을 깨뜨린다
  # (실측: 배포는 성공했는데 제목 매칭이 깨진 글자 때문에 실패해 폴링이 6분을 헛돌았다).
  # 그래서 원시 바이트를 받아 UTF-8 로 직접 해독한다.
  if ($null -ne $Body) {
    $json = $Body | ConvertTo-Json -Depth 6 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $resp = Invoke-WebRequest -Uri $uri -Method $Method -Headers $headers `
      -ContentType "application/json; charset=utf-8" -Body $bytes -TimeoutSec 660 -UseBasicParsing
  } else {
    $resp = Invoke-WebRequest -Uri $uri -Method $Method -Headers $headers -TimeoutSec 660 -UseBasicParsing
  }
  $text = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
  return $text | ConvertFrom-Json
}

function Get-LocalPatch {
  # 로컬 저장소의 미커밋 변경 전체를 패치로 만든다.
  if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
    Write-Host "로컬 저장소가 없습니다. 먼저 받으세요:  .\newplay-hub.ps1 pull" -ForegroundColor Yellow
    exit 1
  }
  Push-Location $RepoDir
  $previousIndex = $env:GIT_INDEX_FILE
  $temporaryIndex = Join-Path $env:TEMP ("newplay-index-" + [guid]::NewGuid().ToString("N"))
  try {
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    # 실제 스테이징 상태는 보존하고 임시 인덱스로 새 파일까지 포함한다.
    $env:GIT_INDEX_FILE = $temporaryIndex
    git read-tree HEAD 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "패치 기준 HEAD를 읽지 못했습니다." }
    git add -N . 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "변경 파일 목록을 만들지 못했습니다." }
    $patch = git diff HEAD --binary --no-ext-diff --no-color 2>$null
    if ($LASTEXITCODE -ne 0) { throw "git diff 실패" }
    $ErrorActionPreference = $prevEap
    if (-not $patch) {
      Write-Host "변경된 것이 없습니다 (git diff 가 비어 있음)." -ForegroundColor Yellow
      exit 0
    }
    return ($patch -join "`n") + "`n"
  } finally {
    $env:GIT_INDEX_FILE = $previousIndex
    $ErrorActionPreference = $prevEap
    Remove-Item -LiteralPath $temporaryIndex -Force -ErrorAction SilentlyContinue
    Pop-Location
  }
}

function Show-Result {
  param($r)
  if ($r.ok) {
    Write-Host "성공" -ForegroundColor Green
    if ($r.commit)        { Write-Host ("  커밋: " + $r.commit) }
    if ($r.revert_commit) { Write-Host ("  revert 커밋: " + $r.revert_commit) }
    if ($r.steps)         { Write-Host ("  단계: " + ($r.steps -join " → ")) }
  } else {
    Write-Host "실패" -ForegroundColor Red
    if ($r.reason)       { Write-Host ("  사유: " + $r.reason) }
    if ($r.out_of_scope) { Write-Host ("  범위 밖: " + ($r.out_of_scope -join ", ")) }
    if ($r.build_error)  { Write-Host "  빌드 오류:"; Write-Host ("    " + $r.build_error) }
  }
}

switch ($Command.ToLower()) {

  "pull" {
    Need-Token
    $bundle = Join-Path $env:TEMP "newplay-hub.bundle"
    Write-Host "서버에서 소스 번들 내려받는 중…"
    # $Api?bundle 이라 쓰면 PS 가 `Api?` 를 변수명으로 읽는다(? 는 변수명에 허용되는 문자다).
    Invoke-WebRequest -Uri "${Api}?bundle=1&target=$Target" `
      -Headers @{ Authorization = "Bearer $Token" } -OutFile $bundle -TimeoutSec 300
    # git 은 진행 메시지를 stderr 로 쓴다 — Stop 상태에서 호출자가 2>&1 로 받으면 중단되므로 이 구간만 Continue.
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    if (Test-Path (Join-Path $RepoDir ".git")) {
      Push-Location $RepoDir
      try {
        git fetch $bundle "HEAD:refs/remotes/server/head" 2>&1 | Out-Null
        # 로컬에 미커밋 변경이 있으면 merge 가 거부된다(맞는 동작이다 — 덮어쓰면 안 되니까).
        # 잠시 stash 에 치웠다가 갱신 후 되살린다. 충돌이 나면 그대로 알려 준다.
        $dirty = git status --porcelain
        if ($dirty) { git stash push -u -m "newplay-hub pull 자동 보관" | Out-Null }
        git merge --ff-only refs/remotes/server/head 2>&1 | ForEach-Object { "$_" }
        if ($LASTEXITCODE -ne 0) { Write-Host "갱신 실패: 서버와 로컬 이력이 갈라졌습니다. 폴더를 지우고 pull 을 다시 하세요." -ForegroundColor Red }
        if ($dirty) {
          git stash pop 2>&1 | Out-Null
          if ($LASTEXITCODE -ne 0) {
            Write-Host "주의: 서버 변경과 로컬 수정이 겹쳤습니다. 파일의 충돌 표시(<<<<<<<)를 정리하세요." -ForegroundColor Yellow
          }
        }
        Write-Host "갱신 완료:" (git log --oneline -1)
      } finally { Pop-Location }
    } else {
      git clone $bundle $RepoDir 2>&1 | Out-Null
      if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $RepoDir ".git"))) {
        $ErrorActionPreference = $prevEap
        Write-Host "받기 실패: git clone 이 실패했습니다. 네트워크·토큰을 확인하세요." -ForegroundColor Red
        exit 1
      }
      Push-Location $RepoDir
      try { Write-Host "받기 완료:" (git log --oneline -1) } finally { Pop-Location }
    }
    $ErrorActionPreference = $prevEap
    Write-Host "→ $RepoDir 안에서 코드를 고친 뒤  check → deploy  하세요."
  }

  "check" {
    $patch = Get-LocalPatch
    Write-Host ("변경 판정 중… (패치 {0:n0}자)" -f $patch.Length)
    Show-Result (Invoke-Api -Method POST -Body @{ target = $Target; patch = $patch; check = $true })
  }

  "deploy" {
    if (-not $Title) {
      Write-Host '무엇을 바꿨는지 적어야 합니다:  .\newplay-hub.ps1 deploy -Title "설명"' -ForegroundColor Yellow
      exit 1
    }
    $patch = Get-LocalPatch
    Write-Host ("배포 요청 중… (패치 {0:n0}자)" -f $patch.Length)
    $r = Invoke-Api -Method POST -Body @{ target = $Target; patch = $patch; title = $Title }
    if (-not $r.accepted) {
      # 두 경우가 여기로 온다: ① 사전 검사에서 거부됨(어느 대상이든) ② watcher — 재기동이
      # 웹서버를 건드리지 않아 서버가 끝까지 기다렸다가 결과를 바로 돌려준다.
      Show-Result $r
      if (-not $r.ok) { exit 1 }
      Write-Host "로컬 저장소를 서버 상태로 동기화하는 중…"
      # 배포 대기 중 추가한 수정도 pull의 stash 경로로 보존한다.
      & $PSCommandPath pull -BaseUrl $BaseUrl -Token $Token -RepoDir $RepoDir -Target $Target
      exit 0
    }

    # 배포는 서버가 자기 자신을 재기동하는 일이라 즉시 응답이 올 수 없다.
    # 원장에 결과가 적힐 때까지 폴링한다 — 재기동 동안 접속 오류는 정상이므로 삼킨다.
    Write-Host "배포가 시작됐습니다. 서버가 빌드+재기동하는 동안 잠시 끊깁니다 — 결과 대기 중…"
    $begun = (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("yyyy-MM-ddTHH:mm:ss")
    $found = $null
    for ($i = 0; $i -lt 60; $i++) {
      Start-Sleep -Seconds 6
      try {
        $h = Invoke-Api -Query "?history=1&target=$Target"
        foreach ($it in $h.items) {
          if ($it.task_title -eq $Title -and ("" + $it.at) -gt $begun) { $found = $it; break }
        }
      } catch { Write-Host "." -NoNewline }
      if ($found) { break }
    }
    Write-Host ""
    if (-not $found) {
      Write-Host "6분 안에 결과가 확인되지 않았습니다. history 로 직접 확인하세요." -ForegroundColor Yellow
      exit 1
    }
    if ($found.status -eq "deployed") {
      Write-Host ("성공 · 커밋 " + $found.commit) -ForegroundColor Green
      Write-Host "로컬 저장소를 서버 상태로 동기화하는 중…"
      # 배포 대기 중 추가한 수정도 pull의 stash 경로로 보존한다.
      & $PSCommandPath pull -BaseUrl $BaseUrl -Token $Token -RepoDir $RepoDir -Target $Target
    } else {
      Write-Host ("실패 · " + $found.status) -ForegroundColor Red
      if ($found.error) { Write-Host ("  " + $found.error) }
      Write-Host "  서버는 이전 상태로 자동 복구됐습니다. 로컬 변경은 그대로 남아 있으니 고쳐서 다시 시도하세요."
    }
  }

  "history" {
    $r = Invoke-Api -Query "?history=1&target=$Target"
    Write-Host ("[" + $Target + "]")
    foreach ($i in $r.items) {
      $mark = "· "
      if ($i.status -eq "deployed")     { $mark = "✔ " }
      if ($i.status -eq "rolled_back")  { $mark = "↩ " }
      if ($i.status -eq "build_failed") { $mark = "✖ " }
      Write-Host ("{0}{1,-13} {2,-9} {3}  {4}" -f $mark, $i.status, $i.commit, `
        ("" + $i.at).Substring(0, [Math]::Min(19, ("" + $i.at).Length)), $i.task_title)
    }
  }

  "rollback" {
    if (-not $Arg) {
      Write-Host '되돌릴 커밋을 지정하세요:  .\newplay-hub.ps1 rollback <커밋>  (history 로 확인)' -ForegroundColor Yellow
      exit 1
    }
    $r = Invoke-Api -Method POST -Body @{ target = $Target; revert = $Arg }
    if (-not $r.accepted) {
      # watcher 는 동기 — 결과가 바로 온다. platform 의 사전 거부도 여기로 온다.
      Show-Result $r
      if ($r.ok) { & $PSCommandPath pull -BaseUrl $BaseUrl -Token $Token -RepoDir $RepoDir -Target $Target }
      exit ([int](-not $r.ok))
    }
    Write-Host "되돌리기가 시작됐습니다. 재빌드+재기동 동안 잠시 끊깁니다 — 결과 대기 중…"
    $begun = (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("yyyy-MM-ddTHH:mm:ss")
    $found = $null
    for ($i = 0; $i -lt 60; $i++) {
      Start-Sleep -Seconds 6
      try {
        $h = Invoke-Api -Query "?history=1&target=$Target"
        foreach ($it in $h.items) {
          if ($it.status -in @("reverted", "rollback_failed") -and $it.revert_of -like "$Arg*" -and ("" + $it.at) -gt $begun) { $found = $it; break }
        }
      } catch { Write-Host "." -NoNewline }
      if ($found) { break }
    }
    Write-Host ""
    if ($found -and $found.status -eq "reverted" -and $found.healthy -eq $true) {
      Write-Host ("되돌림 · revert 커밋 " + $found.commit) -ForegroundColor Green
    } elseif ($found) {
      Write-Host ("되돌리기 실패 · " + $found.error) -ForegroundColor Red
      exit 1
    } else {
      Write-Host "6분 안에 결과가 확인되지 않았습니다. history 로 직접 확인하세요." -ForegroundColor Yellow
      exit 1
    }
  }

  default {
    Write-Host @"
newplay-hub.ps1 — NewPlay Hub 를 PowerShell 에서 수정·배포

  .\newplay-hub.ps1 pull                       소스 받기/갱신 (.\newplay-hub\ 에 생김)
  .\newplay-hub.ps1 check                      로컬 변경이 적용 가능한지 판정 (배포 안 함)
  .\newplay-hub.ps1 deploy -Title "설명"       배포 (서버가 빌드+재기동, 실패 시 자동 복구)
  .\newplay-hub.ps1 history                    배포 이력
  .\newplay-hub.ps1 rollback <커밋>            그 커밋을 되돌리기

  공통 옵션:
    -Target platform (기본)   플랫폼 웹 — 범위 src/·public/, 로컬 .\newplay-hub
    -Target watcher           AI 워처 — 범위 최상위 *.py (배포 장치·requirements 제외), 로컬 .\newplay-hub-ai
    예)  .\newplay-hub.ps1 pull -Target watcher
         .\newplay-hub.ps1 deploy -Target watcher -Title "라우팅 규칙 수정"

  토큰: setx NEWPLAY_TOKEN "nph_..."  (지수님께 발급받아 1회 저장)
  범위 밖(.env·package.json·requirements·배포 장치·게임팀 시스템)은 서버가 거부한다.
"@
  }
}
