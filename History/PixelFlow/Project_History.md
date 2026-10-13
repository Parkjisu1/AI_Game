# PixelFlow Project History

## Overview
PixelFlow (com.loomgames.pixelflow) APK 게임 → BalloonFlow Unity 이식을 위한 레벨 데이터 추출 프로젝트.

핵심 전략: YOLO 화면 인식(Jaccard 0.47 한계) → **APK 바이너리 직접 추출**(100% 정확)

---

## 타임라인

### Phase 1: YOLO 화면 인식 시도 (2026-04-13 ~ 2026-04-22)

#### 04-13~16: Cell + Gimmick 모델 학습
- cell_only v1: 1-class detector, Precision 97.5%, MAE 144.30
- gimmick_detector: P/R/F1 0.62/0.88/0.73, Type 99.5%
- Hybrid 파이프라인 (`hybrid_extractor.py`) — 353 레벨 일괄 추출
- 위치: `E:/AI/virtual_player/yolo/pixelflow/`

#### 04-17~18: cell_only_v2 학습 (실패)
- 3080 Ti / imgsz=1920 / 300 epochs 설정 → 155 epochs 미완주
- 광고 이미지 환각 → v1 채택, v2 폐기

#### 04-19: 광고 데이터 정제
- level_309/310/317 광고 확정 → 353 클린 레벨 확보

#### 04-21~22: Holder/Queue 파이프라인
- holder_detector_v3 학습 (P 0.85, R 0.83, 91 epochs)
- Stage 2d → 42850 observation × before/after JSONL
- Stage 3 timeseries v3~v6 — Jaccard 0.474, first5 0.648 (한계)

**결론**: YOLO 화면 인식만으로는 레벨 큐 정확 복원 불가능.

---

### Phase 2: APK 직접 추출 (2026-04-22)

#### Unity 번들 디코드
- BlueStacks `com.loomgames.pixelflow` → `base.apk` + `unity_data.apk`
- `unity_data.apk` 내부 `datapack.unity3d` 파싱
- 추출 스크립트: `E:/AI/projects/pixelflow_extracted/extract_levels.py`, `decode_all_levels.py`

#### 산출물 (4/22 종료)
- **1,367 레벨** raw JSON: `E:/AI/pixelflow_game_data/levels_json/`
- 구성: 1200 unique levels × 1.14 variants (easy/Medium/Hard 등)
- 정확도 100% (게임 바이너리 그대로)

---

### Phase 3: 큐 재구성 알고리즘 진화 (2026-04-27 ~ 2026-04-28)

YOLO 관측을 APK 정답과 정합시키는 알고리즘 진화 (Played LCS 측정):

| 버전 | 일자 | 방법 | Played LCS |
|------|------|------|:---:|
| v7 | 04-27 | 글로벌 presence + LCS | 38.9% |
| v10 | 04-27 | per-line head 추적 + FIFO | — |
| v11 | 04-27 | + Variant 매칭 | 38.9% |
| v12 | 04-27 | + APK 색 필터 + conf 0.5+ + stable_run 3+ | 75.2% |
| v13b | 04-28 | tap-paired BEFORE/AFTER 검증 | 74.8% |
| v14 | 04-28 | YOLO + pixel_color fallback (Color Jaccard 0.249→0.547) | 76.1% |
| v15 | 04-28 | tap-paired + pixel 결합 | 68.8% |
| **v15c** | 04-28 | **5-way ensemble = max(v12, v13b, v14, v15)** | **84.4%** |

**v7 → v15c 개선폭**: +45.5pp Played LCS

#### v15c 분포 (293 검증 레벨)
- 80-100% 매칭: 200레벨 (68%)
- 60-80%: 61레벨 (21%)
- 40-60%: 21레벨
- <40%: 11레벨
- **High+Good confidence: 89.1%**

#### 알고리즘별 우세 분포
- v12 197 (67%): 전체 프레임 robust
- v14 49 (17%): pixel rescue
- v13b 38 (13%): noise filter
- v15 9 (3%): combo

---

### Phase 4: BalloonFlow 형식 변환 (2026-04-28 22:22)

#### 산출물
- `E:/AI/pixelflow_game_data/balloonflow_format/PixelFlow_LevelDB.json` (473MB, 1362 통합)
- `E:/AI/pixelflow_game_data/balloonflow_format/levels/Level_NNNN_*.json` (1362 개별)
- `_index.json`, `verified_levels.json` (293 cross-validated)
- `cross_validation_report.json`, `README_cross_validation.md`
- `balloonflow_format.zip` (27MB 배포본)

#### 변환 스크립트
- `E:/AI/projects/pixelflow_extracted/convert_to_balloonflow_format.py`
- PixelFlow material(1-29 + 30+ extended) → BalloonFlow color(0-27) 매핑
- queue_format 분기: `holder_defs` (700레벨) / `per_tap_expanded` (667레벨)

---

### Phase 5: Extended Materials 매핑 (2026-04-29)

