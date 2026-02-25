# C10+ v2.5 방법론 개선 방안 (장르 모듈화 + 향상 기능)

> **작성일**: 2026-02-23
> **목적**: C10+ v1(89.5%)의 정확도를 비용 대비 효과적으로 향상시킬 수 있는 모든 방법 조사 및 우선순위 제안
> **기준**: v1 = 89.5% (퍼즐 3종 평균), 관찰 천장 = ~90.6% (32개 중 29개 관찰 가능)
> **구현**: `c10_plus_v25/` - 장르 모듈화된 프로덕션 코드 (run.py --list 로 확인)

---

## 1. 현재 한계 분석

### 1-1. v1 오답 유형 분류 (3종 평균, 96개 파라미터)

| 오답 유형 | 건수 | 비율 | 예시 |
|-----------|:----:|:----:|------|
| **관찰 불가** (아키텍처 내부) | 8 | 8.3% | namespace, pathfinding_algorithm, pattern_count |
| **수치 근사 오차** | 3 | 3.1% | serialization 경로 불완전, 수치 미세 오차 |
| **관찰 누락** | 0 | 0% | v1에서 이미 해결 |

### 1-2. 개선 가능 영역

```
100%  ┬────────────────────────────────────────
      │  ██████████████████████████████████████  98.5% (D10, L2 패턴 필요)
      │  ████████████████████████████████████    96.3% (D2, L2 필요)
 95%  ┤  ────────────── 관찰+후처리 천장 ──────── ~94%  ★ 목표
      │  ██████████████████████████████████      93.2% (C10+ → L1 순차)
      │  █████████████████████████████           91%   v2 (미션 재설계)
 90%  ┤  ████████████████████████████            90.6%  순수관찰 천장
      │  ██████████████████████████              89.5%  v1 (현재)
      │
 85%  ┤  ████████████████████████                85.0%  C10
      └────────────────────────────────────────
```

**핵심 인사이트**: 순수 관찰 천장(~90.6%)을 돌파하려면 **관찰 이외의 데이터 소스**가 필요하다.

---

## 2. 개선 방법 전체 목록 (7가지)

### Tier 1: 비용 0원, 즉시 적용 가능

| # | 방법 | 예상 향상 | 구현 난이도 | 설명 |
|---|------|:---------:|:----------:|------|
| **M1** | v2 미션 재설계 | +1.0~1.5% | ★☆☆ | 이미 구현 완료 (anv_experiment) |
| **M2** | OCR 후처리 | +0.5~1.0% | ★☆☆ | pytesseract로 스크린샷에서 수치 자동 추출 |
| **M3** | 커뮤니티 위키 교차검증 | +0.5~1.0% | ★☆☆ | 공개 게임 위키/가이드 데이터로 관찰값 검증 |

### Tier 2: 비용 0원, 약간의 추가 구현 필요

| # | 방법 | 예상 향상 | 구현 난이도 | 설명 |
|---|------|:---------:|:----------:|------|
| **M4** | APK 에셋 추출 | +1.5~3.0% | ★★☆ | UnityPy로 APK 내 설정 JSON/ScriptableObject 직접 추출 |
| **M5** | OpenCV UI 자동 감지 | +0.3~0.5% | ★★☆ | 템플릿 매칭으로 UI 요소 좌표/크기 자동 측정 |

### Tier 3: 추가 비용 또는 높은 복잡도

| # | 방법 | 예상 향상 | 구현 난이도 | 설명 |
|---|------|:---------:|:----------:|------|
| **M6** | 영상 분석 (Gemini) | +0.5~1.0% | ★★★ | 동영상 녹화 → Gemini Pro Vision으로 애니메이션/타이밍 분석 |
| **M7** | 메모리 스캐닝 | +2.0~4.0% | ★★★ | 런타임 메모리에서 수치 직접 읽기 (법적/윤리적 검토 필요) |

---

