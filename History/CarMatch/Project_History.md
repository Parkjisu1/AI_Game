# CarMatch 프로젝트 개발 히스토리

## 프로젝트 개요
- **프로젝트명**: CarMatch (자동차 매칭 퍼즐 게임)
- **엔진**: Unity 2021.3.45f2
- **플랫폼**: Android
- **개발 기간**: 2026-02-04 ~ 2026-02-12

---

## 1. 구현된 기능 목록

### 1.1 SDK 연동
| 기능 | 파일 | 상태 |
|------|------|------|
| Firebase Analytics | FirebaseManager.cs | 완료 |
| Firebase Cloud Messaging (Push) | FirebaseManager.cs | 완료 |
| Google AdMob | AdMobManager.cs | 완료 |
| Unity IAP | IAPManager.cs | 완료 |

### 1.2 UI 시스템
| 기능 | 파일 | 상태 |
|------|------|------|
| SettingsPopup (BGM, SFX, Vibration, Notification) | SettingsPopup.cs | 완료 |
| SettingsPopup (Support, Terms, Privacy 버튼) | SettingsPopup.cs | 완료 |
| LeaderboardPopup (Journey 스타일) | LeaderboardPopup.cs | 완료 |
| Journey 보상 시스템 | DataManager.cs, GameData.cs | 완료 |

### 1.3 게임플레이
| 기능 | 파일 | 상태 |
|------|------|------|
| Tunnel Spawner 기믹 (레벨 20+) | TunnelController.cs (신규), BoardManager.cs, LevelManager.cs, StageStateHandler.cs, GameData.cs, GameEnums.cs, EventBus.cs | 완료 |
| 합체 연출 개선 (공중 합체) | CarController.cs (PlayMergeEffect) | 완료 |
| 고스트 카 버그 수정 | CarController.cs (PlayMatchEffect, PlayMergeEffect) | 완료 |

### 1.4 에디터 도구
| 기능 | 파일 | 상태 |
|------|------|------|
| PopupUICreator (팝업 자동 생성) | Editor/PopupUICreator.cs | 완료 |
| AutoPopupSetup (기존 팝업 자동 설정) | Editor/AutoPopupSetup.cs | 완료 |
| Tunnel 프리팹/머티리얼 자동 생성 | Editor/SceneBuilder.cs (CreateTunnelPrefab) | 완료 |
| CarType 6종 서브프리팹 자동 생성 | Editor/SceneBuilder.cs (CreateCarPrefab) | 완료 |

---

## 2. 발생한 이슈 및 해결 과정

### 2.1 Firebase SDK 관련

#### 이슈 1: CS0246 Firebase 네임스페이스 에러
- **원인**: Firebase Unity SDK가 설치되지 않음
- **시도한 해결책**:
  1. `#if ENABLE_FIREBASE` 조건부 컴파일 → 실패 (using 문이 조건문 밖에 있음)
  2. 시뮬레이션 모드로 변경 → 임시 해결
  3. Firebase SDK 다운로드 및 설치 → 최종 해결
- **최종 해결**: Firebase Unity SDK 13.7.0 다운로드 후 .unitypackage 임포트

#### 이슈 2: firebase-unity-sdk-13.7.0.tar.gz는 소스코드
- **원인**: 사용자가 다운로드한 파일이 빌드된 SDK가 아닌 소스코드
- **해결**: dl.google.com에서 올바른 firebase_unity_sdk.zip 다운로드

#### 이슈 3: C 드라이브 용량 부족
- **원인**: 다운로드 폴더가 C 드라이브에 있음
- **해결**: E:\AI\firebase_sdk\ 경로에 추출

#### 이슈 4: CS0117 ParameterItemId 에러
- **원인**: Firebase SDK 버전에서 `FirebaseAnalytics.ParameterItemId` 상수 없음
- **해결**: `"item_id"` 문자열 리터럴로 대체

### 2.2 빌드 관련

#### 이슈 5: Google Mobile Ads 네임스페이스 충돌
```
Namespace 'com.google.unity.ads' used in:
:googlemobileads-unity:, :unityLibrary:GoogleMobileAdsPlugin.androidlib
```
- **원인**: `googlemobileads-unity.aar`와 `GoogleMobileAdsPlugin.androidlib` 중복
- **해결**: `googlemobileads-unity.aar` 파일 삭제

