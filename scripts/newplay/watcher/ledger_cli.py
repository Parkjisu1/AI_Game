#!/usr/bin/env python3
"""ledger_cli.py — 변경 원장의 CLI 얼굴. 웹 API 가 이걸 호출한다.

웹(Next.js)과 원장(Python)이 다른 런타임이라 프로세스 경계로 잇는다.
미리보기 빌드(preview-build.sh)도 같은 방식이라 구조가 일관된다.

**항상 JSON 한 덩어리만 stdout 에 낸다.** 호출하는 쪽이 파싱해야 하므로
로그·경고가 섞이면 안 된다(그래서 logging 을 끈다).

Usage:
    ledger_cli.py check  <taskId>
    ledger_cli.py apply  <taskId> <actorEmail>
    ledger_cli.py revert <commit> <actorEmail>
    ledger_cli.py history
    ledger_cli.py platform-{check-raw|deploy-raw|rollback|history} …   플랫폼 자신
    ledger_cli.py watcher-{check-raw|deploy-raw|rollback|history} …    AI 워처
"""
from __future__ import annotations

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# .env 를 직접 읽는다 — systemd 가 아니라 웹서버가 호출하므로 환경이 상속되지 않는다.
_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV):
    for line in open(_ENV, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

logging.disable(logging.CRITICAL)   # stdout 은 JSON 전용이다

import change_ledger as CL  # noqa: E402


def _task(task_id: str):
    from bson import ObjectId
    from pymongo import MongoClient
    cli = MongoClient(CL.MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        return cli[CL.DB_NAME]["pixelforge_tasks"].find_one({"_id": ObjectId(task_id)})
    finally:
        cli.close()


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, default=str))


def _arg(i: int, what: str) -> str:
    """인수를 꺼낸다. 없으면 IndexError 대신 무엇이 필요한지 말해 준다(사람·AI 둘 다 이 CLI 를 손으로 쓴다)."""
    if len(sys.argv) <= i:
        _out({"ok": False, "reason": f"인수가 부족합니다 — {what} 을(를) 주세요. 자세한 사용법은 ledger_cli.py 맨 위 Usage 참고"})
        raise SystemExit(2)
    return sys.argv[i]


def main() -> None:
    if len(sys.argv) < 2:
        _out({"ok": False, "reason": "명령이 없습니다"})
        return
    cmd = sys.argv[1]

    if cmd == "history":
        _out({"ok": True, "items": CL.history(40)})
        return

    if cmd in ("check", "apply"):
        task_id = _arg(2, "작업 ID")
        t = _task(task_id)
        if not t:
            _out({"ok": False, "reason": "작업을 찾을 수 없습니다"})
            return
        patch = str(t.get("proposed_patch") or "")
        if not patch:
            _out({"ok": False, "reason": "이 작업에는 적용할 수정안이 없습니다"})
            return

        if cmd == "check":
            _out({**CL.dry_run(patch, task_id), "title": t.get("title", "")})
            return

        actor = sys.argv[3] if len(sys.argv) > 3 else "unknown"
        res = CL.apply_change(patch, task_id, t.get("title", ""), actor)
        if res.get("ok") and res.get("conflicts"):
            res["notified"] = CL.notify_conflicts(task_id, t.get("title", ""),
                                                  res["conflicts"], actor)
        _out(res)
        return

    if cmd == "revert":
        commit = _arg(2, "되돌릴 커밋")
        actor = sys.argv[3] if len(sys.argv) > 3 else "unknown"
        _out(CL.revert_change(commit, actor))
        return

    # ── 플랫폼(ProjectHub 자신) 대상.
    # webstore 와 분리한 이유: 이쪽은 적용이 곧 배포라 실패하면 화면이 죽는다.
    # 위험도가 달라서 호출 경로도 분리해 두는 편이 낫다.
    # `watcher-*` 는 AI 워처(~/.hermes-newteam/watcher) 대상 — 같은 모듈, 다른 프로파일.
    # 범위·자동 복구 보장이 같은 코드에서 나오도록 분기만 다르다.
    if cmd.startswith("platform-") or cmd.startswith("watcher-"):
        import platform_deploy as PD

        prof, sub = cmd.split("-", 1)
        P = PD.profile_of(prof)
        if sub == "history":
            _out({"ok": True, "target": P.name, "items": PD.history(40, P)})
            return
        if sub == "rollback":
            _out(PD.rollback_to(_arg(2, "되돌릴 커밋"), sys.argv[3] if len(sys.argv) > 3 else "unknown", P))
            return
        # raw 계열: 태스크가 아니라 **패치 파일**을 직접 받는다.
        # PowerShell CLI 가 사람 손 패치를 올리는 경로다. 태스크 경로와 같은
        # platform_deploy 를 타므로 범위 검사·자동 복구 보장이 동일하다.
        if sub == "check-raw":
            patch = open(_arg(2, "패치 파일 경로"), encoding="utf-8").read()
            _out(PD.dry_run(patch, P))
            return
        if sub == "deploy-raw":
            patch = open(_arg(2, "패치 파일 경로"), encoding="utf-8").read()
            # 분리 실행(detached)으로 넘어온 임시 패치는 여기서 지운다 —
            # 웹 라우트는 응답 후 죽을 수 있어 청소를 맡길 수 없다.
            if os.path.basename(sys.argv[2]).startswith("nph-"):
                try:
                    os.unlink(sys.argv[2])
                except OSError:
                    pass
            title = sys.argv[3] if len(sys.argv) > 3 else "직접 업로드 패치"
            actor = sys.argv[4] if len(sys.argv) > 4 else "unknown"
            _out(PD.deploy(patch, "direct", title, actor, P))
            return
        if sub in ("check", "deploy"):
            task_id = _arg(2, "작업 ID")
            t = _task(task_id)
            if not t:
                _out({"ok": False, "reason": "작업을 찾을 수 없습니다"})
                return
            patch = str(t.get("proposed_patch") or "")
            if not patch:
                _out({"ok": False, "reason": "이 작업에는 적용할 수정안이 없습니다"})
                return
            if sub == "check":
                _out({**PD.dry_run(patch, P), "title": t.get("title", "")})
            else:
                actor = sys.argv[3] if len(sys.argv) > 3 else "unknown"
                _out(PD.deploy(patch, task_id, t.get("title", ""), actor, P))
            return

    _out({"ok": False, "reason": f"알 수 없는 명령: {cmd}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        _out({"ok": False, "reason": f"{type(e).__name__}: {e}"})
