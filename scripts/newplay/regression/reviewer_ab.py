#!/usr/bin/env python3
"""reviewer_ab.py — 검수 모델 A/B. 같은 입력에 리뷰어만 바꿔 잰다.

왜 이렇게 재나:
    전체 파이프라인을 돌리면 코더 단계가 매번 달라져서 리뷰어 차이를 분리할 수 없다.
    이미 나온 산출물을 **고정 입력**으로 두고 리뷰어만 교체하면 통제된 비교가 된다.
    지금 검수는 opus 로 158초씩 12회 = 32분을 쓰고 있다. 그 값을 하는지가 질문이다.

라벨(정답)을 어떻게 정했나:
    [자연] 사람 PR·실측으로 답을 아는 것.
      - payment-old : backend 파일이 0개다. 사람 PR#1819 은 backend/src/lib/paymentMethodName.ts
                      를 고쳤다 → 표면 누락 → revise
      - payment-new : backend 9개 + diff + 테스트까지 → approve
      - footer      : Footer.ts + 로케일 + 테스트, 범위가 정확히 맞다 → approve
    [변이] 자연 케이스에 revise 정답이 1건뿐이라 검출력을 못 잰다.
           정답을 아는 **좋은** 산출물을 일부러 망가뜨려 잡는지 본다.
           소프트웨어 테스트의 mutation testing 과 같은 논리다.
      - mut-truncate : 좋은 답의 diff 를 헝크 중간에서 자른다 → git apply 실패 → revise
      - mut-nobackend: 좋은 답에서 backend 언급을 전부 걷어낸다 → 표면 누락 → revise

    총 5건(approve 2 / revise 3). 통계가 아니라 **판별력 점검**이다. 그 이상으로 읽지 말 것.
    특히 5건짜리로 "정확도 80%" 같은 말을 만들면 안 된다.

Usage:
    python3 reviewer_ab.py
    python3 reviewer_ab.py --models claude-opus-5,claude-sonnet-5 --repeat 2
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/home/aimed/.hermes-newteam/watcher")
os.chdir("/home/aimed/.hermes-newteam/watcher")

# claude CLI 는 nvm 밑에 있다. systemd 유닛은 PATH 를 명시하지만 수동 실행은 안 받는다.
_NVM = "/home/aimed/.nvm/versions/node/v20.20.2/bin"
if _NVM not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _NVM + ":" + os.environ.get("PATH", "")

from dotenv import load_dotenv  # noqa: E402

load_dotenv("/home/aimed/.hermes-newteam/watcher/.env")

import logging  # noqa: E402

logging.disable(logging.WARNING)

from pymongo import MongoClient  # noqa: E402

import agent_team  # noqa: E402
import hermes_executor as HE  # noqa: E402

MONGO = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27018/?directConnection=true")
DB = os.environ.get("MONGODB_DB", "newteam")

args = sys.argv[1:]


def _arg(k, d):
    return args[args.index(k) + 1] if k in args else d


MODELS = [m.strip() for m in _arg(
    "--models",
    "claude-opus-5,claude-sonnet-5,claude-haiku-4-5-20251001,gpt-4o").split(",") if m.strip()]
REPEAT = int(_arg("--repeat", "1"))

GOOD = "[재검증] 결제수단 표시명을 유저가 알아보기 쉽게 바꾸기"

# (id, 원본 태스크 제목, 변이함수 | None, 기대 verdict, 왜)
LABELS = [
    ("payment-old", "결제수단(FOREIGN_EASY_PAY 등)을 실제 유저가 알아보기 쉽게 표시 변경",
     None, "revise", "backend 표면 0개 — 사람 PR#1819 은 paymentMethodName.ts 를 고쳤다"),
    ("payment-new", GOOD, None, "approve", "backend 9개 + diff + 테스트, 영향 범위 표까지 갖췄다"),
    ("footer", "스토어 푸터 저작권 연도가 하드코딩이면 현재 연도로 자동 계산되게 바꿔줘",
     None, "approve", "Footer.ts + 로케일 + 테스트, 범위가 정확하다"),
    ("mut-truncate", GOOD, "truncate", "revise", "[변이] diff 를 헝크 중간에서 잘랐다 → git apply 실패"),
    ("mut-nobackend", GOOD, "nobackend", "revise", "[변이] backend 관련 줄을 전부 걷어냈다 → 표면 누락"),
]


def mutate(kind: str, text: str) -> str:
    """정답을 아는 좋은 산출물을 일부러 망가뜨린다."""
    if kind == "truncate":
        i = text.find("```diff")
        if i < 0:
            i = text.find("--- a/")
        # diff 시작 후 900자에서 뚝 자른다. 닫는 ``` 도 없앤다 = 잘린 패치.
        cut = text[: i + 900] if i >= 0 else text[: len(text) // 2]
        return cut + "\n(이하 생략)\n"
    if kind == "nobackend":
        keep = [ln for ln in text.splitlines() if "backend" not in ln.lower()]
        return "\n".join(keep)
    return text


def call_reviewer(model: str, prompt: str, timeout: int = 900):
    t0 = time.time()
    if model.startswith("claude-"):
        ok, out, err = agent_team._call_claude(prompt, timeout, None, model=model)
    else:
        ok, out, err = agent_team._call_litellm(model, prompt, timeout)
    return ok, out, err, time.time() - t0


def main() -> None:
    cli = MongoClient(MONGO, serverSelectionTimeoutMS=10000)
    col = cli[DB]["pixelforge_tasks"]

    cases = []
    for lid, title, mut, expect, why in LABELS:
        t = col.find_one({"title": title})
        if not t or not t.get("deliverable"):
            print(f"  건너뜀 {lid}: 산출물 없음 ({title[:36]})")
            continue
        deliv = str(t["deliverable"])
        if mut:
            deliv = mutate(mut, deliv)
        prompt = HE.REVIEW_PROMPT.format(
            worker=t.get("deliverable_role", "coder"),
            title=t.get("title", ""),
            description=(t.get("description") or "(없음)")[:3000],
            result=deliv[:12000],
            kb="## 관련 코드\n(A/B 비교 — 모든 모델에 동일 조건을 주려고 KB 는 비운다)",
        ) + "\n\n반드시 JSON 객체 하나만 반환한다."
        cases.append({"id": lid, "expect": expect, "why": why, "prompt": prompt,
                      "chars": len(deliv), "mutated": bool(mut)})

    total = len(cases) * len(MODELS) * REPEAT
    print(f"라벨 {len(cases)}건 (approve {sum(1 for c in cases if c['expect']=='approve')} / "
          f"revise {sum(1 for c in cases if c['expect']=='revise')}) · 모델 {len(MODELS)}종 · "
          f"반복 {REPEAT} = 호출 {total}회\n")

    results = []
    for m in MODELS:
        print(f"── {m}")
        for rep in range(REPEAT):
            for c in cases:
                ok, out, err, dur = call_reviewer(m, c["prompt"])
                v, score, issues = "", None, 0
                if ok:
                    j = agent_team._extract_json(out) or {}
                    v = str(j.get("verdict") or "").lower()
                    score = j.get("score")
                    issues = len(j.get("issues") or [])
                hit = (v == c["expect"])
                results.append({"model": m, "case": c["id"], "rep": rep,
                                "expect": c["expect"], "verdict": v, "score": score,
                                "issues": issues, "ok": ok, "hit": hit,
                                "sec": round(dur, 1), "error": (err or "")[:160]})
                print(f"   {'O' if hit else 'X'} {c['id']:<14} 기대={c['expect']:<8} "
                      f"판정={v or '(실패)':<9} 점수={score if score is not None else '-':<5} "
                      f"지적={issues:<2} {dur:5.0f}s {('· ' + err[:60]) if err else ''}")

    print("\n=== 요약 ===")
    print(f"{'모델':<30} {'정답':<8} {'거짓통과':<9} {'거짓반려':<9} {'평균초':<8} 평균지적")
    summary = []
    for m in MODELS:
        rs = [r for r in results if r["model"] == m]
        hits = sum(1 for r in rs if r["hit"])
        # 거짓 통과 = 반려해야 하는데 통과시킴 (가장 비싼 오류)
        fp = sum(1 for r in rs if r["expect"] == "revise" and r["verdict"] == "approve")
        fn = sum(1 for r in rs if r["expect"] == "approve" and r["verdict"] != "approve")
        avg = sum(r["sec"] for r in rs) / max(1, len(rs))
        iss = sum(r["issues"] for r in rs) / max(1, len(rs))
        summary.append({"model": m, "hits": hits, "n": len(rs), "false_approve": fp,
                        "false_revise": fn, "avg_sec": round(avg, 1), "avg_issues": round(iss, 1)})
        print(f"{m:<30} {str(hits)+'/'+str(len(rs)):<8} {fp:<9} {fn:<9} {avg:<8.0f} {iss:.1f}")

    cli[DB]["newplay_regression_runs"].insert_one({
        "run_id": "revab_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "mode": "reviewer_ab", "started_at": datetime.now(timezone.utc).isoformat(),
        "models": MODELS, "repeat": REPEAT, "labels": [c["id"] for c in cases],
        "summary": summary, "results": results,
    })
    print("\n저장됨 → newplay_regression_runs")


if __name__ == "__main__":
    main()