#### 이슈 6: minSdkVersion 충돌
```
uses-sdk:minSdkVersion 22 cannot be smaller than version 23
declared in library [com.google.firebase:firebase-messaging:25.0.1]
```
- **원인**: Firebase Messaging 25.0.1이 SDK 23 이상 요구
- **해결**: `AndroidMinSdkVersion: 22` → `24`로 변경

#### 이슈 7: BlueStacks 설치 불가
- **원인**: APK에 x86 아키텍처 미포함 (BlueStacks는 x86 에뮬레이터)
- **분석**:
  - `AndroidTargetArchitectures: 1` (ARMv7만)
  - gradle에서 모든 아키텍처 exclude
- **해결**:
  - `AndroidTargetArchitectures: 7` (ARMv7 + ARM64 + x86)
  - packagingOptions에서 arm64, x86, x86_64 제외 해제

### 2.3 UI/UX 관련

#### 이슈 8: Puzzle 씬 자동차 크기 작음
- **원인**: Car.prefab의 Model 스케일이 0.4
- **해결**: 스케일 0.4 → 0.7로 변경, BoxCollider도 비율 조정

### 2.4 UX 폴리시 (2026-02-11)

#### 이슈 9: 고스트 카 버그 — 매칭 후 원래 위치에 차가 1프레임 보임
- **원인**: `PlayMatchEffect`/`PlayMergeEffect` 완료 → `onComplete` → ObjectPool.Return → `OnDespawn()`에서 `localScale = Vector3.one` 리셋 → 1프레임 동안 scale 1로 보임
- **해결**: PlayMatchEffect/PlayMergeEffect 끝에 `gameObject.SetActive(false)` 추가 (풀 반환 전에 비활성화)

#### 이슈 10: 합체 연출 밋밋함
- **원인**: 기존에는 단순 scale 0→1→0 연출만 존재
- **해결**: 양옆 차량이 가운데 차 위치 + Vector3.up*0.5f로 날아감 → 커짐(1.3f) → 작아지며 사라짐(InBack). 가운데 차량은 DOPunchScale → DOScale(0)

#### 이슈 11: Main 씬 팝업 토글 미동작
- **원인**: MainPage.OnSettingsClick/OnCoinButtonClick이 항상 Show() 호출 (activeSelf 체크 없음). levelButton, coinButton, bottomBarController SerializedField 미연결
- **해결**: activeSelf 체크로 토글 동작 구현 + SceneBuilder에서 누락 필드 연결

#### 이슈 12: Main 씬 텍스트 세로로 길게 늘어남
- **원인**: CreateTMPText가 StretchRect(부모 채움)로 생성 + enableWordWrapping=true → 좁은 레이아웃에서 글자별 줄바꿈
- **해결**: `enableWordWrapping = false`, `enableAutoSizing = true`, `fontSizeMin = 10`, `fontSizeMax = FONT_H2`, `overflowMode = Ellipsis`

#### 이슈 13: Settings 팝업 버튼 기능 없음
- **원인**: CreateSettingsPopupPortrait에서 토글 버튼(bgmButton, sfxButton 등)을 SettingsPopup의 SerializedField에 연결하지 않음
- **해결**: CreateSettingsToggleRow 반환값을 캡처하여 모든 버튼/아이콘 SerializedProperty 연결

#### 이슈 14: CreateCarPrefab NullReferenceException (SceneBuilder.cs:485)
- **원인**: SceneBuilder가 CarController에 없는 필드(bodyRenderer, topRenderer, colorMaterials)를 FindProperty로 접근 → null 반환
- **실제 CarController 필드**: carTypePrefabs(GameObject[6]), modelParent(Transform), selectHighlight(GameObject), moveSpeed(float)
- **해결**: CreateCarPrefab 전면 재작성 — 6종 CarType 서브프리팹(FBX별) 생성 + 실제 필드에 맞게 SerializedProperty 연결

### 2.5 코드 리뷰 기반 전체 개선 (2026-02-12)

