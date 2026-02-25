"""
Reference Database
===================
Per-screen-type reference screenshot database built from recorded annotations.
Used by LocalVision for SSIM-based screen classification and template matching.
"""

import json
import struct
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from ..adb import log
from ..navigation.classifier import compute_phash


# ---------------------------------------------------------------------------
# Region definitions (1080x1920 base resolution)
# ---------------------------------------------------------------------------
REGIONS = {
    "top_bar":       (0, 0, 1080, 160),      # title / back button area
    "bottom_nav":    (0, 1760, 1080, 1920),   # tab bar
    "center":        (100, 480, 980, 1440),   # main content area
}

# Thumbnail size for fast SSIM comparison
THUMB_W, THUMB_H = 135, 240


def _img_to_gray_array(img: "Image.Image") -> np.ndarray:
    """Convert PIL Image to grayscale numpy array."""
    return np.array(img.convert("L"), dtype=np.float64)


def _crop_region(img: "Image.Image", region: Tuple[int, int, int, int],
                 target_w: int = 0, target_h: int = 0) -> np.ndarray:
    """Crop a region from image and optionally resize. Returns grayscale float64."""
    x1, y1, x2, y2 = region
    # Scale region coords to actual image size
    w, h = img.size
    sx, sy = w / 1080.0, h / 1920.0
    cropped = img.crop((int(x1*sx), int(y1*sy), int(x2*sx), int(y2*sy)))
    if target_w > 0 and target_h > 0:
        cropped = cropped.resize((target_w, target_h), Image.LANCZOS)
    return np.array(cropped.convert("L"), dtype=np.float64)


def ssim_simple(img1: np.ndarray, img2: np.ndarray) -> float:
    """Simplified SSIM using numpy only.

    Both inputs should be grayscale float64 arrays of the same shape.
    Returns structural similarity score (0.0-1.0).
    """
    if img1.shape != img2.shape:
        return 0.0

    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    mu1 = img1.mean()
    mu2 = img2.mean()
    sigma1_sq = img1.var()
    sigma2_sq = img2.var()
    sigma12 = ((img1 - mu1) * (img2 - mu2)).mean()

    num = (2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)
    den = (mu1 ** 2 + mu2 ** 2 + C1) * (sigma1_sq + sigma2_sq + C2)

    return float(num / den) if den != 0 else 0.0


# ---------------------------------------------------------------------------
# Reference Entry
# ---------------------------------------------------------------------------
class RefEntry:
    """A single reference frame entry."""
    __slots__ = ("frame_path", "phash", "thumbnail", "regions",
                 "screen_type", "element_crops")

    def __init__(self, frame_path: str, phash: int, thumbnail: np.ndarray,
                 regions: Dict[str, np.ndarray], screen_type: str,
                 element_crops: Optional[Dict[str, Tuple[np.ndarray, int, int]]] = None):
        self.frame_path = frame_path
        self.phash = phash
        self.thumbnail = thumbnail       # (THUMB_H, THUMB_W) grayscale
        self.regions = regions            # region_name -> grayscale array
        self.screen_type = screen_type
        self.element_crops = element_crops or {}  # element -> (crop_array, cx, cy)


