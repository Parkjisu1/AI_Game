"""
JournalSearch -- Full-Text + Tag Journal Search
================================================
Searches across journal entries by keyword, tag, date, and game.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class JournalSearch:
    """Search across session journal entries."""

    def __init__(self, journal_dir: Optional[Path] = None):
        if journal_dir:
            self.journal_dir = Path(journal_dir)
        else:
            self.journal_dir = Path(__file__).parent.parent / "data" / "journal"

    def search(
        self,
        query: str = "",
        tags: Optional[List[str]] = None,
        package_name: Optional[str] = None,
        genre: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search journal entries.

        Args:
            query: Full-text search query (searches in all string values).
            tags: Filter by tags (OR match).
            package_name: Filter by package name.
            genre: Filter by genre.
            date_from: ISO date string (YYYY-MM-DD).
            date_to: ISO date string (YYYY-MM-DD).
            limit: Max results.

        Returns:
            List of matching journal entries (JSON data dicts).
        """
        results = []

        if not self.journal_dir.exists():
            return results

        # Walk all JSON files
        json_files = sorted(self.journal_dir.rglob("*.json"), reverse=True)

        for json_path in json_files:
            if len(results) >= limit:
                break

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            # Apply filters
            if package_name and data.get("package_name") != package_name:
                continue

            if genre and data.get("genre") != genre:
                continue

            if tags:
                entry_tags = set(data.get("tags", []))
                if not entry_tags.intersection(tags):
                    continue

            # Date filter
            entry_date = data.get("timestamp", "")[:10]
            if date_from and entry_date < date_from:
                continue
            if date_to and entry_date > date_to:
                continue

            # Full-text search
            if query:
                text_content = json.dumps(data, ensure_ascii=False).lower()
                if query.lower() not in text_content:
                    continue

            results.append({
                "session_id": data.get("session_id", json_path.stem),
                "package_name": data.get("package_name", ""),
                "genre": data.get("genre", ""),
                "timestamp": data.get("timestamp", ""),
                "tags": data.get("tags", []),
                "path": str(json_path),
            })

        return results

    def get_entry(self, session_id: str) -> Optional[Dict]:
        """Get a specific journal entry by session_id."""
        for json_path in self.journal_dir.rglob("*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("session_id") == session_id:
                    return data
            except Exception:
                continue
        return None

    def list_games(self) -> List[str]:
        """List all unique package names in the journal."""
        packages = set()
        for json_path in self.journal_dir.rglob("*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pkg = data.get("package_name")
                if pkg:
                    packages.add(pkg)
            except Exception:
                continue
        return sorted(packages)
