# AI 게임 코드 생성 워크플로우 개선 피드백

## 개요
CarMatch 프로젝트 개발 과정에서 발견된 워크플로우 개선점 및 교훈

---

## 1. SDK 통합 관련 개선사항

### 1.1 Firebase SDK 설치 프로세스 표준화

**현재 문제점:**
- Firebase Unity SDK 설치 방법이 여러 가지 (UPM, .unitypackage, 수동)
- 버전별 API 차이로 인한 컴파일 에러 빈발
- 조건부 컴파일 (#if ENABLE_FIREBASE) 처리 미흡

**개선 제안:**
```yaml
# rules/sdk_integration.yaml
firebase_integration:
  preferred_method: "unitypackage"
  min_sdk_version: 24  # Firebase Messaging 요구사항
  required_files:
    - "google-services.json"  # Android
    - "GoogleService-Info.plist"  # iOS
  conditional_compilation:
    pattern: |
      #if FIREBASE_ANALYTICS || FIREBASE_MESSAGING
      using Firebase;
      using Firebase.Analytics;
      #endif
    note: "using 문도 조건부 컴파일 블록 안에 포함"

  common_errors:
    CS0246:
      cause: "Firebase 네임스페이스 없음"
      solution: "SDK 설치 또는 조건부 컴파일 확인"
    CS0117_ParameterItemId:
      cause: "SDK 버전에서 상수 제거됨"
      solution: "문자열 리터럴 사용: \"item_id\""
```

### 1.2 SDK 버전 호환성 매트릭스

**추가해야 할 DB 항목:**
```yaml
# db/rules/sdk_compatibility.yaml
firebase_unity_sdk:
  "13.7.0":
    min_android_sdk: 24
    min_ios: "12.0"
    deprecated_apis:
      - "FirebaseAnalytics.ParameterItemId"
      - "FirebaseAnalytics.ParameterItemName"
    replacement:
      ParameterItemId: "item_id"
      ParameterItemName: "item_name"

google_mobile_ads:
  "23.0.0":
    min_android_sdk: 21
    required_permissions:
      - "com.google.android.gms.permission.AD_ID"
    duplicate_check:
      - "googlemobileads-unity.aar"
      - "GoogleMobileAdsPlugin.androidlib"
    note: "두 파일 중 하나만 존재해야 함"
```

---

## 2. Android 빌드 관련 개선사항

### 2.1 Gradle 설정 검증 자동화

**현재 문제점:**
- packagingOptions에서 필요한 아키텍처까지 exclude
- 플러그인 충돌 (동일 네임스페이스)
- minSdkVersion 불일치

**개선 제안 - 빌드 전 검증 스크립트:**
```csharp
// Editor/BuildValidator.cs 자동 생성 템플릿
[InitializeOnLoad]
public class BuildValidator
{
    static BuildValidator()
    {
        BuildPlayerWindow.RegisterBuildPlayerHandler(ValidateAndBuild);
    }

    static void ValidateAndBuild(BuildPlayerOptions options)
    {
        var errors = new List<string>();

        // 1. minSdkVersion 검증
        if (PlayerSettings.Android.minSdkVersion < AndroidSdkVersions.AndroidApiLevel24)
        {
            errors.Add("Firebase requires minSdkVersion >= 24");
        }

        // 2. 중복 플러그인 검증
        var aarFiles = Directory.GetFiles("Assets/Plugins/Android", "*.aar");
        var androidlibs = Directory.GetDirectories("Assets/Plugins/Android", "*.androidlib");
        // 네임스페이스 충돌 검사...

        // 3. 아키텍처 설정 검증
        if (options.target == BuildTarget.Android)
        {
            // BlueStacks 테스트 시 x86 필요 경고
        }

        if (errors.Count > 0)
        {
            // 에러 표시 및 빌드 중단
        }
        else
        {
            BuildPipeline.BuildPlayer(options);
        }
    }
}
```

### 2.2 아키텍처 설정 가이드

**추가해야 할 규칙:**
```yaml
# db/rules/android_architectures.yaml
target_architectures:
  values:
    1: "ARMv7"
    2: "ARM64"
    4: "x86"
    5: "ARMv7 + ARM64"  # 권장 (실제 기기용)
    7: "ARMv7 + ARM64 + x86"  # 에뮬레이터 테스트 포함

  recommendations:
    production: 5  # ARMv7 + ARM64
    development: 7  # 에뮬레이터 테스트 포함

  emulator_compatibility:
    bluestacks: "x86, x86_64 필요"
    android_studio: "ARM 이미지 사용 가능"

  gradle_packaging_options:
    safe_excludes:
      - "armeabi"  # 구형, 거의 사용 안함
      - "mips"
      - "mips64"
    never_exclude:
      - "arm64-v8a"  # 최신 기기 필수
      - "armeabi-v7a"  # 구형 기기 지원
      - "x86"  # 에뮬레이터용
```

---

## 3. UI 자동화 관련 개선사항

### 3.1 씬 파일 직접 수정의 한계

**현재 문제점:**
- Unity YAML 형식은 FileID 참조가 복잡
- 직접 수정 시 참조 깨짐 위험
- 사용자가 "씬에 직접 추가해"라고 요청해도 한계 있음

**개선 제안:**
```yaml
# db/rules/scene_modification.yaml
scene_modification:
  direct_edit:
    risk: "high"
    issues:
      - "FileID 충돌"
      - "참조 깨짐"
      - "Unity 버전 호환성"

  preferred_approach:
    method: "Editor Script"
    tools:
      - "EditorWindow"
      - "MenuItem"
      - "SerializedObject"
    auto_run:
      - "[InitializeOnLoad]"
      - "EditorApplication.delayCall"

  communication:
    user_request: "씬에 직접 추가해"
    response: |
      Unity 씬 파일 직접 수정은 위험합니다.
      대신 Editor 스크립트를 생성하여 메뉴에서 실행하면
      자동으로 UI가 추가됩니다.
      메뉴: [MenuPath] 실행하세요.
```

### 3.2 UI 컴포넌트 자동 생성 패턴

**추가해야 할 템플릿:**
```csharp
// db/base/generic/Editor/PopupCreatorTemplate.cs
/*
 * Layer: Core
 * Genre: Generic
 * Role: Helper
 * Tags: [FlowControl, Spawn]
 *
 * UI 팝업 자동 생성 에디터 도구 템플릿
 */
public class PopupCreatorTemplate : EditorWindow
{
    // SerializedObject를 통한 필드 연결 패턴
    // MenuItem 등록 패턴
    // Canvas/UI 요소 동적 생성 패턴
}
```

---

## 4. 에러 처리 및 디버깅 개선

### 4.1 빌드 에러 자동 분석

**추가해야 할 규칙:**
```yaml
# db/rules/build_error_patterns.yaml
android_build_errors:
  manifest_merger:
    pattern: "Manifest merger failed"
    sub_patterns:
      namespace_conflict:
        pattern: "Namespace .* used in: .*, .*"
        cause: "동일 네임스페이스의 플러그인 중복"
        solution: "중복 플러그인 중 하나 삭제"

      min_sdk_conflict:
        pattern: "minSdkVersion .* cannot be smaller than"
        cause: "라이브러리가 더 높은 SDK 버전 요구"
        solution: "ProjectSettings에서 minSdkVersion 상향"
        extract_version: "version (\\d+) declared in library"

  gradle_errors:
    duplicate_class:
      pattern: "Duplicate class .* found"
      cause: "동일 클래스가 여러 라이브러리에 존재"
      solution: "충돌하는 라이브러리 제거 또는 exclude"
```

### 4.2 에디터 로그 분석 자동화

**개선 제안:**
```yaml
# 워크플로우에 추가
build_debugging:
  log_locations:
    windows: "C:\\Users\\{user}\\AppData\\Local\\Unity\\Editor\\Editor.log"
    mac: "~/Library/Logs/Unity/Editor.log"

  analysis_strategy:
    1: "로그 끝부분부터 읽기 (최근 에러)"
    2: "FAILED, error, Error 키워드 검색"
    3: "exit code: 1 이후 스택트레이스 분석"
    4: "known_errors DB와 매칭"
```

---

## 5. 프리팹/에셋 수정 관련

### 5.1 프리팹 스케일 조정 가이드

**현재 문제점:**
- 프리팹 스케일 변경 시 관련 컴포넌트(Collider 등) 누락
- 사용자 피드백 "작다/크다"에 대한 기준 불명확

**개선 제안:**
```yaml
# db/rules/prefab_scaling.yaml
prefab_scaling:
  related_components:
    - "BoxCollider"
    - "SphereCollider"
    - "CapsuleCollider"
    - "MeshCollider"

  scale_multiplier:
    "조금": 1.2
    "많이": 1.5
    "2배": 2.0

  adjustment_ratio:
    collider_size: "scale과 동일 비율"
    collider_center: "scale 비율에 맞게 조정"

  example:
    before:
      scale: 0.4
      collider_size: [0.6, 0.4, 0.8]
      collider_center: [0, 0.2, 0]
    after:
      scale: 0.7
      collider_size: [1.05, 0.7, 1.4]  # 0.6*(0.7/0.4)
      collider_center: [0, 0.35, 0]   # 0.2*(0.7/0.4)
```

---

## 6. 워크플로우 통합 제안

### 6.1 Phase 3 (코드 생성) 확장

**현재:**
```
AI_기획서 → DB 검색 → 코드 생성 → 자가 검증 → 피드백 반영
```

**개선:**
```
AI_기획서 → DB 검색 → 코드 생성 → 자가 검증 → 빌드 검증 → 피드백 반영
                                              ↓
                                    SDK 호환성 검사
                                    Gradle 설정 검사
                                    아키텍처 검사
                                    플러그인 충돌 검사
```

### 6.2 신규 Phase 추가: SDK 통합

```yaml
# Phase 2.5: SDK Integration
sdk_integration_phase:
  inputs:
    - "게임 기획서"
    - "필요 SDK 목록"

  steps:
    1_compatibility_check:
      - "SDK 버전 호환성 확인"
      - "minSdkVersion 결정"
      - "플러그인 충돌 검사"

    2_installation:
      - "SDK 다운로드"
      - ".unitypackage 임포트"
      - "설정 파일 배치"

    3_wrapper_generation:
      - "Manager 클래스 생성"
      - "조건부 컴파일 적용"
      - "시뮬레이션 모드 포함"

    4_verification:
      - "컴파일 확인"
      - "에디터 실행 확인"
      - "빌드 테스트"

  outputs:
    - "SDK Manager 클래스들"
    - "Android/iOS 설정 파일"
    - "빌드 설정 (minSdk 등)"
```

---

## 7. DB 확장 제안

### 7.1 신규 DB 카테고리

```
E:\AI\db\
├── base\
├── expert\
├── rules\
│   ├── sdk_compatibility.yaml    # 신규
│   ├── android_build.yaml        # 신규
│   ├── build_error_patterns.yaml # 신규
│   └── prefab_scaling.yaml       # 신규
└── templates\                    # 신규
    ├── FirebaseManager.cs
    ├── AdMobManager.cs
    ├── IAPManager.cs
    └── PopupCreatorTemplate.cs
```

### 7.2 에러 패턴 DB

```yaml
# db/rules/known_errors.yaml
errors:
  - id: "CS0246_FIREBASE"
    pattern: "CS0246.*Firebase"
    cause: "Firebase SDK 미설치"
    solutions:
      - "Firebase Unity SDK 설치"
      - "조건부 컴파일 적용"

  - id: "MANIFEST_NAMESPACE_CONFLICT"
    pattern: "Namespace .* used in:"
    cause: "Android 플러그인 중복"
    solutions:
      - "중복 .aar 또는 .androidlib 삭제"

  - id: "MIN_SDK_CONFLICT"
    pattern: "minSdkVersion .* cannot be smaller"
    cause: "라이브러리 SDK 버전 요구사항"
    solutions:
      - "ProjectSettings에서 minSdkVersion 상향"
```

---

## 8. 커뮤니케이션 개선

### 8.1 사용자 요청 해석 패턴

```yaml
user_request_patterns:
  "씬에 직접 추가해":
    interpretation: "UI 요소를 씬에 배치"
    limitation: "YAML 직접 수정 위험"
    response: "Editor 스크립트로 대체 제안"

  "빌드가 안 돼":
    interpretation: "빌드 에러 발생"
    action: "Editor.log 분석"
    log_path: "AppData\\Local\\Unity\\Editor\\Editor.log"

  "설치가 안 돼":
    interpretation: "APK 설치 실패"
    common_causes:
      - "아키텍처 미스매치"
      - "서명 문제"
      - "minSdkVersion"

  "작아/커":
    interpretation: "스케일 조정 필요"
    clarify: "어떤 오브젝트? 얼마나?"
    default_adjustment: 1.5x
```

---

## 9. 즉시 적용 가능한 액션 아이템

### 우선순위 높음
1. `sdk_compatibility.yaml` 생성 및 CLAUDE.md에 참조 추가
2. `build_error_patterns.yaml` 생성
3. `BuildValidator.cs` 템플릿 생성

### 우선순위 중간
4. SDK Manager 템플릿들 DB에 추가
5. 아키텍처 설정 가이드 문서화
6. 에디터 로그 분석 자동화 스크립트

### 우선순위 낮음
7. UI 자동 생성 도구 템플릿화
8. 프리팹 스케일링 규칙 정립
9. 사용자 요청 해석 패턴 DB화

---

## 10. 결론

이번 CarMatch 프로젝트에서 가장 많은 시간이 소요된 부분:
1. **SDK 통합 및 호환성 문제** (40%)
2. **Android 빌드 설정 문제** (30%)
3. **UI 씬 수정 요청 처리** (20%)
4. **기타** (10%)

워크플로우 개선을 통해 이러한 반복적인 문제를 사전에 방지하고,
빌드 성공률을 높일 수 있습니다.
