"""
ScreenFingerprinter -- pHash Clustering + Screen Type Labeling
===============================================================
Groups exploration screenshots by visual similarity (perceptual hash),
then labels each cluster with a screen type.
"""

import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _compute_phash(image_path: Path, hash_size: int = 8) -> Optional[str]:
    """Compute perceptual hash of an image."""
    try:
        from PIL import Image
        img = Image.open(image_path).convert("L").resize(
            (hash_size + 1, hash_size), Image.LANCZOS
        )
        arr = np.array(img, dtype=np.float64)
        # Compute DCT-like difference hash
        diff = arr[:, 1:] > arr[:, :-1]
        return "".join("1" if b else "0" for row in diff for b in row)
    except Exception as e:
        logger.debug("pHash failed for %s: %s", image_path, e)
        return None


def _hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two hash strings."""
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))


class ScreenFingerprinter:
    """Groups screenshots by visual similarity and labels clusters."""

    DEFAULT_THRESHOLD = 10  # Max Hamming distance for same cluster

    def __init__(
        self,
        threshold: int = DEFAULT_THRESHOLD,
        label_fn: Optional[Callable[[Path], str]] = None,
    ):
        """
        Args:
            threshold: Max Hamming distance to consider two screenshots the same.
            label_fn: (screenshot_path) -> screen_type. Called once per cluster
                      representative. Use Claude Vision or a classifier.
                      If None, labels are auto-generated ("screen_0", "screen_1", ...).
        """
        self.threshold = threshold
        self._label_fn = label_fn
        self.clusters: Dict[str, List[Path]] = {}  # label -> [paths]
        self._hashes: List[Tuple[str, Path, str]] = []  # (hash, path, label)

    def add_screenshot(self, path: Path) -> str:
        """
        Add a screenshot and return its cluster label.

        Args:
            path: Path to screenshot image.

        Returns:
            Cluster label (screen type).
        """
        phash = _compute_phash(path)
        if phash is None:
            return "unknown"

        # Find closest existing cluster
        best_label = None
        best_dist = self.threshold + 1

        for existing_hash, _, label in self._hashes:
            dist = _hamming_distance(phash, existing_hash)
            if dist < best_dist:
                best_dist = dist
                best_label = label

        if best_dist <= self.threshold and best_label:
            # Belongs to existing cluster
            self.clusters[best_label].append(path)
            self._hashes.append((phash, path, best_label))
            return best_label

        # New cluster -- label it
        if self._label_fn:
            label = self._label_fn(path)
        else:
            label = f"screen_{len(self.clusters)}"

        self.clusters[label] = [path]
        self._hashes.append((phash, path, label))
        return label

    def cluster_screenshots(self, paths: List[Path]) -> Dict[str, List[Path]]:
        """
        Cluster a batch of screenshots.

        Args:
            paths: List of screenshot paths.

        Returns:
            {label: [paths]} mapping.
        """
        for p in paths:
            self.add_screenshot(p)
        return dict(self.clusters)

    def get_representatives(self) -> Dict[str, Path]:
        """Get one representative screenshot per cluster."""
        return {
            label: paths[0]
            for label, paths in self.clusters.items()
            if paths
        }

    def get_cluster_sizes(self) -> Dict[str, int]:
        """Get the number of screenshots in each cluster."""
        return {label: len(paths) for label, paths in self.clusters.items()}

    def export_screen_types(self) -> Dict[str, str]:
        """Export screen types as {label: description} dict."""
        result = {}
        for label in self.clusters:
            count = len(self.clusters[label])
            result[label] = f"Auto-discovered screen ({count} occurrences)"
        return result

    def save(self, path: Path) -> None:
        """Save cluster data to JSON."""
        data = {
            "threshold": self.threshold,
            "clusters": {
                label: [str(p) for p in paths]
                for label, paths in self.clusters.items()
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
