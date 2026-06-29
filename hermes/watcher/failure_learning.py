"""
Failure Learning — 실패 패턴 자동 감지 + 스킬 자동 생성

Hermes의 차별화 핵심 기능: 같은 실수를 반복하지 않도록 **스스로 스킬을 만들어 학습**.

Flow:
  1. _handle_unity_modify에서 실패 → record_failure()
  2. MongoDB activity_logs에 기록
  3. 같은 category 실패 임계값 초과 시 generate_learned_skill()
  4. 스킬 파일 (~/.hermes/skills/learned/auto_<category>.md) 생성
  5. 다음 에이전트 호출 시 load_learned_skills()가 이를 프리런으로 주입
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("failure-learning")

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
LEARNED_SKILLS_DIR = Path(
    os.environ.get(
        "HERMES_LEARNED_SKILLS_DIR",
        "/home/aimed/.hermes/skills/learned",
    )
)
FAILURE_THRESHOLD = int(os.environ.get("HERMES_FAILURE_THRESHOLD", "3"))
LOOKBACK_HOURS = int(os.environ.get("HERMES_FAILURE_LOOKBACK_HOURS", "72"))
ACTIVITY_COLLECTION = "activity_logs"


# ──────────────────────────────────────────────
# 실패 기록 (MongoDB)
# ──────────────────────────────────────────────
def record_failure(
    db,
    *,
    task_id: str,
    category: str,
    details: str,
    agent_role: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """activity_logs 컬렉션에 실패 기록"""
    try:
        doc = {
            "type": "failure",
            "task_id": task_id,
            "category": category,
            "details": (details or "")[:2000],
            "agent_role": agent_role,
            "context": context or {},
            "timestamp": datetime.now(timezone.utc),
        }
        db[ACTIVITY_COLLECTION].insert_one(doc)
        log.info("Failure recorded: category=%s task=%s", category, task_id[:8])
    except Exception:
        log.exception("record_failure DB 쓰기 실패 (무시하고 계속)")


def record_success(
    db,
    *,
    task_id: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """성공도 기록 (실패 대비 비율 보기 위해)"""
    try:
        doc = {
            "type": "success",
            "task_id": task_id,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc),
        }
        db[ACTIVITY_COLLECTION].insert_one(doc)
    except Exception:
        log.exception("record_success 실패")


# ──────────────────────────────────────────────
# 실패 패턴 집계
# ──────────────────────────────────────────────
def count_recent_failures(db, category: str, hours: int = LOOKBACK_HOURS) -> int:
    """최근 N시간 내 같은 카테고리 실패 수"""
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return db[ACTIVITY_COLLECTION].count_documents({
            "type": "failure",
            "category": category,
            "timestamp": {"$gte": since},
        })
    except Exception:
        log.exception("count_recent_failures 실패")
        return 0


def get_recent_failure_samples(
    db, category: str, hours: int = LOOKBACK_HOURS, limit: int = 5,
) -> list[dict[str, Any]]:
    """카테고리별 최근 실패 샘플 (스킬 생성 시 참조용)"""
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        cursor = db[ACTIVITY_COLLECTION].find({
            "type": "failure",
            "category": category,
            "timestamp": {"$gte": since},
        }).sort("timestamp", -1).limit(limit)
        return list(cursor)
    except Exception:
        log.exception("get_recent_failure_samples 실패")
        return []


# ──────────────────────────────────────────────
# 카테고리별 스킬 템플릿
# ──────────────────────────────────────────────
SKILL_TEMPLATES: dict[str, dict[str, str]] = {
    "non_fast_forward": {
        "title": "Handle non-fast-forward push rejections",
        "guidance": (
            "Before pushing, always check if the remote branch has diverged:\n"
            "1. `git fetch origin`\n"
            "2. `git status` to see if local is behind\n"
            "3. If diverged, `git pull --rebase origin <branch>` before push\n"
            "4. Only force-push with `--force-with-lease` in rework scenarios"
        ),
    },
    "auth_failure": {
        "title": "GitHub authentication setup for git push",
        "guidance": (
            "If git push fails with auth error:\n"
            "1. Run `gh auth setup-git` to configure credential helper\n"
            "2. Verify with `gh auth status`\n"
            "3. For fresh installs, also run `gh auth login` with browser OAuth"
        ),
    },
    "no_changes_made": {
        "title": "Ensure agents actually use Edit/Write tools",
        "guidance": (
            "When agents respond without modifying files:\n"
            "1. Check prompt explicitly demands ACTION (not description)\n"
            "2. Verify `--dangerously-skip-permissions --tools default` flags\n"
            "3. If still failing, include clear example: 'Use the Edit tool to modify file X'\n"
            "4. Check stdin is passing full prompt (avoid $(cat) in cmd.exe)"
        ),
    },
    "validator_rejected": {
        "title": "Common validation issues and fixes",
        "guidance": (
            "When Validator rejects changes:\n"
            "1. Include _CONTRACTS.yaml cross-check in Main Coder prompt\n"
            "2. Ensure namespaces follow AimedPuzzle.<Project>.<Layer> pattern\n"
            "3. Singleton Managers need unity_config.is_singleton: true metadata\n"
            "4. Event keys must be in static constant class, not hardcoded strings"
        ),
    },
    "timeout": {
        "title": "Handle SSH/network timeouts gracefully",
        "guidance": (
            "When SSH or network times out:\n"
            "1. Reduce prompt size (trim context)\n"
            "2. Check Tailscale connectivity first\n"
            "3. Consider breaking task into smaller sub-tasks\n"
            "4. Retry with exponential backoff (already implemented)"
        ),
    },
}


def _default_template(category: str) -> dict[str, str]:
    return {
        "title": f"Avoid repeated {category} failures",
        "guidance": (
            f"This skill was auto-generated after {FAILURE_THRESHOLD}+ failures "
            f"in category `{category}`. Review recent failure logs in MongoDB "
            f"activity_logs and adjust the pipeline accordingly."
        ),
    }


# ──────────────────────────────────────────────
# 스킬 파일 생성
# ──────────────────────────────────────────────
def generate_learned_skill(
    db, category: str,
) -> Optional[Path]:
    """
    임계값 초과 시 스킬 파일 자동 생성.
    이미 있으면 업데이트, 없으면 신규.
    """
    try:
        count = count_recent_failures(db, category)
        if count < FAILURE_THRESHOLD:
            log.debug("Category %s: %d failures (threshold %d) — no skill",
                      category, count, FAILURE_THRESHOLD)
            return None

        samples = get_recent_failure_samples(db, category, limit=5)
        template = SKILL_TEMPLATES.get(category, _default_template(category))

        LEARNED_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        skill_path = LEARNED_SKILLS_DIR / f"auto_{category}.md"

        content = _render_skill(category, template, count, samples)
        skill_path.write_text(content, encoding="utf-8")

        log.info("📚 Learned skill %s → %s (%d occurrences)",
                 category, skill_path, count)
        return skill_path
    except Exception:
        log.exception("generate_learned_skill 실패")
        return None


def _render_skill(
    category: str, template: dict[str, str],
    count: int, samples: list[dict[str, Any]],
) -> str:
    """스킬 Markdown 렌더링"""
    task_ids = [s.get("task_id", "?")[:8] for s in samples]
    first_seen = min((s.get("timestamp") for s in samples), default=None)
    first_seen_str = first_seen.isoformat() if first_seen else "?"

    sample_snippets = "\n".join(
        f"- `{s.get('task_id', '?')[:8]}` ({s.get('timestamp').isoformat()[:19] if s.get('timestamp') else '?'}): "
        f"{(s.get('details') or '')[:150]}"
        for s in samples[:3]
    )

    return f"""---