## 3. 각 방법 상세 분석

### M1. v2 미션 재설계 (이미 완료)

**상태**: `anv_experiment/run_anv_c10_plus_v2.py`에 구현 완료

**변경 내용**:
- Numeric 미션 2분할 (초반 Lv.1~15 / 후반 Lv.30+) → 회귀분석 데이터 포인트 2배
- Visual 미션에 다해상도 비교 추가 → `ui_reference_resolution` 역산
- 장르별 미션 재설계 (퍼즐 → Idle RPG 특화)

**예상 효과**: +1.0~1.5% (v1 89.5% → 약 91%)
**비용**: 0원
**리스크**: 없음 (기존 파이프라인 확장)

**검토 의견**: ✅ **바로 적용 권장**. 이미 구현되어 있고 리스크가 없다. 기존 10개 미션 구조를 유지하면서 데이터 품질만 올리는 접근이라 검증도 용이하다.

---

### M2. OCR 후처리 (pytesseract)

**원리**: 현재 Claude Vision이 스크린샷의 숫자를 "읽는" 방식 → OCR 엔진으로 **먼저** 수치를 추출한 후 Claude에 전달

**구현 예시**:
```python
import pytesseract
from PIL import Image

def extract_numbers_from_screenshot(img_path, regions=None):
    """스크린샷에서 수치 데이터를 OCR로 추출"""
    img = Image.open(img_path)

    if regions:
        # 특정 영역만 크롭하여 정확도 향상
        results = {}
        for name, (x, y, w, h) in regions.items():
            cropped = img.crop((x, y, x+w, y+h))
            # 수치 인식에 최적화: 흰 배경 + 숫자만
            text = pytesseract.image_to_string(
                cropped,
                config='--psm 7 -c tessedit_char_whitelist=0123456789.,%+-'
            )
            results[name] = text.strip()
        return results
    else:
        return pytesseract.image_to_string(img)
```

**적용 위치**: Phase 2 (Vision 분석) 전에 OCR 전처리 단계 추가
```
기존: 스크린샷 → Claude Vision → 텍스트
개선: 스크린샷 → OCR 추출 → {숫자 데이터 + 스크린샷} → Claude Vision → 텍스트
```

**예상 효과**: +0.5~1.0%
- 현재 Claude Vision의 수치 인식은 대부분 정확하나, 작은 폰트나 겹치는 UI에서 간헐적 오류 발생
- OCR이 특히 강한 영역: HP/ATK 수치, 레벨, 재화량, 가격표
- **회귀분석 신뢰도 직결**: OCR로 정확한 수치 → 더 정확한 공식 역산

**비용**: 0원 (pytesseract는 오픈소스, Tesseract OCR 무료)
**설치**: `pip install pytesseract` + Tesseract OCR 엔진 설치

**검토 의견**: ✅ **강력 권장**. 구현이 단순하고 (함수 1개 추가), 수치 정확도에 직접적 영향을 준다. v2에서 Numeric 미션을 분할했는데, OCR과 결합하면 시너지가 크다.

---

### M3. 커뮤니티 위키 교차검증

**원리**: 게임 위키, 공략 사이트, Reddit, 커뮤니티 가이드에서 이미 공개된 게임 데이터를 수집하여 관찰값 검증

**데이터 소스**:
| 소스 | 데이터 유형 | 신뢰도 |
|------|------------|:------:|
| 게임 공식 공지 (확률 공시 등) | 가챠 확률, 업데이트 내역 | ★★★ |
| TapTap / Google Play 리뷰 | 밸런스 불만, 수치 언급 | ★★☆ |
| Reddit / 디시인사이드 | 사용자 검증 수치, 역산 공식 | ★★☆ |
| 유튜브 공략 영상 | 전투 타이밍, UI 레이아웃 | ★★☆ |
| Fandom / 나무위키 | 장비 스탯, 스킬 설명 | ★★☆ |

