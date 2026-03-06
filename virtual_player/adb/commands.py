"""
ADB Commands
==============
Low-level ADB control functions for BlueStacks/Android emulator.
Extracted from C10+ core.py -- game control subset only.
"""

import os
import re
import json
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Optional: PIL for screenshot-based resolution detection
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ADBConfig:
    """ADB and Claude CLI configuration."""
    adb_path: str = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
    device: str = "emulator-5554"
    claude_cmd: str = r"C:\Users\user\AppData\Roaming\npm\claude.cmd"
    claude_model: str = "sonnet"
    screenshot_min_bytes: int = 1000
    claude_vision_timeout: int = 180
    data_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data")


adb_cfg = ADBConfig()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str):
    """Timestamped console log with Unicode safety."""
    import sys as _sys
    text = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode(_sys.stdout.encoding or 'utf-8', errors='replace').decode(
            _sys.stdout.encoding or 'utf-8', errors='replace'), flush=True)


# ---------------------------------------------------------------------------
# ADB Core
# ---------------------------------------------------------------------------

def adb_run(*args, timeout=30) -> subprocess.CompletedProcess:
    """Execute an ADB command and return the result."""
    cmd = [adb_cfg.adb_path, "-s", adb_cfg.device] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def adb_check_device() -> bool:
    """Check if the configured device is connected."""
    r = adb_run("devices")
    return adb_cfg.device.encode() in r.stdout


# ---------------------------------------------------------------------------
# Screen Resolution
# ---------------------------------------------------------------------------

_device_resolution: Optional[Tuple[int, int]] = None


def get_device_resolution() -> Tuple[int, int]:
    """Get effective screen resolution (width, height).

    Uses screenshot dimensions first (most reliable for BlueStacks),
    falls back to `wm size`. Caches the result.
    """
    global _device_resolution
    if _device_resolution:
        return _device_resolution

    # Method 1: Screenshot dimensions (handles rotated displays)
    try:
        r = adb_run("exec-out", "screencap", "-p", timeout=10)
        if r.returncode == 0 and r.stdout and len(r.stdout) > 1000:
            if HAS_PIL:
                import io
                img = Image.open(io.BytesIO(r.stdout))
                _device_resolution = img.size
                return _device_resolution
    except Exception:
        pass

    # Method 2: wm size with orientation check
    try:
        r = adb_run("shell", "wm", "size", timeout=5)
        if r.returncode == 0 and r.stdout:
            text = r.stdout.decode("utf-8", errors="replace")
            m = re.search(r'(\d+)x(\d+)', text)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                r2 = adb_run("shell", "dumpsys", "input", timeout=5)
                if r2.returncode == 0 and r2.stdout:
                    orient_text = r2.stdout.decode("utf-8", errors="replace")
                    if "SurfaceOrientation: 1" in orient_text or "SurfaceOrientation: 3" in orient_text:
                        w, h = min(w, h), max(w, h)
                _device_resolution = (w, h)
                return _device_resolution
    except Exception:
        pass

    _device_resolution = (1080, 1920)
    return _device_resolution


def reset_resolution_cache():
    """Clear cached resolution (e.g. after resolution change)."""
    global _device_resolution
    _device_resolution = None


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

def take_screenshot(path: Path) -> bool:
    """Capture device screen to a PNG file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    r = adb_run("exec-out", "screencap", "-p")
    if r.returncode == 0 and r.stdout and len(r.stdout) > adb_cfg.screenshot_min_bytes:
        path.write_bytes(r.stdout)
        return True
    return False


# ---------------------------------------------------------------------------
# Input Actions
# ---------------------------------------------------------------------------

def tap(x: int, y: int, wait: float = 1.5):
    """Tap at (x, y) coordinates."""
    adb_run("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(wait)


def swipe(x1: int, y1: int, x2: int, y2: int, dur: int = 300, wait: float = 1.5):
    """Swipe from (x1,y1) to (x2,y2) over dur milliseconds."""
    adb_run("shell", "input", "swipe",
            str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(dur)))
    time.sleep(wait)


def press_back(wait: float = 1.5):
    """Press the Android Back key."""
    adb_run("shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(wait)


# ---------------------------------------------------------------------------
# App Control
# ---------------------------------------------------------------------------

def force_stop(pkg: str):
    """Force-stop an app by package name."""
    adb_run("shell", "am", "force-stop", pkg)
    time.sleep(1)


def launch_game(pkg: str, wait: float = 8):
    """Launch an app via monkey command."""
    adb_run("shell", "monkey", "-p", pkg, "-c",
            "android.intent.category.LAUNCHER", "1")
    time.sleep(wait)


def is_game_running(pkg: str) -> bool:
    """Check if a game is currently in the foreground."""
    r = adb_run("shell", "dumpsys", "window", timeout=5)
    return pkg.encode() in (r.stdout or b"")


# ---------------------------------------------------------------------------
# Claude Vision Classify
# ---------------------------------------------------------------------------

def _clean_env() -> dict:
    """Create clean environment for Claude CLI (no inherited API keys)."""
    env = os.environ.copy()
    for key in ("ANTHROPIC_API_KEY", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_MODEL"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_claude_vision(full_prompt: str, model: str = "haiku",
                       timeout: int = 60) -> Dict[str, Any]:
    """Run Claude CLI with a prompt and extract JSON from response."""
    cmd = [adb_cfg.claude_cmd, "--print", "--model", model,
           "--allowed-tools", "Read"]
    try:
        r = subprocess.run(
            cmd, input=full_prompt, capture_output=True, encoding="utf-8",
            env=_clean_env(), timeout=timeout,
            cwd=str(adb_cfg.data_dir.parent),
        )
        if r.returncode == 0 and r.stdout.strip():
            text = r.stdout.strip()
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*$', '', text)
            text = text.strip()
            json_match = re.search(
                r'\{(?:[^{}]|\{[^{}]*\})*\}', text, re.DOTALL
            )
            if json_match:
                return json.loads(json_match.group())
            return {"error": "no_json", "raw": text[:500]}
        return {"error": f"rc={r.returncode}", "raw": (r.stderr or "")[:300]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


def claude_vision_classify(prompt: str, image_path: Path,
                           model: str = "haiku", timeout: int = 60) -> Dict[str, Any]:
    """Classify a screenshot using Claude Vision, returning parsed JSON.

    Uses Claude CLI with --print mode. Extracts JSON from response.
    Default model: haiku (fast + cheap for classification).
    """
    full_prompt = (
        f"다음 이미지 파일을 Read 도구로 읽어서 분석하세요:\n"
        f"  - {image_path}\n\n{prompt}"
    )
    return _run_claude_vision(full_prompt, model, timeout)


def claude_vision_annotate(prompt: str, before_path: Path, after_path: Path,
                           model: str = "haiku", timeout: int = 90) -> Dict[str, Any]:
    """Compare two screenshots using Claude Vision, returning parsed JSON.

    Sends both before/after images for comparative analysis.
    Used for action annotation -- identifying what was tapped and what changed.
    """
    full_prompt = (
        f"다음 두 이미지 파일을 Read 도구로 각각 읽어서 비교 분석하세요:\n"
        f"  - Before: {before_path}\n"
        f"  - After: {after_path}\n\n{prompt}"
    )
    return _run_claude_vision(full_prompt, model, timeout)
