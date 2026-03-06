"""
Screen Classifier
==================
2-tier classification: perceptual hash cache (fast) -> Claude Vision (accurate).
Classifies game screenshots into genre-defined screen types.

Ported from C10+ smart_player/classifier.py.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..adb import log, claude_vision_classify

# Perceptual hashing requires PIL (optional, graceful fallback)
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@dataclass
class ScreenClassification:
    """Result of classifying a single screenshot."""
    screen_type: str            # e.g. "menu_summon"
    confidence: float           # 0.0 ~ 1.0
    sub_info: Dict[str, Any] = field(default_factory=dict)
    screenshot_path: Path = field(default_factory=lambda: Path("."))


# ---------------------------------------------------------------------------
# Perceptual Hashing
# ---------------------------------------------------------------------------

def compute_phash(image_path: Path, hash_size: int = 8) -> Optional[int]:
    """Compute a perceptual hash (average hash) for an image.

    Resizes to hash_size x hash_size grayscale, then produces a
    64-bit hash based on whether each pixel is above average.
    """
    if not HAS_PIL:
        return None
    try:
        img = Image.open(image_path).convert("L").resize(
            (hash_size, hash_size), Image.LANCZOS
        )
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = 0
        for px in pixels:
            bits = (bits << 1) | (1 if px >= avg else 0)
        return bits
    except Exception:
        return None


def hamming_distance(h1: int, h2: int) -> int:
    """Count differing bits between two hashes."""
    return bin(h1 ^ h2).count("1")


# ---------------------------------------------------------------------------
# Screen Classifier
# ---------------------------------------------------------------------------

class ScreenClassifier:
    """2-tier screen classifier: hash cache + local SSIM fallback."""

    HASH_THRESHOLD = 10  # Max hamming distance for cache hit

    def __init__(self, genre_screen_types: Dict[str, str], cache_dir: Path,
                 reference_db=None):
        """
        Args:
            genre_screen_types: {screen_type: description} from genre module
            cache_dir: Directory for hash cache persistence
            reference_db: Optional ReferenceDB for local SSIM classification
        """
        self.screen_types = genre_screen_types
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._reference_db = reference_db

        # hash -> ScreenClassification mapping
        self._hash_cache: Dict[int, ScreenClassification] = {}
        self._cache_file = cache_dir / "classifier_cache.json"
        self._stats = {"cache_hits": 0, "vision_calls": 0, "local_calls": 0}
        self.load_cache()

    # --- Public API ---

    def classify(self, screenshot_path: Path) -> ScreenClassification:
        """Classify a single screenshot. Uses cache first, Claude Vision on miss."""
        # Tier 1: Hash cache lookup (L0 -- <50ms)
        img_hash = compute_phash(screenshot_path)
        if img_hash is not None:
            cached = self._find_in_cache(img_hash)
            if cached:
                self._stats["cache_hits"] += 1
                return ScreenClassification(
                    screen_type=cached.screen_type,
                    confidence=cached.confidence,
                    sub_info=cached.sub_info,
                    screenshot_path=screenshot_path,
                )

        # Tier 2: Local SSIM classification (replaces Claude Vision)
        result = self._local_classify(screenshot_path)

        # Store in cache for future L0 hits
        if img_hash is not None and result.screen_type != "unknown":
            self._hash_cache[img_hash] = result

        return result

    def classify_batch(self, paths: List[Path]) -> List[ScreenClassification]:
        """Classify multiple screenshots in order."""
        return [self.classify(p) for p in paths]

    def get_stats(self) -> Dict[str, int]:
        """Return cache hit/miss statistics."""
        return dict(self._stats)

    def save_cache(self):
        """Persist hash cache to disk."""
        data = {}
        for h, cls in self._hash_cache.items():
            data[str(h)] = {
                "screen_type": cls.screen_type,
                "confidence": cls.confidence,
                "sub_info": cls.sub_info,
                "screenshot_path": str(cls.screenshot_path),
            }
        self._cache_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"  [Classifier] Cache saved: {len(data)} entries "
            f"(hits={self._stats['cache_hits']}, calls={self._stats['vision_calls']})")

    def load_cache(self):
        """Load hash cache from disk."""
        if not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            for h_str, entry in data.items():
                self._hash_cache[int(h_str)] = ScreenClassification(
                    screen_type=entry["screen_type"],
                    confidence=entry["confidence"],
                    sub_info=entry.get("sub_info", {}),
                    screenshot_path=Path(entry["screenshot_path"]),
                )
            log(f"  [Classifier] Cache loaded: {len(self._hash_cache)} entries")
        except Exception as e:
            log(f"  [Classifier] Cache load failed: {e}")

    # --- Internal ---

    def _find_in_cache(self, img_hash: int) -> Optional[ScreenClassification]:
        """Find a matching classification in hash cache."""
        best_dist = self.HASH_THRESHOLD + 1
        best_cls = None
        for cached_hash, cls in self._hash_cache.items():
            dist = hamming_distance(img_hash, cached_hash)
            if dist < best_dist:
                best_dist = dist
                best_cls = cls
        if best_dist <= self.HASH_THRESHOLD:
            return best_cls
        return None

    def _local_classify(self, screenshot_path: Path) -> ScreenClassification:
        """Classify using local SSIM reference matching (replaces Claude Vision)."""
        if self._reference_db:
            try:
                from ..brain.local_vision import LocalVision
                lv = LocalVision(self._reference_db)
                screen_type, confidence = lv.classify_screen(screenshot_path)
                if screen_type != "unknown":
                    self._stats["local_calls"] += 1
                    log(f"  [Classifier] Local SSIM: {screen_type} "
                        f"(conf={confidence:.2f})")

                    # Validate screen_type exists
                    if (screen_type not in self.screen_types
                            and not screen_type.startswith("popup_")):
                        screen_type = "unknown"
                        confidence = 0.0

                    return ScreenClassification(
                        screen_type=screen_type,
                        confidence=confidence,
                        sub_info={"method": "local_ssim"},
                        screenshot_path=screenshot_path,
                    )
                log(f"  [Classifier] Local SSIM: unknown (conf={confidence:.2f}), "
                    f"falling back to API")
            except Exception as e:
                log(f"  [Classifier] Local classify error: {e}")

        # Fallback: Claude Vision API (only if local fails)
        self._stats["vision_calls"] += 1
        return self._claude_classify(screenshot_path)

    def _claude_classify(self, screenshot_path: Path) -> ScreenClassification:
        """Classify using Claude Vision API."""
        screen_list = "\n".join(
            f"  - {k}: {v}" for k, v in self.screen_types.items()
        )
        prompt = f"""모바일 게임 스크린샷을 분류하세요.

