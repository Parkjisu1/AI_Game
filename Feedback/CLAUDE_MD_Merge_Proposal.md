# CLAUDE.md 워크플로우 머지 제안서

## 기존 CLAUDE.md에 추가할 내용

---

## 1. SDK 통합 규칙 섹션 추가

### 위치: "파이프라인 단계" 섹션 이후

```markdown
---

## SDK 통합 가이드

### Firebase Unity SDK
| 버전 | 최소 Android SDK | 주의사항 |
|------|------------------|----------|
| 13.7.0 | 24 | ParameterItemId → "item_id" 문자열 사용 |

### 조건부 컴파일 패턴
```csharp
// using 문도 조건부 블록 안에 포함
#if FIREBASE_ANALYTICS
using Firebase;
using Firebase.Analytics;
#endif
```

### 플러그인 충돌 검사
빌드 전 확인:
- `googlemobileads-unity.aar`와 `GoogleMobileAdsPlugin.androidlib` 중복 금지
- 동일 네임스페이스 사용 플러그인 제거

---

## Android 빌드 설정

### 아키텍처 값
| 값 | 의미 | 용도 |
|----|------|------|
| 1 | ARMv7 | - |
| 2 | ARM64 | - |
| 4 | x86 | 에뮬레이터 |
| 5 | ARMv7 + ARM64 | **프로덕션 권장** |
| 7 | ARMv7 + ARM64 + x86 | 개발/테스트 |

### Gradle packagingOptions
**절대 exclude 금지:**
- `arm64-v8a`
- `armeabi-v7a`
- `x86` (에뮬레이터 테스트 시)

**안전한 exclude:**
- `armeabi` (구형)
- `mips`, `mips64`

---

## 빌드 에러 패턴

### Manifest merger failed
```
Namespace 'xxx' used in: A, B
```
→ 중복 플러그인 제거

### minSdkVersion 충돌
```
minSdkVersion X cannot be smaller than Y
```
→ ProjectSettings에서 minSdkVersion을 Y 이상으로 변경

### 에뮬레이터 설치 불가
→ `AndroidTargetArchitectures`에 x86 포함 (값 4 추가)
```
