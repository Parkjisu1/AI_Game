# PixelFlow Hybrid Package

APK 정답 데이터(100% 정확) + YOLO 실시간 화면 인식(95% 정확)을
결합한 하이브리드 게임 인터페이스.

## 📦 패키지 구조

```
pixelflow_hybrid/
├── __init__.py              # 패키지 entry point
├── level_loader.py          # APK 레벨 데이터 로더 (정답)
├── runtime_detector.py      # YOLO 실시간 화면 인식
├── state_matcher.py         # 두 소스 매칭 + 진행도 추정
└── README.md                # 본 문서
```

## 🔑 핵심 개념

| 컴포넌트 | 정확도 | 역할 |
|----------|:---:|------|
| `LevelLoader` (APK) | 100% | 게임 정답: queue, board, gimmicks |
| `RuntimeDetector` (YOLO) | 95% per-frame | 실시간 화면 인식 |
| `StateMatcher` (Hybrid) | 80%+ | 두 소스 매칭 → 게임 진행도 추정 |

## 🚀 빠른 시작

### 1. 레벨 데이터 로드 (APK 정답)

```python
from pixelflow_hybrid import LevelLoader

loader = LevelLoader()

# 통계
print(loader.stats())
# {'total_levels': 1200, 'total_variants': 1367, 'level_range': (1, 1200)}

# Level 184 데이터
queue = loader.get_queue(184)        # 4 lines, 97 shooters
board = loader.get_board(184)        # 36×40 board, 1440 cells
gimmicks = loader.get_gimmicks(184)  # ice blocks, wood blocks 등
meta = loader.get_meta(184)          # slot_count, conveyor_limit

# 변형 선택
queue_hard = loader.get_queue(184, variant="Hard")

# 평탄화된 queue (선형 list)
flat = loader.get_expanded_queue(184)
# [{line, position, shooter_id, material, material_name, ammo}, ...]
```

### 2. 실시간 화면 인식 (YOLO)

```python
from pixelflow_hybrid import RuntimeDetector

det = RuntimeDetector()  # default: holder_detector best.pt

# 스크린샷 (파일 또는 numpy array)
state = det.get_visible_state("screenshot.png")
# {
#   "holders": [...],
#   "line_heads": [{line, material, name, conf}, ...],
#   "gimmicks": [...],
#   "current_balloon": {...} or None,
#   "color_distribution": {color: count, ...}
# }
```

### 3. Hybrid 매칭 (APK 정답 + YOLO 관측)

```python
from pixelflow_hybrid import LevelLoader, RuntimeDetector, StateMatcher

loader = LevelLoader()
det = RuntimeDetector()
matcher = StateMatcher(loader)

# 1. 화면 캡처 + 인식
screenshot = capture_screen()  # ADB 또는 다른 방법
visible_state = det.get_visible_state(screenshot)

# 2. APK queue와 매칭
matches = matcher.match_lines(184, visible_state["line_heads"])
# [{observed_line, expected_material, match: True/False, ...}]

# 3. 게임 진행도 추정
progress = matcher.estimate_progress(184, visible_state)
# {progress_pct: 12.5, estimated_consumed: 12, estimated_total: 97, per_line: [...]}

# 4. 다음 5개 탭 예측 (APK 기반)
next_taps = matcher.predict_next_taps(184, visible_state, n=5)
# [{line, material, material_name, ammo}, ...]
```

## 🎮 활용 시나리오

### A. AI Tester (자동 플레이)

```python
def ai_tester_loop(level_num):
    loader = LevelLoader()
    det = RuntimeDetector()
    matcher = StateMatcher(loader)

    queue = loader.get_queue(level_num)  # 정답 미리 로드

    while not is_level_clear():
        screenshot = capture_screen()
        state = det.get_visible_state(screenshot)

        # 다음 탭 결정 (APK 정답 기반)
        next_taps = matcher.predict_next_taps(level_num, state, n=1)
        if next_taps:
            target = next_taps[0]
            tap_holder(line=target["line"])

        time.sleep(0.5)
```

### B. Unity 씬 복제

```python
# 모든 1362 레벨 데이터를 Unity 프로젝트에 export
loader = LevelLoader()
for lv in loader.list_levels():
    data = loader.get_level(lv)
    # JSON 그대로 Unity StreamingAssets/levels/ 에 복사
```

### C. 레벨 디자인 분석

```python
loader = LevelLoader()

# 난이도별 평균 queue 길이
for lv in loader.list_levels():
    queue = loader.get_queue(lv)
    if queue:
        # 분석 로직
        pass
```

## 📊 데이터 정확도 비교

```
              YOLO 단독    APK 단독     Hybrid (현 패키지)
─────────────────────────────────────────────────────────────────
Cell 정확도:      19%       100%       100% (APK 사용)
Gimmick:         54%       100%       100% (APK 사용)
Queue:           41%       100%       100% (APK 사용)
실시간 화면 인식:  90%        N/A         90% (YOLO 사용)
─────────────────────────────────────────────────────────────────
종합 활용도:     35%       제한적       95%+
```

## 🔧 설정 변경

```python
# 다른 weights 사용
det = RuntimeDetector(weights_path="path/to/custom.pt")

# Confidence threshold
det = RuntimeDetector(conf_threshold=0.5)

# APK 데이터 위치
loader = LevelLoader(apk_dir="custom/path/v2_apk_scenes")
```

## 📁 데이터 소스

```
APK 데이터:  E:\AI\pixelflow_game_data\v2_apk_scenes\Level_NNNN*.json (1367 파일)
YOLO 모델:  E:\AI\virtual_player\yolo\pixelflow\runs\holder_detector\weights\best.pt
Palette:    E:\AI\virtual_player\data\pixelflow\profile\cell_profile.json
```

## 의존성

```
ultralytics  (YOLO)
opencv-python
numpy
```

## 향후 확장 가능

1. ADB 통합: BlueStacks 자동 캡처 + 탭 실행
2. WebSocket API: Unity와 양방향 통신
3. Replay 시스템: 게임 진행 기록 + 분석
4. Multi-level batch loader: 여러 레벨 동시 로드
