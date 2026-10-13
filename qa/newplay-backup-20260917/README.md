# F: 기존 자료 보존과 NewPlay 백업 준비

2026-09-17. 사용자의 `백업 진행` 요청 후 시작했다.

## 지금 실행한 백업

- 원본: AIMED 컴퓨터의 F:, Seagate Expansion HDD 약 1TB, exFAT.
- 사본: `E:\AI\backups\external-F-20260917\files`.
- 범위: 사용자 파일 251,884개, 286,470,867,265 bytes. 숨김 파일과 휴지통 자료도 포함한다.
- 제외: `F:\System Volume Information`의 Windows 볼륨 관리 정보. 제품 자료를 골라서 제외하지 않는다.
- 방법: 새 폴더에 Robocopy로 복사한다. 원본을 지우거나 옮기지 않으며 `/MIR`, `/PURGE`, `/MOVE`를 사용하지 않는다.
- 복사 후: 원본과 사본의 전체 파일·폴더 목록 및 크기, 모든 파일의 SHA256을 대조한다. 원본이 검증 도중 바뀌면 통과로 처리하지 않는다.
- 사본 폴더 접근권은 현재 Windows 사용자, 관리자, SYSTEM으로 제한했다.
- F: 파일시스템 수리·포맷은 실행하지 않았다.

## 진행 상태 확인

백업 폴더의 `status.json`을 확인한다.

- `copying`: 복사 중.
- `verifying`: 복사가 끝났고 내용 대조 중. `verification-progress.json`에 진행량이 기록된다.
- `complete`: 복사와 전체 대조 모두 완료. `verification.json`의 `passed`도 `true`여야 한다.
- `failed`: 완료로 취급하지 않는다. `robocopy.log`, `verification.json`, `sha256-files.jsonl`에서 원인을 확인한다.

`files` 폴더가 보이거나 일부 큰 파일의 크기가 원본과 같다는 이유만으로 완료로 판단하면 안 된다. 복사 중 미리 할당된 파일 공간일 수 있다.

복사와 대조가 끝날 때까지 현재 PC를 끄거나 F:를 빼지 않는다. 백업 중에는 F:의 원본을 편집하지 않는다. 재시작이 필요하면 같은 시작 스크립트를 그대로 재실행하지 말고, 기존 사본과 로그를 먼저 확인한다. 시작 스크립트는 기존 백업 폴더를 덮어쓰지 않도록 중단한다.

## 완료 알림

사용자의 `끝나면 알림` 요청에 따라 `Notify-Backup-Result.ps1`을 현재 Windows 사용자 세션에서 실행했다. 30초 간격으로 백업 상태를 확인한다. 전체 검증이 통과하면 이 PC에 완료 팝업과 시스템 알림음을 내고, 실패하거나 완료 결과 없이 검증 프로세스가 종료되면 확인 필요 팝업을 띄운다. 팝업은 확인 버튼을 누를 때까지 남는다. PC 음소거 상태에서는 알림음이 들리지 않을 수 있다.

알림 감시 기록은 이 문서 옆 `notification-watcher.json`에, 알림 결과는 `notification-result.json`에 남는다. 이 설정은 현재 PC가 켜져 있고 Windows 세션이 유지되는 동안 동작하며 재부팅 후 자동 시작 설정은 추가하지 않았다. 휴대폰이나 다른 사람에게 메시지를 보내는 방식은 아니다.

## NewPlay 서버 백업은 별도 단계

현재 실행 중인 것은 외장하드에 이미 있던 자료를 보존하는 작업이다. NewPlay 서버 데이터 백업을 완료했다는 뜻이 아니다.

NewPlay 전용 PC `DESKTOP-DPTR8RL`은 읽기 전용으로 용량과 경로만 확인했다. 서버 중단, DB 변경, Docker 재시작, WSL 종료는 하지 않았다.

- WSL 현재 사용 공간: 약 33.5GB.
- Linux 홈: 약 3.42GB, `/data/newplay`: 약 2.97GB, 기존 Qdrant 데이터: 약 0.30GB.
- Docker의 이미지 크기 표시: 약 15.42GB. 공유 레이어가 있으므로 실제 export 크기는 다를 수 있다.
- Windows `C:\newplay`: 4,636개 파일, 829,983,556 bytes.
- 확인한 Windows 바탕화면·문서·다운로드 추가 자료: 약 25MB.
- E:의 백업 전 여유는 약 443.7GB로, F: 사용자 자료 약 286.5GB를 복사한 뒤 약 157GB가 남는 계산이다. 실제 NewPlay 백업 직전에 남은 용량을 다시 확인한다.

NewPlay 서버는 기존 운영 경로와 Docker 경로가 함께 있고 DB도 두 벌이다. 두 DB 덤프, 네 Git 저장소 이력, 소스·비밀 설정·작업 폴더, Docker 이미지, Windows 자료, WSL 전체 사본을 보존하고 복원 시험해야 한다. Windows를 지우는 작업은 그 이후다.

전체 이전 절차: `E:\AI\scripts\newplay\handoff\beginner-runbook-20260917\START-HERE.md`.
