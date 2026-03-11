"""
Demo Recorder V2 — pyautogui 기반 시연 녹화기
================================================
V1 문제점:
  - ADB screencap은 Unity overlay를 못 찍음
  - getevent 감지 후 screencap → pre가 실제로는 "탭 후" 화면
  - 탭 좌표만 저장 → 레벨별 좌표 차이로 학습 의미 없음

V2 해결:
  1. pyautogui로 실제 렌더링된 BlueStacks 화면 캡처
  2. 폴링 방식: 연속 스크린샷 + getevent 탭 매칭 → pre/post 정확
  3. 탭 주변 패치(120x120) 저장 → template matching용
  4. Zone 분류 저장 → 좌표 의존 제거

출력 구조:
  data/games/{game_id}/demonstrations/demo_YYYYMMDD_HHMMSS/
    frames/
      frame_0001.png       ← 연속 스크린샷
    patches/
      tap_0001.png         ← 탭 주변 120x120 크롭
    demo_log.jsonl         ← 프레임별 기록
    summary.json           ← 세션 요약

사용법:
  python -m virtual_player.tester.demo_recorder --game carmatch
  python -m virtual_player.tester.demo_recorder --game pixelflow --duration 20
"""

import ctypes
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"

# ---------------------------------------------------------------------------
# Zone 정의 (1080x1920 기준)
# ---------------------------------------------------------------------------
ZONES = {
    "top_bar":     (0, 0, 1080, 150),
    "top_left":    (0, 0, 200, 150),
    "top_right":   (880, 0, 1080, 150),
    "board_upper": (0, 150, 1080, 600),
    "board_lower": (0, 600, 1080, 1100),
    "queue_area":  (0, 1100, 1080, 1650),
    "bottom_menu": (0, 1650, 1080, 1920),
    "center":      (270, 480, 810, 1440),
    "close_x":     (900, 0, 1080, 200),
}


def tap_to_zone(x: int, y: int) -> str:
    """탭 좌표 → Zone 이름."""
    # 작은 영역(close_x, top_left 등)을 먼저 체크
    priority = ["close_x", "top_left", "top_right"]
    for name in priority:
        x1, y1, x2, y2 = ZONES[name]
        if x1 <= x < x2 and y1 <= y < y2:
            return name
    for name, (x1, y1, x2, y2) in ZONES.items():
        if name in priority:
            continue
        if x1 <= x < x2 and y1 <= y < y2:
            return name
    return "unknown"


# ---------------------------------------------------------------------------
# BlueStacks 윈도우 감지
# ---------------------------------------------------------------------------
def find_bluestacks_window() -> Optional[Tuple[int, int, int, int]]:
    """BlueStacks App Player 윈도우의 클라이언트 영역 (x, y, w, h).

    Returns None if not found.
    """
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    from ctypes import wintypes

    found = []

    def _enum_cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if "BlueStacks App Player" in title and user32.IsWindowVisible(hwnd):
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found.append((rect.left, rect.top, rect.right, rect.bottom))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)

    if not found:
        return None
    left, top, right, bottom = found[0]
    return (left, top, right - left, bottom - top)


