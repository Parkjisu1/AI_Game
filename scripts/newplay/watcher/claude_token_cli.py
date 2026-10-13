#!/usr/bin/env python3
"""claude_token_cli.py — 팀원 Claude 계정 토큰 등록/목록/삭제 (서버 PC 에서, 관리자).

팀원이 자기 PC 에서 만든다:
    npm i -g @anthropic-ai/claude-code
    claude setup-token            # 브라우저 로그인 → 장기 토큰 출력 (1회만 표시)
그 토큰을 팀 관리자에게 비밀 경로(DM)로 보내고, 관리자가 서버 PC 의 WSL 에서:
    ~/.hermes-newteam/watcher/venv/bin/python ~/.hermes-newteam/watcher/claude_token_cli.py add <email>
    (프롬프트에 토큰 붙여넣기 — 화면에 안 보임)

Usage:
    claude_token_cli.py add <email>       등록/교체 (프롬프트 입력)
    claude_token_cli.py add _default      팀 공용 토큰 (요청자 토큰이 없을 때 폴백)
    claude_token_cli.py list              등록 계정 + 마지막 검증 결과
    claude_token_cli.py remove <email>
    claude_token_cli.py test <email>      그 토큰으로 `claude -p ping` 1회
"""
from __future__ import annotations

import getpass
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_pool as CP  # noqa: E402


def _ensure_dir() -> None:
    os.makedirs(CP.TOKEN_DIR, mode=0o700, exist_ok=True)
    os.chmod(CP.TOKEN_DIR, 0o700)


def _test(email: str) -> str:
    tok = CP._read(email)
    if not tok:
        return "토큰 없음"
    env = dict(os.environ, CLAUDE_CODE_OAUTH_TOKEN=tok)
    try:
        p = subprocess.run(["claude", "-p", "ping 이라고만 답해", "--model", "claude-sonnet-5"],
                           capture_output=True, text=True, timeout=90, env=env)
        if p.returncode == 0:
            return "OK: " + (p.stdout or "").strip()[:40]
        return "실패: " + ((p.stderr or p.stdout) or "").strip()[:120]
    except Exception as e:  # noqa: BLE001
        return f"실패: {type(e).__name__}: {e}"


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    _ensure_dir()
    if cmd == "add":
        email = CP._norm(sys.argv[2])
        if sys.stdin.isatty():
            tok = getpass.getpass(f"{email} 의 Claude 토큰 (claude setup-token 결과): ").strip()
        else:
            # 파이프/스크립트 입력 — getpass 는 /dev/tty 를 기다리므로 여기서는 stdin 을 읽는다
            tok = sys.stdin.readline().strip()
        if not tok or len(tok) < 20:
            print("토큰이 비어 있거나 너무 짧습니다."); return
        p = CP._path(email)
        with open(p, "w", encoding="utf-8") as f:
            f.write(tok + "\n")
        os.chmod(p, 0o600)
        print(f"등록됨: {email}. 검증 중…")
        print("  " + _test(email))
    elif cmd == "list":
        names = CP.accounts() + (["_default"] if CP._read("_default") else [])
        if not names:
            print("등록된 계정 없음 (CLI 의 claude login 자격으로만 동작)")
        for e in names:
            print(f"  {e:<32} {'휴식중' if CP.is_cooling(e) else '가용'}")
    elif cmd == "remove":
        email = CP._norm(sys.argv[2])
        try:
            os.unlink(CP._path(email)); print(f"삭제됨: {email}")
        except OSError:
            print("없음")
    elif cmd == "test":
        print(_test(CP._norm(sys.argv[2])))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
