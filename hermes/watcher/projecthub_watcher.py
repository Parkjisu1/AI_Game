"""
ProjectHub Watcher — MongoDB Change Streams 기반 작업 감지

역할:
  - aigame.pixelforge_tasks 컬렉션을 실시간 구독
  - assignee="hermes"인 작업의 생성/업데이트 감지
  - 감지된 작업을 컨텍스트 조립 → 실행기로 전달
  - 결과를 ProjectHub task에 status/comment로 반영

운영:
  - systemd 서비스로 24/7 가동 (systemd/projecthub-watcher.service)
  - 재연결 로직 내장 (Change Stream 끊겨도 자동 복구)
  - Graceful shutdown (SIGTERM 처리)
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Iterator

# .env 자동 로드 (특수문자 안전)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass  # dotenv 없으면 환경변수에 의존

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from context_builder import build_context
from projecthub_writer import ProjectHubWriter
from task_router import route_task
from hermes_executor import execute_task

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "aigame")
TASKS_COLLECTION = "pixelforge_tasks"

# assignee 값이 이 집합에 속하면 Hermes가 픽업
HERMES_ASSIGNEES = {
    name.strip().lower()
    for name in os.environ.get("HERMES_ASSIGNEE_NAMES", "hermes,Hermes,헤르메스,hermes-bot").split(",")
    if name.strip()
}

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("projecthub-watcher")

# ──────────────────────────────────────────────
# Graceful shutdown
# ──────────────────────────────────────────────
_shutdown_requested = False


def _handle_signal(signum: int, frame: Any) -> None:
    global _shutdown_requested
    log.info("Signal %d received, shutting down gracefully...", signum)
    _shutdown_requested = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ──────────────────────────────────────────────
# Change Stream 파이프라인
# ──────────────────────────────────────────────
def _build_pipeline() -> list[dict[str, Any]]:
    """
    감지 대상:
      1. 신규 insert — 작업 생성 즉시 hermes 담당
      2. assignee를 hermes로 변경 (다른 사람 → hermes에 넘김)
      3. hermes 담당 작업에 comments 추가 (사용자 추가 지시)
      4. status를 todo 또는 in_progress로 변경 (재시도/재개 지시)
    """
    return [
        {
            "$match": {
                "$or": [
                    # 1. 신규 insert
                    {
                        "operationType": "insert",
                    },
                    # 2/3/4. update
                    {
                        "operationType": "update",
                    },
                ]
            }
        }
    ]


def _is_hermes_task(task: dict[str, Any]) -> bool:
    """작업이 Hermes 처리 대상인지 판정"""
    assignee = (task.get("assignee") or "").strip().lower()
    return assignee in HERMES_ASSIGNEES


def _is_active_status(task: dict[str, Any]) -> bool:
    """처리 가능한 상태인지 (done 아님)"""
    status = task.get("status", "todo")
    # review는 별도 조건(피드백 감지)에서 처리
    return status in {"todo", "in_progress", "review"}


def _is_user_feedback_on_review(task: dict[str, Any], change: dict[str, Any]) -> bool:
    """
    review 상태에서 사용자 피드백 코멘트가 추가됐는지.

    조건:
    - status == "review"
    - 이번 변경이 comments 필드
    - 마지막 코멘트 작성자가 hermes 계열 아님 (사용자가 남긴 피드백)
    - 마지막 코멘트가 `kind=ask_owner`가 아님 (설명 요청은 재작업 트리거 안 함 — Slack DM 목적 전용)
    """
    if task.get("status") != "review":
        return False
    updated = change.get("updateDescription", {}).get("updatedFields", {})
    if not any(k.startswith("comments") for k in updated.keys()):
        return False
    comments = task.get("comments") or []
    if not comments:
        return False
    last = comments[-1]
    last_author = (last.get("author") or "").strip().lower()
    if last_author in HERMES_ASSIGNEES:
        return False
    # 설명 요청 코멘트는 Slack DM 발송용 — 담당자에게 정보 요청만 하고 재작업하지 않음
    if (last.get("kind") or "") == "ask_owner":
        return False
    # 승인 코멘트는 재작업 트리거 안 함 — "승인 코멘트=rework" 버그 차단 (P2-H).
    # 거짓양성 방지: kind=approval 또는 코멘트 전체가 승인어와 정확히 일치할 때만(지시형은 rework 유지).
    _txt = (last.get("text") or "").strip().lower().rstrip("!.~ ")
    _APPROVE = {"승인", "승인합니다", "승인함", "approve", "approved", "lgtm", "ok", "okay", "오케이", "좋아요", "굿", "good", "merge", "머지"}
    if (last.get("kind") or "") == "approval" or _txt in _APPROVE:
        return False
    return True


# ──────────────────────────────────────────────
# 이벤트 처리
# ──────────────────────────────────────────────
def _dispatch_event(change: dict[str, Any], writer: ProjectHubWriter) -> None:
    """
    Change Stream 이벤트를 받아서 Hermes 처리로 분기.
    실패는 로깅만 하고 계속 진행 (watcher가 죽으면 안 됨).
    """
    op = change.get("operationType")
    task = change.get("fullDocument")

    if not task:
        # update인데 fullDocument가 없으면 updateLookup으로 가져와야 함
        # (watch() 옵션에 full_document='updateLookup' 지정됨)
        log.debug("Change without fullDocument, skipping: %s", op)
        return

    task_id = str(task.get("_id"))
    title = (task.get("title") or "")[:60]

    # 필터: Hermes 담당인지
    if not _is_hermes_task(task):
        log.debug("Not a hermes task (assignee=%s): %s", task.get("assignee"), title)
        return

    # ── 결정론적 중단 가드 (LLM 무관) ──────────────────────
    # UI '⛔ 중단' 버튼이 hermes_stopped=true 를 세팅하면, 이 task는
    # 어떤 이벤트(코멘트/상태변경/phase 자동진행)로도 처리되지 않는다.
    # fullDocument는 updateLookup이라 항상 최신값을 반영 → 폭주/재점화 방지.
    # 재개는 '▶️ 재개' 버튼이 hermes_stopped=false + status=todo 로 해제.
    if task.get("hermes_stopped"):
        log.info("  ⛔ STOPPED flag set — skipping all processing: [%s] %s", task_id, title)
        return

    # 필터: 활성 상태인지
    if not _is_active_status(task):
        log.debug("Inactive status (%s): %s", task.get("status"), title)
        return

    log.info("Processing task: [%s] %s (op=%s)", task_id, title, op)

    # update 이벤트일 때, 어떤 필드가 바뀌었는지 확인
    updated_fields = change.get("updateDescription", {}).get("updatedFields", {})
    is_review_feedback = False
    if op == "update":
        # review 상태에서 사용자 피드백(코멘트) 감지 → 재작업 트리거
        if task.get("status") == "review":
            if _is_user_feedback_on_review(task, change):
                log.info("  → USER FEEDBACK on review — triggering rework")
                is_review_feedback = True
            else:
                log.debug("  → review status, no actionable feedback — skipping")
                return
        elif any(k.startswith("comments") for k in updated_fields.keys()):
            _cm = (task.get("comments") or [])
            # self-trigger 차단: hermes 자신이 남긴 코멘트(처리시작/진행/결과)는 재처리 대상 아님.
            # 이 author 가드가 없어 hermes 코멘트가 "new comment"로 잡혀 self-retrigger 스톰을 유발했음.
            if _cm and (_cm[-1].get("author") or "").strip().lower() in HERMES_ASSIGNEES:
                log.debug("  → hermes 자기 코멘트 — self-trigger skip")
                return
            # 설명 요청(kind=ask_owner) 코멘트는 재작업 트리거 안 함 — DM 발송 목적 전용
            if _cm and (_cm[-1].get("kind") or "") == "ask_owner":
                log.debug("  → ask_owner comment — skipping re-processing")
                return
            log.info("  → new comment detected")
        elif "status" in updated_fields:
            # self-trigger 차단: in_progress는 watcher 자신이 처리 시작 시 세팅하는 전이라
            # 사용자 액션이 아님 → 재처리하면 같은 작업이 두 번 돈다.
            if updated_fields.get("status") == "in_progress":
                log.debug("  → hermes 자기 in_progress 전이 — self-trigger skip")
                return
            log.info("  → status changed to %s", updated_fields["status"])
        elif "assignee" in updated_fields:
            log.info("  → re-assigned to hermes")
        elif "hermes_stopped" in updated_fields:
            # ▶️ 재개: hermes_stopped 가 false로 바뀜. status 변화가 없어도(이미 todo였던 경우)
            # 처리를 재개해야 함 — status-only 트리거에 의존하면 no-op PATCH가 묻힘.
            log.info("  → resumed (hermes_stopped cleared)")
        else:
            # 관련 없는 필드 변경이면 무시
            log.debug("  → unrelated field change, skipping")
            return

    # 피드백 재작업 플래그를 태스크에 주입 (컨텍스트에 전달됨)
    if is_review_feedback:
        task["_hermes_is_rework"] = True

    # 실제 처리
    try:
        # 1. 처리 시작 표시
        writer.update_status(task_id, "in_progress")
        writer.add_comment(task_id, "📋 처리 시작합니다...", author="hermes")

        # 2. 컨텍스트 조립 (scoped memory + 관련 MongoDB 문서)
        context = build_context(task)
        log.info("  Context built: memory_files=%d, related_docs=%d",
                 len(context.get("memory_files", [])),
                 len(context.get("related_docs", [])))

        # 3. 라우팅 결정 (어느 도구로 처리할지)
        route = route_task(task, context)
        log.info("  Route: %s", route["action"])

        # 4. 실행
        result = execute_task(task, context, route)

        # 5. 결과 반영
        if result.get("success"):
            writer.add_comment(
                task_id,
                result.get("summary", "완료"),
                author="hermes",
            )
            final_status = result.get("next_status", "review")
            writer.update_status(task_id, final_status)
            log.info("  ✓ Task completed: status=%s", final_status)
            # 진실성 게이트: done으로 ship = 객관적 수용. 리뷰 시점에 보류해둔 학습을
            # 이 시점에 grounded reflect + candidate 패치 승격으로 확정한다.
            if final_status == "done":
                try:
                    from truth_gate import on_objective_acceptance
                    on_objective_acceptance(task_id)
                except Exception:
                    log.exception("on_objective_acceptance failed")
        else:
            writer.add_comment(
                task_id,
                f"⚠️ 실행 실패\n{result.get('error', 'unknown error')}",
                author="hermes",
            )
            writer.update_status(task_id, "review")  # 사람 개입 필요
            log.error("  ✗ Task failed: %s", result.get("error"))

    except Exception as e:
        log.exception("Unhandled error processing task %s", task_id)
        try:
            writer.add_comment(
                task_id,
                f"🚨 시스템 오류: {type(e).__name__}: {e}",
                author="hermes",
            )
            writer.update_status(task_id, "review")
        except Exception:
            log.exception("Failed to report error to task")


# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────
def _catchup_pending_tasks(collection, writer) -> None:
    """
    워처 시작 시, 이미 쌓여있는 Hermes 대기 태스크를 생성 순서대로 처리.

    대상: assignee ∈ HERMES_ASSIGNEES && status == "todo"
    순서: created_at 오름차순 (먼저 들어온 것 먼저)
    상한: 최근 50개 (이보다 많이 쌓였으면 사람이 봐야 하는 상황)

    in_progress 상태는 일부러 제외 — 이전 실행이 도중에 죽었을 수 있어
    자동 재처리가 위험함 (예: PR 이미 생성되었을 수 있음). 사람이 검토 후
    status를 todo로 되돌리거나 review로 옮겨야 함.
    """
    try:
        hermes_names = [name for name in HERMES_ASSIGNEES if name]
        # 대소문자 변형도 포함: 원본 + 타이틀케이스
        name_variants = set()
        for n in hermes_names:
            name_variants.add(n)
            name_variants.add(n.capitalize())
            name_variants.add(n.upper())
        pending = list(
            collection.find({
                "assignee": {"$in": list(name_variants)},
                "status": "todo",
            })
            .sort("created_at", 1)
            .limit(50)
        )
        if not pending:
            log.info("Catch-up: no pending tasks")
            return
        log.info("Catch-up: found %d pending hermes task(s) — processing in creation order", len(pending))
        for task in pending:
            if _shutdown_requested:
                log.info("Catch-up aborted (shutdown requested)")
                return
            fake_change = {"operationType": "insert", "fullDocument": task}
            _dispatch_event(fake_change, writer)
        log.info("Catch-up: complete")
    except Exception:
        log.exception("Catch-up failed (non-fatal, continuing to live stream)")


def watch_forever() -> None:
    """
    Change Stream 구독. 연결 끊기면 자동 재연결 (최대 60초 간격).
    최초 연결 시 그동안 쌓인 todo 태스크를 생성 순서로 catch-up 처리.
    """
    backoff = 1
    max_backoff = 60
    did_catchup = False

    while not _shutdown_requested:
        client = None
        try:
            log.info("Connecting to MongoDB...")
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
            client.admin.command("ping")  # 연결 확인
            log.info("Connected. Watching %s.%s for hermes tasks...",
                     DB_NAME, TASKS_COLLECTION)

            db = client[DB_NAME]
            collection = db[TASKS_COLLECTION]
            writer = ProjectHubWriter(collection)

            # 최초 연결 시에만 catch-up (재연결에서는 스킵 — 중복 처리 방지)
            if not did_catchup:
                _catchup_pending_tasks(collection, writer)
                did_catchup = True

            pipeline = _build_pipeline()
            with collection.watch(pipeline, full_document="updateLookup") as stream:
                backoff = 1  # 성공적으로 연결되면 백오프 리셋
                for change in stream:
                    if _shutdown_requested:
                        break
                    _dispatch_event(change, writer)

        except PyMongoError as e:
            log.warning("MongoDB error: %s. Reconnecting in %ds...", e, backoff)
        except Exception:
            log.exception("Unexpected error in watch loop. Reconnecting in %ds...", backoff)
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

        if not _shutdown_requested:
            # 지수 백오프
            for _ in range(backoff):
                if _shutdown_requested:
                    break
                time.sleep(1)
            backoff = min(backoff * 2, max_backoff)

    log.info("Watcher stopped.")


# ──────────────────────────────────────────────
# 엔트리 포인트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    log.info("ProjectHub Watcher starting (db=%s, collection=%s)",
             DB_NAME, TASKS_COLLECTION)
    log.info("Hermes assignee names: %s", sorted(HERMES_ASSIGNEES))
    try:
        watch_forever()
    except KeyboardInterrupt:
        log.info("Interrupted")
    sys.exit(0)
