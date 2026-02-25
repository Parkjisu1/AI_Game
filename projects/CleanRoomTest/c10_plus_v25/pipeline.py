"""
C10+ v2.5 Pipeline
===================
6-phase analysis pipeline with v2.5 enhancements (OCR, Wiki, APK Assets).

Pipeline flow:
  [PRE]  APK Asset Extraction (M4, once per game)
  [P1]   CAPTURE — ADB screenshots via genre capture scripts
  [P1.5] OCR Preprocessing (M2, per screenshot)
  [P2]   VISION — Claude Sonnet per-session analysis
  [P2.5] WIKI Cross-Reference (M3, once per game)
  [P3]   AGGREGATE — Domain-weighted consensus
  [P4]   SPEC — Parameter estimation (32 params)
  [P5]   SCORING — vs Ground Truth (if available)
  [P6]   REPORT — Final summary
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from core import (
    SYS_CFG, log, adb_check_device,
    take_screenshot, tap, swipe, press_back,
    force_stop, launch_game,
    claude_vision, claude_text,
    ocr_extract_numbers, extract_apk_assets, format_asset_data_for_prompt,
    fetch_wiki_data,
    extract_average, extract_sum, extract_param_scores,
)
from genres import (
    GenreBase, GameConfig, CaptureContext, find_game, load_all_genres,
)


# ---------------------------------------------------------------------------
# Output Directory Structure
# ---------------------------------------------------------------------------

def get_output_dir(game_key: str) -> Path:
    return SYS_CFG.base_dir / "output" / game_key


def get_dirs(game_key: str) -> Dict[str, Path]:
    base = get_output_dir(game_key)
    dirs = {
        "sessions":     base / "sessions",
        "ocr_data":     base / "ocr_data",
        "observations": base / "observations",
        "wiki_data":    base / "wiki_data",
        "asset_data":   base / "asset_data",
        "aggregated":   base / "aggregated",
        "specs":        base / "specs",
        "scoring":      base / "scoring",
        "report":       base / "report",
        "ground_truth": base / "ground_truth",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


# ---------------------------------------------------------------------------
# PRE-PHASE: APK Asset Extraction (M4)
# ---------------------------------------------------------------------------

def pre_extract_assets(game: GameConfig, dirs: Dict[str, Path]) -> str:
    """Extract assets from APK if available. Returns formatted text for prompts."""
    if not SYS_CFG.features.get("assets", False):
        return ""

    asset_file = dirs["asset_data"] / "extracted_assets.json"
    if asset_file.exists() and asset_file.stat().st_size > 100:
        log(f"  [ASSETS] Already extracted, loading cache")
        data = json.loads(asset_file.read_text(encoding="utf-8"))
        return format_asset_data_for_prompt(data)

    if not game.apk_path:
        log(f"  [ASSETS] No APK path configured, skipping")
        return ""

    log(f"  [ASSETS] Extracting from {game.apk_path}...")
    data = extract_apk_assets(game.apk_path)
    if data:
        asset_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return format_asset_data_for_prompt(data)
    return ""


# ---------------------------------------------------------------------------
# PHASE 1: CAPTURE
# ---------------------------------------------------------------------------

def phase1_capture(genre: GenreBase, game: GameConfig, dirs: Dict[str, Path]):
    missions = genre.get_missions()
    log("=" * 60)
    log(f"PHASE 1: CAPTURE — {game.name} ({genre.genre_name})")
    log(f"  {len(missions)} specialized sessions")
    log("=" * 60)

    for sid in sorted(missions.keys()):
        mission = missions[sid]
        sdir = dirs["sessions"] / f"session_{sid:02d}"
        existing = list(sdir.glob("*.png")) if sdir.exists() else []
        if len(existing) >= 3:
            log(f"  Session {sid:02d}: {mission.name} — already {len(existing)} shots, skip")
            continue

        sdir.mkdir(parents=True, exist_ok=True)
        log(f"  Session {sid:02d}: {mission.name}")

        # Fresh game state
        force_stop(game.package)
        launch_game(game.package, wait=8)

        # Create capture context
        ctx = CaptureContext(
            game=game, session_dir=sdir,
            tap_fn=tap, swipe_fn=swipe,
            shot_fn=take_screenshot, press_back_fn=press_back,
        )

        # Execute genre-specific capture
        try:
            genre.capture_session(ctx, sid)
            log(f"    -> {len(ctx.shots)} screenshots")
        except Exception as e:
            log(f"    -> ERROR: {e}")

    force_stop(game.package)
    log("Phase 1 complete.\n")


# ---------------------------------------------------------------------------
# PHASE 1.5: OCR Preprocessing (M2)
# ---------------------------------------------------------------------------

def phase1_5_ocr(genre: GenreBase, game: GameConfig, dirs: Dict[str, Path]) -> Dict[str, Dict]:
    """Run OCR on all screenshots. Returns {session_file: {region: value}}."""
    if not SYS_CFG.features.get("ocr", False):
        return {}

    log("=" * 60)
    log("PHASE 1.5: OCR PREPROCESSING (M2)")
    log("=" * 60)

    ocr_regions = genre.get_ocr_regions(game.key)
    if not ocr_regions:
        log("  No OCR regions defined for this game, skipping")
        return {}

    all_ocr = {}
    ocr_cache = dirs["ocr_data"] / "ocr_results.json"
    if ocr_cache.exists():
        all_ocr = json.loads(ocr_cache.read_text(encoding="utf-8"))
        log(f"  Loaded {len(all_ocr)} cached OCR results")

    missions = genre.get_missions()
    new_count = 0
    for sid in sorted(missions.keys()):
        sdir = dirs["sessions"] / f"session_{sid:02d}"
        if not sdir.exists():
            continue
        for img_path in sorted(sdir.glob("*.png")):
            key = f"s{sid:02d}/{img_path.name}"
            if key in all_ocr:
                continue
            result = ocr_extract_numbers(img_path, ocr_regions)
            if result:
                all_ocr[key] = result
                new_count += 1

    if new_count > 0:
        ocr_cache.write_text(json.dumps(all_ocr, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  Extracted {new_count} new OCR results (total: {len(all_ocr)})")
    else:
        log(f"  No new screenshots to OCR")

    log("Phase 1.5 complete.\n")
    return all_ocr


# ---------------------------------------------------------------------------
# PHASE 2: VISION ANALYSIS
# ---------------------------------------------------------------------------

def phase2_vision(genre: GenreBase, game: GameConfig, dirs: Dict[str, Path],
                  ocr_data: Dict = None, asset_text: str = ""):
    missions = genre.get_missions()
    log("=" * 60)
    log(f"PHASE 2: VISION ANALYSIS — {len(missions)} sessions")
    log("=" * 60)

    for sid in sorted(missions.keys()):
        mission = missions[sid]
        obs_file = dirs["observations"] / f"session_{sid:02d}.txt"
        if obs_file.exists() and obs_file.stat().st_size > 100:
            log(f"  Session {sid:02d}: already analyzed, skip")
            continue

        sdir = dirs["sessions"] / f"session_{sid:02d}"
        images = sorted(sdir.glob("*.png")) if sdir.exists() else []
        if not images:
            log(f"  Session {sid:02d}: no screenshots, skip")
            obs_file.write_text("ERROR: No screenshots\n", encoding="utf-8")
            continue

        log(f"  Session {sid:02d}: {mission.name} — {len(images)} images...")

        # Build prompt with genre-specific instructions
        prompt = genre.get_vision_prompt(sid, game.name)

        # Inject OCR data if available
        if ocr_data:
            session_ocr = {k: v for k, v in ocr_data.items() if k.startswith(f"s{sid:02d}/")}
            if session_ocr:
                ocr_text = "\n".join(f"  {k}: {v}" for k, v in session_ocr.items())
                prompt += f"\n\n[OCR 사전 추출 데이터 — 참고용, 정확도 검증 필요]\n{ocr_text}"

        # Inject asset data for relevant sessions (numeric, equipment, gacha)
        if asset_text and sid in [3, 4, 6, 8]:
            prompt += f"\n\n[APK 에셋 데이터 — 배포 데이터에서 추출, 소스코드 아님]\n{asset_text[:5000]}"

        result = claude_vision(prompt, images, timeout=SYS_CFG.claude_vision_timeout)
        obs_file.write_text(result, encoding="utf-8")

        if result.startswith("ERROR"):
            log(f"    -> {result[:80]}")
        else:
            log(f"    -> {len(result)} chars")

    log("Phase 2 complete.\n")


# ---------------------------------------------------------------------------
# PHASE 2.5: WIKI Cross-Reference (M3)
# ---------------------------------------------------------------------------

def phase2_5_wiki(genre: GenreBase, game: GameConfig, dirs: Dict[str, Path]) -> str:
    """Fetch community wiki data. Returns text for aggregation."""
    if not SYS_CFG.features.get("wiki", False):
        return ""

    log("=" * 60)
    log("PHASE 2.5: WIKI CROSS-REFERENCE (M3)")
    log("=" * 60)

    wiki_file = dirs["wiki_data"] / "community_data.txt"
    if wiki_file.exists() and wiki_file.stat().st_size > 100:
        log("  Already fetched, using cache")
        return wiki_file.read_text(encoding="utf-8")

    keywords = genre.get_wiki_keywords(game.key)
    if not keywords:
        log("  No wiki keywords defined, skipping")
        return ""

    log(f"  Searching for community data ({len(keywords)} queries)...")
    result = fetch_wiki_data(game.name, keywords)
    if result:
        wiki_file.write_text(result, encoding="utf-8")
        log(f"  -> {len(result)} chars of community data")
    else:
        log("  -> No community data found")

    log("Phase 2.5 complete.\n")
    return result


# ---------------------------------------------------------------------------
# PHASE 3: AGGREGATION
# ---------------------------------------------------------------------------

def phase3_aggregate(genre: GenreBase, game: GameConfig, dirs: Dict[str, Path],
                     wiki_text: str = "", asset_text: str = ""):
    missions = genre.get_missions()
    weights = genre.get_domain_weights()
    sections = genre.get_aggregation_sections()

    log("=" * 60)
    log("PHASE 3: ENHANCED AGGREGATION (domain-weighted)")
    log("=" * 60)

    agg_file = dirs["aggregated"] / "consensus.txt"
    if agg_file.exists() and agg_file.stat().st_size > 100:
        log("  Already aggregated, skip")
        return

    # Load all observations
    obs_texts = []
    for sid in sorted(missions.keys()):
        obs_file = dirs["observations"] / f"session_{sid:02d}.txt"
        if obs_file.exists():
            text = obs_file.read_text(encoding="utf-8")
            if not text.startswith("ERROR"):
                m = missions[sid]
                obs_texts.append(
                    f"=== 전문가 {sid}: {m.name} (도메인: {m.domain}) ===\n"
                    f"미션: {m.desc}\n\n{text}"
                )

    if not obs_texts:
        log("  No valid observations, skip")
        return

    log(f"  Aggregating {len(obs_texts)} specialist observations...")
    all_obs = "\n\n".join(obs_texts)

    # Build weight description
    weight_desc = "\n".join(
        f"   - {domain} → 전문가 {','.join(str(s) for s in sids)}"
        for domain, sids in weights.items()
    )

    # Build section list
    section_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sections))

    # Genre-specific rules
    extra_rules = genre.get_aggregation_rules()

    prompt = f"""게임 "{game.name}" ({genre.genre_name})에 대한 {len(obs_texts)}명의 전문가 AI 테스터 관찰을 통합하세요.

