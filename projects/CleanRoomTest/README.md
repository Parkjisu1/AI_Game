# C10+ v2.5: Clean Room Game Analysis System

소스코드 없이 게임의 설계 파라미터를 역추정하는 자동화 파이프라인.

## 정확도

| 버전 | 정확도 | 방법 |
|------|:------:|------|
| v1 (past/) | 89.5% | 10명 전문 관찰 (퍼즐 3종) |
| **v2.5** | **93~95% (예상)** | **+ OCR + APK 에셋 + 커뮤니티 교차검증** |

## 폴더 구조

```
CleanRoomTest/
├── c10_plus_v25/              ★ 최종 프로덕션 코드
│   ├── run.py                 CLI 엔트리포인트
│   ├── core.py                ADB, Claude, OCR, APK추출, Wiki
│   ├── pipeline.py            6+3 Phase 파이프라인
│   └── genres/                장르별 모듈
│       ├── __init__.py        GenreBase ABC + 레지스트리
│       ├── puzzle.py          퍼즐 (TapShift, MagicSort, CarMatch)
│       ├── idle_rpg.py        Idle RPG (Ash N Veil)
│       └── merge.py           머지 (템플릿)
│
├── ground_truth/              Ground Truth (소스코드에서 추출한 정답)
├── C10_Plus_Methodology.md    방법론 상세 기술서 (v1 기준, 600줄)
├── C10_Plus_개선방안.md        v2.5 개선 방안 + 비용 분석
├── past/                      이전 실험 데이터 아카이브
└── README.md                  이 파일
```

## 사용법

```bash
cd c10_plus_v25

# 게임/장르 목록 확인
python run.py --list

# 전체 분석 (BlueStacks 실행 필요)
python run.py ash_n_veil

# APK 에셋 추출 포함
python run.py ash_n_veil --apk /path/to/anv.apk

# 기존 스크린샷으로 분석만 (캡처 건너뜀)
python run.py carmatch --skip-capture

# 특정 기능 비활성화
python run.py ash_n_veil --no-wiki --no-ocr
```

## 파이프라인 흐름

```
[PRE] APK 에셋 추출 (M4) ─────────────────────────────────┐
                                                           │
[P1]  CAPTURE ─→ [P1.5] OCR (M2) ─→ [P2] VISION ─→      │
                                                    │      │
                         [P2.5] WIKI (M3) ──────────┤      │
                                                    ↓      ↓
                                              [P3] AGGREGATE
                                                    │
                                              [P4] SPEC (32 params)
                                                    │
                                              [P5] SCORING (vs GT)
                                                    │
                                              [P6] REPORT
```

## 장르 모듈 시스템

각 장르가 GenreBase를 상속하여 정의:

| 항목 | 설명 |
|------|------|
| 10 AI 테스터 역할 | Core 4 (공통) + Flex 6 (장르 특화) |
| 10 Vision 프롬프트 | 장르별 분석 지시문 |
| 10 캡처 스크립트 | ADB 조작 시퀀스 |
| 32 파라미터 정의 | 게임별 추정 대상 |
| 도메인 가중치 | 합의 시 전문가 우선순위 |

### 장르별 Flex Role 비교

```
  #  | Puzzle             | Idle RPG              | Merge
-----+--------------------+-----------------------+---------------------
  3  | Numeric Collection | Numeric Early (1~15)  | Numeric Collection
  4  | Timing Observation | Numeric Late (30+)    | Merge Chain Analysis
  6  | Edge Case Testing  | Equipment & Enhance   | Board Management
  7  | Economy Tracking   | Economy & Idle        | Economy Tracking
  8  | Algorithm Behavior | Gacha & Pet System    | Orders & Events
  9  | State & Flow       | Skills & Combat       | Production Chains
```

## v2.5 향상 기능

| 코드 | 기능 | 효과 | 비용 |
|------|------|------|:----:|
| M1 | 장르별 미션 재설계 | +1.0~1.5% | 0원 |
| M2 | OCR 수치 전처리 (pytesseract) | +0.5~1.0% | 0원 |
| M3 | 커뮤니티 위키 교차검증 | +0.5~1.0% | 0원 |
| M4 | APK 에셋 추출 (UnityPy) | +1.5~3.0% | 0원 |

## 새 장르 추가

1. `genres/merge.py`를 템플릿으로 복사
2. `GenreBase` 상속, 10개 미션/프롬프트/캡처 정의
3. 32개 파라미터 정의
4. `register_genre()` 호출
5. `genres/__init__.py`의 `load_all_genres()`에 import 추가

## 새 게임 추가 (기존 장르)

해당 장르 모듈의 `get_games()`에 GameConfig 추가:
- key, name, package, prefix
- coords (ADB 좌표 - 게임 설치 후 실측)
- wiki_keywords (커뮤니티 검색어)
- apk_path (APK 파일 경로, 선택)

## 요구사항

- Python 3.10+
- BlueStacks 에뮬레이터 (ADB 포함)
- Claude CLI (`claude` command)
- 선택: `pip install pytesseract Pillow` (M2)
- 선택: `pip install UnityPy` (M4)
