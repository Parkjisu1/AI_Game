"""
Phase 3: Auto Playbook Generator
==================================
스크린샷 + OCR 분석으로 Playbook을 자동 생성.

플로우:
  1. 게임 실행 → 5~10장 스크린샷 수집
  2. OCR + UI 분석 → 화면 유형 분류
  3. 버튼 좌표 자동 추출
  4. 화면 전이 그래프 생성
  5. Playbook 코드 생성

사람 개입 최소화: 게임 설치 + 스크립트 실행만으로 Playbook 완성.
"""

import json
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .playbook import Action, Playbook, ScreenHandler
from .universal_vision import (
    UniversalVision, ScreenClassifier, UIState, TextElement, UIRegion
)


@dataclass
class ScreenSample:
    """수집된 화면 샘플."""
    img_path: Path
    screen_type: str
    confidence: float
    ui_state: UIState
    timestamp: float


@dataclass
class ScreenProfile:
    """화면 유형별 프로필 (여러 샘플에서 집계)."""
    screen_type: str
    samples: List[ScreenSample] = field(default_factory=list)
    common_texts: List[str] = field(default_factory=list)
    button_positions: List[Tuple[int, int, str]] = field(default_factory=list)  # (x, y, text)
    close_positions: List[Tuple[int, int]] = field(default_factory=list)
    transitions_to: List[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.samples)


# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------
ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"


def _adb_screenshot(output_dir: Path, name: str = "frame") -> Optional[Path]:
    """ADB 스크린샷 캡처."""
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=10,
        )
        if len(r.stdout) < 1000:
            return None
        path = output_dir / f"{name}.png"
        path.write_bytes(r.stdout)
        return path
    except Exception:
        return None


def _adb_tap(x: int, y: int):
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _adb_back():
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "keyevent", "4"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _adb_launch(package: str):
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "monkey", "-p", package,
             "-c", "android.intent.category.LAUNCHER", "1"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# PlaybookGenerator
