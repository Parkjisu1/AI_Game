# 운영자가 받을 것과 확인할 것

일반 팀원은 웹 주소로 들어가는 사람, 개발자는 코드를 고치는 사람, 운영자는 컴퓨터·데이터·계정을 책임지는 사람입니다. 서로 필요한 권한이 다릅니다.

| 권한 | 인수 방법 | 완료 확인 |
|---|---|---|
| Ubuntu 관리자 | 인수자 본인의 운영 계정/SSH 키 등록, 필요한 sudo 또는 Docker 권한 부여 | 인수자 본인이 로그인하고 상태 조회 |
| NewPlay 일반 사용자 | 허용 이메일에 본인 Google 계정 등록 | 실제 Google 로그인 |
| NewPlay 플랫폼 개발/관리자 | 허용 이메일에 더해 `.env.web`의 `ADMIN_EMAILS` 등록 | 본인 Hub 토큰으로 플랫폼/워처 조회·검사·배포 |
| Tailscale | 기존 팀 계정의 관리자 권한과 새 Ubuntu 기기 연결 | 인수자 PC에서 최종 팀 주소 HTTPS·WSS 접속 |
| Google OAuth | 현재 OAuth 프로젝트를 팀 관리 계정이 관리하도록 권한 이전, 최종 콜백 주소 확인 | 실제 팀원 로그인과 허용 목록 제거 검수 |
| 개인 Claude | 사람마다 본인 계정 토큰 등록 | 실제 작업 1건 완료 |
| 백업 | 운영자 전용 전체 백업과 별도 실제 설정 보관 | 별도 환경에서 복원하고 조회 |

이름·이메일·인수자 계정은 임의로 정하지 않았습니다. 현재 계정을 전부 폐기하지 않았고, 임시 QA 계정만 정확히 지정해 정리했습니다.

## 매일 확인하는 명령

Ubuntu 터미널에서 한 줄씩 실행합니다. `sudo`가 암호를 물으면 Ubuntu 본인 암호를 입력합니다.

```bash
cd /home/newplay/newplay-deploy
docker compose --env-file .env.compose ps
systemctl status newplay-backup.timer --no-pager
sudo journalctl -u newplay-backup.service -n 25 --no-pager
df -h /data /media/newplay/Expansion
```

서비스 재생성에는 **반드시 `--env-file .env.compose`**를 붙입니다. 빠뜨리면 Docker 그룹 번호가 기본값으로 바뀌어 터미널이 실패할 수 있습니다.

```bash
docker compose --env-file .env.compose up -d
```

웹 설정의 허용/관리자 이메일을 운영자가 변경했다면 영향을 받는 웹·배포 실행기·게이트웨이의 설정을 다시 반영합니다. 이 작업은 현재 터미널 연결에 영향을 줄 수 있어 사용자 없는 시간에 진행합니다.

```bash
docker compose --env-file .env.compose up -d --no-deps web ops gateway
```

개발자용 Hub 토큰은 운영자가 발급해 해당 사람에게만 전달합니다. 아래 이메일을 실제 인수자의 것으로 바꿉니다. 발급은 그 사람을 자동으로 관리자로 만들지 않습니다.

```bash
docker compose --env-file .env.compose exec ops python token_mint.py issue developer@example.com handoff
```

`token_mint.py revoke 이메일`은 **그 이메일의 토큰 전부**를 폐기합니다. QA 정리나 단일 토큰 교체 용도로 무심코 실행하지 않습니다. 실제 토큰은 공유 문서나 검수 로그에 붙이지 않습니다.

## 검증된 백업

- 서버: `/data/newplay-backups/20260918T180601`
- 외장하드: `/media/newplay/Expansion/NewPlay-native-backups/20260918T180601`
- Ubuntu 설치 전 원본: 외장하드 `NewPlay-server-backup-20260918` 및 Windows `E:\AI\backups\newplay-server-20260918`

새 백업의 `native-state.tar.zst`에는 소스·설정·DB 원본 볼륨·프로젝트 Git·개인 홈·검색 자료·Ollama 모델·백업 서비스 구성이 들어 있습니다. `newteam.archive.gz`는 운영 MongoDB 논리 백업, `docker-images.tar.zst`는 7개 실행 이미지입니다. 실제 비밀 설정과 사용자 자료가 포함되므로 운영자에게만 줍니다.

파일이 온전한지 확인:

```bash
cd /media/newplay/Expansion/NewPlay-native-backups/20260918T180601
sha256sum -c SHA256SUMS
```

