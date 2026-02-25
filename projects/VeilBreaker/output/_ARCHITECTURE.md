# VeilBreaker - Core Architecture Guide

Phase 0에서 생성된 Core 시스템의 규약 문서입니다.
Sub Coder는 이 문서를 반드시 참조하여 일관된 코드를 작성해야 합니다.

---

## 1. Namespace Rules

```
VeilBreaker.Core       - Phase 0 기반 시스템 (Singleton, EventManager, ObjectPool, Util, GameConstants)
VeilBreaker.Battle     - 전투 시스템 (BattleManager, DamageCalculator, WaveController 등)
VeilBreaker.Character  - 캐릭터/영웅 시스템 (HeroManager, StatCalculator, SkillController 등)
VeilBreaker.Idle       - 방치 수익 시스템 (IdleRewardManager, OfflineCalculator 등)
VeilBreaker.Inventory  - 장비/아이템 시스템 (EquipmentManager, EnhanceProcessor 등)
VeilBreaker.Gacha      - 뽑기 시스템 (GachaManager, PityTracker 등)
VeilBreaker.Quest      - 퀘스트 시스템 (QuestManager, QuestTracker 등)
VeilBreaker.Content    - 던전/타워 컨텐츠 (TowerManager, DungeonManager 등)
VeilBreaker.Economy    - 재화 시스템 (CurrencyManager 등)
VeilBreaker.Data       - 데이터/저장 (SaveManager, DataProvider 등)
VeilBreaker.UI         - UI 시스템 (Pages, Popups, Elements)
```

**규칙:**
- 모든 클래스는 반드시 namespace 안에 정의
- Core Layer는 `VeilBreaker.Core`, Domain Layer는 `VeilBreaker.{System}`, Game Layer는 `VeilBreaker.UI`
- using 문에서 Core 참조: `using VeilBreaker.Core;`

---

## 2. Event Key Constants (GameConstants.Events)

이벤트 키는 절대 하드코딩 문자열을 사용하지 않습니다. 반드시 `GameConstants.Events.*`를 참조합니다.

### Stage / Battle Flow
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnStageStart` | `"OnStageStart"` | `int stageId` |
| `Events.OnStageComplete` | `"OnStageComplete"` | `int stageId` |
| `Events.OnStageFail` | `"OnStageFail"` | `int stageId` |
| `Events.OnBossSpawn` | `"OnBossSpawn"` | `null` |
| `Events.OnWaveStart` | `"OnWaveStart"` | `int waveIndex` |
| `Events.OnWaveComplete` | `"OnWaveComplete"` | `int waveIndex` |

### Character / Hero
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnHeroDie` | `"OnHeroDie"` | `string heroId` |
| `Events.OnEnemyDie` | `"OnEnemyDie"` | `GameObject enemy` |
| `Events.OnCharacterLevelUp` | `"OnCharacterLevelUp"` | `(string heroId, int newLevel)` |
| `Events.OnCharacterStatChanged` | `"OnCharacterStatChanged"` | `string heroId` |

### Skill
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnSkillActivated` | `"OnSkillActivated"` | `(string heroId, int skillId)` |
| `Events.OnSkillCooldownComplete` | `"OnSkillCooldownComplete"` | `(string heroId, int skillId)` |

### Equipment
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnEquipmentChanged` | `"OnEquipmentChanged"` | `string heroId` |
| `Events.OnEquipmentEnhanced` | `"OnEquipmentEnhanced"` | `(string equipId, int newLevel)` |

### Currency / Economy
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnCurrencyChanged` | `"OnCurrencyChanged"` | `CurrencyType type` |
| `Events.OnGachaResult` | `"OnGachaResult"` | `List<string> heroIds` |

### Quest
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnQuestProgress` | `"OnQuestProgress"` | `string questId` |
| `Events.OnQuestComplete` | `"OnQuestComplete"` | `string questId` |

### Content
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnTowerFloorComplete` | `"OnTowerFloorComplete"` | `int floor` |
| `Events.OnDungeonComplete` | `"OnDungeonComplete"` | `string dungeonId` |

### Data / Save
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnDataLoaded` | `"OnDataLoaded"` | `null` |
| `Events.OnGameSaved` | `"OnGameSaved"` | `null` |
| `Events.OnOfflineRewardCalculated` | `"OnOfflineRewardCalculated"` | `(double gold, double exp)` |

### Monetization
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnAdWatched` | `"OnAdWatched"` | `string adType` |
| `Events.OnIAPPurchased` | `"OnIAPPurchased"` | `string productId` |

### UI
| Constant | Key | Payload |
|----------|-----|---------|
| `Events.OnPopupOpened` | `"OnPopupOpened"` | `string popupName` |
| `Events.OnPopupClosed` | `"OnPopupClosed"` | `string popupName` |
| `Events.OnPageChanged` | `"OnPageChanged"` | `string pageName` |

### 사용 예시
```csharp
// Subscribe
EventManager.Subscribe(GameConstants.Events.OnStageComplete, OnStageComplete);

// Publish
EventManager.Publish(GameConstants.Events.OnStageComplete, stageId);

// Unsubscribe (OnDisable에서)
EventManager.Unsubscribe(GameConstants.Events.OnStageComplete, OnStageComplete);

// Callback
private void OnStageComplete(object data)
{
    int stageId = (int)data;
    // handle...
}
```

---

## 3. Singleton Usage Pattern

### 기본 사용법
```csharp
using VeilBreaker.Core;

