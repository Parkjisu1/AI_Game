"""
Layer 3: Decision — Pixel Flow 전용
=====================================
Pixel Flow 전략:
  P0: 비-gameplay 화면 → playbook 핸들러
  P1: 홀더 가득 참 경고 → 홀더 돼지 희생
  P2: 큐에 돼지가 있으면 → PIL 감지 → 첫 번째 돼지 탭
  P3: 큐가 비었으면 → 홀더 돼지 재배치
  P4: 대기

TO DON'T:
  - 결제 버튼 탭 금지 (900 코인 등)
  - 보드 직접 탭 금지 (돼지만 탭)
"""

from pathlib import Path
from typing import List, Optional, Tuple

from .playbook import Action, Playbook
from .perception import BoardState
from .memory import GameMemory

try:
    from PIL import Image
    import numpy as np
    from scipy import ndimage
    _HAS_DETECT = True
except ImportError:
    _HAS_DETECT = False


def detect_queue_pigs(img_path: Path) -> List[Tuple[int, int]]:
    """PIL로 큐 돼지 위치 감지. (x, y) 리스트 반환, y 오름차순.

    방법: 큐 영역(y>1050)에서 흰색 숫자 텍스트 클러스터를 찾고,
    고정 UI 노이즈(y<1150)를 제외한 후 클러스터 중심 반환.
    """
    if not _HAS_DETECT or not img_path or not img_path.exists():
        return []

    try:
        img = Image.open(img_path)
        arr = np.array(img)

        # 큐 영역: y 970~1700 (홀더 아래), x 220~750
        # 레벨에 따라 위치 변동: Level 7: y≈1070-1400, Level 8+: y≈1430-1700
        y1, y2 = 970, 1700
        x1, x2 = 220, 750
        if arr.shape[0] < 1700 or arr.shape[1] < 750:
            return []

        region = arr[y1:y2, x1:x2]

        # 흰색 텍스트 (돼지 숫자): R>215, G>215, B>215
        white = (region[:, :, 0] > 215) & \
                (region[:, :, 1] > 215) & \
                (region[:, :, 2] > 215)

        # 클러스터 찾기
        labeled, num = ndimage.label(white)
        if num == 0:
            return []

        sizes = ndimage.sum(white, labeled, range(1, num + 1))
        centroids = ndimage.center_of_mass(white, labeled, range(1, num + 1))

        # 돼지 숫자 크기: 40~800 픽셀 (너무 작은 노이즈, 너무 큰 배경 제외)
        # 홀더 슬롯 영역(y<970) 제외 — 홀더 숫자 텍스트와 혼동 방지
        pigs = []
        for i, (cy, cx) in enumerate(centroids):
            if 40 < sizes[i] < 800:
                real_x = int(cx) + x1
                real_y = int(cy) + y1
                if real_y < 970:
                    continue  # 홀더 영역 스킵
                pigs.append((real_x, real_y))

        if not pigs:
            return []

        # 같은 돼지의 여러 클러스터를 병합 (거리 50px 이내)
        merged = []
        used = [False] * len(pigs)
        for i in range(len(pigs)):
            if used[i]:
                continue
            group = [pigs[i]]
            used[i] = True
            for j in range(i + 1, len(pigs)):
                if used[j]:
                    continue
                dx = abs(pigs[i][0] - pigs[j][0])
                dy = abs(pigs[i][1] - pigs[j][1])
                if dx < 50 and dy < 50:
                    group.append(pigs[j])
                    used[j] = True
            # 그룹 중심
            avg_x = int(sum(p[0] for p in group) / len(group))
            avg_y = int(sum(p[1] for p in group) / len(group))
            merged.append((avg_x, avg_y))

        # y 오름차순 정렬 (위에 있는 돼지 먼저)
        merged.sort(key=lambda p: (p[1], p[0]))
        return merged

    except Exception:
        return []


