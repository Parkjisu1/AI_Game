#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seed_granular_roles_v2.py — Hermes 분과 추가 세분화 (granular_v2)
- 2026-06-17. BalloonFlow Assets/1.Scripts 실제 폴더 구조에 근거한 신규 sub_team 추가.
- 기존 role(granular_v1)의 base persona를 읽어 재사용 → "## 전문 분야" 섹션만 교체(일관성).
- `role` 필드 키로 upsert → 멱등(재실행 안전).
- dev/design 만 (art는 role-kind 구조 불규칙이라 별도 패스).
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"]).get_database("aigame")
col = db["hermes_agent_roles"]

# team별 (kind, model, tool) — 기존 스키마와 동일
KINDS = {
    "dev": [("lead", "claude-opus-4-7", "claude"),
            ("coder", "claude-opus-4-7", "claude"),
            ("validator", "validator-agent", "litellm"),
            ("reviewer", "claude-opus-4-7", "claude")],
    "design": [("lead", "claude-opus-4-7", "claude"),
               ("writer", "claude-opus-4-7", "claude"),
               ("validator", "validator-agent", "litellm"),
               ("reviewer", "claude-opus-4-7", "claude")],
    "art": [("prompter", "claude-opus-4-7", "claude"),
            ("validator", "validator-agent", "litellm"),
            ("reviewer", "claude-opus-4-7", "claude")],
}

# 신규 sub_team → 전문 분야 설명 (BalloonFlow 1.Scripts 실제 클래스 근거)
NEW = {
    "dev": {
        "ingame_board":    "보드/타일/그리드 구성, 풍선 식별·배치, 레벨 생성. BoardTileManager·BalloonIdentifier·LevelGenerator 계열.",
        "ingame_rail":     "레일/큐/튜브 경로와 이동·렌더. RailRenderer·RailTileSet·FlexTubePart 계열.",
        "ingame_pop":      "팝/매칭 판정·스코어·클리어율·팝 이펙트풀. PopProcessor·ScoreManager·ClearRateValidator·PopEffectPool 계열.",
        "ingame_balance":  "인게임 난이도/밸런스 수치 연산. BalanceProcessor·DifficultyCalculator 계열. 기획 수치를 코드로.",
        "ui_fx":           "UI 동적 연출/트윈/마스크/코인플라이 등. ButtonScaleEffect·CoinFlyEffect·CutoutMaskUI·AnimatedCoinLabel 계열. 런타임 연출 코드.",
        "ui_title":        "타이틀/스플래시/로딩 화면. UITitle·SplashBackgroundFitter·LoadingText 계열.",
        "outgame_shop":    "상점/상품/IAP 노출·카탈로그. ShopManager·ShopCatalogService·StoreProductExposure·Offer/Package 계열.",
        "outgame_currency":"재화/라이프/부스터 인벤. GemManager·LifeManager·BoosterManager 계열.",
        "outgame_dailyops":"데일리 보상·위닝스트릭·오퍼 스케줄. DailyRewardManager·WinningStreak* 계열.",
        "audio":           "오디오 BGM/SFX/진동. AudioManager·VibrationManager 계열.",
        "ads":             "광고(리워드/전면)·노애드. AdManager·PopupNoAds 계열.",
        "analytics":       "애널리틱스/어트리뷰션/푸시토큰/유저 스냅샷. Firebase·Attribution·FCMToken·UserSnapshot 계열.",
    },
    "design": {
        "content_tutorial": "튜토리얼/온보딩/FTUE 설계. 단계·게이트·연출 흐름.",
        "content_meta":     "메타/수집/도감/업적 설계.",
        "content_event":    "이벤트/시즌/한정 콘텐츠 설계.",
    },
    "art": {
        "art_balloon":  "풍선/게임피스/말풍선 등 인게임 오브젝트 아트. 색·형태 일관성, 팔레트 규격 준수.",
        "art_popup":    "팝업/결과/보상 화면의 일러스트·배경 아트.",
        "art_mapscene": "월드맵/스테이지 배경 씬 아트(메타포 풍경).",
    },
}


def base_persona(team, kind):
    """기존 granular_v1 role의 persona에서 '## 전문 분야' 앞부분(base)만 추출."""
    d = (col.find_one({"team": team, "kind": kind, "seeded": "granular_v1"})
         or col.find_one({"team": team, "kind": kind}))
    if not d or not d.get("persona"):
        return None
    return d["persona"].split("## 전문 분야")[0].rstrip()


added = updated = skipped = 0
for team, subs in NEW.items():
    for sub, specialty in subs.items():
        for kind, model, tool in KINDS[team]:
            base = base_persona(team, kind)
            if base is None:
                print(f"  ! base persona 없음: {team}/{kind} — skip {sub}")
                skipped += 1
                continue
            role = f"{team}_{sub}_{kind}"
            persona = f"{base}\n\n## 전문 분야 ({sub})\n{specialty}"
            doc = {
                "role": role, "team": team, "sub_team": sub, "kind": kind,
                "model": model, "tool": tool, "persona": persona,
                "description": f"{team}/{sub} {kind}", "seeded": "granular_v2",
            }
            r = col.update_one({"role": role}, {"$set": doc}, upsert=True)
            if r.upserted_id is not None:
                added += 1
            else:
                updated += 1

print(f"\n[granular_v2] added={added} updated={updated} skipped={skipped}")
print("dev sub_teams:", sorted(col.distinct("sub_team", {"team": "dev"})))
print("design sub_teams:", sorted(col.distinct("sub_team", {"team": "design"})))
print("total role docs:", col.estimated_document_count())