{all_obs}

"""

    # Add wiki data if available
    if wiki_text:
        prompt += f"""
=== 커뮤니티 공개 데이터 (M3 교차검증용) ===
{wiki_text[:5000]}

"""

    # Add asset data if available
    if asset_text:
        prompt += f"""
=== APK 에셋 데이터 (M4, 소스코드 아님) ===
{asset_text[:5000]}

"""

    prompt += f"""---

통합 규칙 (전문가 도메인 가중치 적용):
1. 도메인 전문성 우선:
{weight_desc}
2. 교차검증: 전문가 1과 2의 독립 플레이스루 비교
3. 전문가 10의 재확인으로 신뢰도 상향
4. 측정 정밀도: 전문가의 구체적 수치 > 대략적 추정
5. OCR 데이터가 있으면 Vision 분석보다 OCR 수치를 우선 채택
6. APK 에셋 데이터가 있으면 최고 신뢰도로 채택 (게임 실제 데이터)
7. 커뮤니티 데이터는 관찰과 일치할 때만 보조 확인으로 활용
{extra_rules}

출력: 다음 섹션으로 구성된 합의 문서
{section_list}

각 항목에 [HIGH]/[MED]/[LOW] 신뢰도 표시.
데이터 소스 명시: (관찰), (OCR), (에셋), (커뮤니티)"""

    result = claude_text(prompt, timeout=SYS_CFG.claude_text_timeout)
    agg_file.write_text(result, encoding="utf-8")

    if result.startswith("ERROR"):
        log(f"  -> {result[:80]}")
    else:
        log(f"  -> {len(result)} chars consensus")

    log("Phase 3 complete.\n")


# ---------------------------------------------------------------------------
# PHASE 4: SPEC GENERATION
# ---------------------------------------------------------------------------

def phase4_spec(genre: GenreBase, game: GameConfig, dirs: Dict[str, Path],
                asset_text: str = ""):
    log("=" * 60)
    log("PHASE 4: SPEC GENERATION (v2.5)")
    log("=" * 60)

    spec_file = dirs["specs"] / f"{game.key}_C10_plus_v25_spec.yaml"
    if spec_file.exists() and spec_file.stat().st_size > 100:
        log("  Already exists, skip")
        return

    agg_file = dirs["aggregated"] / "consensus.txt"
    if not agg_file.exists():
        log("  No aggregated data, skip")
        return

    agg_text = agg_file.read_text(encoding="utf-8")
    params = genre.get_parameters(game.key)

    if not params:
        log("  No parameters defined for this game, skip")
        return

    log(f"  {game.name}: generating C10+ v2.5 spec...")

    prompt = f"""당신은 모바일 게임 밸런스 시트 전문가입니다.