전체 코드 리뷰 결과 Critical 5건 + High 18건 + Medium ~60건 발견.
Agent Team (Main Coder + Sub Coder x2) 병렬 수정, 3 Phase로 진행.

#### Phase 1: Critical + Core 안정화

#### 이슈 15: DataManager.SetLevelCleared() 배열 범위 미검증
- **원인**: levelId가 levelStars[200] 범위를 벗어나면 IndexOutOfRangeException
- **해결**: bounds check `if (levelId < 0 || levelId >= _userData.levelStars.Length) return;` 추가

#### 이슈 16: DataManager Journey 보상 인덱스 inline 계산 반복
- **원인**: `(milestoneLevel / 5) - 1` 계산이 여러 메서드에 분산, 범위 검증 누락
- **해결**: `GetJourneyRewardIndex()` private 헬퍼로 추출 + bounds 검증 통합

#### 이슈 17: ObjectPool.Get() CreateInstance 후 null 미체크
- **원인**: 프리팹이 파괴된 경우 CreateInstance가 null 반환 → SetParent에서 NullRef
- **해결**: `if (obj == null) return null;` null guard 추가

#### 이슈 18: BoosterProcessor Stack 기반 이력 관리 비효율
- **원인**: 기존 Stack 트림 시 double-stack reversal 필요, UseUndo에서 파괴된 car 미검증
- **해결**: List 기반으로 변환, `while (_moveHistory.Count > 50)` 트림, `record.car.gameObject == null` 검증 추가, UseMagnet에 홀더 용량 체크

#### 이슈 19: ResultPopup Time.timeScale 미복원
- **원인**: ResultPopup이 `Time.timeScale = 0f` 설정 후 OnDestroy 시 복원 안 함
- **해결**: `OnDestroy()` 추가 → `Time.timeScale = 1f`

#### 이슈 20: ShopPopup onClick 리스너 누적
- **원인**: ClearContent()에서 버튼 리스너 정리 없이 Destroy만 호출
- **해결**: `btn.onClick.RemoveAllListeners()` 호출 후 Destroy

#### Phase 2: High 이슈 병렬 수정

#### 이슈 21: PathFinder openList Sort 매 반복 O(n log n)
- **원인**: `List<Node>` + `.Sort()` + `.Find()` → 비효율적 탐색
- **해결**: `Dictionary<Vector2Int, Node>` + linear min scan + `.TryGetValue()` O(1) 조회

#### 이슈 22: StageStateHandler Pause/Resume에서 DOTween 미일시정지
- **원인**: `Time.timeScale = 0f`만 설정, DOTween 트윈은 계속 실행
- **해결**: Pause에 `DOTween.PauseAll()`, Resume에 `DOTween.PlayAll()` 추가

#### 이슈 23: HolderController DOVirtual.DelayedCall fire-and-forget
- **원인**: L201, L269의 DelayedCall이 필드에 저장 안 됨 → Clear() 시 콜백이 파괴된 객체 참조
- **해결**: `_holderFullCheckTween`, `_matchRearrangeTween` 필드에 저장 + Clear()에서 Kill

#### 이슈 24: BoardManager.FindNearestBoardExit 전수 A* 탐색
- **원인**: y=0 모든 위치에 A* 실행 → 그리드 크기에 비례하는 성능 문제
- **해결**: 현재 x 우선 체크 → 좌우 확장 + Manhattan distance 하한 기반 조기 탈출

#### 이슈 25: CarController 트윈/경로 리스트 미캐싱
- **원인**: MoveAlongPath 호출마다 새 List 생성, PlayMatchEffect 트윈 미저장
- **해결**: `_cachedWaypoints` 필드 재사용, `_matchTween` 필드에 저장

#### 이슈 26: TunnelController DOVirtual 트윈 미관리
- **원인**: 스폰 딜레이 트윈이 fire-and-forget → Cleanup 시 콜백 실행 가능
- **해결**: `_spawnTweens` 리스트에 저장 + Cleanup에서 Kill

#### 이슈 27: EventBus Unsubscribe 후 빈 딕셔너리 키 잔류
- **원인**: 핸들러 전부 제거 후에도 빈 리스트가 딕셔너리에 남음
- **해결**: `if (_handlers[eventName].Count == 0) _handlers.Remove(eventName);`

