# NewPlay 외장 저장장치 준비 — 2026-09-17

작업 PC: AIMED. 외장 장치들은 이 PC에 연결돼 있다. NewPlay 전용 PC DESKTOP-DPTR8RL에는 USB 저장장치가 연결되지 않은 상태를 확인했다.

## 확인한 장치

| 장치 | 내용 | 현재 처리 |
|---|---|---|
| F:, Seagate Expansion HDD, 약 1TB | exFAT, 기존 사용량 약 283GiB, 여유 약 649GiB | 관리자 읽기 전용 검사 완료: 오류 없음, 종료 코드 0. Dirty / Full Repair Needed 표시는 남음 |
| H:, Generic Flash Disk, 약 16GB | 처음에는 G:/H:로 보이던 하나의 USB. 새 Ubuntu 설치 파일 기록됨 | 제작·파일 검증 완료. 대상 PC 실제 부팅은 아직 확인하지 않음 |

F:의 파일시스템 오류 표시만으로 물리적인 고장을 확정할 수는 없다. 기존 자료를 보존하기 전에는 포맷하거나 강제 수리하지 않는다. 이 문서는 현재 진행 상태이며 검사 통과 기록이 아니다.

## 설치 파일 준비 완료

- Ubuntu Desktop 24.04.5.1 amd64, 6,250,332,160 bytes.
- 파일: `downloads/ubuntu-24.04.5.1-desktop-amd64.iso`.
- 공식 SHA256과 다운로드 파일이 일치: `4da4a0c9035da8e68a59a838674f403f0a54472c78a83b4fb7f78d03588f85a7`.
- 공식 원본: https://releases.ubuntu.com/24.04/SHA256SUMS
- Rufus 4.15 portable: `downloads/rufus-4.15p.exe`.
- GitHub 공식 release digest 일치, Windows 전자서명 Valid / Akeo Consulting 확인.
- Rufus 창의 `준비` 표시와 시작 버튼 활성화를 16:13에 확인했다. USB 파일 기록은 완료됐다. 파일 대조와 대상 PC에서의 실제 부팅 검사는 별도다.

## 최신 확인 — 19:25

- 설치 USB: 원본 목록의 448개 파일이 모두 일치했다. 해당 목록에 없는 EFI 부팅 파일 3개도 검증된 ISO의 SHA256과 별도 대조해 모두 일치했다. 최종 판정은 `usb-final-verification.json`의 `file_verification_passed: true`다. SHA256 대조 대상은 총 28개다.
- 초기 `usb-file-verification.json`은 위 3개가 미검사여서 종합 판정이 false였다. 파일 불일치가 발견된 것은 아니며, 원본 기록은 그대로 두고 추가 검사 결과를 최종 보고서로 남겼다.
- F: 기존 사용자 자료 251,884개, 286,470,867,265 bytes는 E: 별도 폴더로 17:46에 모두 복사됐다. Robocopy 실패·불일치는 0이었다.
- F: 백업은 전체 내용 검증 중이다. 19:25 확인 시 약 5.5만 개 파일의 해시 대조가 끝났고 현재까지 불일치가 없다. 전체 검증 완료로 취급하지 않는다.
- 백업 위치: `E:\AI\backups\external-F-20260917`. 진행 상태는 해당 폴더의 `status.json`, `verification-progress.json`을 확인한다.
- NewPlay 서버 자체 백업, F: 수리, Ubuntu 설치는 아직 실행하지 않았다. NewPlay 컨테이너 8개가 계속 실행 중임을 확인했다.

## 16:20 진행 기록 — 아래는 당시 상태

