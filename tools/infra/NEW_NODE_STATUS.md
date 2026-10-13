# 신규 임베딩 노드 구축 현황

> 최종 갱신: 2026-07-28

## 현재 상태: **보류** (신규 HP 장비 Ubuntu 설치 실패)

새 팀 전용 임베딩/작업 환경을 신규 증설 PC에 올리려 했으나, 장비 자체가 리눅스를 부팅하지
못해 보류. 대신 **기존 인프라(Mother / aimed-sub)에 새 팀 공간을 만드는 방향**으로 전환.

---

## 신규 장비 정보

| 항목 | 값 |
|---|---|
| 모델 | HP Pavilion Gaming Desktop TG01-2xxx (System Board 8860) |
| 제품번호 | `3Y5X7PA#AB1` / S/N `4CE151C7JT` |
| CPU | Intel i7-11700F (11세대 Rocket Lake, 8C/16T) — **내장 그래픽 없음** |
| RAM | 32GB |
| GPU | RTX 3060 Ti (8GB) |
| 디스크 | 952GB |
| BIOS | AMI **F.21** (2023-07-11) |
| 기존 OS | Windows (미삭제) |

## 실패 원인 — BIOS ACPI 버그 (확정)

부팅 1.28초 시점 커널 oops:

```
RIP: acpi_ps_get_arg+0x16/0x70
pci_pm_runtime_suspend → __pci_set_power_state → acpi_pci_set_power_state
  → acpi_device_set_power → acpi_evaluate_object → acpi_ns_evaluate → 💥
Modules linked in: ... xhci_pci ... xhci_pci_renesas ...
```

리눅스가 PCI 장치를 런타임 절전으로 넘기며 ACPI 객체를 평가하다 펌웨어 버그를 밟아 크래시.
그 여파로 xHCI(USB) 컨트롤러가 정상화되지 못한다.

**증상 사슬:**

```
ACPI 크래시 (1.28s)
  → USB 컨트롤러 비정상
  → USB 장치가 724초(12분) 뒤 인식되거나 아예 미인식
  → casper: "Unable to find a medium containing a live file system"
  → "Attempt interactive netboot from a URL? yes no (default yes):"
  → stdin 읽기 실패 → `stdin: Invalid argument` 무한 반복
```

`stdin: Invalid argument` 플러드는 원인이 아니라 **맨 끝의 증상**이었다.

## 배제한 것 (전부 실측, 추정 아님)

| 가설 | 검증 방법 | 결과 |
|---|---|---|
| USB 데이터 손상 | raw 굽기 후 되읽기 SHA256 대조 (2회) | 완전 일치 — 무관 |
| USB 읽기 불량 | 캐시 우회(NoBuffering) 읽기 벤치 | 17.61 MB/s, 최악 청크 243ms, 스톨 없음 — 무관 |
| USB 쓰기 불량 | 200MB 쓰기 벤치 | 3.66 MB/s (느림). 단 `toram`으로도 실패 → 주원인 아님 |
| USB 포트 | 앞면 / 뒷면 USB3.0 | 둘 다 실패 |
| 굽기 방식 | Rufus ISO 모드 → raw(DD) | 둘 다 실패 |
| 커널 버전 | 6.8(24.04) / 6.8 HWE / 5.15(22.04) | 셋 다 동일 지점 실패 |
| 부팅 파라미터 | `toram`, `pcie_port_pm=off pcie_aspm=off`, `acpi=off` | 전부 실패 |

## 재개 시 할 일 (우선순위)

1. **BIOS 업데이트** — 근본 해결. HP 지원 페이지에서 제품번호 `3Y5X7PA#AB1` 검색,
   F.21보다 높은 버전 확인. Windows에서 업데이트하는 것이 안전.
2. **SATA Emulation: RAID → AHCI** (`Configuration` 탭). 리눅스 필수 설정.
   ⚠️ 바꾸면 기존 Windows가 부팅되지 않는다. BIOS 업데이트를 Windows에서 하려면
   먼저 RAID로 되돌릴 것.
3. **After Power Loss: Off → On** (`Configuration` 탭). 서버는 정전 후 자동 복귀해야 한다.
4. `POST Hotkey Delay: 0 → 5` (`Boot Options` 탭). 현재 0이라 부팅 중 F9/F10 진입이 어렵다.
5. 그래도 실패하면 USB를 배제한 설치(내장 디스크에 설치 이미지를 심어 부팅) 또는 장비 교체.

## 이미 준비되어 있는 자산

| 경로 | 용도 |
|---|---|
| `E:\ISO\ubuntu-24.04.4-live-server-amd64.iso` | 공식 SHA256 검증 완료 |
| `E:\ISO\ubuntu-22.04.5-live-server-amd64.iso` | 공식 SHA256 검증 완료 |
| `E:\AI\tools\infra\write-ubuntu-usb.ps1` | raw(DD) 굽기 + 되읽기 해시 검증 |
| `E:\AI\tools\infra\wipe-usb.ps1` | USB 완전 삭제 + 쓰기 성능 검증 |
| `E:\AI\tools\infra\provision-embed-node.sh` | SSH 열린 직후 실행할 기본 프로비저닝 |

**설치 시 반드시**: SSH Setup 화면에서 `Install OpenSSH server` 체크 +
`Import SSH identity: from GitHub` → **`jisupark-tech`**.
워크스테이션 공개키(`ssh-ed25519 AAAAC3...DH+5NM`)가 그 계정에 등록돼 있어,
설치가 끝나는 즉시 비밀번호 없이 원격 접속이 가능해진다. 이것만 놓치면 서버 앞에 다시 가야 한다.