#### 이슈 28: TitlePage OnDestroy 코루틴 미정리
- **원인**: 씬 언로드 시 실행 중인 코루틴이 파괴된 객체 참조 가능
- **해결**: OnDestroy 첫 줄에 `StopAllCoroutines()` 추가

#### 이슈 29: HolderWarningEffect .material 직접 접근 Material 인스턴스 누수
- **원인**: `.material` 프로퍼티 접근마다 새 Material 인스턴스 생성
- **해결**: `_cachedMaterials[]`에 1회 캐싱 + OnDestroy에서 `Destroy(_cachedMaterials[i])`

#### 이슈 30: DailyPopup Update 매 프레임 타이머 갱신
- **원인**: 타이머 텍스트를 매 프레임 업데이트 → 불필요한 문자열 생성
- **해결**: `_lastUpdateTime` + `Time.time` 비교로 1초 주기 갱신

#### 이슈 31: UIBase Hide() 이중 호출 시 DOTween 충돌
- **원인**: Hide() 연속 호출 시 fade 트윈 중복 → OnComplete 꼬임
- **해결**: `_isHiding` 플래그로 이중 호출 방지, Show()에서 리셋

#### Phase 3: Medium 이슈

#### 이슈 32: GameData.levelStars 고정 배열 안전 접근 부재
- **원인**: `int[200]` 직접 접근 시 범위 초과 가능
- **해결**: `GetLevelStarsSafe(int levelId)` bounds-safe 헬퍼 메서드 추가

#### 이슈 33: ShopBundleData itemType 매직 스트링
- **원인**: "undo", "shuffle", "adFree" 등 문자열 직접 사용 → 오타 위험
- **해결**: `BonusItemTypes` static class에 const 문자열 정의

#### 이슈 34: MoveValidator BFS 도달성 매번 재계산
- **원인**: CanCollect 호출마다 BFS 전체 재실행
- **해결**: `_reachabilityCache` Dictionary + `InvalidateCache()` 메서드 추가

#### 이슈 35: AdMobManager 광고 로드 실패 시 재시도 없음
- **원인**: 광고 로드 1회 실패 시 그대로 종료
- **해결**: `MaxRetryCount = 3`, `RetryDelays = {5f, 15f, 30f}` 지수 백오프 재시도

#### 이슈 36: FirebaseManager 초기화 타임아웃 없음
- **원인**: Firebase 초기화가 무한 대기할 수 있음
- **해결**: `_initTimeoutCoroutine` 10초 타임아웃 추가

---

## 3. 주요 파일 변경 내역

### 3.1 신규 생성 파일
```
Assets/1.Scripts/SDK/FirebaseManager.cs
Assets/Editor/PopupUICreator.cs
Assets/Editor/AutoPopupSetup.cs
Assets/1.Scripts/Controller/TunnelController.cs     (2026-02-11) Tunnel Spawner 기믹
Assets/Resources/Prefabs/CarTypes/CarType_0~5.prefab (2026-02-11) 6종 차량 서브프리팹 (SceneBuilder 자동 생성)
```