name: auto_{category}
description: Auto-learned pattern from {count} repeated failures in category `{category}`
type: learned
auto_generated: true
category: {category}
occurrences: {count}
first_seen: {first_seen_str}
updated: {datetime.now(timezone.utc).isoformat()}
---

# 🧠 Learned Skill: {template['title']}

## Context

This skill was **automatically generated** by Hermes after detecting **{count}** failures in category `{category}` over the last {LOOKBACK_HOURS} hours. When similar situations arise, agents should follow the guidance below to avoid repeating the failure.

## Guidance

{template['guidance']}

## Recent failures referenced

{sample_snippets or '(no samples available)'}

## How this skill is used

Hermes pre-loads this skill at the start of each agent invocation relevant to category `{category}`. The guidance is added to the agent's context window.

This skill auto-updates when new failures are recorded. Delete the file to reset if the pattern no longer applies.

---

*Auto-generated by failure_learning.py. Review and promote to permanent skill if useful.*
"""


# ──────────────────────────────────────────────
# 스킬 로드 (에이전트 프롬프트에 주입)
# ──────────────────────────────────────────────
def load_learned_skills_text() -> str:
    """
    모든 학습 스킬을 한 덩어리 텍스트로 반환.
    에이전트 프롬프트 상단에 주입 가능.
    """
    if not LEARNED_SKILLS_DIR.is_dir():
        return ""
    parts: list[str] = []
    for skill_file in sorted(LEARNED_SKILLS_DIR.glob("auto_*.md")):
        try:
            content = skill_file.read_text(encoding="utf-8")
            # Front matter 건너뛰고 본문만 추출
            if content.startswith("---"):
                _, _, body = content.partition("---\n")
                _, _, body = body.partition("---\n")
                parts.append(body.strip())
            else:
                parts.append(content)
        except Exception:
            log.exception("스킬 로드 실패: %s", skill_file)

    if not parts:
        return ""
    header = (
        "# 🧠 LEARNED PATTERNS (auto-generated from past failures)\n"
        "Follow these guidelines to avoid repeated mistakes.\n\n"
    )
    return header + "\n\n---\n\n".join(parts) + "\n\n---\n\n"


def list_learned_skills() -> list[dict[str, Any]]:
    """현재 등록된 학습 스킬 메타 목록"""
    if not LEARNED_SKILLS_DIR.is_dir():
        return []
    result = []
    for f in sorted(LEARNED_SKILLS_DIR.glob("auto_*.md")):
        result.append({
            "file": f.name,
            "category": f.stem.replace("auto_", ""),
            "size": f.stat().st_size,
            "mtime": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    return result