#### 발견
PixelFlow의 mat=30~33이 1-29 팔레트 외 → 미해석 상태였음.
CSV/board 분석 결과 **gimmick이 아닌 색상 (extended colors)** 으로 판명:
- mat=32 first L46 (Frozen Shooter는 L290부터) → Frozen Shooter ≠ mat=32
- L46 mat=32 셀이 gimmick GridPoints 외부에 위치

#### 샘플링 결과
- `sample_extended_v2.py` (V8 jsonl + 스크린샷 RGB 샘플링, median-based)
- `extended_mat_color_mapping.json`:
  - **mat=30** → BF DarkGray (idx 7) — 1200 samples confirmed (RGB 60,60,90)
  - **mat=32** → BF Cyan-ext (idx 11) — 50 samples confirmed (RGB 0,180,240), L46 검증
  - **mat=31, 33** — TBD (스크린샷 부족, HotPink placeholder)

#### 재변환
- 13:50: `convert_to_balloonflow_format.py` 매핑 반영
- 13:51: 1362 레벨 + zip 재생성 (`PixelFlow_LevelDB.json` 갱신)

---

### Phase 6: L46 단독 deliverable (2026-04-29 13:59)

`E:/AI/pixelflow_game_data/L46_delivery/`:
- `Level_0046_easy.json` — APK 정답 (BalloonFlow 포맷)
- `L46_yolo_reconstructed.json` — v15c YOLO 재구성
- `L46_cross_validation.json` — 비교 분석
- `README_L46.md` — 결과 보고서
- `L46_delivery.zip` (17KB)

#### 검증 결과
- Played LCS **100%** (4 lines 모두 일치)
- Session coverage: 6.32% (158 frames / 95 shooters 중 6 head 전이)
- APK 색 11종 vs YOLO 관측 2종 (Jaccard 0.182)
- 결론: 본 segment에서는 완벽 일치, 후반부는 검증 불가 (사용자가 짧게 플레이)

---

## 보조 패키지

### pixelflow_hybrid (2026-04-27)
`E:/AI/pixelflow_hybrid/` — APK 정답 + YOLO 실시간 매칭 인터페이스
- `LevelLoader` (APK 100%): get_queue, get_board, get_gimmicks, get_meta
- `RuntimeDetector` (YOLO 95%): get_visible_state from screenshot
- `StateMatcher` (Hybrid 80%+): match_lines, estimate_progress, predict_next_taps
- 사용처: AI Tester 자동 플레이, Unity 씬 복제, 레벨 디자인 분석

---

## 미해결 / 이어할 후보

1. **mat=31, 33 매핑** — 추가 스크린샷 확보 후 sample_extended_v2.py 재실행
2. **gimmick code 30+ 정확 매핑** — IL2CPP `global-metadata.dat` 디컴파일 (Il2CppDumper)
3. **보드 cells 바이너리 앞 섹션 직접 파싱** — 현재 미해석 (BF 변환은 다른 경로)
4. **Unity import 검증** — 1362 레벨 BalloonFlow Unity 프로젝트에 실제 로드 테스트
5. **L46 외 변형 레벨 deliverable** 또는 전체 대량 검증 보고서

---

## 주요 파일 위치

### 데이터
- 원본 APK: `E:/AI/projects/pixelflow_extracted/{base.apk, unity_data.apk}`
- Unity 번들: `E:/AI/projects/pixelflow_extracted/unity_extracted/assets/bin/Data/datapack.unity3d`
- Raw 레벨: `E:/AI/pixelflow_game_data/levels_json/` (1367)
- BF 형식: `E:/AI/pixelflow_game_data/balloonflow_format/` (1362)
- 통합: `PixelFlow_LevelDB.json` (473MB)

### 스크립트
- 추출: `E:/AI/projects/pixelflow_extracted/extract_levels.py`, `decode_all_levels.py`
- 변환: `E:/AI/projects/pixelflow_extracted/convert_to_balloonflow_format.py`
- 큐 알고리즘: `E:/AI/projects/pixelflow_extracted/queue_v7~v15_*.py`
- 샘플링: `E:/AI/projects/pixelflow_extracted/sample_extended_v2.py`
- L46 빌더: `E:/AI/projects/pixelflow_extracted/build_l46_delivery.py`

### YOLO 모델 (보조)
- Cell v1: `E:/AI/virtual_player/yolo/pixelflow/runs/cell_only/weights/best.pt`
- Gimmick: `E:/AI/virtual_player/yolo/pixelflow/runs/gimmick_detector/weights/best.pt`
- Holder v3: `E:/AI/virtual_player/yolo/pixelflow/runs/holder_detector_v3/weights/best.pt`

### 관측 데이터
- v8 JSONL (pixel_color 포함): `E:/AI/virtual_player/tools/queue_pipeline/queue_all_observations_v8_{before,after}.jsonl` (각 76MB)
- 큐 파이프라인 가이드: `E:/AI/virtual_player/tools/queue_pipeline/README.md`, `RUN_3080TI.md`