다음은 "{game.name}" ({genre.genre_name})에 대해 10명의 전문가 AI 테스터가 관찰하고,
OCR/에셋추출/커뮤니티 데이터로 보강된 합의 데이터입니다:

{agg_text}

"""
    if asset_text:
        prompt += f"""
추가 참조 — APK 에셋에서 직접 추출된 데이터:
{asset_text[:5000]}

"""

    prompt += f"""---

위 데이터를 사용하여 아래 32개 파라미터를 추정하세요.
[HIGH] 항목은 확정적으로, [MED]는 합리적 추정, [LOW]는 추론.
관찰 불가능한 내부 구조 파라미터는 null로 표시.
에셋 데이터에서 직접 확인된 값은 confidence: confirmed로 표시.

파라미터 목록:
{params}

YAML 형식:
game: "{game.name}"
genre: "{genre.genre_name}"
condition: "C10_plus_v25"
parameters:
  - id: {game.prefix}01
    name: (파라미터명)
    value: (추정값)
    confidence: confirmed/high/medium/low
    source: "데이터 소스 (관찰/OCR/에셋/커뮤니티)"
  ...

반드시 32개 모두 포함."""

    result = claude_text(prompt, timeout=SYS_CFG.claude_text_timeout)
    spec_file.write_text(result, encoding="utf-8")
    log(f"  -> {'ERROR' if result.startswith('ERROR') else f'{len(result)} chars'}")
    log("Phase 4 complete.\n")


# ---------------------------------------------------------------------------
# PHASE 5: SCORING
# ---------------------------------------------------------------------------

def phase5_scoring(genre: GenreBase, game: GameConfig, dirs: Dict[str, Path]):
    log("=" * 60)
    log("PHASE 5: SCORING")
    log("=" * 60)

    score_file = dirs["scoring"] / f"{game.key}_C10_plus_v25_score.yaml"
    if score_file.exists() and score_file.stat().st_size > 100:
        log("  Already scored, skip")
        return

    gt_file = dirs["ground_truth"] / f"{game.key}_ground_truth.yaml"
    spec_file = dirs["specs"] / f"{game.key}_C10_plus_v25_spec.yaml"

    if not spec_file.exists():
        log("  No spec generated, skip")
        return

    spec_text = spec_file.read_text(encoding="utf-8")
    if spec_text.startswith("ERROR"):
        log("  Spec has errors, skip")
        return

    if not gt_file.exists():
        log("  No ground truth available — generating review template instead")
        _generate_review_template(genre, game, dirs, spec_text)
        return

    gt_text = gt_file.read_text(encoding="utf-8")
    params = genre.get_parameters(game.key)

    log(f"  {game.name}: scoring against ground truth...")

    prompt = f"""다음 두 데이터를 비교하여 각 파라미터를 채점하세요.