# ---------------------------------------------------------------------------
# Reference Database
# ---------------------------------------------------------------------------
class ReferenceDB:
    """Per-screen-type reference screenshot database."""

    def __init__(self):
        self.entries: Dict[str, List[RefEntry]] = {}  # screen_type -> entries
        self._all_entries: List[RefEntry] = []         # flat list for pHash search

    def build_from_annotations(self, annotations_path: Path, frames_dir: Path):
        """Build reference DB from annotated recording frames.

        Groups frames by screen_type, computes pHash + crops key regions.
        Also extracts element crops for template matching.
        """
        if not HAS_PIL:
            log("  [RefDB] PIL not available, cannot build reference DB")
            return

        annotations = json.loads(annotations_path.read_text(encoding="utf-8"))
        log(f"  [RefDB] Building from {len(annotations)} annotations, "
            f"frames: {frames_dir}")

        # Collect (screen_type, frame, elements_with_coords) mappings
        frame_info: Dict[str, Dict[str, Any]] = {}  # frame -> info

        for ann in annotations:
            before_frame = ann.get("screenshot_before", "")
            before_screen = ann.get("before_screen", "")
            element = ann.get("element", "")
            x, y = ann.get("x", 0), ann.get("y", 0)

            if before_frame and before_screen:
                if before_frame not in frame_info:
                    frame_info[before_frame] = {
                        "screen_type": before_screen,
                        "elements": {},
                    }
                # Store element coordinates for this frame
                if element and x > 0 and y > 0:
                    frame_info[before_frame]["elements"][element] = (x, y)

            # Also register after_frame screen type
            after_frame = ann.get("screenshot_after", "")
            after_screen = ann.get("after_screen", "")
            if after_frame and after_screen and after_frame not in frame_info:
                frame_info[after_frame] = {
                    "screen_type": after_screen,
                    "elements": {},
                }

        # Build entries
        built = 0
        for frame_name, info in frame_info.items():
            frame_path = frames_dir / frame_name
            if not frame_path.exists():
                continue

            screen_type = info["screen_type"]
            try:
                img = Image.open(frame_path)
            except Exception:
                continue

            phash = compute_phash(frame_path)
            if phash is None:
                continue

            # Compute thumbnail
            thumb = _img_to_gray_array(
                img.convert("L").resize((THUMB_W, THUMB_H), Image.LANCZOS)
            )

            # Crop key regions
            regions = {}
            for rname, rbox in REGIONS.items():
                try:
                    regions[rname] = _crop_region(img, rbox, target_w=64, target_h=32)
                except Exception:
                    pass

            # Extract element crops (60x60 region around recorded coords)
            element_crops = {}
            w_img, h_img = img.size
            crop_half = 30
            for elem, (ex, ey) in info["elements"].items():
                # Scale coords to image size
                sx, sy = w_img / 1080.0, h_img / 1920.0
                px, py = int(ex * sx), int(ey * sy)
                x1 = max(0, px - crop_half)
                y1 = max(0, py - crop_half)
                x2 = min(w_img, px + crop_half)
                y2 = min(h_img, py + crop_half)
                try:
                    crop_arr = np.array(
                        img.crop((x1, y1, x2, y2)).convert("L"),
                        dtype=np.float64
                    )
                    element_crops[elem] = (crop_arr, ex, ey)
                except Exception:
                    pass

            entry = RefEntry(
                frame_path=str(frame_path),
                phash=phash,
                thumbnail=thumb,
                regions=regions,
                screen_type=screen_type,
                element_crops=element_crops,
            )

            if screen_type not in self.entries:
                self.entries[screen_type] = []
            self.entries[screen_type].append(entry)
            self._all_entries.append(entry)
            built += 1

        log(f"  [RefDB] Built {built} reference entries across "
            f"{len(self.entries)} screen types")
        for st, entries in sorted(self.entries.items()):
            log(f"    {st}: {len(entries)} frames")

    def get_entries(self, screen_type: str) -> List[RefEntry]:
        """Get all reference entries for a screen type."""
        return self.entries.get(screen_type, [])

    def get_all_entries(self) -> List[RefEntry]:
        """Get flat list of all entries."""
        return self._all_entries

    def get_screen_types(self) -> List[str]:
        """Get all screen types in the DB."""
        return list(self.entries.keys())

    # --- Persistence ---

    def save(self, db_dir: Path):
        """Save reference DB to directory (numpy arrays compressed)."""
        db_dir.mkdir(parents=True, exist_ok=True)

        index = {}
        for screen_type, entries in self.entries.items():
            index[screen_type] = []
            for i, entry in enumerate(entries):
                entry_id = f"{screen_type}_{i}"

                # Save numpy arrays as compressed files
                arrays_file = db_dir / f"{entry_id}.npz"
                arrays = {"thumbnail": entry.thumbnail}
                for rname, rarr in entry.regions.items():
                    arrays[f"region_{rname}"] = rarr
                for elem, (crop, cx, cy) in entry.element_crops.items():
                    safe_elem = elem.replace("/", "_").replace("\\", "_")
                    arrays[f"elem_{safe_elem}"] = crop

                np.savez_compressed(str(arrays_file), **arrays)

                # Index entry
                elem_info = {
                    elem: {"cx": cx, "cy": cy}
                    for elem, (_, cx, cy) in entry.element_crops.items()
                }
                index[screen_type].append({
                    "entry_id": entry_id,
                    "frame_path": entry.frame_path,
                    "phash": entry.phash,
                    "elements": elem_info,
                })

        index_file = db_dir / "index.json"
        index_file.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"  [RefDB] Saved to {db_dir}: {len(self._all_entries)} entries")

    @classmethod
    def load(cls, db_dir: Path) -> "ReferenceDB":
        """Load reference DB from directory."""
        db = cls()
        index_file = db_dir / "index.json"
        if not index_file.exists():
            log(f"  [RefDB] No index at {index_file}, returning empty DB")
            return db

        index = json.loads(index_file.read_text(encoding="utf-8"))

        for screen_type, entries_data in index.items():
            db.entries[screen_type] = []
            for edata in entries_data:
                entry_id = edata["entry_id"]
                arrays_file = db_dir / f"{entry_id}.npz"

                if not arrays_file.exists():
                    continue

                try:
                    loaded = np.load(str(arrays_file))
                except Exception:
                    continue

                thumbnail = loaded.get("thumbnail", np.zeros((THUMB_H, THUMB_W)))
                regions = {}
                element_crops = {}

                for key in loaded.files:
                    if key.startswith("region_"):
                        rname = key[len("region_"):]
                        regions[rname] = loaded[key].astype(np.float64)
                    elif key.startswith("elem_"):
                        safe_elem = key[len("elem_"):]
                        # Reverse the safe_elem to original
                        elem_info = edata.get("elements", {})
                        # Find matching element
                        for orig_elem in elem_info:
                            orig_safe = orig_elem.replace("/", "_").replace("\\", "_")
                            if orig_safe == safe_elem:
                                cx = elem_info[orig_elem]["cx"]
                                cy = elem_info[orig_elem]["cy"]
                                element_crops[orig_elem] = (
                                    loaded[key].astype(np.float64), cx, cy
                                )
                                break

                entry = RefEntry(
                    frame_path=edata["frame_path"],
                    phash=edata["phash"],
                    thumbnail=thumbnail.astype(np.float64),
                    regions=regions,
                    screen_type=screen_type,
                    element_crops=element_crops,
                )
                db.entries[screen_type].append(entry)
                db._all_entries.append(entry)

        log(f"  [RefDB] Loaded from {db_dir}: {len(db._all_entries)} entries "
            f"across {len(db.entries)} screen types")
        return db
