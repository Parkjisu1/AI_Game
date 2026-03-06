"""
Demo Recorder — 시연 녹화기
==============================
사람이 게임을 플레이하면, 그 행동을 자동 기록하여
AI가 학습할 수 있는 구조화된 데이터로 변환.

사람이 하는 것:
  1. BlueStacks에서 게임을 정상적으로 플레이
  2. 이 스크립트를 백그라운드로 실행
  3. 끝나면 Ctrl+C

이 스크립트가 하는 것:
  1. ADB getevent로 터치 이벤트 실시간 캡처
  2. 터치 발생 시점의 스크린샷 자동 저장
  3. (터치 직전 화면 + 탭 좌표 + 터치 직후 화면) 묶어서 JSONL 저장
  4. 세션 종료 시 요약 통계 출력

출력 구조:
  data/games/{game_id}/demonstrations/
    demo_YYYYMMDD_HHMMSS/
      frames/
        pre_0001.png       ← 탭 직전 스크린샷
        post_0001.png      ← 탭 직후 스크린샷
      demo_log.jsonl       ← 프레임별 기록
      summary.json         ← 세션 요약

AI가 이해하는 방식:
  각 JSONL 줄 = {
    "frame": 1,
    "timestamp": "2026-03-06T10:00:01.234",
    "action": {"type": "tap", "x": 450, "y": 800},
    "pre_screenshot": "frames/pre_0001.png",
    "post_screenshot": "frames/post_0001.png",
    "interval_sec": 2.3          ← 이전 탭으로부터 경과 시간
  }

  AI는 이 데이터를 보고:
  - "이 화면(pre)에서 사람은 여기(x,y)를 탭했다"
  - "탭 후 화면(post)이 이렇게 바뀌었다"
  - "사람은 평균 2.3초 간격으로 탭한다"
  를 학습할 수 있다.

사용법:
  python -m virtual_player.tester.demo_recorder --game carmatch
  python -m virtual_player.tester.demo_recorder --game carmatch --duration 10
"""

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


