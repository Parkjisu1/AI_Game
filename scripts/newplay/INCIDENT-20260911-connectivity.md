# NewPlay 접속 장애 조사·수정 기록 — 2026-09-11

대상: https://newplay.tailf6f809.ts.net/  
시간대: 한국 표준시(KST, UTC+09:00)

## 확인된 원인

Windows 업데이트가 공개 접속 입구 서버 `DESKTOP-DPTR8RL`의 재부팅을 촉발했다. 이 서버의 Tailscale은 **무인 실행 모드가 꺼져 있었고**, 재부팅 후 연결 프로필을 자동으로 불러오지 못해 `NeedsLogin` 상태에 머물렀다. 따라서 인터넷 공개 접속과 웹앱으로 향하는 SSH 터널이 함께 끊겼다.

실제 접속 경로는 다음과 같다.

```text
사용자 → Tailscale Funnel → newplay Windows 서버(100.111.77.39)
       → 127.0.0.1:3000 SSH 터널 → aimed-sub(100.87.87.59)의 웹앱
```

Windows 서비스가 `Running / Automatic`이어도 Tailscale의 네트워크 연결 프로필은 별도로 `NeedsLogin`일 수 있다. 이번 장애는 이 차이 때문에 부팅 시 터널 예약 작업만으로 복구되지 않았다.

업데이트와 재부팅의 인과관계는 Windows 이벤트로 확인했다. 특정 KB의 네트워크 결함이나 방화벽 변경이 원인이라는 증거는 확인되지 않았다.

## 로그 근거

| 시각 | 확인 내용 |
|---|---|
| 09-09 12:29:03 | Windows System 이벤트 1074: `MoUsoCoreWorker.exe`가 OS 서비스 팩 적용을 이유로 재시작 요청 |
| 09-09 12:31:45 | Windows System 이벤트 1074: `TrustedInstaller.exe`가 OS 업그레이드를 이유로 재시작 요청 |
| 09-09 12:31:59 | 서버의 마지막 Windows 부팅 시각 |
| 09-09 12:32:12.974 | Tailscale: `Start: serverMode=false` |
| 09-09 12:32:12.984 | Tailscale: `NoState -> NeedsLogin (WantRunning=false, nm=false)` |
| 09-09 12:32:29.756 | 다시 `serverMode=false`, `NeedsLogin`, `Tailscale is stopped` 기록 |
| 장애 조사 시 | SSH 터널 로그에 `connect to host 100.87.87.59 port 22: Connection timed out` 반복 |
| 09-11 15:13:00~15:13:05 | Tailscale GUI 실행 및 `NeedsLogin -> NoState -> Starting -> Running` 기록. 조사 시작 전 이미 연결이 복구된 상태였음 |
| 09-11 수정 전 | 영구 상태 파일에 `server-mode-start-key` 항목 없음 |
| 09-11 수정 후 | `server-mode-start-key` 항목 생성 확인 |
| 09-11 15:41:06.433 | 서비스 재시작 후 `Start: serverMode=true` |
| 09-11 15:41:06.865 | 서비스 재시작 후 `Starting -> Running (WantRunning=true, nm=true)` |

원본 증거는 newplay 서버에 있다.

- Windows 이벤트 뷰어: System, 이벤트 1074 / 6005 / 6006.
- `C:\ProgramData\Tailscale\Logs\tailscale-service-20260909T123210-1788924730.txt`
- `C:\ProgramData\Tailscale\Logs\tailscale-service-20260911T151300-1789107180.txt`
- `C:\ProgramData\Tailscale\Logs\tailscale-service-20260911T154105-1789108865.txt`
- `C:\newplay\logs\tunnel.log`
- `C:\newplay\logs\tailscale-restart-check-20260911.log`

## 적용한 수정

newplay 서버의 관리자 PowerShell에서 다음 설정을 적용했다.

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' set --unattended=true
```

사용자가 GUI를 실행하지 않아도 서비스가 저장된 연결 프로필로 자동 접속하도록 영구 설정했다. 기존 Funnel은 백그라운드 설정으로 `https://newplay.tailf6f809.ts.net`을 `http://127.0.0.1:3000`에 연결하고 있다.

공식 동작 설명: [Tailscale 무인 실행](https://tailscale.com/docs/how-to/run-unattended), [Funnel 재시작 시 동작](https://tailscale.com/docs/reference/tailscale-cli/funnel#effects-of-rebooting-and-restarting).

## 수정 후 검증

SYSTEM 권한의 일회성 작업으로 15:41:05에 Tailscale 서비스를 실제 재시작했다. 이후 무인 실행 상태와 자동 연결을 확인했다. 검증기의 첫 JSON 판독은 PowerShell 문자 인코딩 오류로 실패했으며, UTF-8로 보정한 검증을 15:43:27~15:43:35에 다시 실행해 종료 코드 `0`을 확인했다. 두 번째 검증에서는 서비스를 다시 재시작하지 않았다.

15:44 최종 확인 결과:

| 검증 | 결과 |
|---|---|
| 서비스 | `Running`, 시작 유형 `Automatic` |
| Tailscale | `BackendState=Running`, 무인 실행 프로필 영구 저장 |
| 공개 설정 | Funnel 활성, 프록시 `http://127.0.0.1:3000` |
| 서버 내부 웹앱 | HTTP `200` |
| Tailscale 내부 주소 경유 | 로그인 화면 HTTP `200`, TLS 검증 성공 |
| 공용 DNS로 해석한 인터넷 경로 | 로그인 화면 HTTP `200`, TLS 검증 성공, 접속 IP `103.84.155.153` |
| Google Public DNS / Cloudflare DNS | 모두 `Status=0`, 공용 IPv4 주소 두 개 반환 |

인터넷 경로는 `curl --doh-url https://cloudflare-dns.com/dns-query`로 공용 DNS를 사용해 확인했다. Tailscale 내부 주소로만 확인한 결과와 구분된다. 초기 DNS 조회 일부에서는 `NXDOMAIN`이 관찰됐지만, 최신 조회에서는 두 DNS 제공자 모두 정상 응답했다. 특정 문의자 PC의 DNS 캐시 상태는 수집하지 않았다.

검증 범위는 Tailscale 서비스 재시작 및 웹 로그인 화면까지다. Windows 전체 재부팅과 문의자 PC별 접속은 별도 검증 대상이다.

## 재확인 명령

newplay 서버에서:

```powershell
Get-Service Tailscale
& 'C:\Program Files\Tailscale\tailscale.exe' status
& 'C:\Program Files\Tailscale\tailscale.exe' funnel status
curl.exe --noproxy '*' -sS -L -o NUL -w '%{http_code}' http://127.0.0.1:3000/
```

외부 접속 경로 확인:

```powershell
curl.exe --noproxy '*' --doh-url https://cloudflare-dns.com/dns-query -sS -L -o NUL -w 'status=%{http_code} remote_ip=%{remote_ip} tls=%{ssl_verify_result}' --connect-timeout 8 --max-time 20 https://newplay.tailf6f809.ts.net/
```

보고서에 기록된 공용 IP는 관측 당시 값이며, 접속 주소를 해당 IP로 고정하지 않는다.