**구현 방식**: Phase 3 (합의 통합) 시 추가 데이터 소스로 활용
```python
def fetch_community_data(game_name):
    """웹 검색으로 공개 게임 데이터 수집"""
    sources = [
        f"{game_name} wiki stats",
        f"{game_name} gacha rates",
        f"{game_name} damage formula reddit",
        f"{game_name} growth curve guide",
    ]
    # Claude에 웹 검색 결과를 추가 컨텍스트로 전달
    ...
```

**예상 효과**: +0.5~1.0%
- 특히 **가챠 확률** (법적 공시 의무), **데미지 공식** (커뮤니티 역산), **성장 곡선** (가이드)에 효과적
- 관찰 불가 파라미터 중 일부를 커뮤니티 데이터로 보완 가능

**비용**: 0원
**리스크**: 커뮤니티 데이터의 정확성 검증 필요 (출처별 가중치 차등)

**검토 의견**: ✅ **권장**. 특히 Idle RPG는 커뮤니티 데이터가 풍부하다. 가챠 확률은 법적 공시이므로 100% 정확한 데이터를 얻을 수 있다. 다만 **순수 관찰(Clean Room)** 원칙과의 정합성을 정의해야 한다 — "공개 데이터 참조는 Clean Room 위반이 아닌가?"

> **권장 정의**: Clean Room은 "소스코드 미접근"이 핵심이지, "공개 정보 미참조"가 아니다. 공개된 게임 데이터를 참조하는 것은 합법적이며 Clean Room 원칙에 부합한다.

---

### M4. APK 에셋 추출 (UnityPy) ⭐ 가성비 최고

**원리**: Unity 게임의 APK 파일에는 소스코드 외에 **설정 데이터**가 포함되어 있다. UnityPy 라이브러리로 이 데이터를 추출하면 소스코드 없이도 핵심 파라미터를 직접 얻을 수 있다.

**추출 가능 데이터**:
| 에셋 유형 | 추출 가능 데이터 | C10+ 파라미터 매핑 |
|-----------|-----------------|-------------------|
| TextAsset (.json, .csv) | 레벨 데이터, 밸런스 테이블 | 성장 공식, 스테이지 구성 |
| ScriptableObject | 장비 스탯, 스킬 데이터, 가챠 테이블 | 장비/스킬/가챠 전체 |
| Sprite / Texture2D | UI 에셋 크기, 해상도 | UI 기준 해상도 |
| MonoScript (메타데이터만) | 클래스명, 네임스페이스 | namespace, pattern_count |
| AnimationClip | 애니메이션 길이, 프레임 수 | 타이밍 파라미터 |