class DemoRecorder:
    """시연 녹화기.

    ADB 터치 이벤트를 실시간 캡처하고,
    각 터치마다 전/후 스크린샷을 저장.
    """

    def __init__(
        self,
        game_id: str,
        output_dir: Optional[Path] = None,
        resolution: Tuple[int, int] = (1080, 1920),
    ):
        self.game_id = game_id
        self.resolution = resolution

        # 출력 경로
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = output_dir or Path(
            f"E:/AI/virtual_player/data/games/{game_id}/demonstrations/demo_{ts}"
        )
        self.frames_dir = self.output_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)

        self.log_path = self.output_dir / "demo_log.jsonl"
        self._frame_count = 0
        self._last_tap_time: Optional[float] = None
        self._entries: List[dict] = []
        self._running = False

    def record(self, duration_minutes: int = 0):
        """녹화 시작.

        duration_minutes=0 이면 Ctrl+C까지 무한 녹화.
        """
        print(f"[DemoRecorder] Game: {self.game_id}")
        print(f"[DemoRecorder] Output: {self.output_dir}")
        print(f"[DemoRecorder] Duration: {'unlimited' if duration_minutes == 0 else f'{duration_minutes}min'}")
        print(f"[DemoRecorder] Waiting for touch events... (Ctrl+C to stop)")
        print()

        self._running = True
        end_time = (
            time.time() + duration_minutes * 60
            if duration_minutes > 0
            else float("inf")
        )

        try:
            self._capture_loop(end_time)
        except KeyboardInterrupt:
            print("\n[DemoRecorder] Stopped by user.")
        finally:
            self._running = False
            self._save_summary()

    def _capture_loop(self, end_time: float):
        """getevent 기반 터치 이벤트 캡처 루프."""
        proc = subprocess.Popen(
            [ADB, "-s", SERIAL, "shell", "getevent", "-lt"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # 터치 상태 추적
        touch_x = -1
        touch_y = -1
        touch_down = False
        # BlueStacks 터치 입력 디바이스의 해상도
        # getevent는 0~32767 범위로 좌표를 보고함
        ABS_MAX = 32767

        try:
            for line in proc.stdout:
                if not self._running or time.time() > end_time:
                    break

                line = line.strip()
                if not line:
                    continue

                # getevent 출력 형식:
                # [timestamp] /dev/input/eventN: EV_ABS ABS_MT_POSITION_X 00008000
                # [timestamp] /dev/input/eventN: EV_ABS ABS_MT_POSITION_Y 0000c000
                # [timestamp] /dev/input/eventN: EV_KEY BTN_TOUCH DOWN/UP

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
                        self._on_touch(touch_x, touch_y)
                    touch_down = False
                    touch_x = -1
                    touch_y = -1

        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def _on_touch(self, x: int, y: int):
        """터치 이벤트 발생 시 호출."""
        now = time.time()
        self._frame_count += 1
        frame_id = self._frame_count

        # 시간 간격
        interval = now - self._last_tap_time if self._last_tap_time else 0.0
        self._last_tap_time = now

        # pre 스크린샷 (터치 직후이지만, 결과 반영 전)
        pre_path = self.frames_dir / f"pre_{frame_id:04d}.png"
        self._screenshot(pre_path)

        # 잠시 대기 후 post 스크린샷 (결과 반영 후)
        time.sleep(0.8)
        post_path = self.frames_dir / f"post_{frame_id:04d}.png"
        self._screenshot(post_path)

        # 기록
        entry = {
            "frame": frame_id,
            "timestamp": datetime.now().isoformat(),
            "action": {"type": "tap", "x": x, "y": y},
            "pre_screenshot": f"frames/pre_{frame_id:04d}.png",
            "post_screenshot": f"frames/post_{frame_id:04d}.png",
            "interval_sec": round(interval, 2),
        }
        self._entries.append(entry)

        # JSONL 즉시 기록
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] Frame {frame_id}: tap({x},{y}) interval={interval:.1f}s")

    def _screenshot(self, path: Path) -> bool:
        """ADB 스크린샷 캡처."""
        try:
            r = subprocess.run(
                [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=10,
            )
            if len(r.stdout) > 1000:
                path.write_bytes(r.stdout)
                return True
        except Exception:
            pass
        return False

    def _save_summary(self):
        """세션 요약 저장."""
        if not self._entries:
            print("[DemoRecorder] No frames recorded.")
            return

        intervals = [e["interval_sec"] for e in self._entries if e["interval_sec"] > 0]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0

        summary = {
            "game_id": self.game_id,
            "total_frames": self._frame_count,
            "duration_sec": round(
                (self._entries[-1]["interval_sec"] if self._entries else 0)
                + sum(e["interval_sec"] for e in self._entries), 1
            ),
            "avg_interval_sec": round(avg_interval, 2),
            "started_at": self._entries[0]["timestamp"],
            "ended_at": self._entries[-1]["timestamp"],
        }

        summary_path = self.output_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"\n[DemoRecorder] === Session Summary ===")
        print(f"  Frames: {self._frame_count}")
        print(f"  Avg interval: {avg_interval:.1f}s")
        print(f"  Output: {self.output_dir}")
        print(f"  Log: {self.log_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    """커맨드라인 실행."""
    import argparse
    parser = argparse.ArgumentParser(description="Demo Recorder — Record human gameplay")
    parser.add_argument("--game", default="carmatch", help="Game ID (default: carmatch)")
    parser.add_argument("--duration", type=int, default=0, help="Duration in minutes (0=unlimited)")
    args = parser.parse_args()

    recorder = DemoRecorder(game_id=args.game)
    recorder.record(duration_minutes=args.duration)


if __name__ == "__main__":
    main()
