"""mirror_lookup.py — "이 파일을 고치면 같이 봐야 하는 파일"을 데이터로 알려준다.

왜 필요한가 (실측):
    결제수단 표기 태스크에서 AI 가 프런트만 고치고 backend/src/lib/paymentMethodName.ts 를
    빠뜨렸다. 사람 PR#1819 은 그 파일을 고쳤다.
    이 레포는 같은 개념을 backend 와 front-end 에 **따로** 구현해 둔 곳이 많은데,
    두 구현은 서로 import 하지 않는다 — 그래서 import 그래프로는 안 보인다.
    유일한 실마리는 공유하는 상수값이다. build-mirror-graph.js 가 그걸 그래프로 만들어 뒀다.

무엇을 주나:
    - 짝(mirror partner): 같은 도메인 상수를 상당수 공유하는, 다른 area 의 파일
    - 구멍(gap): 짝인데 한쪽에만 있는 키. razer_* 44개가 프런트에만 있고 백엔드에 없는 게 그 예다.

한계 (알고 쓸 것):
    상수값 기반이라 **값을 공유하지 않는 미러는 못 본다**(로직만 중복된 경우).
    반대로 constants.ts 처럼 잡동사니 파일은 짝이 과다하게 잡힌다 — 그래서 상위 N 개만 준다.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from pymongo import MongoClient

log = logging.getLogger(__name__)

MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "newteam")
COL = "newplay_mirror_edges"


#: 짝으로 인정할 최소 결합도. 낮추면 constants.ts 같은 잡동사니 파일이
#: 무관한 키 90여 개를 끌고 들어와 프롬프트를 오염시킨다(실측).
MIN_COVERAGE = 0.4

#: 검색 상위 몇 개까지를 앵커로 볼지.
#: 실측: 6개를 다 쓰면 하위에 딸려온 잡동사니 파일(constants.ts, 로케일)이
#: 자기 미러 엣지를 끌고 들어와, 푸터·네비 같은 무관한 태스크에도 결제 파일이 붙었다
#: (회귀 9건 중 6건에서 같은 결제 짝이 떴다). 상위만 쓰면 질의 관련성이 유지된다.
ANCHOR_TOP = 4

#: 도메인 키가 이보다 많은 파일은 잡동사니(grab-bag)로 본다.
#: 무엇과도 짝이 되므로 앵커로 쓰면 신호가 아니라 소음이 된다.
GRAB_BAG_KEYS = 60


def partners(paths: list[str], project: str = "webstore",
             per_file: int = 2, max_total: int = 4) -> list[dict[str, Any]]:
    """검색 상위 파일들의 미러 짝을 양방향 구멍이 큰 순으로 돌려준다."""
    if not paths or not MONGO_URI:
        return []
    paths = paths[:ANCHOR_TOP]
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    cli = None
    try:
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        col = cli[DB_NAME][COL]
        for p in paths:
            if len(out) >= max_total:
                break
            cur = (col.find({"project": project, "coverage": {"$gte": MIN_COVERAGE},
                             "$or": [{"a": p}, {"b": p}]})
                   .sort("gapMin", -1).limit(per_file * 3))
            for e in cur:
                me_is_a = e["a"] == p
                other = e["b"] if me_is_a else e["a"]
                # 앵커가 잡동사니면 건너뛴다. 키 100개짜리 파일은 무엇과도 짝이 되므로
                # 그 짝을 보여주는 건 질의와 무관한 파일을 들이미는 것이다.
                if (e.get("aKeys" if me_is_a else "bKeys") or 0) > GRAB_BAG_KEYS:
                    continue
                key = tuple(sorted((p, other)))
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "file": p,
                    "partner": other,
                    "shared": e.get("sharedCount", 0),
                    "coverage": e.get("coverage", 0),
                    # 상대에만 있는 키 = 내가 고칠 때 상대에 없어서 생기는 구멍
                    "only_partner": (e.get("onlyB") if me_is_a else e.get("onlyA")) or [],
                    "only_partner_count": (e.get("onlyBCount") if me_is_a else e.get("onlyACount")) or 0,
                    "only_me": (e.get("onlyA") if me_is_a else e.get("onlyB")) or [],
                    "only_me_count": (e.get("onlyACount") if me_is_a else e.get("onlyBCount")) or 0,
                    "gap_min": e.get("gapMin", 0),
                })
                if len(out) >= max_total:
                    break
    except Exception as e:  # noqa: BLE001
        log.warning("미러 조회 실패(무시): %s: %s", type(e).__name__, e)
        return []
    finally:
        if cli is not None:
            try:
                cli.close()
            except Exception:  # noqa: BLE001
                pass
    out.sort(key=lambda x: (x["gap_min"], x["shared"]), reverse=True)
    return out


def as_prompt_block(paths: list[str], project: str = "webstore") -> str:
    """코더 프롬프트에 끼울 블록. 짝이 없으면 빈 문자열."""
    rows = partners(paths, project=project)
    if not rows:
        return ""
    lines = [
        "## 같이 봐야 하는 파일 (미러 표면)",
        "",
        "이 레포는 같은 개념이 backend 와 front-end 에 따로 구현돼 있고 서로 import 하지 않는다.",
        "아래는 **공유하는 상수값**으로 찾은 짝이다. 한쪽만 고치면 절반만 고친 것이 된다.",
        "",
    ]
    for r in rows:
        lines.append(f"- `{r['file']}`")
        lines.append(f"  ↔ `{r['partner']}`  (상수 {r['shared']}개 공유, 결합도 {r['coverage']})")
        if r["only_partner_count"]:
            ex = ", ".join(r["only_partner"][:8])
            lines.append(f"  · 짝에만 있고 이쪽엔 없는 값 {r['only_partner_count']}개: {ex}")
        if r["only_me_count"]:
            ex = ", ".join(r["only_me"][:8])
            lines.append(f"  · 이쪽에만 있고 짝엔 없는 값 {r['only_me_count']}개: {ex}")
        lines.append("")
    lines.append("이 목록은 상수값 일치로 기계적으로 뽑은 것이라 **후보**다. 관련 없으면 무시해도 된다.")
    lines.append("다만 영향 범위 표를 쓸 때 여기 나온 짝을 한 번은 확인하고 판단 근거를 적어라.")
    return "\n".join(lines)
