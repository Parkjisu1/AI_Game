"""
Local Vision
=============
OpenCV-based screen analysis for mobile games.
Replaces all Claude Vision API calls with local template matching + SSIM.

Zero API cost -- uses reference screenshot database for classification
and element finding.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from ..adb import log
from ..navigation.classifier import compute_phash, hamming_distance
from .reference_db import (
    ReferenceDB, RefEntry, REGIONS, THUMB_W, THUMB_H,
    ssim_simple, _crop_region, _img_to_gray_array,
)


# Region weights for screen classification
_REGION_WEIGHTS = {
    "top_bar": 0.4,
    "bottom_nav": 0.3,
    "center": 0.3,
}

# Thresholds
_CLASSIFY_THRESHOLD = 0.45       # Min weighted SSIM to accept classification
_CLASSIFY_PHASH_CANDIDATES = 8   # How many pHash candidates to check with SSIM
_TEMPLATE_MATCH_THRESHOLD = 0.65 # Min confidence for template matching
_ELEMENT_SEARCH_EXPAND = 40      # Pixels to expand search area on retry


class LocalVision:
    """OpenCV-based screen analysis -- replaces Claude Vision API calls."""

    def __init__(self, reference_db: ReferenceDB):
        self._ref_db = reference_db

    # ------------------------------------------------------------------
    # Screen Classification
    # ------------------------------------------------------------------

    def classify_screen(self, screenshot_path: Path
                        ) -> Tuple[str, float]:
        """Classify screen using SSIM region matching against reference DB.

        Returns (screen_type, confidence). Returns ("unknown", 0.0) on failure.
        """
        if not HAS_PIL:
            return ("unknown", 0.0)

        try:
            img = Image.open(screenshot_path)
        except Exception:
            return ("unknown", 0.0)

        # Compute pHash for fast candidate filtering
        phash = compute_phash(screenshot_path)
        all_entries = self._ref_db.get_all_entries()

        if not all_entries:
            return ("unknown", 0.0)

        # Find top candidates by pHash distance
        if phash is not None:
            scored = []
            for entry in all_entries:
                if entry.phash is not None:
                    dist = hamming_distance(phash, entry.phash)
                    scored.append((dist, entry))
            scored.sort(key=lambda x: x[0])
            candidates = [e for _, e in scored[:_CLASSIFY_PHASH_CANDIDATES]]
        else:
            # No pHash -- sample from each screen type
            candidates = []
            for st_entries in self._ref_db.entries.values():
                candidates.extend(st_entries[:2])

        if not candidates:
            return ("unknown", 0.0)

        # Compute SSIM scores for candidates using key regions
        current_regions = {}
        for rname, rbox in REGIONS.items():
            try:
                current_regions[rname] = _crop_region(img, rbox, target_w=64, target_h=32)
            except Exception:
                pass

        best_score = 0.0
        best_type = "unknown"

        for entry in candidates:
            score = 0.0
            weight_sum = 0.0

            for rname, weight in _REGION_WEIGHTS.items():
                if rname in current_regions and rname in entry.regions:
                    s = ssim_simple(current_regions[rname], entry.regions[rname])
                    score += s * weight
                    weight_sum += weight

            if weight_sum > 0:
                score /= weight_sum  # Normalize by actual weights used
                score *= weight_sum  # But scale back to show coverage

            # Also compute thumbnail SSIM as tiebreaker
            try:
                current_thumb = _img_to_gray_array(
                    img.convert("L").resize((THUMB_W, THUMB_H), Image.LANCZOS)
                )
                thumb_ssim = ssim_simple(current_thumb, entry.thumbnail)
                # Blend: 70% region-based, 30% thumbnail
                score = 0.7 * score + 0.3 * thumb_ssim
            except Exception:
                pass

            if score > best_score:
                best_score = score
                best_type = entry.screen_type

        if best_score >= _CLASSIFY_THRESHOLD:
            return (best_type, min(best_score, 1.0))
        else:
            return ("unknown", best_score)

    # ------------------------------------------------------------------
    # Element Finding (Template Matching)
    # ------------------------------------------------------------------

    def find_element_by_region(self, screenshot_path: Path,
                               screen_type: str, element_name: str
                               ) -> Optional[Tuple[int, int]]:
        """Find a named UI element by template matching reference crops.

        Uses element crops from reference frames for the given screen_type.
        Returns (x, y) center coordinates or None.
        """
        if not HAS_CV2 or not HAS_PIL:
            return None

        entries = self._ref_db.get_entries(screen_type)
        if not entries:
            return None

        try:
            screenshot = cv2.imread(str(screenshot_path), cv2.IMREAD_GRAYSCALE)
            if screenshot is None:
                return None
        except Exception:
            return None

        # Collect all template crops for this element from reference frames
        templates = []
        for entry in entries:
            if element_name in entry.element_crops:
                crop_arr, cx, cy = entry.element_crops[element_name]
                templates.append((crop_arr, cx, cy))

        if not templates:
            return None

        # Try template matching with each crop
        best_val = 0.0
        best_coords = None

        for crop_arr, orig_cx, orig_cy in templates:
            template = crop_arr.astype(np.uint8)
            if template.shape[0] < 5 or template.shape[1] < 5:
                continue

            # Scale template to match screenshot resolution
            sh, sw = screenshot.shape[:2]
            scale_x, scale_y = sw / 1080.0, sh / 1920.0
            th = max(5, int(template.shape[0] * scale_y))
            tw = max(5, int(template.shape[1] * scale_x))

            try:
                template_scaled = cv2.resize(template, (tw, th))
            except Exception:
                continue

            # Search in a region around expected position first
            exp_x = int(orig_cx * scale_x)
            exp_y = int(orig_cy * scale_y)
            margin = int(100 * max(scale_x, scale_y))

            # Expanded search region
            rx1 = max(0, exp_x - margin - tw)
            ry1 = max(0, exp_y - margin - th)
            rx2 = min(sw, exp_x + margin + tw)
            ry2 = min(sh, exp_y + margin + th)

            roi = screenshot[ry1:ry2, rx1:rx2]
            if roi.shape[0] < th or roi.shape[1] < tw:
                # ROI too small, search full image
                roi = screenshot
                rx1, ry1 = 0, 0

            try:
                result = cv2.matchTemplate(roi, template_scaled,
                                           cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
            except Exception:
                continue

            if max_val > best_val:
                best_val = max_val
                # Convert local coords back to global
                match_x = rx1 + max_loc[0] + tw // 2
                match_y = ry1 + max_loc[1] + th // 2
                # Scale back to 1080x1920
                best_coords = (int(match_x / scale_x), int(match_y / scale_y))

        if best_val >= _TEMPLATE_MATCH_THRESHOLD and best_coords:
            log(f"  [LocalVision] Template match: {element_name} at "
                f"{best_coords} (conf={best_val:.2f})")
            return best_coords

        # Fallback: return original recorded coords if confidence is marginal
        if best_val >= 0.4 and best_coords:
            log(f"  [LocalVision] Marginal match: {element_name} at "
                f"{best_coords} (conf={best_val:.2f}, using anyway)")
            return best_coords

        return None

    # ------------------------------------------------------------------
    # Close Button Detection
    # ------------------------------------------------------------------

    def find_close_button(self, screenshot_path: Path
                          ) -> Optional[Tuple[int, int]]:
        """Find popup close/X button using visual heuristics.

        Strategy stack:
        1. Template match known close button crops from reference DB
        2. OpenCV contour detection for small dark circles/squares (X buttons)
        3. Fallback positions
        """
        if not HAS_CV2:
            return None

        try:
            screenshot = cv2.imread(str(screenshot_path), cv2.IMREAD_GRAYSCALE)
            screenshot_color = cv2.imread(str(screenshot_path))
            if screenshot is None:
                return None
        except Exception:
            return None

        sh, sw = screenshot.shape[:2]
        scale_x, scale_y = sw / 1080.0, sh / 1920.0

        # Strategy 1: Template match known close buttons from popup refs
        close_templates = self._get_close_button_templates()
        if close_templates:
            best_val = 0.0
            best_loc = None

            for template in close_templates:
                t = template.astype(np.uint8)
                if t.shape[0] < 5 or t.shape[1] < 5:
                    continue
                th = max(5, int(t.shape[0] * scale_y))
                tw = max(5, int(t.shape[1] * scale_x))

                try:
                    t_scaled = cv2.resize(t, (tw, th))
                    result = cv2.matchTemplate(screenshot, t_scaled,
                                               cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                except Exception:
                    continue

                if max_val > best_val:
                    best_val = max_val
                    best_loc = (max_loc[0] + tw // 2, max_loc[1] + th // 2)

            if best_val >= 0.6 and best_loc:
                cx = int(best_loc[0] / scale_x)
                cy = int(best_loc[1] / scale_y)
                log(f"  [LocalVision] Close button template match at "
                    f"({cx},{cy}) conf={best_val:.2f}")
                return (cx, cy)

        # Strategy 2: Contour detection in top-right quadrant
        # Close buttons are usually small, dark, circular/square in top-right
        top_right = screenshot[0:int(sh*0.25), int(sw*0.5):]
        if top_right.size > 0:
            coords = self._find_x_button_by_contour(
                top_right, offset_x=int(sw*0.5), offset_y=0,
                scale_x=scale_x, scale_y=scale_y
            )
            if coords:
                return coords

        # Strategy 3: Look for confirm/OK buttons at bottom center
        bottom_center = screenshot[int(sh*0.6):, int(sw*0.2):int(sw*0.8)]
        if bottom_center.size > 0:
            coords = self._find_button_by_contour(
                bottom_center, offset_x=int(sw*0.2), offset_y=int(sh*0.6),
                scale_x=scale_x, scale_y=scale_y,
                min_w=80, min_h=30, max_w=400, max_h=120
            )
            if coords:
                return coords

        return None

    def _get_close_button_templates(self) -> List[np.ndarray]:
        """Collect close button crops from popup reference entries."""
        templates = []
        for screen_type in self._ref_db.get_screen_types():
            if not screen_type.startswith("popup_"):
                continue
            for entry in self._ref_db.get_entries(screen_type):
                for elem_name in ("close_button", "x_button", "cancel_button",
                                  "dismiss_button", "confirm_button"):
                    if elem_name in entry.element_crops:
                        crop, _, _ = entry.element_crops[elem_name]
                        templates.append(crop)
        return templates

    def _find_x_button_by_contour(self, roi: np.ndarray,
                                  offset_x: int, offset_y: int,
                                  scale_x: float, scale_y: float
                                  ) -> Optional[Tuple[int, int]]:
        """Find X/close button via contour detection in a ROI."""
        # Threshold to find dark elements on lighter popup background
        _, binary = cv2.threshold(roi, 60, 255, cv2.THRESH_BINARY_INV)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            # Close buttons are roughly 30-80px square
            min_s = int(20 * min(scale_x, scale_y))
            max_s = int(100 * max(scale_x, scale_y))
            if min_s <= w <= max_s and min_s <= h <= max_s:
                # Roughly square (aspect ratio close to 1)
                aspect = w / h if h > 0 else 0
                if 0.5 <= aspect <= 2.0:
                    cx = offset_x + x + w // 2
                    cy = offset_y + y + h // 2
                    candidates.append((area, cx, cy))

        if candidates:
            # Pick the one most likely to be an X button (moderate size)
            candidates.sort(key=lambda c: abs(c[0] - 1500))
            _, cx, cy = candidates[0]
            result_x = int(cx / scale_x)
            result_y = int(cy / scale_y)
            log(f"  [LocalVision] X button contour at ({result_x},{result_y})")
            return (result_x, result_y)

        return None

    def _find_button_by_contour(self, roi: np.ndarray,
                                offset_x: int, offset_y: int,
                                scale_x: float, scale_y: float,
                                min_w: int = 60, min_h: int = 20,
                                max_w: int = 500, max_h: int = 150
                                ) -> Optional[Tuple[int, int]]:
        """Find a rectangular button in a ROI via contour detection."""
        # Use adaptive threshold for varied backgrounds
        binary = cv2.adaptiveThreshold(roi, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 15, 5)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            s_min_w = int(min_w * scale_x)
            s_max_w = int(max_w * scale_x)
            s_min_h = int(min_h * scale_y)
            s_max_h = int(max_h * scale_y)
            if s_min_w <= w <= s_max_w and s_min_h <= h <= s_max_h:
                # Buttons are wider than tall
                aspect = w / h if h > 0 else 0
                if aspect >= 1.5:
                    area = w * h
                    cx = offset_x + x + w // 2
                    cy = offset_y + y + h // 2
                    candidates.append((area, cx, cy))

        if candidates:
            # Pick the largest button-like contour
            candidates.sort(key=lambda c: c[0], reverse=True)
            _, cx, cy = candidates[0]
            result_x = int(cx / scale_x)
            result_y = int(cy / scale_y)
            log(f"  [LocalVision] Button contour at ({result_x},{result_y})")
            return (result_x, result_y)

        return None

    # ------------------------------------------------------------------
    # Tutorial Highlight Detection
    # ------------------------------------------------------------------

    def find_tutorial_target(self, screenshot_path: Path
                             ) -> Optional[Tuple[int, int]]:
        """Find bright highlight area in dimmed tutorial overlay.

        Tutorial overlays typically dim most of the screen while highlighting
        the target element brightly. We find the brightest non-fullscreen region.
        """
        if not HAS_CV2:
            return None

        try:
            screenshot = cv2.imread(str(screenshot_path), cv2.IMREAD_GRAYSCALE)
            if screenshot is None:
                return None
        except Exception:
            return None

        sh, sw = screenshot.shape[:2]
        scale_x, scale_y = sw / 1080.0, sh / 1920.0

        # Threshold to find bright regions (highlights on dimmed background)
        _, bright = cv2.threshold(screenshot, 180, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        total_area = sw * sh
        candidates = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Skip very small noise and full-screen regions
            if area < total_area * 0.005 or area > total_area * 0.5:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            candidates.append((area, cx, cy))

        if candidates:
            # Pick the brightest, most prominent region
            candidates.sort(key=lambda c: c[0], reverse=True)
            _, cx, cy = candidates[0]
            result_x = int(cx / scale_x)
            result_y = int(cy / scale_y)
            log(f"  [LocalVision] Tutorial highlight at ({result_x},{result_y})")
            return (result_x, result_y)

        return None
