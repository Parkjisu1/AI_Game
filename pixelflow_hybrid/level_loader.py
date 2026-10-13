"""
LevelLoader — APK 레벨 데이터 통합 로더.

APK에서 추출된 1,362 레벨 데이터에 대한 단일 API.
모든 게임 로직 (queue, board, gimmicks)의 정답.
"""
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from collections import Counter


DEFAULT_APK_DIR = Path("E:/AI/pixelflow_game_data/v2_apk_scenes")

COLOR_NAMES = {
    1: "Pink", 2: "Cyan", 3: "Purple", 4: "Yellow", 5: "Green",
    6: "Orange", 7: "White", 8: "Dark", 9: "LightBlue", 10: "DarkGreen",
    11: "Red", 12: "Blue", 13: "Teal", 14: "Lavender", 15: "Periwinkle",
    16: "Brown", 17: "Peach", 18: "LightPink", 19: "Maroon", 20: "MintGreen",
    21: "DarkPurple", 22: "DustyRose", 23: "Silver", 24: "Gray", 25: "HotPink",
    26: "Amber", 27: "DarkRed", 28: "SageTeal", 29: "BrownDark",
    30: "gimmick_snake", 31: "gimmick_pinata", 32: "gimmick_ice",
    33: "gimmick_block", 34: "gimmick_wall", 35: "gimmick_key",
    36: "gimmick_door", 37: "gimmick_egg", 38: "gimmick_hidden",
    39: "gimmick_cannon", 40: "current_balloon",
}


class LevelLoader:
    """APK 레벨 데이터 로더."""

    def __init__(self, apk_dir: Path = DEFAULT_APK_DIR):
        self.apk_dir = Path(apk_dir)
        if not self.apk_dir.exists():
            raise FileNotFoundError(f"APK dir not found: {self.apk_dir}")
        self._cache: Dict[int, Optional[dict]] = {}
        self._variants_index: Optional[Dict[int, List[Path]]] = None

    @property
    def variants_index(self) -> Dict[int, List[Path]]:
        """Lazy-build: level_num → [variant files]."""
        if self._variants_index is None:
            idx: Dict[int, List[Path]] = {}
            for p in sorted(self.apk_dir.glob("Level_*.json")):
                stem = p.stem
                try:
                    lv = int(stem.split("_")[1])
                except (IndexError, ValueError):
                    continue
                idx.setdefault(lv, []).append(p)
            self._variants_index = idx
        return self._variants_index

    def list_levels(self) -> List[int]:
        """Return sorted list of available level numbers."""
        return sorted(self.variants_index.keys())

    def list_variants(self, level_num: int) -> List[str]:
        """Return variant file names for a level (e.g. ['Level_0184_easy', 'Level_0184_Hard'])."""
        return [p.stem for p in self.variants_index.get(level_num, [])]

    def get_level(self, level_num: int, variant: Optional[str] = None) -> Optional[dict]:
        """
        Load full level data.

        Args:
            level_num: Level number (1-1200)
            variant: Optional variant filter (e.g. 'easy', 'Hard'). None = canonical.

        Returns:
            Full level dict or None.
        """
        cache_key = (level_num, variant or "_canonical")
        if cache_key in self._cache:
            return self._cache[cache_key]

        candidates = self.variants_index.get(level_num, [])
        if not candidates:
            return None

        chosen = None
        if variant:
            for p in candidates:
                if variant.lower() in p.stem.lower():
                    chosen = p
                    break
        if chosen is None:
            # Canonical: largest raw_size, must have queueGroup
            best, best_size = None, 0
            for p in candidates:
                try:
                    d = json.loads(p.read_text(encoding='utf-8'))
                except Exception:
                    continue
                if d.get("raw_size", 0) < 1000:
                    continue
                if "queueGroup" not in d:
                    continue
                if d.get("raw_size", 0) > best_size:
                    best, best_size = (p, d), d.get("raw_size", 0)
            if best is None:
                return None
            chosen, data = best
        else:
            data = json.loads(chosen.read_text(encoding='utf-8'))

        self._cache[cache_key] = data
        return data

    def get_queue(self, level_num: int, variant: Optional[str] = None) -> Optional[dict]:
        """Return queueGroup section."""
        d = self.get_level(level_num, variant)
        return d.get("queueGroup") if d else None

    def get_board(self, level_num: int, variant: Optional[str] = None) -> Optional[dict]:
        """Return board section (cells, dimensions)."""
        d = self.get_level(level_num, variant)
        return d.get("board") if d else None

    def get_gimmicks(self, level_num: int, variant: Optional[str] = None) -> Optional[dict]:
        """Return boardGimmicks section."""
        d = self.get_level(level_num, variant)
        return d.get("boardGimmicks") if d else None

    def get_meta(self, level_num: int, variant: Optional[str] = None) -> Optional[dict]:
        """Return meta section (slot_count, conveyor_limit, etc)."""
        d = self.get_level(level_num, variant)
        return d.get("meta") if d else None

    def get_expanded_queue(self, level_num: int, variant: Optional[str] = None) -> List[dict]:
        """
        Return queue as flat list of taps in line order.
        Each entry: {"line": int, "position": int, "shooter_id": int, "material": int, "ammo": int}.
        """
        qg = self.get_queue(level_num, variant)
        if not qg:
            return []
        flat = []
        for line in qg.get("lines", []):
            li = line.get("line_index")
            for s in line.get("shooters", []):
                flat.append({
                    "line": li,
                    "position": s.get("position_in_line"),
                    "shooter_id": s.get("id"),
                    "material": s.get("material"),
                    "material_name": s.get("material_name", COLOR_NAMES.get(s.get("material"), "?")),
                    "ammo": s.get("ammo", 1),
                })
        return flat

    def material_name(self, material_code: int) -> str:
        """Convert material code to human-readable name."""
        return COLOR_NAMES.get(material_code, f"unknown_{material_code}")

    def stats(self) -> dict:
        """Summary stats for all loaded levels."""
        return {
            "total_levels": len(self.variants_index),
            "total_variants": sum(len(v) for v in self.variants_index.values()),
            "level_range": (min(self.variants_index.keys()), max(self.variants_index.keys())),
        }


if __name__ == "__main__":
    loader = LevelLoader()
    print(f"Stats: {loader.stats()}")
    print(f"\nLevel 184 variants: {loader.list_variants(184)}")

    queue = loader.get_queue(184)
    if queue:
        print(f"\nLevel 184 canonical queue:")
        print(f"  Lines: {queue.get('line_count')}")
        print(f"  Total shooters: {queue.get('total_shooters')}")
        print(f"  Total ammo: {queue.get('total_ammo_sum')}")

    expanded = loader.get_expanded_queue(184)[:5]
    print(f"\nFirst 5 shooters of L184:")
    for s in expanded:
        print(f"  Line {s['line']} pos {s['position']}: id={s['shooter_id']} "
              f"{s['material_name']} × {s['ammo']}")
