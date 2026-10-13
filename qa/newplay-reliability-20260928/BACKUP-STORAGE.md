# 외장 백업 디스크 운영·복구 안내

현재 HP의 외장 백업 디스크는 Expansion, exFAT, UUID `2E71-4623`이다. 고정 경로는 `/media/newplay/Expansion`이다.

2026-09-28 발견: 부팅 후 USB 디스크는 인식되지만 자동 마운트가 없어 외장 백업이 복사되지 않을 수 있었다. 또한 기존 백업 스크립트가 외장 디스크가 없을 때도 전체 성공으로 끝났다.

수정: 현재 HP의 `/etc/fstab`에 아래 항목을 추가했고, 백업 스크립트는 서버 내부 백업을 완료한 뒤 외장 복사를 못 하면 종료 코드 4와 `EXTERNAL_BACKUP_MISSING`을 남긴다. 기존 백업은 삭제하지 않는다.

```fstab
UUID=2E71-4623 /media/newplay/Expansion exfat defaults,nofail,x-systemd.device-timeout=10s,uid=1000,gid=1000,umask=0077 0 0
```

`nofail`은 디스크가 빠졌다고 PC 부팅까지 막지 않기 위한 설정이다. 외장 백업 누락은 `newplay-backup.service` 실패로 확인한다. 마운트 설정은 자동 로그인에 의존하지 않는다.

## 다른 PC 또는 새 디스크로 복구할 때

**전체 백업에는 기존 PC의 `/etc/fstab`을 포함하지 않는다.** 다른 PC의 시스템 디스크 설정을 덮어쓰지 않기 위해서다. 아래 단계는 인수 운영자가 새 환경에 맞춰 수행한다.

1. `lsblk -f`로 백업용 디스크의 실제 UUID·파일시스템을 확인한다. 현재 디스크를 그대로 옮기면 UUID는 위 값이고, 다른 디스크라면 새 값을 사용한다. 디스크를 포맷하지 않는다.
2. 인수 서버 사용자의 `id`로 UID/GID를 확인한다. 위 예시의 1000은 현재 newplay 계정 기준이다.
3. `/etc/fstab`을 별도로 백업하고 `sudoedit /etc/fstab`으로 백업 디스크 항목만 추가한다. 기존 같은 경로/UUID 항목이 있으면 중복으로 추가하지 않는다. 경로는 현 백업 스크립트와 맞추고 디스크 라벨도 Expansion인지 확인한다.
4. 마운트 경로를 준비한 뒤 `sudo findmnt --verify --tab-file /etc/fstab`, `sudo systemctl daemon-reload`, `sudo systemctl start media-newplay-Expansion.mount`로 검증·기동한다.
5. `findmnt --mountpoint /media/newplay/Expansion`에서 UUID·exFAT·경로를 대조한다.
6. 진행 중 업무와 개인 작업대가 없는 시간에 `sudo systemctl start newplay-backup.service`를 실행한다. 이 작업은 일관된 백업을 위해 NewPlay 서비스를 잠시 멈췄다가 다시 시작한다.
7. 서버 내부 `/data/newplay-backups/<시각>`와 외장 `NewPlay-native-backups/<시각>` 양쪽의 `COMPLETE`, `SHA256SUMS`를 확인한다. `systemctl show newplay-backup.service -p Result`도 확인한다.
8. 정상 재부팅 후 데스크톱에 로그인하기 전에 SSH로 외장 마운트·서비스·백업 예약이 정상인지 확인한다.

마운트 후 인식되는 모든 디스크를 포맷·초기화하거나 원본 데이터를 지우는 절차는 없다. 다른 파일시스템의 디스크를 사용한다면 exFAT 전용 UID/GID 옵션을 그대로 복사하지 말고 운영자가 맞춘다.

## 일상 점검

```bash
findmnt --mountpoint /media/newplay/Expansion
systemctl status newplay-backup.timer --no-pager
systemctl show newplay-backup.service -p Result -p ExecMainExitTimestamp
journalctl -u newplay-backup.service -n 25 --no-pager
```

서버 내부 `COMPLETE`만으로 외장 사본도 있다고 판단하지 않는다. 외장 사본과 실행 결과를 함께 확인한다. 백업 보관 파일은 자동 삭제하지 않으므로 여유 용량과 보관 기간도 운영자가 관리한다.

현재 적용 전 원본은 HP `/home/newplay/reliability-20260928/originals`에 root 전용으로 보존했다. 결과의 최종 판정은 함께 제공하는 최신 연속 검수 보고서를 따른다.