### 3.2 수정된 파일
```
Assets/1.Scripts/Page/SettingsPopup.cs - Support/Terms/Privacy 버튼 추가
Assets/1.Scripts/Page/LeaderboardPopup.cs - Journey 스타일로 전면 재작성
Assets/1.Scripts/Manager/DataManager.cs - Journey 보상 시스템 추가
Assets/1.Scripts/Data/GameData.cs - JourneyRewardData 클래스 추가, TunnelSpawnData 추가(2/11)
Assets/Resources/Prefabs/Car.prefab - 스케일 확대
Assets/Plugins/Android/mainTemplate.gradle - 아키텍처 exclude 수정
ProjectSettings/ProjectSettings.asset - minSdkVersion, targetArchitectures 변경

--- 2026-02-11 추가 ---
Assets/1.Scripts/Enums/GameEnums.cs - ObstacleType.Tunnel 추가
Assets/1.Scripts/Data/GameData.cs - TunnelSpawnData 클래스, LevelData.tunnels 필드 추가
Assets/1.Scripts/Core/EventBus.cs - OnTunnelSpawn 이벤트 추가
Assets/1.Scripts/Controller/CarController.cs - PlayMergeEffect 공중합체, SetActive(false) 고스트카 수정
Assets/1.Scripts/Manager/BoardManager.cs - 터널 스폰/관리/정리, IsBoardCleared 터널 포함
Assets/1.Scripts/Manager/LevelManager.cs - 레벨 20+ 터널 자동 생성, GenerateTunnelData
Assets/1.Scripts/Handler/StageStateHandler.cs - GetProgress 터널 차량 포함
Assets/1.Scripts/Page/MainPage.cs - 팝업 토글 동작 수정
Assets/Editor/SceneBuilder.cs - CreateCarPrefab 재작성(CarType 서브프리팹), CreateTunnelPrefab 추가, 터널 머티리얼, Main씬 필드 연결 수정, CreateTMPText 텍스트 늘어남 수정, CreateSettingsPopupPortrait 버튼 연결

--- 2026-02-12 코드 리뷰 개선 (34파일) ---
# Phase 1: Critical
Assets/1.Scripts/Manager/DataManager.cs - SetLevelCleared bounds check, GetJourneyRewardIndex 헬퍼
Assets/1.Scripts/Core/ObjectPool.cs - Get() null check after CreateInstance
Assets/1.Scripts/Processor/BoosterProcessor.cs - List 기반 history, car 검증, Magnet 용량 체크
Assets/1.Scripts/Page/ResultPopup.cs - OnDestroy Time.timeScale=1f 복원
Assets/1.Scripts/Page/ShopPopup.cs - ClearContent RemoveAllListeners

# Phase 2: High
Assets/1.Scripts/Logic/PathFinder.cs - openList → Dictionary, linear min scan
Assets/1.Scripts/Handler/StageStateHandler.cs - DOTween.PauseAll/PlayAll
Assets/1.Scripts/Controller/HolderController.cs - Tween 필드 저장 + Clear Kill
Assets/1.Scripts/Manager/BoardManager.cs - FindNearestBoardExit 최적화
Assets/1.Scripts/Controller/CarController.cs - _matchTween, _cachedWaypoints 캐시
Assets/1.Scripts/Controller/TunnelController.cs - _spawnTweens 리스트 관리
Assets/1.Scripts/Base/Singleton.cs - lock 불필요 주석
Assets/1.Scripts/Core/EventBus.cs - Unsubscribe 빈 키 제거
Assets/1.Scripts/Page/PuzzlePage.cs - null 체크 추가
Assets/1.Scripts/Page/TitlePage.cs - StopAllCoroutines in OnDestroy
Assets/1.Scripts/Page/PausePopup.cs - StageStateHandler 위임
Assets/1.Scripts/UX/HolderWarningEffect.cs - .material 캐싱 + OnDestroy 정리
Assets/1.Scripts/Page/ProfilePopup.cs - OnDestroy null 정리
Assets/1.Scripts/Page/DailyPopup.cs - 타이머 1초 주기 갱신
Assets/1.Scripts/Manager/SceneLoader.cs - 코루틴 핸들 저장
Assets/1.Scripts/UI/InfiniteScroll.cs - 풀 재사용 주석

# Phase 3: Medium
Assets/1.Scripts/Data/GameData.cs - GetLevelStarsSafe 헬퍼
Assets/1.Scripts/Data/ShopData.cs - IReadOnlyList + lookup 헬퍼
Assets/1.Scripts/Data/ShopBundleData.cs - BonusItemTypes 상수
Assets/1.Scripts/Logic/MoveValidator.cs - 도달 캐시 + InvalidateCache
Assets/1.Scripts/Logic/ScoreCalculator.cs - null 체크 확인
Assets/1.Scripts/Controller/StorageController.cs - DOKill + null-safe RetrieveCar
Assets/1.Scripts/UI/UIBase.cs - _isHiding 이중 호출 방지
Assets/1.Scripts/SDK/AdMobManager.cs - 재시도 로직 (지수 백오프)
Assets/1.Scripts/SDK/FirebaseManager.cs - 초기화 타임아웃
Assets/1.Scripts/Page/SettingsPopup.cs - FirebaseManager null 안전
Assets/1.Scripts/Page/LeaderboardPopup.cs - MilestoneItemUI null 체크
Assets/1.Scripts/Page/EditProfilePopup.cs - AvatarButton null 안전
Assets/1.Scripts/UI/BottomBarController.cs - ResetButtonStates in Start
```

