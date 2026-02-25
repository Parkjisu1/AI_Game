"""
C10+ v2.5 Core Module
=====================
ADB control, Claude CLI wrapper, OCR, APK asset extraction, wiki cross-reference.
All low-level utilities used by the pipeline.
"""

import os
import sys
import subprocess
import time
import re
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any

# ---------------------------------------------------------------------------
# Optional dependencies (graceful fallback)
# ---------------------------------------------------------------------------
try:
    from PIL import Image
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    import UnityPy
    HAS_UNITYPY = True
except ImportError:
    HAS_UNITYPY = False

# ---------------------------------------------------------------------------
# Global Config
# ---------------------------------------------------------------------------

@dataclass
class SystemConfig:
    adb_path: str = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
    device: str = "emulator-5554"
    claude_cmd: str = r"C:\Users\user\AppData\Roaming\npm\claude.cmd"
    claude_model: str = "sonnet"
    base_dir: Path = field(default_factory=lambda: Path(r"E:\AI\projects\CleanRoomTest\c10_plus_v25"))
    screenshot_min_bytes: int = 1000
    claude_vision_timeout: int = 180
    claude_text_timeout: int = 300
    features: Dict[str, bool] = field(default_factory=lambda: {
        "ocr": True,
        "wiki": True,
        "assets": True,
    })

SYS_CFG = SystemConfig()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str):
    import sys as _sys
    text = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode(_sys.stdout.encoding or 'utf-8', errors='replace').decode(
            _sys.stdout.encoding or 'utf-8', errors='replace'), flush=True)


# ---------------------------------------------------------------------------
# ADB Commands
# ---------------------------------------------------------------------------

def adb_run(*args, timeout=30) -> subprocess.CompletedProcess:
    cmd = [SYS_CFG.adb_path, "-s", SYS_CFG.device] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def adb_check_device() -> bool:
    r = adb_run("devices")
    return SYS_CFG.device.encode() in r.stdout


_device_resolution: Optional[Tuple[int, int]] = None

def get_device_resolution() -> Tuple[int, int]:
    """Get the effective screen resolution (width, height) for ADB tap coordinates.

    Uses a quick screenshot to determine actual dimensions, since wm size
    reports physical dimensions which differ from the app coordinate space
    when screen orientation is rotated (e.g. BlueStacks portrait mode).

    Caches the result. Falls back to (1080, 1920) on error.
    """
    global _device_resolution
    if _device_resolution:
        return _device_resolution
    # Method 1: Take a quick screenshot and check its dimensions (most reliable)
    try:
        r = adb_run("exec-out", "screencap", "-p", timeout=10)
        if r.returncode == 0 and r.stdout and len(r.stdout) > 1000:
            if HAS_OCR:  # PIL is available
                import io
                img = Image.open(io.BytesIO(r.stdout))
                _device_resolution = img.size  # (width, height)
                return _device_resolution
    except Exception:
        pass
    # Method 2: Fallback to wm size
    try:
        r = adb_run("shell", "wm", "size", timeout=5)
        if r.returncode == 0 and r.stdout:
            text = r.stdout.decode("utf-8", errors="replace")
            m = re.search(r'(\d+)x(\d+)', text)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                # Check orientation — swap if needed for portrait mode
                r2 = adb_run("shell", "dumpsys", "input", timeout=5)
                if r2.returncode == 0 and r2.stdout:
                    orient_text = r2.stdout.decode("utf-8", errors="replace")
                    if "SurfaceOrientation: 1" in orient_text or "SurfaceOrientation: 3" in orient_text:
                        w, h = min(w, h), max(w, h)  # portrait: width < height
                _device_resolution = (w, h)
                return _device_resolution
    except Exception:
        pass
    _device_resolution = (1080, 1920)
    return _device_resolution