**핵심**: **소스코드(C# 로직)는 추출하지 않는다**. 데이터 에셋만 읽는 것이므로 Clean Room 원칙에 부합한다.

**구현 예시**:
```python
import UnityPy

def extract_game_assets(apk_path):
    """APK에서 게임 설정 데이터 추출"""
    env = UnityPy.load(apk_path)

    extracted = {
        "text_assets": [],    # JSON/CSV 설정 파일
        "scriptable_objects": [],  # SO 데이터
        "sprites": [],        # UI 에셋 정보
        "animations": [],     # 애니메이션 클립
        "mono_scripts": [],   # 클래스명/네임스페이스
    }

    for obj in env.objects:
        if obj.type.name == "TextAsset":
            data = obj.read()
            if any(ext in data.m_Name.lower() for ext in
                   ['config', 'level', 'stage', 'balance', 'gacha',
                    'equipment', 'skill', 'stat', 'reward']):
                extracted["text_assets"].append({
                    "name": data.m_Name,
                    "content": data.m_Script.decode('utf-8', errors='ignore')
                })

        elif obj.type.name == "MonoScript":
            data = obj.read()
            extracted["mono_scripts"].append({
                "name": data.m_Name,
                "namespace": data.m_Namespace,
                "class_name": data.m_ClassName,
            })

        elif obj.type.name == "AnimationClip":
            data = obj.read()
            extracted["animations"].append({
                "name": data.m_Name,
                "length": data.m_MuscleClip.m_StopTime,
            })

    return extracted
```

**예상 효과**: +1.5~3.0%
- **관찰 불가였던 파라미터**를 직접 추출 가능:
  - `namespace`: MonoScript 메타데이터에서 직접 확인
  - `pattern_count`: 클래스명 패턴 분석으로 추정 가능
  - 성장 공식: 밸런스 테이블에서 정확한 계수 확인
- v1에서 0점이었던 3개 파라미터 중 1~2개를 해결 가능

**비용**: 0원 (UnityPy 오픈소스, `pip install UnityPy`)
**구현 시간**: ~2시간 (에셋 추출 스크립트 + 데이터 정리)

**리스크**:
- APK 다운로드 필요 (APKPure 등에서 공개 배포 버전)
- 일부 게임은 에셋 번들을 서버에서 별도 다운로드 (초기 APK에 미포함)
- 난독화/암호화된 에셋은 추출 불가

**Clean Room 정합성**:
> APK의 에셋 데이터(JSON 설정, 스프라이트 메타데이터)는 **이미 배포된 공개 데이터**이다. 소스코드(IL2CPP/Mono DLL)를 디컴파일하는 것과 근본적으로 다르다. 에셋 추출은 게임의 "콘텐츠"를 읽는 것이지 "로직"을 읽는 것이 아니다.

**검토 의견**: ✅ **최우선 권장**. 관찰 천장(90.6%)을 돌파할 수 있는 유일한 Tier 2 방법이다. 구현도 단순하고 비용도 0원이다. 다만 Clean Room의 정의를 "소스코드 미접근"에서 "에셋 데이터 참조 허용"으로 명시적으로 확장해야 한다.

---

### M5. OpenCV UI 자동 감지

**원리**: 스크린샷에서 UI 요소(버튼, 슬롯, HP바 등)를 OpenCV 템플릿 매칭으로 자동 감지하여 좌표/크기 정밀 측정

**구현 예시**:
```python
import cv2
import numpy as np

def detect_ui_elements(screenshot_path, template_dir):
    """UI 요소 위치/크기 자동 감지"""
    img = cv2.imread(screenshot_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    results = []
    for template_file in os.listdir(template_dir):
        template = cv2.imread(os.path.join(template_dir, template_file), 0)
        w, h = template.shape[::-1]

        res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        threshold = 0.8
        loc = np.where(res >= threshold)

        for pt in zip(*loc[::-1]):
            results.append({
                "element": template_file.replace(".png", ""),
                "x": pt[0], "y": pt[1],
                "width": w, "height": h,
            })

    return results
```

**예상 효과**: +0.3~0.5%
- UI 좌표/크기 측정 정밀도 향상
- 현재 Claude Vision의 "~70도" 같은 추정값을 정밀 수치로 변환
- 다해상도 비교(v2 M1)와 결합 시 시너지

**비용**: 0원 (`pip install opencv-python`)
**구현 시간**: ~3시간 (템플릿 제작 + 매칭 로직)

**검토 의견**: ⚠️ **후순위**. 효과가 제한적이고 구현 비용이 높다. v2의 다해상도 비교로 대부분 커버 가능하므로, M2/M3/M4를 먼저 적용한 후 추가 효과가 필요할 때 검토.

---

### M6. 영상 분석 (Gemini Pro Vision)

**원리**: ADB screenrecord로 게임 영상 녹화 → Gemini Pro Vision API로 동영상 직접 분석

**장점**:
- 애니메이션 타이밍, 전투 리듬, UI 트랜지션을 "시간 흐름" 속에서 분석
- 스크린샷 기반 분석의 한계(정적 캡처 → 동적 행동 추론) 해소

**한계**:
- Claude는 동영상 직접 분석 불가 → Gemini API 필요 (별도 비용)
- BlueStacks에서 ADB screenrecord 불안정 (VM 환경)
  - 대안: BlueStacks 내장 녹화 기능 또는 OBS Studio 사용
- 분석 결과를 Claude 파이프라인에 통합하는 추가 작업 필요

**예상 효과**: +0.5~1.0%
- 주로 타이밍/애니메이션 파라미터에 효과
- 전투 쿨다운, 공격 속도 등 시간 기반 수치에 특화

**비용**: Gemini API 호출 비용 (10분 영상 × 10세션 = ~$1~2)
**구현 시간**: ~4시간 (녹화 + Gemini 통합 + 결과 병합)

**검토 의견**: ⚠️ **후순위**. 비용이 발생하고 구현 복잡도가 높다. v2의 프레임 분석 미션(#4)으로 대부분 커버 가능. Gemini API는 나중에 정밀도 목표가 94%+ 일 때 검토.

---

### M7. 메모리 스캐닝

**원리**: 게임 실행 중 메모리를 직접 읽어 수치 확인

**장점**: 내부 수치를 100% 정확하게 읽을 수 있음

**한계**:
- 법적/윤리적 문제 (게임 서비스 약관 위반 가능)
- 안티치트 시스템이 감지할 수 있음
- Clean Room 원칙에 부합하는지 논란 여지

**검토 의견**: ❌ **비권장**. Clean Room 방법론의 취지에 맞지 않고, 법적 리스크가 있다.

---

## 4. 종합 추천: "v2.5" 패키지

CEO 요청사항("가성비 있는건 시도해보는거")에 맞춰, 비용 0원 + 최대 효과 조합을 제안한다.

### v2.5 = v2 + M2(OCR) + M3(위키) + M4(에셋추출)

```
v1 (89.5%)
  ↓ +1.0~1.5%  M1: 미션 재설계 (v2, 완료)
v2 (~91%)
  ↓ +0.5~1.0%  M2: OCR 후처리
  ↓ +0.5~1.0%  M3: 커뮤니티 위키 교차검증
  ↓ +1.5~3.0%  M4: APK 에셋 추출
v2.5 (~93~95%)  ★ 예상 목표
```

### 구현 우선순위 및 일정

| 순서 | 방법 | 구현 시간 | 누적 예상 정확도 |
|:----:|------|:--------:|:---------------:|
| 1 | M1: v2 미션 재설계 | 완료 | ~91% |
| 2 | M2: OCR 후처리 추가 | ~1시간 | ~91.5% |
| 3 | M4: APK 에셋 추출 | ~2시간 | ~93.5% |
| 4 | M3: 커뮤니티 위키 참조 | ~1시간 | ~94% |
| **합계** | | **~4시간 추가** | **~93~95%** |

### 파이프라인 변경도

```
[기존 v1 파이프라인]
CAPTURE → VISION → AGGREGATE → SPEC → SCORING → REPORT

[v2.5 파이프라인]
                    ┌─ M4: APK 에셋 추출 ─────────┐
                    │                              │
CAPTURE → OCR(M2) → VISION → M3: 위키검증 → AGGREGATE → SPEC → SCORING → REPORT
            │                                  ↑
            └── 수치 데이터 사전 추출 ──────────┘
```

**핵심 변경**:
1. CAPTURE 직후 OCR 단계 추가 (수치 사전 추출)
2. 별도로 APK 에셋 추출 (1회, 게임 최초 분석 시)
3. AGGREGATE 단계에서 위키 데이터 + 에셋 데이터를 추가 소스로 포함
4. 기존 10개 VISION 세션은 그대로 유지

---

## 5. v2 기존 안 검토 의견

### 5-1. Numeric 미션 분할 (v2-M1) ✅

**평가**: 가장 확실한 개선. 데이터 포인트가 2배가 되면 회귀분석 R² 값이 실질적으로 향상된다.

**추가 제안**: M2(OCR)와 결합하면 효과 극대화
- OCR로 정확한 수치 추출 → 회귀분석에 정밀 데이터 투입
- "HP = 100 + 15×Lv" 같은 공식이 "HP = 102 + 14.8×Lv (R²=0.994)" 수준으로 정밀화

### 5-2. 다해상도 비교 (v2-M2) ✅

**평가**: 비용 0원으로 `ui_reference_resolution` 정확도를 크게 올릴 수 있는 좋은 아이디어.

**추가 제안**: BlueStacks 해상도 변경이 ADB 좌표에 영향을 줄 수 있으므로, 해상도 변경 시 좌표 재측정 자동화 필요.

### 5-3. Idle RPG 특화 미션 재설계 (v2-M3) ✅

**평가**: 필수적. 퍼즐 게임용 미션으로 Idle RPG를 분석하면 핵심 시스템(장비/가챠/방치보상)을 놓친다.

**추가 제안**: 장르별 미션 템플릿 라이브러리를 만들면 새 게임 분석 시 시간 절약 가능.

---

## 6. Clean Room 정의 확장 제안

v2.5에서 APK 에셋 추출과 커뮤니티 데이터를 사용하려면, Clean Room의 정의를 명확히 해야 한다.

### 기존 Clean Room 정의
> 소스코드에 접근하지 않고, 게임의 외부 관찰만으로 내부 설계 파라미터를 역추정

### 확장 Clean Room 정의 (v2.5)
> 소스코드(C#/IL2CPP 로직)에 접근하지 않고, **허용된 데이터 소스**를 활용하여 게임 설계 파라미터를 추정

**허용 데이터 소스 3계층**:

| 계층 | 소스 | 예시 | Clean Room 위반 여부 |
|:----:|------|------|:-------------------:|
| L1 | 외부 관찰 | 스크린샷, 플레이 녹화, UI 조작 | ✅ 허용 |
| L2 | 공개 데이터 | 게임 위키, 공식 공시, 커뮤니티 역산 | ✅ 허용 |
| L3 | 배포 에셋 | APK 내 JSON/SO/스프라이트 메타 | ✅ 허용 (데이터만) |
| ❌ | 소스코드 | C# 디컴파일, IL2CPP dump | ❌ 금지 |

---

## 7. 비용 요약

| 항목 | v1 | v2 | v2.5 |
|------|:--:|:--:|:----:|
| Claude API | 구독 내 | 구독 내 | 구독 내 |
| pytesseract | - | - | 무료 |
| UnityPy | - | - | 무료 |
| OpenCV | - | - | (선택) 무료 |
| Gemini API | - | - | (선택) ~$2 |
| **총 추가 비용** | **0원** | **0원** | **0원** |
| **추가 구현 시간** | - | - | **~4시간** |

---

## 8. 결론 및 권장 사항

1. **v2는 즉시 실행**: 이미 구현 완료. Ash N Veil에서 바로 테스트 가능.

2. **M2(OCR) + M4(APK 에셋)를 우선 추가**: 비용 0원, 구현 ~3시간, 예상 +2~4% 향상. **관찰 천장을 돌파**할 수 있는 핵심 방법.

3. **M3(위키)는 게임에 따라 선택 적용**: 인기 게임은 데이터가 풍부하여 효과적, 비인기 게임은 데이터 부족으로 효과 제한적.

4. **M5(OpenCV), M6(Gemini)는 v2.5 검증 후 필요 시 추가**: 현재 단계에서는 오버엔지니어링.

5. **M7(메모리)은 비권장**: Clean Room 취지에 맞지 않음.

> **한 줄 요약**: v2 + OCR + APK 에셋 = **비용 0원으로 89.5% → 93~95% 달성 가능**. CEO 요청의 "가성비 있는 시도"에 정확히 부합한다.