### 3.3 삭제된 파일
```
Assets/Plugins/Android/googlemobileads-unity.aar - 중복 플러그인
Assets/1.Scripts/Page/JourneyPopup.cs - LeaderboardPopup과 중복
```

---

## 4. 기술 스택 및 버전

| 항목 | 버전/값 |
|------|---------|
| Unity | 2021.3.45f2 |
| Firebase Unity SDK | 13.7.0 |
| Google Mobile Ads | 23.0.0 |
| Unity IAP | 4.9.4 |
| DOTween | 사용 중 |
| TextMeshPro | 3.0.6 |
| Android minSdkVersion | 24 |
| Android targetArchitectures | ARMv7 + ARM64 + x86 |

---

## 5. 프로젝트 구조

```
Assets/
├── 0.Scenes/
│   ├── Main.unity
│   ├── Puzzle.unity
│   └── SceneMaker.unity
├── 1.Scripts/
│   ├── Base/
│   │   └── Singleton.cs
│   ├── Controller/
│   │   ├── CarController.cs
│   │   ├── HolderController.cs
│   │   ├── ObstacleController.cs
│   │   └── TunnelController.cs      ← NEW (2/11)
│   ├── Core/
│   │   ├── EventBus.cs
│   │   └── ObjectPool.cs
│   ├── Data/
│   │   └── GameData.cs
│   ├── Enums/
│   │   └── GameEnums.cs
│   ├── Handler/
│   │   └── StageStateHandler.cs
│   ├── Logic/
│   │   ├── MoveValidator.cs
│   │   └── PathFinder.cs
│   ├── Manager/
│   │   ├── BoardManager.cs
│   │   ├── DataManager.cs
│   │   ├── LevelManager.cs
│   │   └── SceneLoader.cs
│   ├── Page/
│   │   ├── MainPage.cs
│   │   ├── PuzzlePage.cs
│   │   ├── TitlePage.cs
│   │   ├── PausePopup.cs
│   │   ├── ResultPopup.cs
│   │   ├── ShopPopup.cs
│   │   ├── DailyPopup.cs
│   │   ├── ProfilePopup.cs
│   │   ├── EditProfilePopup.cs
│   │   ├── SettingsPopup.cs
│   │   └── LeaderboardPopup.cs
│   ├── Processor/
│   │   └── BoosterProcessor.cs
│   ├── SDK/
│   │   ├── FirebaseManager.cs
│   │   ├── AdMobManager.cs
│   │   └── IAPManager.cs
│   ├── UI/
│   │   ├── UIBase.cs
│   │   ├── InfiniteScroll.cs
│   │   └── BottomBarController.cs
│   └── UX/
│       └── HolderWarningEffect.cs
├── Editor/
│   ├── SceneBuilder.cs
│   ├── PopupUICreator.cs
│   └── AutoPopupSetup.cs
├── Plugins/
│   └── Android/
│       ├── AndroidManifest.xml
│       ├── mainTemplate.gradle
│       ├── gradleTemplate.properties
│       ├── FirebaseApp.androidlib/
│       └── GoogleMobileAdsPlugin.androidlib/
└── Resources/
    ├── Materials/
    │   ├── CarMat_0~7.mat
    │   ├── ObstacleMat.mat
    │   ├── TunnelActiveMat.mat       ← NEW (2/11)
    │   └── TunnelEmptyMat.mat        ← NEW (2/11)
    ├── Prefabs/
    │   ├── Car.prefab
    │   ├── Obstacle.prefab
    │   ├── Tunnel.prefab             ← NEW (2/11)
    │   ├── Cell.prefab
    │   └── CarTypes/                 ← NEW (2/11)
    │       ├── CarType_0.prefab (Taxi)
    │       ├── CarType_1.prefab (TractorPolice)
    │       ├── CarType_2.prefab (Truck)
    │       ├── CarType_3.prefab (Firetruck)
    │       ├── CarType_4.prefab (GarbageTruck)
    │       └── CarType_5.prefab (HatchbackSports)
    └── Ref/
        └── cars/kenney_car-kit/      (FBX 모델)
```