## Ground Truth
{gt_text}

## Generated Spec (C10+ v2.5)
{spec_text}

## 파라미터 목록 (32개)
{params}

## 채점 기준
- 1.0: Exact (정확 일치)
- 0.7: Close (20% 이내 또는 핵심 맞고 세부 다름)
- 0.4: Partial (방향은 맞으나 수치 오차)
- 0.1: Wrong (완전히 다른 값)
- 0.0: Missing/Null (관찰 불가 또는 미응답)

## 출력
scoring:
  game: "{game.name}"
  genre: "{genre.genre_name}"
  condition: "C10_plus_v25"
  results:
    - id: {game.prefix}01
      name: (파라미터명)
      ground_truth: "(실제값)"
      generated: "(추정값)"
      score: 0.0
      note: "(설명)"
    ...
  summary:
    total: 32
    sum: (합계)
    average: (평균)

32개 모두 채점. sum/average 정확히 계산."""

    result = claude_text(prompt, timeout=SYS_CFG.claude_text_timeout)
    score_file.write_text(result, encoding="utf-8")

    if result.startswith("ERROR"):
        log(f"  -> {result[:80]}")
    else:
        avg = extract_average(result)
        log(f"  -> average: {avg:.3f} ({avg*100:.1f}%)")

    log("Phase 5 complete.\n")


def _generate_review_template(genre: GenreBase, game: GameConfig,
                              dirs: Dict[str, Path], spec_text: str):
    """Generate a review template for game team verification."""
    params = genre.get_parameters(game.key)
    template = f"""# {game.name} C10+ v2.5 분석 결과 검토 요청