# ---------------------------------------------------------------------------
class PlaybookGenerator:
    """스크린샷 분석으로 Playbook 자동 생성.

    사용법:
        gen = PlaybookGenerator("com.example.game", "my_game")
        gen.collect_screens(num_screens=10, interval=5)
        playbook = gen.generate()
        gen.save_playbook(playbook, Path("playbook_mygame.py"))
    """

    def __init__(
        self,
        package: str,
        game_id: str,
        genre: str = "unknown",
        output_dir: Optional[Path] = None,
    ):
        self.package = package
        self.game_id = game_id
        self.genre = genre
        self.output_dir = output_dir or Path(
            f"E:/AI/virtual_player/data/games/{game_id}/playbook_gen"
        )
        self.vision = UniversalVision()
        self.classifier = ScreenClassifier()
        self.samples: List[ScreenSample] = []
        self.profiles: Dict[str, ScreenProfile] = {}

    def collect_screens(
        self,
        num_screens: int = 10,
        interval: float = 5.0,
        auto_interact: bool = True,
    ):
        """게임 실행 후 스크린샷 수집 + 분석.

        auto_interact=True면 각 화면에서 자동으로 버튼을 탭하여 전이 탐색.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[PlaybookGen] Launching {self.package}...")
        _adb_launch(self.package)
        time.sleep(8)

        prev_screen = None

        for i in range(num_screens):
            # 스크린샷
            img = _adb_screenshot(self.output_dir, f"screen_{i:03d}")
            if not img:
                print(f"  [{i}] Screenshot failed, skipping")
                time.sleep(interval)
                continue

            # UI 분석
            ui_state = self.vision.analyze(img)
            screen_type, conf = self.classifier.classify(ui_state)

            sample = ScreenSample(
                img_path=img,
                screen_type=screen_type,
                confidence=conf,
                ui_state=ui_state,
                timestamp=time.time(),
            )
            self.samples.append(sample)

            # 프로필 업데이트
            if screen_type not in self.profiles:
                self.profiles[screen_type] = ScreenProfile(screen_type=screen_type)
            profile = self.profiles[screen_type]
            profile.samples.append(sample)

            # 전이 기록
            if prev_screen and prev_screen != screen_type:
                if screen_type not in self.profiles.get(prev_screen, ScreenProfile(prev_screen)).transitions_to:
                    self.profiles.setdefault(prev_screen, ScreenProfile(prev_screen))
                    self.profiles[prev_screen].transitions_to.append(screen_type)

            # 버튼/텍스트 수집
            for btn in ui_state.buttons:
                profile.button_positions.append((btn.cx, btn.cy, btn.text))
            for close in ui_state.close_buttons:
                profile.close_positions.append((close.cx, close.cy))
            for text in ui_state.texts:
                if text.text not in profile.common_texts:
                    profile.common_texts.append(text.text)

            print(
                f"  [{i}] Screen: {screen_type} (conf={conf:.2f}) | "
                f"Texts: {len(ui_state.texts)} | "
                f"Buttons: {len(ui_state.buttons)} | "
                f"Close: {len(ui_state.close_buttons)}"
            )

            prev_screen = screen_type

            # 자동 인터랙션: 버튼 탭으로 화면 전이 탐색
            if auto_interact and ui_state.buttons:
                # 안전한 버튼만 (결제 키워드 제외)
                safe_buttons = [
                    b for b in ui_state.buttons
                    if not any(
                        f in b.text.lower()
                        for f in UniversalVision.FORBIDDEN_KEYWORDS
                    )
                ]
                if safe_buttons:
                    # 가장 큰 버튼 탭
                    target = max(safe_buttons, key=lambda b: b.width * b.height)
                    print(f"    → Auto-tap: '{target.text}' at ({target.cx},{target.cy})")
                    _adb_tap(target.cx, target.cy)
                    time.sleep(3)
                elif ui_state.close_buttons:
                    # X 닫기
                    x_btn = ui_state.close_buttons[0]
                    print(f"    → Auto-close X at ({x_btn.cx},{x_btn.cy})")
                    _adb_tap(x_btn.cx, x_btn.cy)
                    time.sleep(2)

            time.sleep(interval)

        print(f"\n[PlaybookGen] Collected {len(self.samples)} samples")
        print(f"  Screen types: {list(self.profiles.keys())}")

    def collect_from_directory(self, img_dir: Path):
        """기존 스크린샷 폴더에서 분석."""
        for img_path in sorted(img_dir.glob("*.png")):
            ui_state = self.vision.analyze(img_path)
            screen_type, conf = self.classifier.classify(ui_state)

            sample = ScreenSample(
                img_path=img_path,
                screen_type=screen_type,
                confidence=conf,
                ui_state=ui_state,
                timestamp=img_path.stat().st_mtime,
            )
            self.samples.append(sample)

            if screen_type not in self.profiles:
                self.profiles[screen_type] = ScreenProfile(screen_type=screen_type)
            profile = self.profiles[screen_type]
            profile.samples.append(sample)

            for btn in ui_state.buttons:
                profile.button_positions.append((btn.cx, btn.cy, btn.text))
            for close in ui_state.close_buttons:
                profile.close_positions.append((close.cx, close.cy))

        print(f"[PlaybookGen] Analyzed {len(self.samples)} images from {img_dir}")

    def generate(self) -> Playbook:
        """수집된 데이터로 Playbook 생성."""
        screen_handlers = {}

        for screen_type, profile in self.profiles.items():
            if screen_type in ("gameplay", "unknown"):
                continue

            actions = self._generate_actions_for_screen(screen_type, profile)
            if actions:
                screen_handlers[screen_type] = ScreenHandler(
                    screen_type=screen_type,
                    actions=actions,
                    description=f"Auto-generated: {len(profile.samples)} samples",
                )

        # 기본 핸들러 추가 (감지 안 된 것)
        for default_screen in ["popup", "unknown"]:
            if default_screen not in screen_handlers:
                screen_handlers[default_screen] = ScreenHandler(
                    screen_type=default_screen,
                    actions=[Action("back", wait=1.0, reason=f"Default: back from {default_screen}")],
                    description="Default handler",
                )

        # board_region 추정 (gameplay 화면의 밝은 영역)
        board_region = self._estimate_board_region()

        # forbidden_regions 추정 (결제 버튼 위치)
        forbidden = self._estimate_forbidden_regions()

        pb = Playbook(
            game_id=self.game_id,
            genre=self.genre,
            screen_handlers=screen_handlers,
            board_region=board_region,
            forbidden_regions=forbidden,
            forbidden_keywords=[
                "purchase", "buy", "install", "구매", "설치", "결제",
                "krw", "usd", "₩", "$",
            ],
        )

        return pb

    def _generate_actions_for_screen(
        self, screen_type: str, profile: ScreenProfile
    ) -> List[Action]:
        """화면 유형별 액션 생성."""
        actions = []

        # X 닫기 버튼 (가장 빈번한 위치)
        if profile.close_positions:
            freq = self._most_frequent_position(profile.close_positions)
            actions.append(Action("tap", freq[0], freq[1], 1.0,
                                  f"X close ({screen_type})"))

        # 주요 버튼 (결제 제외, 빈도 높은 순)
        safe_buttons = [
            (x, y, text) for x, y, text in profile.button_positions
            if not any(f in text.lower() for f in UniversalVision.FORBIDDEN_KEYWORDS)
        ]
        if safe_buttons:
            # 가장 빈번한 버튼 위치
            btn_positions = [(x, y) for x, y, _ in safe_buttons]
            freq = self._most_frequent_position(btn_positions)
            # 해당 위치의 텍스트
            text = next(
                (t for x, y, t in safe_buttons
                 if abs(x - freq[0]) < 50 and abs(y - freq[1]) < 50),
                ""
            )
            actions.append(Action("tap", freq[0], freq[1], 1.5,
                                  f"Button: '{text}' ({screen_type})"))

        # 액션 없으면 back
        if not actions:
            actions.append(Action("back", wait=1.0, reason=f"No buttons for {screen_type}"))

        return actions

    def _most_frequent_position(
        self, positions: List[Tuple[int, ...]], threshold: int = 50
    ) -> Tuple[int, int]:
        """가장 빈번한 좌표 클러스터의 중심."""
        if not positions:
            return (540, 960)

        # 간단한 클러스터링: 첫 번째 좌표 기준 50px 내 그룹핑
        clusters = []
        for pos in positions:
            x, y = pos[0], pos[1]
            found = False
            for cluster in clusters:
                cx = sum(p[0] for p in cluster) / len(cluster)
                cy = sum(p[1] for p in cluster) / len(cluster)
                if abs(x - cx) < threshold and abs(y - cy) < threshold:
                    cluster.append((x, y))
                    found = True
                    break
            if not found:
                clusters.append([(x, y)])

        # 가장 큰 클러스터
        biggest = max(clusters, key=len)
        cx = int(sum(p[0] for p in biggest) / len(biggest))
        cy = int(sum(p[1] for p in biggest) / len(biggest))
        return (cx, cy)

    def _estimate_board_region(self) -> Tuple[int, int, int, int]:
        """gameplay 화면에서 보드 영역 추정."""
        # 기본값
        return (30, 200, 1050, 1300)

    def _estimate_forbidden_regions(self) -> List[Tuple[int, int, int, int]]:
        """결제 관련 버튼 위치 → 금지 영역."""
        forbidden = []
        for profile in self.profiles.values():
            for x, y, text in profile.button_positions:
                if any(f in text.lower() for f in UniversalVision.FORBIDDEN_KEYWORDS):
                    # 버튼 주변 100px 마진
                    forbidden.append((
                        max(0, x - 100), max(0, y - 50),
                        min(1080, x + 100), min(1920, y + 50),
                    ))
        return forbidden

    def save_playbook(self, playbook: Playbook, output_path: Optional[Path] = None):
        """Playbook을 Python 파일로 저장."""
        path = output_path or self.output_dir / f"playbook_{self.game_id}.py"
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            '"""',
            f'Auto-generated Playbook for {self.game_id}',
            f'Generated from {len(self.samples)} screen samples.',
            '"""',
            '',
            'from virtual_player.tester.playbook import Action, Playbook, ScreenHandler',
            '',
            '',
            f'def create_{self.game_id}_playbook() -> Playbook:',
            f'    """Auto-generated Playbook for {self.game_id}."""',
            f'    pb = Playbook(',
            f'        game_id="{playbook.game_id}",',
            f'        genre="{playbook.genre}",',
            f'        board_region={playbook.board_region},',
            f'        forbidden_regions={playbook.forbidden_regions},',
            f'        forbidden_keywords={playbook.forbidden_keywords},',
            f'    )',
            '',
            '    pb.screen_handlers = {',
        ]

        for screen_type, handler in playbook.screen_handlers.items():
            lines.append(f'        "{screen_type}": ScreenHandler("{screen_type}", [')
            for action in handler.actions:
                if action.type == "tap":
                    lines.append(
                        f'            Action("tap", {action.x}, {action.y}, '
                        f'{action.wait}, "{action.reason}"),')
                elif action.type == "back":
                    lines.append(
                        f'            Action("back", wait={action.wait}, '
                        f'reason="{action.reason}"),')
                else:
                    lines.append(
                        f'            Action("{action.type}", wait={action.wait}, '
                        f'reason="{action.reason}"),')
            lines.append(f'        ], "{handler.description}"),')

        lines.extend([
            '    }',
            '',
            '    return pb',
            '',
        ])

        path.write_text('\n'.join(lines), encoding='utf-8')
        print(f"[PlaybookGen] Saved: {path}")

    def save_report(self, output_path: Optional[Path] = None):
        """분석 보고서 JSON 저장."""
        path = output_path or self.output_dir / "analysis_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        report = {
            "game_id": self.game_id,
            "package": self.package,
            "genre": self.genre,
            "total_samples": len(self.samples),
            "screen_types": {},
        }

        for screen_type, profile in self.profiles.items():
            report["screen_types"][screen_type] = {
                "count": profile.count,
                "common_texts": profile.common_texts[:20],
                "button_count": len(profile.button_positions),
                "close_button_count": len(profile.close_positions),
                "transitions_to": profile.transitions_to,
            }

        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"[PlaybookGen] Report saved: {path}")