- Rufus 창은 닫아도 된다. USB는 파일 대조가 끝날 때까지 연결해 둔다. 시작 버튼을 다시 누를 필요는 없다.
- `verify_install_usb.py`가 읽기 전용으로 원본의 448개 파일과 대조 중이다. 핵심 부팅 파일과 설치 데이터는 SHA256도 확인한다. 결과 파일은 `usb-file-verification.json`이다. 아직 결과 파일이 없으면 검증 완료가 아니다. USB 읽기 속도가 낮아 시간이 걸리고 있다.
- 최초 자동 대기는 USB 기록이 30분 안에 끝나지 않아 종료됐다. 16:13에 Rufus 완료를 확인한 뒤 검증을 다시 실행했다. 자동 대기 종료를 검증 통과로 취급하지 않았다.
- F: 관리자 읽기 전용 검사는 14:30에 완료됐다. 파일 251,886개를 확인했고, 출력은 `파일 시스템에 문제가 없음`, 종료 코드 0이다. 수리는 하지 않았다. 물리 디스크 전체 표면 검사를 했다는 뜻은 아니다.
- F:의 `Dirty / Full Repair Needed` 표시는 16:13 재확인에서도 남아 있었다. 검사 결과와 경고 표시를 함께 기록하며, 완전 정상이나 물리 고장으로 단정하지 않는다.
- F:에 이미 들어 있는 자료 약 283GiB의 별도 사본 여부를 사용자에게 확인 중이다. 답변 없이 수리를 진행하지 않는다.
- NewPlay 서버 백업과 Ubuntu 설치는 아직 하지 않았다. 이 두 장치가 연결된 곳은 준비용 PC AIMED다.
- 설치 이미지 대조용으로 잠깐 연결한 가상 G:는 대조 자료를 확보한 뒤 해제했다. 현재 설치 USB는 H:다.

## Rufus 설정 참고 — 제작은 완료됐으므로 다시 실행할 필요 없음

1. 장치가 **Generic Flash Disk / 약 16GB**인지 확인한다. 약 1TB Seagate는 백업용이므로 선택하지 않는다.
2. 부트 선택에 `ubuntu-24.04.5.1-desktop-amd64.iso`가 표시되는지 확인한다.
3. 실제 만들어진 USB는 MBR/FAT32이며 EFI 부팅 파일이 있다. 대상 PC에서 부팅이 안 될 경우 GPT/UEFI 설정으로 재제작하는 방법은 Ubuntu 공식 안내를 따른다. 현재 부팅 실패가 확인된 상태는 아니므로 다시 기록하지 않는다.
4. 시작을 누르면 선택한 16GB USB의 기존 Ubuntu 22.04 설치 내용이 지워진다. 보존할 별도 USB 자료가 있다면 먼저 보관한다.
5. ISO 쓰기 방식 선택 창이 나오면 권장 ISO 이미지 모드를 사용한다.
6. 완료 표시까지 기다리고, 오류가 나면 그 내용을 기록한다.

검증되지 않은 상태에서 NewPlay PC의 Windows를 지우지 않는다. NewPlay 전체 백업·복원 확인은 별도 단계다.

## F: 처리에 필요한 현재 확인

- 기존 자료의 다른 사본이 있는지 사용자에게 확인 중.
- 별도 사본이 없다면, 파일시스템 수리 전에 여유 공간이 있는 E:의 별도 폴더에 보존하는 방안을 사용한다.
- 검사 결과: `admin-readonly-result.json`이 생성되면 확인한다. 진행 상태는 `admin-readonly-state.json`, 검사 출력은 `chkdsk-admin-readonly.stdout.txt`다.
- 일반 권한 검사에는 Access is denied가 표시돼 결과를 정상 판정에 사용하지 않았고, 관리자 권한 검사로 전환했다.
- F: 자동 수리·포맷은 실행하지 않았다. 16GB USB의 설치 파일 복사는 완료됐고 원본과 파일 대조 중이다.

## 공식 참고

- Rufus 완료 표시와 USB 설정: https://ubuntu.com/desktop/docs/en/latest/how-to/create-a-bootable-usb-stick/
- Dirty 표시는 파일시스템의 불일치 가능성을 나타내며 원인은 여러 가지다: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/fsutil-dirty