> 생성일: {datetime.now().strftime('%Y-%m-%d')}
> 방법론: C10+ v2.5 ({genre.genre_name})
> 분석 조건: 10명 전문 AI 테스터 + OCR + 커뮤니티 데이터 교차검증

---

## 검토 방법

아래 32개 파라미터에 대해 **실제값**을 기입하고 **정확도**를 판정해 주세요.

### 정확도 판정 기준
| 판정 | 점수 | 기준 |
|------|:----:|------|
| 정확 (Exact) | 1.0 | 값이 정확히 일치 |
| 근접 (Close) | 0.7 | 20% 이내 차이 또는 핵심 맞고 세부 다름 |
| 부분 (Partial) | 0.4 | 방향은 맞으나 수치 오차 큼 |
| 오답 (Wrong) | 0.1 | 완전히 다른 값 |
| 누락 (Missing) | 0.0 | null 또는 미응답 |

---

## AI 추정값

{spec_text}

---

## 파라미터 검토 표

{params}

---

## 기입 양식

각 파라미터에 대해:
1. **실제값**: 게임 내부의 실제 값
2. **판정**: 정확/근접/부분/오답/누락
3. **비고**: 차이가 있다면 원인 설명

검토 완료 후 이 파일을 `ground_truth/{game.key}_ground_truth.yaml`로 저장하면
Phase 5를 재실행하여 최종 점수를 산출합니다.
"""

    review_file = dirs["report"] / f"{game.key}_review_template.md"
    review_file.write_text(template, encoding="utf-8")
    log(f"  Review template: {review_file}")


# ---------------------------------------------------------------------------
# PHASE 6: REPORT
# ---------------------------------------------------------------------------

def phase6_report(genre: GenreBase, game: GameConfig, dirs: Dict[str, Path]):
    log("=" * 60)
    log("PHASE 6: REPORT")
    log("=" * 60)

    score_file = dirs["scoring"] / f"{game.key}_C10_plus_v25_score.yaml"
    score = 0.0
    has_score = False
    if score_file.exists():
        text = score_file.read_text(encoding="utf-8")
        score = extract_average(text)
        has_score = score > 0

    # Count sessions and shots
    session_count = 0
    shot_count = 0
    for sdir in sorted((dirs["sessions"]).glob("session_*")):
        shots = list(sdir.glob("*.png"))
        if shots:
            session_count += 1
            shot_count += len(shots)

    # Check which features were used
    has_ocr = (dirs["ocr_data"] / "ocr_results.json").exists()
    has_wiki = (dirs["wiki_data"] / "community_data.txt").exists()
    has_assets = (dirs["asset_data"] / "extracted_assets.json").exists()

    report = f"""# C10+ v2.5 분석 보고서: {game.name}