화면 타입 목록:
{screen_list}

팝업 판별 규칙 (중요):
- 팝업 = 메인 화면 위에 별도 창/패널이 떠서 뒤의 게임 화면을 가리는 오버레이
- 팝업이 아닌 것: 하단 채팅 로그, 알림 텍스트 바, 인게임 HUD, 스킬바, 메뉴바
- 화면 전체를 차지하는 메뉴/상점/캐릭터 화면은 팝업이 아니라 해당 화면 타입으로 분류
- 팝업이 확실할 때만 popup_ 타입을 선택

일반 규칙:
- 마을/필드에서 캐릭터가 자동전투 중이면 "battle"
- 확실하지 않으면 "unknown" 선택
- confidence는 0.0~1.0 사이 값

출력 (JSON만, 설명 없이):
{{"screen_type": "...", "confidence": 0.X, "sub_info": {{}}}}"""

        result = claude_vision_classify(prompt, screenshot_path, model="haiku")

        screen_type = result.get("screen_type", "unknown")
        confidence = float(result.get("confidence", 0.0))
        sub_info = result.get("sub_info", {})
        if isinstance(sub_info, str):
            sub_info = {}

        # Validate screen_type exists
        if screen_type not in self.screen_types and screen_type != "unknown":
            # Allow popup_ prefix types through
            if not screen_type.startswith("popup_"):
                screen_type = "unknown"
                confidence = 0.0

        return ScreenClassification(
            screen_type=screen_type,
            confidence=confidence,
            sub_info=sub_info,
            screenshot_path=screenshot_path,
        )