def take_screenshot(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    r = adb_run("exec-out", "screencap", "-p")
    if r.returncode == 0 and r.stdout and len(r.stdout) > SYS_CFG.screenshot_min_bytes:
        path.write_bytes(r.stdout)
        return True
    return False


def tap(x: int, y: int, wait: float = 1.5):
    adb_run("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(wait)


def swipe(x1: int, y1: int, x2: int, y2: int, dur: int = 300, wait: float = 1.5):
    adb_run("shell", "input", "swipe",
            str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(dur)))
    time.sleep(wait)


# ---------------------------------------------------------------------------
# ADB getevent (for Replay System)
# ---------------------------------------------------------------------------

def find_touch_device() -> str:
    """Auto-detect the touch input device (e.g. /dev/input/event4 on BlueStacks)."""
    r = adb_run("shell", "getevent", "-il", timeout=10)
    if r.returncode != 0 or not r.stdout:
        return "/dev/input/event1"  # fallback

    text = r.stdout.decode("utf-8", errors="replace")
    current_device = ""
    for line in text.splitlines():
        if line.startswith("add device"):
            # e.g. "add device 3: /dev/input/event4"
            parts = line.split(":")
            if len(parts) >= 2:
                current_device = parts[-1].strip()
        elif "ABS_MT_POSITION_X" in line and current_device:
            return current_device
    return "/dev/input/event1"


def getevent_start(device: str = "") -> subprocess.Popen:
    """Start capturing raw touch events via `adb shell getevent -lt`."""
    if not device:
        device = find_touch_device()
    cmd = [SYS_CFG.adb_path, "-s", SYS_CFG.device, "shell", "getevent", "-lt", device]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc


def getevent_stop(proc: subprocess.Popen) -> str:
    """Terminate getevent process and return captured output."""
    proc.terminate()
    try:
        stdout, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, _ = proc.communicate()
    if isinstance(stdout, bytes):
        return stdout.decode("utf-8", errors="replace")
    return stdout or ""


def get_screen_resolution() -> Tuple[int, int]:
    """Get device screen resolution via `adb shell wm size`.

    Returns (width, height), default (1080, 1920) on failure.
    """
    r = adb_run("shell", "wm", "size")
    if r.returncode == 0 and r.stdout:
        text = r.stdout.decode("utf-8", errors="replace")
        m = re.search(r'(\d+)x(\d+)', text)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 1080, 1920


def press_back(wait: float = 1.5):
    adb_run("shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(wait)


def force_stop(pkg: str):
    adb_run("shell", "am", "force-stop", pkg)
    time.sleep(1)


def launch_game(pkg: str, wait: float = 8):
    adb_run("shell", "monkey", "-p", pkg, "-c",
            "android.intent.category.LAUNCHER", "1")
    time.sleep(wait)


def change_resolution(width: int, height: int, dpi: int = 320):
    adb_run("shell", "wm", "size", f"{width}x{height}")
    adb_run("shell", "wm", "density", str(dpi))
    time.sleep(2)


def reset_resolution():
    adb_run("shell", "wm", "size", "reset")
    adb_run("shell", "wm", "density", "reset")
    time.sleep(2)


# ---------------------------------------------------------------------------
# Claude CLI Wrapper
# ---------------------------------------------------------------------------

def _clean_env() -> dict:
    env = os.environ.copy()
    for key in ("ANTHROPIC_API_KEY", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_MODEL"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def claude_vision(prompt: str, images: List[Path], timeout: int = None) -> str:
    timeout = timeout or SYS_CFG.claude_vision_timeout
    img_list = "\n".join(f"  - {p}" for p in images)
    full_prompt = f"다음 이미지 파일들을 Read 도구로 읽어서 분석하세요:\n{img_list}\n\n{prompt}"
    cmd = [SYS_CFG.claude_cmd, "--print", "--model", SYS_CFG.claude_model,
           "--allowed-tools", "Read"]
    try:
        r = subprocess.run(
            cmd, input=full_prompt, capture_output=True, encoding="utf-8",
            env=_clean_env(), timeout=timeout, cwd=str(SYS_CFG.base_dir),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return f"ERROR: rc={r.returncode} {r.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    except Exception as e:
        return f"ERROR: {e}"


def claude_text(prompt: str, timeout: int = None) -> str:
    timeout = timeout or SYS_CFG.claude_text_timeout
    cmd = [SYS_CFG.claude_cmd, "--print", "--model", SYS_CFG.claude_model]
    try:
        r = subprocess.run(
            cmd, input=prompt, capture_output=True, encoding="utf-8",
            env=_clean_env(), timeout=timeout, cwd=str(SYS_CFG.base_dir),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return f"ERROR: rc={r.returncode} {r.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# OCR Preprocessing (M2)
# ---------------------------------------------------------------------------

def ocr_extract_numbers(img_path: Path,
                        regions: Dict[str, Tuple[int, int, int, int]] = None
                        ) -> Dict[str, str]:
    """Extract numeric text from screenshot regions using pytesseract.

    Args:
        img_path: Path to screenshot PNG
        regions: Dict of name -> (x, y, width, height) crop regions.
                 If None, performs full-image OCR.

    Returns:
        Dict of region_name -> extracted_text
    """
    if not HAS_OCR:
        log("  [OCR] pytesseract not installed, skipping")
        return {}

    try:
        img = Image.open(img_path)
    except Exception as e:
        log(f"  [OCR] Failed to open {img_path}: {e}")
        return {}

    results = {}
    if regions:
        for name, (x, y, w, h) in regions.items():
            try:
                cropped = img.crop((x, y, x + w, y + h))
                # Upscale for better OCR accuracy
                cropped = cropped.resize((w * 3, h * 3), Image.LANCZOS)
                text = pytesseract.image_to_string(
                    cropped,
                    config='--psm 7 -c tessedit_char_whitelist=0123456789.,%+-/xX'
                ).strip()
                if text:
                    results[name] = text
            except Exception as e:
                log(f"  [OCR] Region '{name}' failed: {e}")
    else:
        try:
            text = pytesseract.image_to_string(
                img,
                config='--psm 6 -c tessedit_char_whitelist=0123456789.,%+-/xXABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz '
            ).strip()
            results["full"] = text
        except Exception as e:
            log(f"  [OCR] Full image OCR failed: {e}")

    return results


# ---------------------------------------------------------------------------
# APK Asset Extraction (M4)
# ---------------------------------------------------------------------------

def extract_apk_assets(apk_path: str) -> Dict[str, Any]:
    """Extract game configuration data from Unity APK using UnityPy.

    Extracts:
    - TextAsset: JSON/CSV config files (level data, balance tables, gacha rates)
    - MonoScript: Class names and namespaces (metadata only, NOT source code)
    - AnimationClip: Animation durations
    - Sprite metadata: UI asset dimensions

    Does NOT extract or decompile source code (IL2CPP/Mono).

    Returns:
        Dict with keys: text_assets, mono_scripts, animations, sprite_meta
    """
    if not HAS_UNITYPY:
        log("  [ASSETS] UnityPy not installed, skipping")
        return {}

    if not os.path.exists(apk_path):
        log(f"  [ASSETS] APK not found: {apk_path}")
        return {}

    log(f"  [ASSETS] Extracting from {apk_path}...")
    extracted = {
        "text_assets": [],
        "mono_scripts": [],
        "animations": [],
        "sprite_meta": [],
    }

    try:
        env = UnityPy.load(apk_path)
        config_keywords = [
            'config', 'level', 'stage', 'balance', 'gacha', 'summon',
            'equipment', 'gear', 'skill', 'stat', 'reward', 'shop',
            'quest', 'mission', 'pet', 'character', 'monster', 'enemy',
            'wave', 'chapter', 'dungeon', 'item', 'upgrade', 'enhance',
            'table', 'data', 'setting', 'const',
        ]

        for obj in env.objects:
            try:
                if obj.type.name == "TextAsset":
                    data = obj.read()
                    name_lower = data.m_Name.lower()
                    if any(kw in name_lower for kw in config_keywords):
                        content = ""
                        if hasattr(data, 'm_Script'):
                            raw = data.m_Script
                            if isinstance(raw, bytes):
                                content = raw.decode('utf-8', errors='ignore')
                            else:
                                content = str(raw)
                        extracted["text_assets"].append({
                            "name": data.m_Name,
                            "content": content[:10000],  # Limit size
                            "size": len(content),
                        })

                elif obj.type.name == "MonoScript":
                    data = obj.read()
                    extracted["mono_scripts"].append({
                        "name": getattr(data, 'm_Name', ''),
                        "namespace": getattr(data, 'm_Namespace', ''),
                        "class_name": getattr(data, 'm_ClassName', ''),
                    })

                elif obj.type.name == "AnimationClip":
                    data = obj.read()
                    length = 0
                    if hasattr(data, 'm_MuscleClip') and hasattr(data.m_MuscleClip, 'm_StopTime'):
                        length = data.m_MuscleClip.m_StopTime
                    extracted["animations"].append({
                        "name": data.m_Name,
                        "length_sec": length,
                    })

                elif obj.type.name == "Sprite":
                    data = obj.read()
                    rect = getattr(data, 'm_Rect', None)
                    if rect:
                        extracted["sprite_meta"].append({
                            "name": data.m_Name,
                            "width": rect.width if hasattr(rect, 'width') else 0,
                            "height": rect.height if hasattr(rect, 'height') else 0,
                        })
            except Exception:
                continue

        log(f"  [ASSETS] Extracted: {len(extracted['text_assets'])} texts, "
            f"{len(extracted['mono_scripts'])} scripts, "
            f"{len(extracted['animations'])} animations, "
            f"{len(extracted['sprite_meta'])} sprites")

    except Exception as e:
        log(f"  [ASSETS] Extraction failed: {e}")

    return extracted


def format_asset_data_for_prompt(asset_data: Dict[str, Any]) -> str:
    """Format extracted asset data into a text block for Claude prompt."""
    if not asset_data:
        return ""

    parts = []

    if asset_data.get("text_assets"):
        parts.append("=== APK TextAsset (설정 파일) ===")
        for ta in asset_data["text_assets"][:20]:  # Limit to 20 files
            parts.append(f"\n--- {ta['name']} ({ta['size']} bytes) ---")
            parts.append(ta["content"][:3000])  # Limit content size

    if asset_data.get("mono_scripts"):
        parts.append("\n=== APK MonoScript (클래스 메타데이터, 소스코드 아님) ===")
        # Group by namespace
        ns_groups: Dict[str, List[str]] = {}
        for ms in asset_data["mono_scripts"]:
            ns = ms["namespace"] or "(global)"
            ns_groups.setdefault(ns, []).append(ms["class_name"] or ms["name"])
        for ns, classes in sorted(ns_groups.items()):
            parts.append(f"  Namespace: {ns}")
            parts.append(f"    Classes: {', '.join(sorted(classes)[:30])}")

    if asset_data.get("animations"):
        parts.append("\n=== APK AnimationClip (애니메이션 길이) ===")
        for anim in sorted(asset_data["animations"], key=lambda a: a["name"])[:30]:
            if anim["length_sec"] > 0:
                parts.append(f"  {anim['name']}: {anim['length_sec']:.3f}s")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Community Wiki Cross-Reference (M3)
# ---------------------------------------------------------------------------

def fetch_wiki_data(game_name: str, keywords: List[str]) -> str:
    """Use Claude CLI with WebSearch to gather community data about a game.

    Returns aggregated community information as text.
    """
    if not keywords:
        return ""

    search_queries = []
    for kw in keywords[:5]:  # Limit queries
        search_queries.append(f'"{game_name}" {kw}')

    prompt = f"""다음 검색어로 "{game_name}" 게임의 공개 데이터를 수집하세요.
WebSearch 도구를 사용하여 각 검색어를 검색하고, 게임 관련 수치 데이터를 추출하세요.

검색어:
{chr(10).join(f"  {i+1}. {q}" for i, q in enumerate(search_queries))}

수집 대상:
- 가챠/소환 확률 (공식 공시)
- 장비/스킬 스탯 테이블
- 성장 공식 (커뮤니티 역산)
- 레벨/스테이지 구성
- 재화 획득량
- 밸런스 패치 내역

출력: 검증된 수치 데이터만 정리. 출처 URL 포함. 추측이 아닌 확인된 데이터만."""

    cmd = [SYS_CFG.claude_cmd, "--print", "--model", SYS_CFG.claude_model,
           "--allowed-tools", "WebSearch,WebFetch"]
    try:
        r = subprocess.run(
            cmd, input=prompt, capture_output=True, encoding="utf-8",
            env=_clean_env(), timeout=120, cwd=str(SYS_CFG.base_dir),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return ""
    except Exception as e:
        log(f"  [WIKI] Failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Claude Vision Classification Helper
# ---------------------------------------------------------------------------

def claude_vision_classify(prompt: str, image_path: Path,
                           model: str = "haiku", timeout: int = 60) -> Dict[str, Any]:
    """Classify a screenshot using Claude Vision, returning parsed JSON.

    Optimized for structured output — extracts JSON from Claude's response.
    Uses haiku by default for speed/cost efficiency on classification tasks.
    """
    full_prompt = (
        f"다음 이미지 파일을 Read 도구로 읽어서 분석하세요:\n"
        f"  - {image_path}\n\n{prompt}"
    )
    cmd = [SYS_CFG.claude_cmd, "--print", "--model", model,
           "--allowed-tools", "Read"]
    try:
        r = subprocess.run(
            cmd, input=full_prompt, capture_output=True, encoding="utf-8",
            env=_clean_env(), timeout=timeout, cwd=str(SYS_CFG.base_dir),
        )
        if r.returncode == 0 and r.stdout.strip():
            text = r.stdout.strip()
            # Strip markdown code fences if present
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*$', '', text)
            text = text.strip()
            # Extract JSON object (supports one level of nested braces for sub_info)
            json_match = re.search(
                r'\{(?:[^{}]|\{[^{}]*\})*\}', text, re.DOTALL
            )
            if json_match:
                return json.loads(json_match.group())
            return {"error": "no_json", "raw": text[:500]}
        return {"error": f"rc={r.returncode}", "raw": r.stderr[:300]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Result Parsing Utilities
# ---------------------------------------------------------------------------

def extract_average(text: str) -> float:
    m = re.search(r'average:\s*([\d.]+)', text)
    return float(m.group(1)) if m else 0.0


def extract_sum(text: str) -> float:
    m = re.search(r'sum:\s*([\d.]+)', text)
    return float(m.group(1)) if m else 0.0


def extract_param_scores(text: str) -> List[Dict]:
    results = []
    blocks = re.split(r'\n\s*-\s*id:\s*', text)
    for block in blocks[1:]:
        id_m = re.match(r'(\w+)', block)
        name_m = re.search(r'name:\s*["\']?(.+?)["\']?\s*\n', block)
        score_m = re.search(r'score:\s*([\d.]+)', block)
        if id_m and score_m:
            results.append({
                "id": id_m.group(1),
                "name": name_m.group(1).strip() if name_m else "",
                "score": float(score_m.group(1)),
            })
    return results