> 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 장르: {genre.genre_name}
> 방법론: C10+ v2.5 (Enhanced Observation + OCR + Wiki + Assets)

---

## 결과 요약

| 항목 | 값 |
|------|-----|
| 대상 게임 | {game.name} |
| 패키지 | {game.package} |
| 장르 모듈 | {genre.genre_key} |
| 분석 세션 | {session_count}/10 |
| 총 스크린샷 | {shot_count} |
| OCR 전처리 | {'O' if has_ocr else 'X'} |
| 커뮤니티 데이터 | {'O' if has_wiki else 'X'} |
| APK 에셋 추출 | {'O' if has_assets else 'X'} |
"""

    if has_score:
        report += f"""| **정확도** | **{score*100:.1f}%** |

## 정확도 비교

| 조건 | 정확도 | 비고 |
|------|:------:|------|
| C (1인 자유 관찰) | 36.5% | 기준선 |
| C10 (10인 자유 관찰) | 85.0% | 기준선 |
| C10+ v1 (10인 전문, 퍼즐) | 89.5% | 이전 결과 |
| **C10+ v2.5 ({game.name})** | **{score*100:.1f}%** | **본 분석** |
"""
    else:
        report += """| **정확도** | 검토 대기 중 |

> Ground Truth가 제공되지 않아 정확도를 산출할 수 없습니다.
> `report/{game_key}_review_template.md`를 게임 팀에 전달하여 검토를 요청하세요.
""".replace("{game_key}", game.key)

    report += f"""
## 사용된 향상 기능

| 기능 | 상태 | 효과 |
|------|:----:|------|
| v2 미션 재설계 | O | 장르 특화 10개 미션 ({genre.genre_name}) |
| M2: OCR 전처리 | {'O' if has_ocr else 'X'} | 수치 데이터 정밀도 향상 |
| M3: 커뮤니티 데이터 | {'O' if has_wiki else 'X'} | 공개 데이터 교차검증 |
| M4: APK 에셋 추출 | {'O' if has_assets else 'X'} | 설정 데이터 직접 확인 |

## 10명 AI 테스터 역할

| # | 역할 | 도메인 | 장르 특화 |
|---|------|--------|:---------:|
"""
    missions = genre.get_missions()
    for sid in sorted(missions.keys()):
        m = missions[sid]
        report += f"| {sid} | {m.name} | {m.domain} | {'Flex' if m.flex else 'Core'} |\n"

    report += f"""
## 파일 구조

```
output/{game.key}/
├── sessions/          {shot_count} screenshots across {session_count} sessions
├── ocr_data/          OCR extraction results
├── observations/      10 specialist analysis texts
├── wiki_data/         Community cross-reference data
├── asset_data/        APK extracted configs
├── aggregated/        Domain-weighted consensus
├── specs/             32-parameter estimation
├── scoring/           Ground truth comparison
├── ground_truth/      Team-provided actual values
└── report/            This report + review template
```

## 실험 환경