namespace VeilBreaker.Battle
{
    public class BattleManager : Singleton<BattleManager>
    {
        protected override void OnSingletonAwake()
        {
            // Awake 대신 여기서 초기화
        }
    }
}
```

### 규칙
- Core Manager 클래스는 반드시 `Singleton<T>` 상속
- `Awake()`를 override하지 말 것. 대신 `OnSingletonAwake()` 사용
- 접근: `BattleManager.Instance.Method()`
- 존재 확인: `if (BattleManager.HasInstance) { ... }`
- 씬에 수동 배치 (DontDestroyOnLoad 자동 적용)
- 코드에서 `new GameObject().AddComponent<T>()` 금지

### 주의사항
- `FindObjectOfType<T>()`는 Instance getter에서 Awake 전 접근 시 1회만 사용됨
- 매 프레임 호출 금지
- OnApplicationQuit 이후 Instance 접근 시 null 반환 (로그 출력)

---

## 4. ObjectPool Usage Convention

### 초기화 (Manager의 Start나 Init에서)
```csharp
ObjectPool.Instance.Init(GameConstants.PoolTags.DamageText, damageTextPrefab, 20);
ObjectPool.Instance.Init(GameConstants.PoolTags.HitEffect, hitEffectPrefab, 10);
```

### Spawn / Despawn
```csharp
// Spawn
var obj = ObjectPool.Instance.Spawn(GameConstants.PoolTags.HitEffect, position, Quaternion.identity);

// Despawn (Destroy 대신 항상 사용)
ObjectPool.Instance.Despawn(obj);
```

### 규칙
- Pool tag는 `GameConstants.PoolTags.*` 상수 사용
- `Destroy()` 대신 반드시 `ObjectPool.Instance.Despawn()` 사용
- 같은 tag로 중복 `Init()` 호출하지 않음 (자동 skip)
- 풀 오브젝트에는 `PoolTag` 컴포넌트가 자동 부착됨
- 동적 확장: 풀이 비면 자동으로 새 인스턴스 생성

---

## 5. Common Base Classes

### Singleton<T>
- **위치**: `VeilBreaker.Core.Singleton<T>`
- **용도**: 전역 Manager 클래스의 base
- **메서드**: `OnSingletonAwake()` (override), `HasInstance` (static)

### PoolTag
- **위치**: `VeilBreaker.Core.PoolTag`
- **용도**: ObjectPool에 의해 자동 부착. 수동 사용 불필요

---

## 6. Contract Writing Rules

### provides (제공하는 API)
```yaml
contract:
  provides:
    - "void Init()"                           # 초기화
    - "float CalculateDamage(HeroData, EnemyData)"  # 핵심 기능
    - "bool IsReady { get; }"                  # 상태 프로퍼티
  requires:
    - "Singleton"                              # 상속
    - "EventManager"                           # 이벤트 구독/발행
    - "GameConstants"                          # 상수 참조
```

### 규칙
- `provides`: 다른 시스템이 호출할 수 있는 public 메서드/프로퍼티
- `requires`: 이 시스템이 의존하는 다른 시스템
- Contract에 명시된 시그니처는 코드에서 정확히 일치해야 함
- provides에 없는 public 메서드는 최소화 (내부 로직은 private)

---

## 7. Coding Conventions

### Naming
| 항목 | 규칙 | 예시 |
|------|------|------|
| Class | PascalCase | `BattleManager` |
| Public Method | PascalCase | `CalculateDamage()` |
| Private Method | PascalCase | `ApplyBuffs()` |
| Public Property | PascalCase | `IsReady` |
| Private Field | _camelCase | `_currentStage` |
| Const | PascalCase | `MaxLevel` |
| Enum | PascalCase | `AttributeType.Fire` |
| Event Key | PascalCase string | `"OnStageComplete"` |
| Parameter | camelCase | `heroData` |
| Local Variable | camelCase | `totalDamage` |

### Structure (Region Order)
```csharp
public class Example : Singleton<Example>
{
    #region Fields
    // SerializeField, private fields
    #endregion

    #region Properties
    // public properties
    #endregion

    #region Unity Lifecycle
    // OnSingletonAwake, OnEnable, OnDisable
    #endregion

    #region Public Methods
    // contract.provides
    #endregion

    #region Private Methods
    // internal logic
    #endregion
}
```

### Required Patterns
- `[SerializeField]` for UI/prefab references (Inspector 연결)
- Null safety: `?.` operator, null checks before collection access
- Event-driven communication (no direct Manager references where possible)
- `#region` blocks for organization
- XML comments (`/// <summary>`) on all public members
- `using VeilBreaker.Core;` at top of every file

### Forbidden Patterns
- God Class (1000+ lines)
- Magic Numbers (use GameConstants)
- Deep Nesting (3+ levels)
- String Comparison for types (use enum)
- Update() abuse (prefer event-driven)
- UI dynamic creation in code (`new GameObject()` + `AddComponent<Image>()`)
- `Find()` / `FindObjectOfType()` for references (use `[SerializeField]`)
- `Destroy()` on pooled objects (use `ObjectPool.Despawn()`)

### SDK Conditional Compilation
```csharp
#if FIREBASE_ANALYTICS
using Firebase;
using Firebase.Analytics;
#endif
```
- `using` statements for SDK must be inside `#if` blocks
- Always provide `#else` simulation block

---

## 8. File Output Paths

```
E:\AI\projects\VeilBreaker\output\
├── Singleton.cs         # Core - Singleton<T> base
├── EventManager.cs      # Core - Global event bus
├── ObjectPool.cs        # Core - Tag-based object pool + PoolTag
├── GameConstants.cs     # Core - All constants, enums, event keys
├── Util.cs              # Core - Static utilities + extensions
├── _ARCHITECTURE.md     # This file
├── SDK\                 # SDK managers (conditional compilation)
└── Editor\              # Editor scripts
```
