"""claude_pool.py — 팀원 각자의 Claude 계정(구독 토큰)으로 작업을 실행하기 위한 자격 풀.

왜 필요한가:
    NewPlay 팀은 OpenAI 없이 **사람마다 Claude 구독 계정 하나**를 가진다. 서버(워처)는 중앙에서
    작업을 처리하지만, 호출은 **그 작업을 낸 사람의 계정**으로 나가야 한다 — 비용·한도가 그 사람에게
    귀속되고, 한 계정의 5시간/주간 한도에 팀 전체가 걸리지 않는다.

구조:
    ~/.hermes-newteam/claude-tokens/<email>.token   — `claude setup-token` 으로 만든 장기 토큰(평문, 0600)
    ~/.hermes-newteam/claude-tokens/_default.token  — 팀 공용(기본 사용 안 함, NEWPLAY_CLAUDE_DEFAULT=1 일 때만)
    (없으면 ~/.claude 의 `claude login` 자격으로 폴백 — 토큰 없이도 동작은 한다)

선택 규칙 (pick):
    1. 작업을 낸 사람(actor)의 토큰 — 쉬는 중(cooldown)이 아니면
    2. (기본 꺼짐) 다른 팀원 토큰 중 쉬지 않는 것 — 라운드로빈. 개인 계정은 개인 것이라 기본은 빌리지 않는다.
       팀이 합의하면 NEWPLAY_CLAUDE_SHARE=1
    3. (기본 꺼짐) _default.token — 팀 공용. 1인 1계정 원칙이라 기본은 쓰지 않는다. NEWPLAY_CLAUDE_DEFAULT=1
    4. None → CLI 의 로그인 자격 (`claude login` 을 서버에서 했다면)

한도 처리:
    호출 결과에 사용량 한도 문구가 보이면 그 토큰을 NEWPLAY_CLAUDE_COOLDOWN_MIN(기본 30)분 쉬게 하고
    다음 후보로 재시도한다. 어느 계정으로 돌았는지는 세션 로그(account)에 남는다.

보안:
    토큰 파일은 서버 관리자만 읽을 수 있다(0600). 웹으로는 등록하지 않는다 — 세션 탈취가 곧 계정 탈취가
    되기 때문. 등록은 PC 에서 `claude_token_cli.py add <email>` (SSH 있는 팀 관리자).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Optional

log = logging.getLogger("claude-pool")

TOKEN_DIR = os.environ.get("NEWPLAY_CLAUDE_TOKEN_DIR",
                           os.path.expanduser("~/.hermes-newteam/claude-tokens"))
COOLDOWN_SEC = int(os.environ.get("NEWPLAY_CLAUDE_COOLDOWN_MIN", "30")) * 60
SHARE = os.environ.get("NEWPLAY_CLAUDE_SHARE", "0") == "1"
#: 팀 공용 토큰(_default) 사용 여부. 기본 꺼짐 — 1인 1계정 원칙.
DEFAULT_OK = os.environ.get("NEWPLAY_CLAUDE_DEFAULT", "0") == "1"

#: CLI 출력에서 "한도"로 판정하는 문구. 보수적으로 잡는다 — 오탐은 다른 계정으로 한 번 더 도는 것뿐이다.
LIMIT_PATTERNS = re.compile(
    r"(usage limit|hit your limit|rate.?limit|too many requests|\b429\b|limit reached|"
    r"out of (extra )?usage|quota|exceeded)", re.I)

_lock = threading.Lock()
_cooling: dict[str, float] = {}      # email → 쉬는 시간이 끝나는 시각
_rr = 0


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def _path(email: str) -> str:
    return os.path.join(TOKEN_DIR, f"{_norm(email)}.token")


def _read(email: str) -> Optional[str]:
    try:
        with open(_path(email), encoding="utf-8") as f:
            t = f.read().strip()
        return t or None
    except OSError:
        return None


def accounts() -> list[str]:
    """등록된 계정(이메일) 목록. _default 는 제외."""
    try:
        names = sorted(f[:-6] for f in os.listdir(TOKEN_DIR) if f.endswith(".token"))
    except OSError:
        return []
    return [n for n in names if n != "_default"]


def is_cooling(email: str) -> bool:
    with _lock:
        until = _cooling.get(_norm(email), 0)
        if until and until > time.time():
            return True
        _cooling.pop(_norm(email), None)
        return False


def mark_limited(email: str) -> None:
    if not email:
        return
    with _lock:
        _cooling[_norm(email)] = time.time() + COOLDOWN_SEC
    log.warning("Claude 계정 %s 한도 도달 — %d분 휴식", email, COOLDOWN_SEC // 60)


def looks_limited(text: str) -> bool:
    return bool(LIMIT_PATTERNS.search(text or ""))


def candidates(actor: str = "") -> list[tuple[str, Optional[str]]]:
    """(계정, 토큰) 후보를 우선순위대로. 마지막 ("", None) 은 CLI 로그인 폴백."""
    global _rr
    out: list[tuple[str, Optional[str]]] = []
    a = _norm(actor)
    if a and not is_cooling(a):
        t = _read(a)
        if t:
            out.append((a, t))
    if SHARE:
        others = [e for e in accounts() if e != a and not is_cooling(e)]
        if others:
            with _lock:
                _rr = (_rr + 1) % len(others)
                start = _rr
            others = others[start:] + others[:start]
            for e in others:
                t = _read(e)
                if t:
                    out.append((e, t))
    # 팀 공용 토큰(_default)은 기본 꺼짐 — "1인 1계정" 결정(v2 설계서 §13-5).
    # 파일이 남아 있어도 NEWPLAY_CLAUDE_DEFAULT=1 을 켜지 않으면 쓰지 않는다.
    if DEFAULT_OK:
        d = _read("_default")
        if d and not is_cooling("_default"):
            out.append(("_default", d))
    out.append(("", None))
    return out
