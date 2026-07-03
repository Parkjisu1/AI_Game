"""
Slack Inbound — bot 토큰 폴링 기반 양방향 DM (JARVIS 대화 레이어)

왜 폴링인가:
  - ProjectHub 웹은 Tailscale 전용 → Slack Events API(공개 URL 필요) 불가
  - Socket Mode는 xapp 앱레벨 토큰 필요 (미보유)
  - 기존 xoxb bot 토큰의 im:write/im:history만으로 폴링 가능

필요 스코프: im:write(conversations.open으로 채널 확보) + im:history(메시지 읽기).
  im:read는 불필요 — conversations.list 대신 매핑된 사용자별 conversations.open을 쓴다
  (기존 DM 채널을 멱등 반환). 2026-07-03 실토큰 검증: 둘 다 보유, 정상 작동.

지원 명령 (DM 답장):
  상태 / status          — 현재 작업 현황
  브리핑 / briefing       — 지난 24h 브리핑
  승인 / approve [#id]    — 대상 task 승인 (목표 task면 하위 실행 시작, 일반이면 done 확정)
  재시도 / retry [#id]    — 실패/리뷰 task 재작업 트리거
  중단 / stop [#id]       — hermes_stopped=true
  재개 / resume [#id]     — hermes_stopped=false + todo
  작업생성: 제목 | 설명    — 새 hermes task 생성
  #id 자유텍스트          — 해당 task에 코멘트 (rework 피드백으로 전달)
  자유텍스트             — 최근 DM 문맥 task에 코멘트

운영:
  systemd user 서비스 hermes-slack-inbound.service
  상태 저장: aigame.hermes_slack_inbound_state (채널별 last_ts)
  DM 문맥: aigame.hermes_dm_context (executor가 DM 발송 시 기록)
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

from bson import ObjectId
from pymongo import MongoClient

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("slack-inbound")

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "aigame")
POLL_SEC = int(os.environ.get("HERMES_SLACK_INBOUND_POLL_SEC", "7"))
TASK_URL = "https://aimed.tailf6f809.ts.net/tasks"

APPROVE_WORDS = {"승인", "승인합니다", "승인함", "approve", "approved", "lgtm", "ok", "okay", "오케이", "좋아요", "굿", "good", "merge", "머지"}
RETRY_WORDS = {"재시도", "retry", "다시", "다시해줘", "재실행"}
STOP_WORDS = {"중단", "stop", "그만", "멈춰"}
RESUME_WORDS = {"재개", "resume", "계속"}
STATUS_WORDS = {"상태", "status", "현황"}
BRIEF_WORDS = {"브리핑", "briefing", "리포트", "report", "요약"}
HELP_WORDS = {"help", "도움", "도움말", "명령어", "?"}

_shutdown = False


def _sig(signum, frame):
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGTERM, _sig)
signal.signal(signal.SIGINT, _sig)


# ──────────────────────────────────────────────
# Slack API (urllib, 의존성 0)
# ──────────────────────────────────────────────
class SlackAPI:
    def __init__(self, token: str) -> None:
        self.token = token

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        req = urllib.request.Request(
            f"https://slack.com/api/{method}",
            data=json.dumps(params).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8",
                     "Authorization": f"Bearer {self.token}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def dm(self, channel: str, text: str) -> None:
        try:
            self.call("chat.postMessage", channel=channel, text=text)
        except Exception:
            log.exception("dm send failed")


# ──────────────────────────────────────────────
# 메인 데몬
# ──────────────────────────────────────────────
class InboundPoller:
    def __init__(self) -> None:
        self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
        self.db = self.client[DB_NAME]
        self.tasks = self.db["pixelforge_tasks"]
        self.state = self.db["hermes_slack_inbound_state"]
        self.dm_ctx = self.db["hermes_dm_context"]
        self.slack: Optional[SlackAPI] = None
        self.bot_user_id = ""
        self.user_map: dict[str, dict[str, str]] = {}  # slack_user_id → {assignee, email}
        self._settings_loaded_at = 0.0
        self._channels: list[dict[str, str]] = []      # [{id, user}]
        self._channels_loaded_at = 0.0
        self._scope_warned_at = 0.0

    # ── 설정/채널 로드 ─────────────────────────
    def _load_settings(self) -> bool:
        if time.time() - self._settings_loaded_at < 300 and self.slack:
            return True
        doc = self.db["projecthub_settings"].find_one({"key": "current"}) or {}
        st = doc.get("settings") or {}
        token = st.get("slack_bot_token", "")
        if not token:
            log.warning("slack_bot_token 없음 — 대기")
            return False
        self.slack = SlackAPI(token)
        self.user_map = {
            w["slack_user_id"]: {"assignee": w.get("assignee") or "", "email": (w.get("email") or "").lower()}
            for w in (st.get("slack_assignee_webhooks") or [])
            if w.get("slack_user_id") and w.get("email")  # 사람만 (hermes 항목은 email 없음)
        }
        if not self.bot_user_id:
            try:
                auth = self.slack.call("auth.test")
                self.bot_user_id = auth.get("user_id", "")
            except Exception:
                log.exception("auth.test failed")
                return False
        self._settings_loaded_at = time.time()
        return True

    def _load_channels(self) -> bool:
        """
        매핑된 사용자별 IM 채널 확보 (10분 캐시).
        conversations.list(im:read 필요) 대신 conversations.open(im:write, 이미 보유)으로
        기존 DM 채널 id를 멱등하게 얻는다 — 추가 스코프 불필요.
        """
        if time.time() - self._channels_loaded_at < 600 and self._channels:
            return True
        channels: list[dict[str, str]] = []
        for uid in self.user_map:
            try:
                r = self.slack.call("conversations.open", users=uid)
            except Exception:
                log.exception("conversations.open failed: %s", uid)
                continue
            if r.get("ok") and (r.get("channel") or {}).get("id"):
                channels.append({"id": r["channel"]["id"], "user": uid})
            elif r.get("error") == "missing_scope":
                log.warning("conversations.open missing_scope (needed=%s) — 대기", r.get("needed"))
                self._warn_scope_once()
                return False
            else:
                log.warning("conversations.open error(%s): %s", uid, r.get("error"))
        if not channels:
            log.warning("확보된 IM 채널 없음")
            return False
        self._channels = channels
        self._channels_loaded_at = time.time()
        log.info("IM 채널 %d개 확보 (conversations.open, 매핑 사용자 %d명)",
                 len(channels), len(self.user_map))
        return True

    def _warn_scope_once(self) -> None:
        """스코프 누락 안내 — 24h에 1번만, 박지수에게 (outbound DM은 스코프 무관하게 동작)."""
        if time.time() - self._scope_warned_at < 86400:
            return
        meta = self.state.find_one({"_id": "_meta"}) or {}
        last = meta.get("scope_warned_at", 0)
        if time.time() - last < 86400:
            self._scope_warned_at = last
            return
        admin = next((uid for uid, m in self.user_map.items()
                      if m["email"] == "jisu.park@gameberry.co.kr"), None)
        if admin and self.slack:
            self.slack.dm(admin,
                "⚙️ *Slack 양방향 설정 필요*\n"
                "Hermes DM 답장 기능에 bot 스코프가 부족합니다 (im:write + im:history 필요).\n"
                "1. https://api.slack.com/apps → 해당 앱 → *OAuth & Permissions*\n"
                "2. Bot Token Scopes에 누락 스코프 추가 → *Reinstall to Workspace*\n"
                "3. 재설치로 토큰이 바뀌었으면 ProjectHub 설정의 bot token도 갱신\n"
                "완료되면 자동으로 작동합니다 (재시작 불필요).")
        self._scope_warned_at = time.time()
        self.state.update_one({"_id": "_meta"}, {"$set": {"scope_warned_at": self._scope_warned_at}}, upsert=True)

    # ── 폴링 ──────────────────────────────────
    def poll_once(self) -> None:
        if not self._load_settings() or not self._load_channels():
            return
        for ch in self._channels:
            try:
                self._poll_channel(ch["id"], ch["user"])
            except Exception:
                log.exception("channel poll failed: %s", ch["id"])
        # 정상 폴링 신호 — executor의 DM 문구가 "답장 가능"으로 자동 전환됨
        try:
            self.state.update_one({"_id": "_meta"},
                                  {"$set": {"last_ok_ts": time.time()}}, upsert=True)
        except Exception:
            pass

    def _poll_channel(self, channel: str, slack_user: str) -> None:
        st = self.state.find_one({"_id": channel})
        last_ts = (st or {}).get("last_ts")
        r = self.slack.call("conversations.history", channel=channel,
                            oldest=last_ts or "0", limit=20, inclusive=False)
        if not r.get("ok"):
            log.warning("history error %s: %s", channel, r.get("error"))
            return
        msgs = sorted(r.get("messages", []), key=lambda m: float(m.get("ts", "0")))
        if last_ts is None:
            # 첫 가동: 과거 메시지 리플레이 방지 — 커서만 저장
            newest = msgs[-1]["ts"] if msgs else "0"
            self.state.update_one({"_id": channel}, {"$set": {"last_ts": newest}}, upsert=True)
            return
        for m in msgs:
            ts = m.get("ts", "0")
            self.state.update_one({"_id": channel}, {"$set": {"last_ts": ts}}, upsert=True)
            if m.get("user") != slack_user or m.get("subtype") or m.get("bot_id"):
                continue  # 봇 자신/시스템 메시지 스킵
            text = (m.get("text") or "").strip()
            if not text:
                continue
            log.info("DM from %s: %s", self.user_map[slack_user]["assignee"], text[:80])
            try:
                self._handle(channel, slack_user, text)
            except Exception:
                log.exception("handle failed")
                self.slack.dm(channel, "⚠️ 처리 중 오류가 발생했습니다. 로그를 확인해주세요.")

    # ── 명령 처리 ──────────────────────────────
    def _handle(self, channel: str, slack_user: str, text: str) -> None:
        user = self.user_map[slack_user]
        norm = text.strip().lower().rstrip("!.~ ")

        # 태스크 참조 추출 (#abcd1234)
        ref_match = re.search(r"#([0-9a-f]{8})", norm)
        ref_id = ref_match.group(1) if ref_match else None
        body = re.sub(r"#[0-9a-f]{8}", "", text).strip()
        norm_body = body.lower().rstrip("!.~ ")

        if norm in STATUS_WORDS:
            from hermes_briefing import build_status_text
            self.slack.dm(channel, build_status_text())
            return
        if norm in BRIEF_WORDS:
            from hermes_briefing import build_briefing_text
            self.slack.dm(channel, build_briefing_text(hours=24))
            return
        if norm in HELP_WORDS:
            self.slack.dm(channel, self._help_text())
            return
        if text.startswith(("작업생성:", "작업 생성:", "task:")):
            self._create_task(channel, user, text.split(":", 1)[1])
            return

        # 이하 명령은 대상 task 필요
        if norm_body in APPROVE_WORDS or norm in APPROVE_WORDS:
            self._approve(channel, slack_user, user, ref_id)
            return
        if norm_body in RETRY_WORDS or norm in RETRY_WORDS:
            self._simple_comment_cmd(channel, slack_user, user, ref_id, "재시도",
                                     "🔁 재시도를 요청했습니다")
            return
        if norm_body in STOP_WORDS or norm in STOP_WORDS:
            self._stop_resume(channel, slack_user, user, ref_id, stop=True)
            return
        if norm_body in RESUME_WORDS or norm in RESUME_WORDS:
            self._stop_resume(channel, slack_user, user, ref_id, stop=False)
            return

        # 자유 텍스트 → 코멘트
        task = self._resolve_task(slack_user, user, ref_id)
        if task is None:
            self.slack.dm(channel, "🤔 어떤 작업에 대한 말씀인지 못 찾았어요. `#작업id`를 붙이거나 `도움`을 입력해주세요.")
            return
        self._add_comment(task["_id"], body or text, user["assignee"])
        self.slack.dm(channel,
                      f"💬 `{(task.get('title') or '')[:40]}` 에 코멘트로 전달했습니다."
                      + (" (리뷰 상태라 재작업이 시작될 수 있어요)" if task.get("status") == "review" else ""))

    # ── 대상 task 결정 ─────────────────────────
    # 안전 원칙: 전역 폴백 금지 — 문맥이 없으면 남의 task에 승인/중단이 잘못 꽂힐 수 있다.
    # 허용 순서: 명시 #id → 최근 DM 문맥 → 본인이 만든 최근 review task. 없으면 None(되물음).
    def _resolve_task(self, slack_user: str, user: dict[str, str], ref_id: Optional[str]) -> Optional[dict]:
        if ref_id:
            for t in self.tasks.find({}, {"title": 1, "status": 1, "goal_children": 1,
                                          "created_by_email": 1}).sort("updated_at", -1).limit(300):
                if str(t["_id"]).endswith(ref_id):
                    return t
            return None
        # 1) 최근 DM 문맥 (executor가 기록)
        ctx = self.dm_ctx.find_one({"slack_user_id": slack_user}, sort=[("ts", -1)])
        if ctx and ctx.get("task_id"):
            try:
                t = self.tasks.find_one({"_id": ObjectId(str(ctx["task_id"]))})
                if t:
                    return t
            except Exception:
                pass
        # 2) 이 사용자가 만든 가장 최근 review task
        return self.tasks.find_one({"status": "review", "created_by_email": user["email"]},
                                   sort=[("updated_at", -1)])

    # ── 액션들 ─────────────────────────────────
    def _approve(self, channel: str, slack_user: str, user: dict, ref_id: Optional[str]) -> None:
        task = self._resolve_task(slack_user, user, ref_id)
        if task is None:
            self.slack.dm(channel, "🤔 승인할 작업을 못 찾았어요. `승인 #작업id` 형식으로 지정해주세요.")
            return
        title = (task.get("title") or "")[:50]
        # 목표 부모면 → 하위 실행 시작
        if task.get("goal_children"):
            import goal_chain
            started = goal_chain.on_goal_approved(task)
            self.slack.dm(channel, f"🚀 목표 승인 — `{title}` 하위 작업 실행을 시작합니다."
                          if started else f"⚠️ `{title}` — 시작할 하위 작업이 없습니다 (이미 실행 중이거나 완료).")
            return
        # 일반 task → 승인 코멘트(kind=approval, rework 트리거 안 됨) + done 확정
        now = datetime.now(timezone.utc).isoformat()
        self.tasks.update_one(
            {"_id": task["_id"]},
            {"$push": {"comments": {"id": str(ObjectId()), "text": "승인 (Slack)",
                                    "author": user["assignee"], "kind": "approval",
                                    "created_at": now}},
             "$set": {"status": "done", "updated_at": now}},
        )
        # 진실성 게이트: 객관적 수용 시점 학습 확정
        try:
            from truth_gate import on_objective_acceptance
            on_objective_acceptance(str(task["_id"]))
        except Exception:
            log.debug("truth_gate acceptance failed (non-fatal)", exc_info=True)
        # 목표 하위 task면 체인 진행
        try:
            import goal_chain
            fresh = self.tasks.find_one({"_id": task["_id"]})
            if fresh:
                goal_chain.on_task_done(fresh)
        except Exception:
            log.debug("goal chain on approve failed", exc_info=True)
        self.slack.dm(channel, f"✅ `{title}` 승인 완료 → done 처리했습니다.")

    def _simple_comment_cmd(self, channel: str, slack_user: str, user: dict,
                            ref_id: Optional[str], comment: str, ack: str) -> None:
        task = self._resolve_task(slack_user, user, ref_id)
        if task is None:
            self.slack.dm(channel, "🤔 대상 작업을 못 찾았어요. `#작업id`를 붙여주세요.")
            return
        self._add_comment(task["_id"], comment, user["assignee"])
        self.slack.dm(channel, f"{ack}: `{(task.get('title') or '')[:40]}`")

    def _stop_resume(self, channel: str, slack_user: str, user: dict,
                     ref_id: Optional[str], stop: bool) -> None:
        task = self._resolve_task(slack_user, user, ref_id)
        if task is None:
            self.slack.dm(channel, "🤔 대상 작업을 못 찾았어요. `중단 #작업id` 형식으로 지정해주세요.")
            return
        now = datetime.now(timezone.utc).isoformat()
        if stop:
            self.tasks.update_one({"_id": task["_id"]},
                                  {"$set": {"hermes_stopped": True, "updated_at": now}})
            self.slack.dm(channel, f"⛔ `{(task.get('title') or '')[:40]}` 중단했습니다.")
        else:
            self.tasks.update_one({"_id": task["_id"]},
                                  {"$set": {"hermes_stopped": False, "status": "todo", "updated_at": now}})
            self.slack.dm(channel, f"▶️ `{(task.get('title') or '')[:40]}` 재개했습니다.")

    def _create_task(self, channel: str, user: dict, payload: str) -> None:
        parts = [p.strip() for p in payload.split("|", 1)]
        title = parts[0][:120]
        desc = parts[1] if len(parts) > 1 else ""
        if not title:
            self.slack.dm(channel, "형식: `작업생성: 제목 | 설명`")
            return
        now = datetime.now(timezone.utc).isoformat()
        res = self.tasks.insert_one({
            "title": title, "description": desc,
            "assignee": "hermes", "status": "todo", "priority": "medium",
            "created_by_email": user["email"], "created_via": "slack_dm",
            "comments": [], "created_at": now, "updated_at": now,
        })
        self.slack.dm(channel, f"📝 작업 생성 완료: `#{str(res.inserted_id)[-8:]}` {title}\n→ {TASK_URL}")

    def _add_comment(self, task_id: Any, text: str, author: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.tasks.update_one(
            {"_id": task_id},
            {"$push": {"comments": {"id": str(ObjectId()), "text": text,
                                    "author": author, "created_at": now}},
             "$set": {"updated_at": now}},
        )

    @staticmethod
    def _help_text() -> str:
        return (
            "🤖 *Hermes DM 명령*\n"
            "• `상태` — 현재 작업 현황\n"
            "• `브리핑` — 지난 24h 요약\n"
            "• `승인 [#id]` — 작업 승인 (목표면 하위 실행 시작)\n"
            "• `재시도 [#id]` — 재작업 트리거\n"
            "• `중단 #id` / `재개 #id`\n"
            "• `작업생성: 제목 | 설명`\n"
            "• `#id 자유텍스트` — 해당 작업에 코멘트\n"
            "• 자유텍스트 — 최근 알림받은 작업에 코멘트"
        )


def main() -> None:
    log.info("Slack Inbound Poller 시작 (poll=%ds)", POLL_SEC)
    poller = InboundPoller()
    while not _shutdown:
        try:
            poller.poll_once()
        except Exception:
            log.exception("poll_once failed")
        for _ in range(POLL_SEC):
            if _shutdown:
                break
            time.sleep(1)
    log.info("Slack Inbound Poller 종료")


if __name__ == "__main__":
    main()
