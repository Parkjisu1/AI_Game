# Drop the Cat - Architecture Reference

> Phase 0 Core 시스템 기반으로 작성. Sub Coder는 반드시 이 문서를 먼저 읽고 패턴을 따를 것.

---

## Namespace 규칙

```
DropTheCat.Core     → Phase 0 Core 시스템 (Singleton, EventManager, ObjectPool, SaveManager, SoundManager)
DropTheCat.Domain   → Phase 1~2 Domain 시스템 (GridManager, CatController, SlideProcessor 등)
DropTheCat.Game     → Phase 3 Game Layer (GameManager, Pages, Popups)
```

- 모든 클래스는 반드시 위 네임스페이스 중 하나에 속해야 함
- Core의 enum/struct는 `DropTheCat.Core` 네임스페이스에 정의됨 (EventManager.cs 하단)

---

## Singleton 패턴

모든 Manager 클래스는 `Singleton<T>`를 상속합니다.

```csharp
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    public class GridManager : Singleton<GridManager>
    {
        protected override void OnSingletonAwake()
        {
            // Awake() 대신 이 메서드를 오버라이드
        }
    }
}
```

**규칙:**
- `Awake()` 직접 오버라이드 금지 → `OnSingletonAwake()` 사용
- `Instance` 접근 시 null 체크 필수: `if (SomeManager.Instance == null) return;`
- `HasInstance` 프로퍼티로 존재 여부 확인 가능
- DontDestroyOnLoad 자동 적용됨

---

## Event System

타입 기반 이벤트 시스템. string 키 대신 struct 타입으로 이벤트를 구분합니다.

### 사용법

```csharp
// 구독
EventManager.Instance.Subscribe<OnCatDropped>(OnCatDroppedHandler);

// 발행
EventManager.Instance.Publish(new OnCatDropped
{
    CatColor = CatColor.Red,
    Position = new Vector2Int(3, 2)
});

// 해제 (OnDestroy에서 반드시!)
EventManager.Instance.Unsubscribe<OnCatDropped>(OnCatDroppedHandler);
```

**규칙:**
- Subscribe한 이벤트는 OnDestroy에서 반드시 Unsubscribe
- EventManager.Instance null 체크 후 호출

### 정의된 이벤트 목록

| Event Struct | 용도 | 필드 |
|---|---|---|
| `OnGridInitialized` | 그리드 초기화 완료 | Width, Height |
| `OnCellStateChanged` | 셀 상태 변경 | X, Y, OldState, NewState |
| `OnSlideComplete` | 타일 슬라이드 완료 | TileId, FromPos, ToPos, Direction |
| `OnMovePerformed` | 이동 수행됨 | (없음) |
| `OnCatDropped` | 고양이 드롭 | CatColor, Position |
| `OnLevelCleared` | 레벨 클리어 | MoveCount, Stars, CoinReward |
| `OnLevelFailed` | 레벨 실패 | Reason |
| `OnLevelLoaded` | 레벨 로드 | LevelNumber |
| `OnLevelProgressUpdated` | 진행도 업데이트 | MaxClearedLevel, TotalStars |
| `OnCoinChanged` | 코인 변경 | Balance, Delta |
| `OnMoveCountChanged` | 이동 횟수 변경 | MoveCount |
| `OnBoosterUsed` | 부스터 사용 | BoosterType |
| `OnBoosterCountChanged` | 부스터 수량 변경 | BoosterType, Count |
| `OnObstacleStateChanged` | 장애물 상태 변경 | X, Y, ObstacleType, NewState |
| `OnTileUnlocked` | 타일 잠금 해제 | X, Y |
| `OnGameStateChanged` | 게임 상태 전환 | NewState |

### 정의된 Enum 목록