`COMPLETE`와 해시 검증을 함께 확인합니다. 가장 오래된 17:31 백업은 외장 복사에서 소유권 오류가 있었으므로, 이번 이양은 위 **18:06 백업**을 기준으로 합니다.

## 다른 컴퓨터로 복구할 때의 순서

1. 새 Ubuntu와 Docker를 준비하고 인수자의 로그인부터 확인합니다. 기존 운영 PC 데이터 위에 덮어쓰지 않습니다.
2. 검증된 백업을 새 PC의 별도 폴더로 복사하고 `sha256sum -c SHA256SUMS`를 통과시킵니다.
3. 먼저 빈 점검 폴더에 `sudo tar --zstd -xpf native-state.tar.zst -C 점검폴더`로 풉니다. 이 폴더에는 비밀 설정이 있으므로 운영자만 접근하게 합니다.
4. 압축 안의 `home/newplay/newplay-deploy`, `home/newplay/preview-build.sh`, `data/newplay`를 확인합니다. 실행 이미지도 `zstd -dc docker-images.tar.zst | sudo docker image load`로 읽습니다.
5. 운영자가 대상 경로가 비어 있고 기존 서비스가 없는 것을 확인한 뒤 원래 경로에 소스와 데이터를 배치합니다. tar 안의 소유권을 유지하고, 새로 생긴 상위 폴더 소유권도 확인합니다. 특히 공유 Git의 `.git/worktrees`가 root 소유이면 개인 터미널과 AI 작업이 실패합니다.
6. 실제 호스트 UID/GID·Docker 그룹 번호를 `.env.compose`와 대조합니다. `.env.web`·`.env.watcher`의 실제 설정을 복원합니다. 예제 양식으로 덮어쓰지 않습니다.
7. `docker compose --env-file .env.compose config --quiet`로 구성을 확인합니다. 우선 Mongo·Qdrant·Ollama를 기동하고 복원된 DB·검색 자료를 확인한 다음 나머지 서비스를 기동합니다. 원본 볼륨 복원과 논리 DB 복원을 같은 데이터에 중복 적용하지 않습니다.
8. 웹 로그인·개인 터미널·작업 1건·배포와 되돌리기·백업을 인수자 계정으로 확인한 뒤 최종 주소를 전환합니다.

이 순서로 새 Ubuntu 24.04 시험 VM에 전체 백업을 실제 복원했고, 웹·터미널·검색 및 OS 재부팅 후 8개 서비스 자동 복귀를 확인했습니다. 시험 사용자는 원본과 같은 UID/GID 1000이었고 Docker 그룹 번호만 988로 맞췄습니다. 운영 HP의 물리 부팅 안정성과 인수자 자신의 계정 인수는 별도로 확인합니다. 상세 근거는 `04-qa/FOLLOWUP-20260918.md`입니다.

백업 예약도 복구하려면 아카이브의 `usr/local/sbin/newplay-native-backup.sh`, `usr/local/share/newplay/mongo-fingerprint.js`, `etc/systemd/system/newplay-backup.service`, `etc/systemd/system/newplay-backup.timer`를 같은 절대 경로에 소유권/실행 권한을 보존하여 복원합니다. 이후 `sudo systemctl daemon-reload`와 `sudo systemctl enable --now newplay-backup.timer`를 실행하고 `systemctl list-timers newplay-backup.timer`로 확인합니다. 외장 복사에는 Expansion 볼륨이 `/media/newplay/Expansion`에 실제 마운트돼 있어야 합니다. 없으면 내부 디스크 백업만 만들어집니다. 시험 VM에서는 예약 백업을 활성화하지 않았습니다.

Qdrant는 운영 구성과 같은 `nofile=65536`이 필요합니다. Mongo의 커널 우회 설정과 현재 부팅 안정성 한계는 `qa/REPORT.md`를 반드시 함께 읽습니다.

## 임시 접근 정리

브라우저 QA용 별도 SSH 키는 검수 후 제거합니다. 이관용 임시 키와 sudo 권한은 2026-09-19 02:45:47 KST에 자동 정리하도록 설정돼 있습니다. 인수자의 정상 접근을 확인한 뒤 더 일찍 정리할 때는 서버에서 다음을 실행합니다.

```bash
sudo /usr/local/sbin/newplay-migration-20260918-cleanup
```

이 명령 이후 임시 이관 키로 원격 작업할 수 없습니다. 상시 운영자 접근을 먼저 확인합니다.
