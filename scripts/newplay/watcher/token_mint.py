#!/usr/bin/env python3
"""token_mint.py — NewPlay Hub API 토큰 발급/폐기.

왜 필요한가:
    플랫폼 API 인증이 구글 로그인 세션(쿠키)뿐이라 브라우저 밖에서는 못 쓴다.
    PowerShell 같은 CLI 에서 쓰려면 토큰이 필요하다.
    SSH 를 주지 않기로 한 설계(격리)를 유지하면서 CLI 작업을 열어 주는 유일한 길이다.

보안 원칙:
    - 토큰 평문은 **발급 순간 한 번만** 출력되고 어디에도 저장되지 않는다.
      DB 에는 sha256 해시만 남는다 — DB 가 새어도 토큰은 안 샌다.
    - 토큰은 이메일에 묶인다. API 는 토큰 → 이메일을 풀어 **그 사람의 권한**으로 판정한다.
      (관리자 여부는 ADMIN_EMAILS 가 정하지, 토큰이 정하지 않는다)
    - 발급·폐기는 이 스크립트(=SSH 있는 사람)만 할 수 있다. 웹에서는 못 만든다 —
      토큰 발급 UI 를 열면 세션 탈취가 곧 영구 토큰 탈취가 된다.

Usage:
    token_mint.py issue  <email> [label]   # 발급 — 평문은 이때 한 번만 보인다
    token_mint.py list                     # 발급 내역 (해시 앞자리만)
    token_mint.py revoke <email>           # 그 사람 토큰 전부 폐기
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sys
from datetime import datetime, timezone

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV):
    for line in open(_ENV, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from pymongo import MongoClient  # noqa: E402

COL = "newplay_api_tokens"


def _col():
    cli = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
    return cli, cli[os.environ.get("MONGODB_DB", "newteam")][COL]


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    cli, col = _col()
    try:
        if cmd == "issue":
            email = sys.argv[2].lower().strip()
            label = sys.argv[3] if len(sys.argv) > 3 else "cli"
            token = "nph_" + secrets.token_urlsafe(32)
            col.insert_one({
                "email": email,
                "hash": hashlib.sha256(token.encode()).hexdigest(),
                "label": label,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            print("발급 완료. 아래 토큰은 지금 한 번만 표시됩니다 — 안전한 경로로 전달하세요.")
            print()
            print("  " + token)
            print()
            print(f"  대상: {email} · 용도: {label}")
            print("  권한은 토큰이 아니라 그 이메일의 등급(허용/관리자)을 따릅니다.")
        elif cmd == "list":
            for d in col.find({}).sort("created_at", -1):
                state = "폐기됨" if d.get("revoked") else "유효"
                print(f"  {d['email']:<30} {d.get('label', ''):<12} {state:<6} "
                      f"{d.get('created_at', '')[:19]}  hash={d['hash'][:12]}…")
        elif cmd == "revoke":
            email = sys.argv[2].lower().strip()
            r = col.update_many({"email": email, "revoked": {"$ne": True}},
                                {"$set": {"revoked": True,
                                          "revoked_at": datetime.now(timezone.utc).isoformat()}})
            print(f"{email}: {r.modified_count}개 폐기")
        else:
            print(__doc__)
    finally:
        cli.close()


if __name__ == "__main__":
    main()