| Enum | 값 |
|---|---|
| `CatColor` | Red, Blue, Green, Yellow, Purple, Orange, Pink, White, Black, Rainbow |
| `CellType` | Empty, Normal, Hole, Wall, Obstacle, Portal, Ice, Lock |
| `SlideDirection` | Up, Down, Left, Right |
| `ObstacleType` | None, Wall, Ice, Lock, Portal, Switch, OneWay |
| `GameState` | Title, Main, Loading, Playing, Paused, Result |
| `BoosterType` | Hint, Undo, Magnet, Shuffle |
| `FailReason` | TrapHole, OutOfMoves, PlayerQuit |
| `MatchResult` | Success, Fail, Trap |
| `CellState` | Empty, Occupied, Blocked |

---

## ObjectPool 사용법

```csharp
ObjectPool.Instance.PreWarm(catPrefab, 20);       // 초기화
var cat = ObjectPool.Instance.Get(catPrefab);       // 가져오기
ObjectPool.Instance.Release(cat);                   // 반환
ObjectPool.Instance.ReleaseAll();                   // 전체 반환
ObjectPool.Instance.ClearPool();                    // 풀 정리
```

**규칙:**
- `Instantiate()` / `Destroy()` 직접 호출 금지 → ObjectPool 사용
- 프리팹은 `[SerializeField]`로 Inspector에서 연결

---

## SaveManager 사용법

```csharp
SaveManager.Instance.SaveInt("MaxLevel", 42);
int maxLevel = SaveManager.Instance.LoadInt("MaxLevel", 0);
SaveManager.Instance.Save("PlayerData", playerData);
var data = SaveManager.Instance.Load<PlayerData>("PlayerData");
```

**규칙:**
- 키 이름은 PascalCase (접두사 `DTC_` 자동 추가됨)
- 복합 데이터는 `Save<T>` / `Load<T>` (JsonUtility)
- 단순 값은 `SaveInt` / `LoadInt` / `SaveFloat` / `LoadFloat`

---

## SoundManager 사용법

```csharp
SoundManager.Instance.PlayBGM("main_theme");
SoundManager.Instance.PlaySFX("cat_drop");
SoundManager.Instance.SetBGMVolume(0.8f);
SoundManager.Instance.ToggleSFXMute();
```

**규칙:**
- AudioClip은 Inspector에서 배열에 연결, clip.name으로 접근
- 볼륨/뮤트 설정은 SaveManager 통해 자동 저장/복원

---

## UI 분업 원칙

AI는 **로직 코드만** 생성. 비주얼은 사용자가 Unity Editor에서 담당.

```csharp
// GOOD
[SerializeField] private Button playButton;
[SerializeField] private Text scoreText;

// BAD - 금지
var panel = new GameObject("Panel");
panel.AddComponent<Image>();
```

---

## 코드 구조 템플릿

```csharp
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using DropTheCat.Core;

namespace DropTheCat.Domain  // or DropTheCat.Game
{
    /// <summary>
    /// {purpose}
    /// </summary>
    /// <remarks>
    /// Layer: {layer} | Genre: Puzzle | Role: {role} | Phase: {phase}
    /// </remarks>
    public class {NodeId} : Singleton<{NodeId}>  // Manager
    // public class {NodeId} : MonoBehaviour       // Controller/Handler
    {
        #region Fields
        #endregion

        #region Properties
        #endregion

        #region Unity Lifecycle
        // OnSingletonAwake() or Awake()
        // OnDestroy() - 이벤트 해제 필수
        #endregion

        #region Public Methods
        #endregion

        #region Private Methods
        #endregion
    }
}
```

---

## 금지 패턴

| 금지 | 대안 |
|------|------|
| God Class (1000줄+) | 역할 분리 |
| Magic Numbers | const / [SerializeField] |
| Deep Nesting (3단계+) | Early return |
| String Comparison | enum 사용 |
| Update() 남용 | 이벤트 기반 |
| new GameObject() + AddComponent | [SerializeField] |
| Find() / FindObjectOfType() | [SerializeField] 직접 참조 |
| Instantiate() / Destroy() 직접 | ObjectPool |

---

## 파일 출력 위치

```
E:\AI\projects\DropTheCat\output\{NodeId}.cs
```