---

## 6. 미구현 기능

| 기능 | 우선순위 | 비고 |
|------|----------|------|
| 시즌/이벤트 시스템 | 중 | 기간 한정 이벤트, 시즌 보상 |
| 서버 연결 (Backend) | 높음 | 유저 데이터 동기화, 클라우드 저장 |
| 소셜 로그인 | 중 | Google, Apple, Facebook |
| 실제 리더보드 | 중 | 서버 기반 글로벌/친구 랭킹 |
| 길드/클랜 시스템 | 낮음 | 멀티플레이어 기능 |

---

## 7. 테스트 체크리스트

### 빌드 전 확인사항
- [ ] Firebase google-services.json 설정 확인
- [ ] AdMob App ID 실제 값으로 변경
- [ ] Package Name 확인 (com.carmatch.game)
- [ ] minSdkVersion >= 24
- [ ] Target Architectures 설정 확인

### 런타임 테스트
- [ ] Firebase 초기화 로그 확인
- [ ] Push Notification 수신 테스트
- [ ] 광고 로드/표시 테스트
- [ ] IAP 구매 테스트 (Sandbox)
- [ ] Settings 토글 동작 확인
- [ ] Journey 보상 수령 테스트

### 2026-02-11 추가 테스트
- [ ] 차량 3대 매칭 → 합체 연출 확인 (양옆이 가운데 위로 날아감)
- [ ] 합체 완료 후 고스트 카 없음 확인
- [ ] Main 씬 팝업 토글: 같은 버튼 → 닫힘, 다른 버튼 → 전환
- [ ] Main 씬 텍스트 정상 가로 표시 (세로 늘어남 없음)
- [ ] Settings 팝업 BGM/SFX/진동/알림 토글 동작
- [ ] 레벨 20+ 터널 오브젝트 보드에 표시
- [ ] 터널에서 차량 소환 → 출구 막힘 시 대기 → 빈 칸 소환 재개
- [ ] 터널 차량 포함 전체 클리어 가능
- [ ] 기존 레벨 (1~19) 정상 동작 (터널 없음)
- [ ] Force Rebuild All 에러 없이 완료

### 2026-02-12 코드 리뷰 개선 후 테스트
#### Critical 수정 확인
- [ ] 레벨 200 이상 levelId로 SetLevelCleared 호출 시 크래시 없음
- [ ] ObjectPool에서 프리팹 파괴 후 Get() 호출 → null 반환 (크래시 없음)
- [ ] Undo 부스터 사용 시 파괴된 차량 → false 반환 (크래시 없음)
- [ ] Magnet 부스터: 홀더 용량 초과 시 사용 불가
- [ ] ResultPopup 표시 후 씬 전환 → Time.timeScale == 1f 확인
- [ ] ShopPopup 반복 열기/닫기 → 메모리 누수 없음

#### High 수정 확인
- [ ] PathFinder 경로 탐색 성능: 큰 그리드에서 체감 개선
- [ ] Pause → Resume 시 DOTween 애니메이션 정상 재개
- [ ] 홀더 꽉 찬 상태에서 Clear() → 콜백 에러 없음
- [ ] 매칭 중 Clear() 호출 시 NullReferenceException 없음
- [ ] 터널 스폰 중 Cleanup() → 콜백 에러 없음
- [ ] 씬 전환 시 TitlePage 코루틴 정리 확인 (에러 로그 없음)
- [ ] HolderWarningEffect: 경고 반복 발생 시 Material leak 없음
- [ ] DailyPopup: Update에서 매 프레임 문자열 생성 없음 (Profiler 확인)

#### Medium 수정 확인
- [ ] UIBase.Hide() 빠른 연속 클릭 → 이중 호출 방지 확인
- [ ] 광고 로드 실패 → 재시도 로그 확인 (최대 3회)
- [ ] Firebase 초기화 지연 시 10초 후 시뮬레이션 모드 전환
- [ ] BottomBar 초기 상태: Home 버튼 선택, 나머지 normal 스케일