# ---------------------------------------------------------------------------
# DemoRecorder V2
# ---------------------------------------------------------------------------
class DemoRecorder:
    """pyautogui 기반 시연 녹화기.

    폴링 방식으로 연속 스크린샷을 찍고,
    getevent에서 수집한 탭 이벤트와 매칭하여
    정확한 pre/post 관계를 기록.
    """

    def __init__(
        self,
        game_id: str,
        output_dir: Optional[Path] = None,
        resolution: Tuple[int, int] = (1080, 1920),
        poll_interval: float = 0.3,
    ):
        self.game_id = game_id
        self.resolution = resolution
        self.poll_interval = poll_interval

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = output_dir or Path(
            f"E:/AI/virtual_player/data/games/{game_id}/demonstrations/demo_{ts}"
        )
        self.frames_dir = self.output_dir / "frames"
        self.patches_dir = self.output_dir / "patches"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.patches_dir.mkdir(parents=True, exist_ok=True)

        self.log_path = self.output_dir / "demo_log.jsonl"
        self._frame_count = 0
        self._tap_count = 0
        self._last_tap_time: Optional[float] = None
        self._entries: List[dict] = []
        self._running = False

        # getevent에서 수집한 탭 큐 (thread-safe)
        self._tap_queue: List[Tuple[float, int, int]] = []  # (time, x, y)
        self._tap_lock = threading.Lock()

        # BlueStacks 윈도우 영역
        self._window_region: Optional[Tuple[int, int, int, int]] = None

    def record(self, duration_minutes: int = 0):
        """녹화 시작."""
        # BlueStacks 윈도우 찾기
        self._window_region = find_bluestacks_window()
        if not self._window_region:
            print("[DemoRecorder] BlueStacks window not found!")
            print("[DemoRecorder] Make sure BlueStacks is running and visible.")
            return

        print(f"[DemoRecorder] Game: {self.game_id}")
        print(f"[DemoRecorder] Output: {self.output_dir}")
        print(f"[DemoRecorder] BlueStacks window: {self._window_region}")
        print(f"[DemoRecorder] Mode: pyautogui + getevent polling")
        dur_str = "unlimited" if duration_minutes == 0 else f"{duration_minutes}min"
        print(f"[DemoRecorder] Duration: {dur_str}")
        print(f"[DemoRecorder] Play the game. Press Ctrl+C to stop.")
        print()

        self._running = True
        end_time = (
            time.time() + duration_minutes * 60
            if duration_minutes > 0
            else float("inf")
        )

        # getevent 백그라운드 스레드
        getevent_thread = threading.Thread(
            target=self._getevent_listener, daemon=True
        )
        getevent_thread.start()

        try:
            self._polling_loop(end_time)
        except KeyboardInterrupt:
            print("\n[DemoRecorder] Stopped by user.")
        finally:
            self._running = False
            getevent_thread.join(timeout=5)
            self._save_summary()

    def _getevent_listener(self):
        """getevent를 백그라운드에서 실행, 탭 좌표를 큐에 넣음."""
        try:
            proc = subprocess.Popen(
                [ADB, "-s", SERIAL, "shell", "getevent", "-lt"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as e:
            print(f"[DemoRecorder] getevent start failed: {e}")
            return

        touch_x, touch_y = -1, -1
        touch_down = False
        ABS_MAX = 32767

        try:
            for line in proc.stdout:
                if not self._running:
                    break
                line = line.strip()
                if not line:
                    continue

                if "ABS_MT_POSITION_X" in line:
                    match = re.search(r'([0-9a-fA-F]+)\s*$', line)
                    if match:
                        raw = int(match.group(1), 16)
                        touch_x = int(raw * self.resolution[0] / ABS_MAX)
                elif "ABS_MT_POSITION_Y" in line:
                    match = re.search(r'([0-9a-fA-F]+)\s*$', line)
                    if match:
                        raw = int(match.group(1), 16)
                        touch_y = int(raw * self.resolution[1] / ABS_MAX)
                elif "BTN_TOUCH" in line and "DOWN" in line:
                    touch_down = True
                elif "BTN_TOUCH" in line and "UP" in line:
                    if touch_down and touch_x >= 0 and touch_y >= 0:
                        with self._tap_lock:
                            self._tap_queue.append(
                                (time.time(), touch_x, touch_y)
                            )
                    touch_down = False
                    touch_x, touch_y = -1, -1
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

    def _polling_loop(self, end_time: float):
        """메인 폴링 루프: 연속 스크린샷 + 탭 이벤트 매칭."""
        import pyautogui

        prev_frame_path: Optional[Path] = None
        prev_frame_time: float = 0

        while self._running and time.time() < end_time:
            # 1. 현재 화면 캡처 (pyautogui)
            frame_path, frame_time = self._capture_frame(pyautogui)
            if frame_path is None:
                time.sleep(self.poll_interval)
                continue

            # 2. 큐에서 탭 이벤트 수집
            taps = self._drain_taps()

            # 3. 탭이 있었으면 기록
            for tap_time, tap_x, tap_y in taps:
                if prev_frame_path is not None:
                    self._record_entry(
                        pre_path=prev_frame_path,
                        post_path=frame_path,
                        tap_x=tap_x,
                        tap_y=tap_y,
                        tap_time=tap_time,
                        pyautogui_mod=pyautogui,
                    )

            prev_frame_path = frame_path
            prev_frame_time = frame_time
            time.sleep(self.poll_interval)

    def _capture_frame(self, pyautogui_mod) -> Tuple[Optional[Path], float]:
        """pyautogui로 BlueStacks 화면 캡처."""
        if not self._window_region:
            return None, 0

        try:
            self._frame_count += 1
            region = self._window_region
            screenshot = pyautogui_mod.screenshot(region=region)
            # 게임 해상도로 리사이즈
            screenshot = screenshot.resize(self.resolution)
            path = self.frames_dir / f"frame_{self._frame_count:04d}.png"
            screenshot.save(str(path))
            return path, time.time()
        except Exception as e:
            print(f"[DemoRecorder] Screenshot failed: {e}")
            return None, 0

    def _drain_taps(self) -> List[Tuple[float, int, int]]:
        """탭 큐에서 모든 이벤트 가져오기."""
        with self._tap_lock:
            taps = list(self._tap_queue)
            self._tap_queue.clear()
        return taps

    def _record_entry(
        self,
        pre_path: Path,
        post_path: Path,
        tap_x: int,
        tap_y: int,
        tap_time: float,
        pyautogui_mod,
    ):
        """탭 이벤트 1개 기록 + 패치 저장."""
        self._tap_count += 1
        tap_id = self._tap_count

        # 시간 간격
        interval = tap_time - self._last_tap_time if self._last_tap_time else 0.0
        self._last_tap_time = tap_time

        # Zone 분류
        zone = tap_to_zone(tap_x, tap_y)

        # 탭 주변 패치 저장 (pre 화면에서 크롭)
        patch_name = f"tap_{tap_id:04d}.png"
        patch_saved = self._save_patch(pre_path, tap_x, tap_y, patch_name)

        # 탭 전후 차이 영역 계산
        diff_zones = self._compute_diff_zones(pre_path, post_path)

        entry = {
            "frame": tap_id,
            "timestamp": datetime.now().isoformat(),
            "action": {"type": "tap", "x": tap_x, "y": tap_y},
            "zone": zone,
            "pre_screenshot": str(pre_path.relative_to(self.output_dir)),
            "post_screenshot": str(post_path.relative_to(self.output_dir)),
            "tap_patch": f"patches/{patch_name}" if patch_saved else None,
            "diff_zones": diff_zones,
            "interval_sec": round(interval, 2),
        }
        self._entries.append(entry)

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        ts_str = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{ts_str}] Tap {tap_id}: ({tap_x},{tap_y}) "
            f"zone={zone} interval={interval:.1f}s"
        )

    def _save_patch(
        self, frame_path: Path, x: int, y: int, patch_name: str,
        patch_size: int = 120,
    ) -> bool:
        """탭 위치 주변 패치(120x120) 크롭 저장."""
        try:
            import cv2
            img = cv2.imread(str(frame_path))
            if img is None:
                return False
            h, w = img.shape[:2]
            half = patch_size // 2
            # 게임 좌표 → 이미지 좌표 (이미 같은 해상도)
            x1 = max(0, x - half)
            y1 = max(0, y - half)
            x2 = min(w, x + half)
            y2 = min(h, y + half)
            patch = img[y1:y2, x1:x2]
            if patch.size == 0:
                return False
            # 패치를 고정 크기로 리사이즈
            patch = cv2.resize(patch, (patch_size, patch_size))
            cv2.imwrite(str(self.patches_dir / patch_name), patch)
            return True
        except Exception:
            return False

    def _compute_diff_zones(
        self, pre_path: Path, post_path: Path
    ) -> List[str]:
        """pre/post 차이가 발생한 Zone 목록."""
        try:
            import cv2
            pre = cv2.imread(str(pre_path), cv2.IMREAD_GRAYSCALE)
            post = cv2.imread(str(post_path), cv2.IMREAD_GRAYSCALE)
            if pre is None or post is None:
                return []
            if pre.shape != post.shape:
                post = cv2.resize(post, (pre.shape[1], pre.shape[0]))
            diff = cv2.absdiff(pre, post)
            changed = []
            for name, (x1, y1, x2, y2) in ZONES.items():
                region = diff[y1:y2, x1:x2]
                if region.size > 0 and region.mean() > 10:
                    changed.append(name)
            return changed
        except Exception:
            return []

    def _save_summary(self):
        """세션 요약 저장."""
        if not self._entries:
            print("[DemoRecorder] No taps recorded.")
            return

        intervals = [
            e["interval_sec"] for e in self._entries if e["interval_sec"] > 0
        ]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0

        # Zone 통계
        zone_counts = {}
        for e in self._entries:
            z = e.get("zone", "unknown")
            zone_counts[z] = zone_counts.get(z, 0) + 1

        summary = {
            "game_id": self.game_id,
            "version": "v2",
            "capture_mode": "pyautogui",
            "total_taps": self._tap_count,
            "total_frames": self._frame_count,
            "avg_interval_sec": round(avg_interval, 2),
            "zone_distribution": zone_counts,
            "started_at": self._entries[0]["timestamp"],
            "ended_at": self._entries[-1]["timestamp"],
        }

        summary_path = self.output_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"\n[DemoRecorder] === Session Summary ===")
        print(f"  Taps: {self._tap_count}")
        print(f"  Frames: {self._frame_count}")
        print(f"  Avg interval: {avg_interval:.1f}s")
        print(f"  Zones: {zone_counts}")
        print(f"  Output: {self.output_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Demo Recorder V2 — pyautogui based"
    )
    parser.add_argument(
        "--game", default="carmatch", help="Game ID (default: carmatch)"
    )
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Duration in minutes (0=unlimited)"
    )
    args = parser.parse_args()

    recorder = DemoRecorder(game_id=args.game)
    recorder.record(duration_minutes=args.duration)


if __name__ == "__main__":
    main()