class DecisionPixelFlow:
    """Pixel Flow 전용 판단 엔진."""

    # 홀더 슬롯 고정 좌표 (5칸) — 2026-03-09 verified
    _HOLDER_POSITIONS = [
        (185, 930), (310, 930), (435, 930), (560, 930), (685, 930)
    ]

    # 큐 돼지 탭 좌표 — 레벨별 검증 위치 + 일반 밀집 그리드
    # BlueStacks screencap은 y>950 영역 픽셀 데이터가 부정확 (배경 레이어만 캡처)
    # → PIL 감지 불가, 폴백 그리드에 의존해야 함
    # 전략: 일반적인 돼지 영역을 밀집 커버 (50px 간격)
    _QUEUE_FALLBACK = [
        # === Priority: Level 11+ 세로 스택 (x≈590, y≈1080-1300) ===
        (590, 1080), (590, 1180), (590, 1280),
        (600, 1100), (600, 1200), (580, 1300),
        # === Level 8-10: 2열 그리드 ===
        (461, 1480), (617, 1480),
        (461, 1580), (617, 1580),
        # === Dense grid: x=350-700, y=1050-1500, 75px intervals ===
        (425, 1080), (500, 1080), (575, 1080), (650, 1080),
        (425, 1155), (500, 1155), (575, 1155), (650, 1155),
        (425, 1230), (500, 1230), (575, 1230), (650, 1230),
        (425, 1305), (500, 1305), (575, 1305), (650, 1305),
        (425, 1380), (500, 1380), (575, 1380), (650, 1380),
        (425, 1455), (500, 1455), (575, 1455), (650, 1455),
        # === Level 7: 3열 그리드 ===
        (290, 1070), (410, 1070), (530, 1070),
        (290, 1190), (410, 1190), (530, 1190),
        (290, 1310), (410, 1310), (530, 1310),
        # === Level 6: 4열 그리드 ===
        (223, 1330), (383, 1330), (539, 1330), (695, 1330),
        (379, 1493), (539, 1493), (691, 1493),
        # === Extra wide coverage ===
        (350, 1550), (500, 1550), (650, 1550),
        (350, 1650), (500, 1650), (650, 1650),
    ]

    # 탭 금지 영역 (IAP 트리거 방지)
    _FORBIDDEN_REGIONS = [
        (0, 0, 1080, 100),      # 상단 전체 (하트+/코인+ 버튼)
        (680, 0, 810, 200),     # 코인+ 및 X 버튼 영역 (Gold Pack 트리거)
    ]

    def __init__(self, playbook: Playbook):
        self.playbook = playbook
        self._deploy_index = 0
        self._last_screenshot: Optional[Path] = None

    def _is_gold_pack_showing(self) -> bool:
        """PIL로 골드 팩 스토어 화면 감지. KRW 가격 텍스트 영역 확인."""
        if not _HAS_DETECT or not self._last_screenshot:
            return False
        try:
            img = Image.open(self._last_screenshot)
            arr = np.array(img)
            # 골드 팩 헤더바: 진한 파란색 바 y≈230-270, 가로 전체
            # RGB approx (40,50,120) to (80,90,170)
            header = arr[230:270, 100:700]
            dark_blue = (header[:,:,0] < 90) & (header[:,:,1] < 100) & \
                        (header[:,:,2] > 120) & (header[:,:,2] < 200)
            if dark_blue.sum() > 500:
                return True
            # 녹색 KRW 가격 버튼: y≈480-530 또는 y≈720-770
            price_area = arr[480:530, 100:700]
            green = (price_area[:,:,0] < 100) & (price_area[:,:,1] > 180) & \
                    (price_area[:,:,2] < 100)
            if green.sum() > 200:
                return True
            return False
        except Exception:
            return False

    def _detect_holder_count(self) -> int:
        """PIL로 홀더 슬롯 사용 수 감지. 홀더 영역에서 색이 있는 슬롯 카운트."""
        if not _HAS_DETECT or not self._last_screenshot:
            return 0
        try:
            img = Image.open(self._last_screenshot)
            arr = np.array(img)
            # 홀더 슬롯 영역: y=880-980, 각 슬롯 x 위치 검사
            count = 0
            for (sx, sy) in self._HOLDER_POSITIONS:
                # 슬롯 중심 주변 30x30 영역 검사
                region = arr[sy-15:sy+15, sx-15:sx+15]
                if region.size == 0:
                    continue
                # 빈 슬롯: 어두운 배경 (R<80, G<80, B<100)
                # 채워진 슬롯: 밝거나 컬러풀 (R>100 or G>100 or B>150)
                avg_r = region[:, :, 0].mean()
                avg_g = region[:, :, 1].mean()
                avg_b = region[:, :, 2].mean()
                if avg_r > 100 or avg_g > 120 or avg_b > 160:
                    count += 1
            return count
        except Exception:
            return 0

    def _detect_pigs_dynamic(self) -> List[Tuple[int, int]]:
        """PIL로 큐 돼지 위치를 동적 감지. 폴백보다 정확."""
        pigs = detect_queue_pigs(self._last_screenshot) if self._last_screenshot else []
        return pigs

    def _is_real_pixelflow(self) -> bool:
        """인터랙티브 광고/loom 로딩화면 거부. 기본 True.

        확실한 비-게임플레이 화면만 거부 (오탐 최소화).
        """
        if not _HAS_DETECT or not self._last_screenshot:
            return True
        try:
            img = Image.open(self._last_screenshot)
            arr = np.array(img)
            if arr.shape[0] < 1200:
                return True  # 기본 통과

            # loom 로딩화면: 균일한 보라색 (stddev < 25, avg_B > 140)
            bg = arr[300:1500, 50:750]
            if bg.std() < 25 and bg[:,:,2].mean() > 140:
                return False

            # DOWNLOAD 버튼 감지: 하단에 밝은 녹색/빨간 버튼
            bottom = arr[1700:1880, 150:650]
            green = (bottom[:,:,1] > 200) & (bottom[:,:,0] < 100)
            if green.sum() > 2000:
                return False  # "DOWNLOAD" 버튼이 있는 광고

            return True
        except Exception:
            return True

    def decide(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """현재 상태에서 실행할 행동 결정."""

        screen = board.screen_type

        # P-1: "gameplay"이지만 실제 Pixel Flow가 아닌 경우 → interactive ad
        if screen == "gameplay" and not self._is_real_pixelflow():
            return [
                Action("back", wait=2.0, reason="Not Pixel Flow (interactive ad)"),
            ]

        # P0: 비-gameplay 화면 → playbook 핸들러
        if screen != "gameplay":
            handler = self.playbook.screen_handlers.get(screen)
            if handler:
                if screen == "lobby":
                    memory.on_game_start()
                    self._deploy_index = 0
                return handler.actions[:]

            unknown = self.playbook.screen_handlers.get("unknown")
            return unknown.actions[:] if unknown else [
                Action("back", wait=1.0, reason="No handler for " + screen)
            ]

        # --- gameplay 전략 ---

        # P0.5: interactive ad 감지 (PIL 기반으로만 — 연속 실패는 비활성화)
        # 이유: YOLO holder_count가 항상 0이므로 모든 탭이 "fail"로 기록됨
        # 연속 실패 기반 back은 정상 게임을 종료시킴
        # 대신 _is_real_pixelflow()가 False일 때만 back 실행 (P-1에서 처리)

        # PIL 홀더 감지 비활성화 (오탐율 높음, 항상 5 반환)
        # 대신 YOLO 결과 사용 (0이면 홀더 안전으로 간주)
        # TODO: 더 정확한 홀더 감지 구현 필요

        # P1: 홀더 가득 참 → 첫 번째 슬롯 희생
        if board.holder_count >= self.playbook.holder_critical:
            pos = self._HOLDER_POSITIONS[0]
            return [
                Action("tap", pos[0], pos[1], 2.0,
                       f"Sacrifice holder pig (slot 1, holder {board.holder_count}/5)")
            ]

        # P1.5: 홀더 위험 (4/5) → 큐 탭 일시 중지, 대기
        if board.holder_count >= self.playbook.holder_danger:
            return [
                Action("wait", wait=3.0,
                       reason=f"Holder danger ({board.holder_count}/5), waiting")
            ]

        # PIL 돼지 감지 비활성화: BlueStacks screencap은 y>950 픽셀 데이터가
        # 배경 레이어만 캡처하므로 white text 감지가 노이즈만 반환함.

        # CRITICAL: YOLO holder_count는 항상 0 반환 → 홀더 가득 차도 감지 불가.
        # holder 4/5 + belt pig 1 = 5 total이면 게임이 새 돼지 배치 차단.
        # 해결: 주기적 홀더 희생 (매 6턴마다 1회 sacrifice)
        # → 빈 홀더면 miss (무해), 가득 차면 슬롯 해제 → 배치 가능

        # P2: 주기적 홀더 희생 (6턴에 1회)
        if self._deploy_index > 0 and self._deploy_index % 6 == 0:
            pos = self._HOLDER_POSITIONS[
                (self._deploy_index // 6) % len(self._HOLDER_POSITIONS)
            ]
            self._deploy_index += 1
            return [
                Action("tap", pos[0], pos[1], 3.0,
                       f"Periodic sacrifice at slot ({pos[0]},{pos[1]})")
            ]

        # P3: 폴백 그리드 순회 — 5초 대기
        pos = self._get_fallback_position()
        return [
            Action("tap", pos[0], pos[1], 5.0,
                   f"Deploy pig #{self._deploy_index} at ({pos[0]},{pos[1]})")
        ]

    def _is_forbidden(self, x: int, y: int) -> bool:
        """좌표가 금지 영역 내인지 확인."""
        for (x1, y1, x2, y2) in self._FORBIDDEN_REGIONS:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return True
        return False

    def _get_fallback_position(self) -> tuple:
        """폴백 좌표 순회 (금지 영역 스킵)."""
        positions = self._QUEUE_FALLBACK
        for _ in range(len(positions)):
            idx = self._deploy_index % len(positions)
            self._deploy_index += 1
            pos = positions[idx]
            if not self._is_forbidden(pos[0], pos[1]):
                return pos
        return positions[0]  # 모든 위치가 금지되면 첫 번째 반환

    def set_screenshot(self, path: Path):
        """현재 스크린샷 경로 설정 (PIL 감지용)."""
        self._last_screenshot = path

    def reset(self):
        """새 게임 시작 시 리셋."""
        self._deploy_index = 0
        self._last_screenshot = None
