"""
DesignDBExporter -- Export Aggregated Parameters to Design DB
==============================================================
Writes domain-grouped design documents to db/design/base/{genre}/{domain}/.

Extracted from carmatch_tester.py and made configurable.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default DB root
DEFAULT_DB_ROOT = Path(__file__).parent.parent.parent / "db" / "design"


class DomainGroup:
    """Configuration for a domain group of parameters."""

    def __init__(
        self,
        domain: str,
        design_id: str,
        system: str,
        balance_area: str,
        params: List[str],
        provides: List[str],
        tags: List[str],
    ):
        self.domain = domain
        self.design_id = design_id
        self.system = system
        self.balance_area = balance_area
        self.params = params
        self.provides = provides
        self.tags = tags


class DesignDBExporter:
    """Export aggregated parameters to Design DB as domain-grouped documents."""

    def __init__(
        self,
        project: str,
        genre: str,
        package_name: str = "",
        domain_groups: Optional[List[DomainGroup]] = None,
        db_root: Optional[Path] = None,
        initial_score: float = 0.4,
    ):
        """
        Args:
            project: Project name (e.g., "CarMatch").
            genre: Genre name (e.g., "Puzzle", "RPG").
            package_name: Android package name.
            domain_groups: List of DomainGroup configs. Auto-generated if None.
            db_root: Root of Design DB. Defaults to E:/AI/db/design/.
            initial_score: Initial score for new entries.
        """
        self.project = project
        self.genre = genre
        self.package_name = package_name
        self.domain_groups = domain_groups or []
        self.db_root = db_root or DEFAULT_DB_ROOT
        self.initial_score = initial_score

    def export(
        self,
        aggregated: Dict[str, Dict[str, Any]],
        dry_run: bool = False,
    ) -> List[Path]:
        """
        Export aggregated parameters to Design DB.

        Args:
            aggregated: Output from ParameterAggregator.aggregate().
            dry_run: If True, log paths but don't write files.

        Returns:
            List of written file paths.
        """
        written = []
        genre_lower = self.genre.lower()

        for group in self.domain_groups:
            # Collect params for this group
            params_data = {}
            for pid in group.params:
                if pid in aggregated:
                    data = aggregated[pid]
                    params_data[pid] = {
                        "name": data.get("name", pid),
                        "value": data.get("value"),
                        "confidence": data.get("confidence", 0.0),
                    }

            if not params_data:
                logger.debug("Skipping empty domain group: %s", group.domain)
                continue

            domain_capitalized = group.domain.capitalize()
            if group.domain == "bm":
                domain_capitalized = "BM"
            elif group.domain == "ux":
                domain_capitalized = "UX"

            # Build detail document
            detail = {
                "designId": group.design_id,
                "project": self.project,
                "domain": domain_capitalized,
                "genre": self.genre,
                "system": group.system,
                "source": "observed",
                "version": "1.0.0",
                "score": self.initial_score,
                "data_type": "spec",
                "balance_area": group.balance_area,
                "source_file": "virtual_player AI Tester observation",
                "content": {
                    "summary": (
                        f"{self.project} ({self.package_name}) {group.system} parameters "
                        f"extracted by AI Tester observation."
                    ),
                    "flow": [],
                    "parameters": params_data,
                    "edge_cases": [],
                    "references": [],
                },
                "design_analysis": {
                    "design_intent": (
                        f"Extract {group.system.lower()} design parameters from "
                        f"{self.project} via automated observation."
                    ),
                    "context": (
                        "External game observation without source code access. "
                        "Parameters estimated via ADB screenshots + pixel analysis + OCR."
                    ),
                    "strengths": [
                        "Direct observation from live game build",
                        "Automated measurement reduces human bias",
                        "Multiple observers cross-validate parameters",
                    ],
                    "concerns": [
                        "No source code access limits parameter accuracy (~85-89%)",
                        "Some parameters require extended play sessions",
                        "OCR-dependent values may have recognition errors",
                    ],
                    "db_recommendation": f"{genre_lower}/{group.domain}/files/",
                    "reasoning": (
                        f"{self.genre} genre entry in Design DB. "
                        f"{self.project} provides baseline {group.system.lower()} data."
                    ),
                },
                "versions": [{
                    "version": "1.0.0",
                    "phase": "post_launch",
                    "data": f"AI Tester observation of {self.project}",
                    "note": "External game analysis import",
                }],
                "feedback_history": [],
                "code_mapping": {
                    "code_domain": "",
                    "code_roles": [],
                    "related_code_nodes": [],
                },
                "timestamp": datetime.now().isoformat(),
            }

            # Index entry
            index_entry = {
                "designId": group.design_id,
                "domain": domain_capitalized,
                "genre": self.genre,
                "system": group.system,
                "score": self.initial_score,
                "source": "observed",
                "data_type": "spec",
                "balance_area": group.balance_area,
                "version": "1.0.0",
                "project": self.project,
                "provides": group.provides,
                "requires": [],
                "tags": group.tags,
            }

            # Write files
            domain_dir = self.db_root / "base" / genre_lower / group.domain
            files_dir = domain_dir / "files"
            detail_path = files_dir / f"{group.design_id}.json"
            index_path = domain_dir / "index.json"

            if dry_run:
                logger.info("[DRY RUN] Would write: %s", detail_path)
                logger.info("[DRY RUN] Would update: %s", index_path)
                written.append(detail_path)
                continue

            files_dir.mkdir(parents=True, exist_ok=True)

            # Write detail file
            self._write_json(detail_path, detail)
            written.append(detail_path)

            # Update index
            self._upsert_index(index_path, index_entry)
            written.append(index_path)

            logger.info("Exported %s -> %s", group.design_id, detail_path)

        return written

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        """Atomic JSON write."""
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            tmp.replace(path)
        except OSError:
            if path.exists():
                path.unlink()
            tmp.rename(path)

    @staticmethod
    def _upsert_index(index_path: Path, entry: Dict) -> None:
        """Insert or update an index entry by designId."""
        index = []
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except Exception:
                index = []

        # Remove existing entry with same designId
        design_id = entry["designId"]
        index = [e for e in index if e.get("designId") != design_id]
        index.append(entry)

        DesignDBExporter._write_json(index_path, index)
