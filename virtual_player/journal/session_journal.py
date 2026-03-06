"""
SessionJournal -- Structured Session History
=============================================
Each test session creates a Markdown summary + JSON sidecar with detailed data.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionJournal:
    """Writes structured session records as Markdown + JSON sidecar."""

    def __init__(self, journal_dir: Optional[Path] = None):
        """
        Args:
            journal_dir: Root directory for journal entries.
                         Defaults to virtual_player/data/journal/.
        """
        if journal_dir:
            self.journal_dir = Path(journal_dir)
        else:
            self.journal_dir = Path(__file__).parent.parent / "data" / "journal"

    def write(
        self,
        package_name: str,
        genre: str,
        session_data: Dict[str, Any],
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Path]:
        """
        Write a session journal entry.

        Args:
            package_name: Game package name.
            genre: Detected genre.
            session_data: Dict with session details:
                - phase_results: {phase_name: result_dict}
                - duration_seconds: float
                - screens_discovered: int
                - parameters_extracted: int
                - errors: [str]
            tags: Optional tags for searching.

        Returns:
            {"markdown": Path, "json": Path}
        """
        timestamp = datetime.now()
        date_str = timestamp.strftime("%Y-%m-%d")
        time_str = timestamp.strftime("%H%M%S")
        session_id = f"{date_str}_{time_str}_{package_name.split('.')[-1]}"

        session_dir = self.journal_dir / date_str
        session_dir.mkdir(parents=True, exist_ok=True)

        # JSON sidecar (full data)
        json_path = session_dir / f"{session_id}.json"
        json_data = {
            "session_id": session_id,
            "package_name": package_name,
            "genre": genre,
            "timestamp": timestamp.isoformat(),
            "tags": tags or [],
            **session_data,
        }
        self._write_json(json_path, json_data)

        # Markdown summary
        md_path = session_dir / f"{session_id}.md"
        md_content = self._render_markdown(session_id, package_name, genre,
                                            timestamp, session_data, tags)
        md_path.write_text(md_content, encoding="utf-8")

        logger.info("Journal written: %s", session_id)
        return {"markdown": md_path, "json": json_path}

    def _render_markdown(
        self,
        session_id: str,
        package_name: str,
        genre: str,
        timestamp: datetime,
        session_data: Dict,
        tags: Optional[List[str]],
    ) -> str:
        lines = [
            f"# Session: {session_id}",
            "",
            f"- **Package**: `{package_name}`",
            f"- **Genre**: {genre}",
            f"- **Date**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Duration**: {session_data.get('duration_seconds', 0):.0f}s",
        ]

        if tags:
            lines.append(f"- **Tags**: {', '.join(tags)}")

        lines.append("")

        # Phase results
        phases = session_data.get("phase_results", {})
        if phases:
            lines.append("## Phases")
            lines.append("")
            for phase_name, result in phases.items():
                status = result.get("status", "unknown")
                emoji = "+" if status == "success" else "-"
                lines.append(f"### {phase_name}")
                lines.append(f"- Status: {status}")
                if "duration" in result:
                    lines.append(f"- Duration: {result['duration']:.1f}s")
                for k, v in result.items():
                    if k not in ("status", "duration"):
                        lines.append(f"- {k}: {v}")
                lines.append("")

        # Stats
        lines.append("## Stats")
        lines.append("")
        lines.append(f"- Screens discovered: {session_data.get('screens_discovered', 0)}")
        lines.append(f"- Parameters extracted: {session_data.get('parameters_extracted', 0)}")

        # Errors
        errors = session_data.get("errors", [])
        if errors:
            lines.append("")
            lines.append("## Errors")
            lines.append("")
            for err in errors:
                lines.append(f"- {err}")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            tmp.replace(path)
        except OSError:
            if path.exists():
                path.unlink()
            tmp.rename(path)