| 항목 | 내용 |
|------|------|
| AI 모델 | Claude {SYS_CFG.claude_model} |
| 장르 모듈 | {genre.genre_key} ({genre.genre_name}) |
| 세션 전략 | 전문 미션 {len(missions)}종 (Core 4 + Flex {sum(1 for m in missions.values() if m.flex)}) |
| 분석일 | {datetime.now().strftime('%Y-%m-%d')} |
"""

    report_file = dirs["report"] / f"{game.key}_C10_plus_v25_report.md"
    report_file.write_text(report, encoding="utf-8")
    log(f"  Report: {report_file}")
    if has_score:
        log(f"  Score: {score*100:.1f}%")
    else:
        log(f"  Score: Awaiting team review")
    log("Phase 6 complete.\n")


# ---------------------------------------------------------------------------
# MAIN PIPELINE ORCHESTRATOR
# ---------------------------------------------------------------------------

def run_pipeline(game_key: str, skip_capture: bool = False,
                 replay: bool = False, replay_speed: float = 1.0,
                 smart: bool = False):
    """Run the full C10+ v2.5 pipeline for a game.

    Args:
        game_key: Game identifier (e.g. "ash_n_veil", "carmatch")
        skip_capture: If True, skip Phase 1 (use existing screenshots)
        replay: If True, use recorded events for Phase 1 instead of genre scripts
        replay_speed: Playback speed multiplier for replay mode
        smart: If True, use smart AI navigation for Phase 1 (requires recording)
    """
    start = time.time()

    # Load all genres
    load_all_genres()

    # Find game
    result = find_game(game_key)
    if not result:
        log(f"ERROR: Game '{game_key}' not found in any genre module.")
        log(f"  Available games:")
        from genres import _GENRE_REGISTRY
        for g in _GENRE_REGISTRY.values():
            for k in g.get_games():
                log(f"    {k} ({g.genre_name})")
        return

    genre, game = result
    dirs = get_dirs(game_key)

    capture_mode = "smart" if smart else ("replay" if replay else ("skip" if skip_capture else "auto"))

    log("=" * 60)
    log(f"C10+ v2.5 Pipeline — {game.name}")
    log(f"  Genre: {genre.genre_name} ({genre.genre_key})")
    log(f"  Package: {game.package}")
    log(f"  Capture: {capture_mode}" + (f" ({replay_speed}x)" if replay else ""))
    log(f"  Output: {get_output_dir(game_key)}")
    log(f"  Features: OCR={SYS_CFG.features.get('ocr')}, "
        f"Wiki={SYS_CFG.features.get('wiki')}, "
        f"Assets={SYS_CFG.features.get('assets')}")
    log("=" * 60)

    # PRE: APK Asset Extraction (once)
    asset_text = pre_extract_assets(game, dirs)

    # P1: Capture
    if smart:
        # Smart mode: AI-driven navigation with screen classification
        if not adb_check_device():
            log(f"ERROR: ADB device {SYS_CFG.device} not found. Start BlueStacks first.")
            return
        log("=" * 60)
        log("PHASE 1: SMART CAPTURE (AI navigation)")
        log("=" * 60)
        from smart_player.smart_capture import smart_capture as _smart_capture
        success = _smart_capture(game_key, genre, game, dirs["sessions"])
        if not success:
            log("ERROR: Smart capture failed.")
            log(f"  Ensure recording exists: python run.py {game_key} record")
            return
        log("Phase 1 (smart) complete.\n")
    elif replay:
        # Replay mode: use recorded touch events
        if not adb_check_device():
            log(f"ERROR: ADB device {SYS_CFG.device} not found. Start BlueStacks first.")
            return
        log("=" * 60)
        log("PHASE 1: REPLAY CAPTURE")
        log("=" * 60)
        from player import replay as replay_events
        success = replay_events(
            game_key, speed=replay_speed,
            output_dir=dirs["sessions"],
        )
        if not success:
            log("ERROR: Replay failed. Check recording exists.")
            log(f"  Record first: python run.py {game_key} record")
            return
        log("Phase 1 (replay) complete.\n")
    elif not skip_capture:
        if not adb_check_device():
            log(f"ERROR: ADB device {SYS_CFG.device} not found. Start BlueStacks first.")
            log("  Use --skip-capture to analyze existing screenshots.")
            return
        phase1_capture(genre, game, dirs)
    else:
        log("Skipping Phase 1 (using existing screenshots)")

    # P1.5: OCR
    ocr_data = phase1_5_ocr(genre, game, dirs)

    # P2: Vision Analysis
    phase2_vision(genre, game, dirs, ocr_data=ocr_data, asset_text=asset_text)

    # P2.5: Wiki Cross-Reference
    wiki_text = phase2_5_wiki(genre, game, dirs)

    # P3: Aggregation
    phase3_aggregate(genre, game, dirs, wiki_text=wiki_text, asset_text=asset_text)

    # P4: Spec Generation
    phase4_spec(genre, game, dirs, asset_text=asset_text)

    # P5: Scoring
    phase5_scoring(genre, game, dirs)

    # P6: Report
    phase6_report(genre, game, dirs)

    elapsed = time.time() - start
    log(f"\nPipeline complete! Total time: {elapsed/60:.1f} minutes")
