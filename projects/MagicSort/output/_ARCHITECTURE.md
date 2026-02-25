# MagicSort Architecture Guide

## Overview
MagicSort is a Water Sort Puzzle clone built with Unity 2021.3.45f2.
This document defines the architecture conventions that all code must follow.

---

## 1. Namespace Structure

```
MagicSort.Core      - Infrastructure layer (Phase 0)
                      Singleton, DI, Signals, Pools, Save, Sound, SceneLoader, Updater

MagicSort.Domain    - Game logic layer (Phase 1+)
                      Bottle, Pour, Level, Blocker, Booster, Currency, Progression

MagicSort.Game      - UI/Scene-specific layer (Phase 1+)
                      Pages, Popups, HUD elements, Scene controllers
```

### Rules
- Core classes NEVER reference Domain or Game classes.
- Domain classes may reference Core. NEVER reference Game classes.
- Game classes may reference both Core and Domain.

---

## 2. Dependency Injection (DI)

### Container Hierarchy
```
ProjectContext (global, DontDestroyOnLoad)
    |
    +-- SceneContext (per-scene, destroyed on scene unload)
```

### Registration
```csharp
// In a MonoBehaviour Awake, register with ProjectContext
ProjectContext.Instance.Register<IMyService>(myServiceInstance);

// Or register in SceneContext for scene-local services
sceneContext.Register<IMySceneService>(mySceneServiceInstance);
```

### Resolution
```csharp
// Manual resolution
var service = ProjectContext.Instance.Resolve<IMyService>();

// Attribute-based injection (call InjectInto on Awake)
public class MyBehaviour : MonoBehaviour
{
    [Inject] private IMyService _service;

    private void Awake()
    {
        ProjectContext.Instance.Inject(this);
    }
}
```

### Pre-registered Core Bindings
ProjectContext automatically registers:
- `SignalBus` - global event bus

---

## 3. Signal System (Event Communication)

### Defining Signals
All signals are defined in `GameSignals.cs` as structs:
```csharp
public struct LevelStartSignal
{
    public int LevelNumber;
    public LevelDifficulty Difficulty;
}
```

### Signal Usage
```csharp
// Get SignalBus from DI
SignalBus signalBus = ProjectContext.Instance.Resolve<SignalBus>();

// Subscribe
signalBus.Subscribe<LevelStartSignal>(OnLevelStart);

// Fire
signalBus.Fire(new LevelStartSignal { LevelNumber = 1, Difficulty = LevelDifficulty.Easy });

// Unsubscribe (MUST do this in OnDestroy)
signalBus.Unsubscribe<LevelStartSignal>(OnLevelStart);
```

### Available Signals
| Signal | Purpose | Key Fields |
|--------|---------|------------|
| `LevelStartSignal` | Level begins | LevelNumber, Difficulty |
| `LevelCompleteSignal` | Level won | LevelNumber, StarRating, MoveCount |
| `LevelFailSignal` | Level lost | LevelNumber, Reason (StuckType) |
| `BottleSelectedSignal` | Player taps bottle | BottleIndex, IsSource |
| `PourCompleteSignal` | Pour animation done | SourceIndex, TargetIndex, Color, LayerCount |
| `BlockerBrokenSignal` | Blocker removed | BottleIndex, BlockerType |
| `BoosterUsedSignal` | Booster activated | BoosterType, RemainingCount |
| `SceneLoadedSignal` | Scene loaded | SceneName |
| `CurrencyChangedSignal` | Currency changed | CurrencyId, OldAmount, NewAmount |

---

## 4. Singleton Pattern

### Usage
```csharp
public class MyManager : Singleton<MyManager>
{
    protected override void OnSingletonAwake()
    {
        // Initialize here (NOT in Awake)
    }

    protected override void OnSingletonDestroy()
    {
        // Cleanup here (NOT in OnDestroy)
    }
}
```

### Access
```csharp
MyManager.Instance.DoSomething();

// Safe check
if (MyManager.HasInstance)
{
    MyManager.Instance.DoSomething();
}
```

### Core Singletons (DontDestroyOnLoad)
| Singleton | Purpose |
|-----------|---------|
| `ProjectContext` | Global DI container |
| `SaveManager` | PlayerPrefs JSON persistence |
| `SoundManager` | BGM/SFX audio |
| `CustomUpdater` | Centralized Update dispatch |
| `PopUpService` | Popup stack management |
| `SceneLoader` | Async scene loading |

---

## 5. Object Pool

### Usage
```csharp
// Create pool
Pool<MyComponent> pool = new Pool<MyComponent>(prefab, parentTransform);
pool.Preload(10);

// Get from pool
MyComponent obj = pool.Get();
MyComponent obj2 = pool.Get(position, rotation);

// Return to pool
pool.Return(obj);

// Return all
pool.ReturnAll();

// Cleanup
pool.Clear();
```

---

## 6. State Machine

### Define States
```csharp
public class PlayingState : IState<LevelState>
{
    public LevelState StateId => LevelState.Playing;
    public void OnEnter() { /* ... */ }
    public void OnUpdate() { /* ... */ }
    public void OnExit() { /* ... */ }
}
```

### Usage
```csharp
StateMachine<LevelState> fsm = new StateMachine<LevelState>();
fsm.AddState(new PlayingState());
fsm.AddState(new PausedState());
fsm.ChangeState(LevelState.Playing);

// In Update
fsm.Update();

// Listen for changes
fsm.OnStateChanged += (prev, next) => Debug.Log($"{prev} -> {next}");
```

---

## 7. CustomUpdater (Centralized Update)

### Usage
```csharp
public class MySystem : IFrameUpdate, ISecondUpdate
{
    public void OnFrameUpdate(float deltaTime) { /* every frame */ }
    public void OnSecondUpdate() { /* every second */ }
}

// Register
CustomUpdater.Instance.RegisterFrameUpdate(mySystem);
CustomUpdater.Instance.RegisterSecondUpdate(mySystem);

// Unregister (in cleanup)
CustomUpdater.Instance.UnregisterFrameUpdate(mySystem);
CustomUpdater.Instance.UnregisterSecondUpdate(mySystem);
```

---

## 8. Scene Structure

### Required Scenes (3)
| Scene | Purpose | Key Objects |
|-------|---------|-------------|
| Title | Loading/Splash | Logo, LoadingBar, auto-transition to Home |
| Home | Main Menu | Play button, Settings, Level select |
| GamePlay | Puzzle gameplay | Bottles, HUD, Manager objects |

### Each Scene Must Have
- Main Camera
- Canvas (Screen Space - Overlay, CanvasScaler: Scale With Screen Size, 1080x1920)
- EventSystem
- SceneContext

### Manager Placement
- Global managers (ProjectContext, SaveManager, SoundManager, etc.) on a `Managers` GameObject in the Title scene with DontDestroyOnLoad.
- Scene-specific managers on a `SceneManagers` GameObject in each scene.

---

## 9. Enums

All enums are centralized in `GameEnums.cs`:

| Enum | Values |
|------|--------|
| `WaterColor` | None, Red, Blue, Green, Yellow, Purple, Orange, Pink, Cyan, Brown, White, Gray, DarkBlue, Lime, Magenta |
| `LevelState` | None, Playing, Paused, Stuck, Win, Lose, Quit |
| `BlockerType` | Ice, Frog, Duck, Tag, Ivy, Safe, MagicSeal, Toggle, Switch, Generator, Snitch, QuestionMark, Carpet, Curtain, Plaster, Clay, Woodbox, Blob, KeyLock |
| `BoosterType` | ExtraBottle, ColorClear, Shuffle, Undo, Hint |
| `StuckType` | NoMove, TimeIsUp |
| `LevelDifficulty` | Easy, Medium, Hard, Expert |
| `GameState` | Title, Home, GamePlay |
| `SceneName` | Title, Home, GamePlay |

---

## 10. Phase Dependency Map

```
Phase 0: Core Infrastructure (this phase)
    Singleton, DIContainer, ProjectContext, SceneContext,
    SignalBus, StateMachine, ObjectPool, SaveManager,
    SoundManager, CustomUpdater, PopUpService, PopUpConfig,
    SceneLoader, GameEnums, GameSignals

Phase 1: Domain Systems (depends on Phase 0)
    BottleController, PourProcessor, WaterLayerData,
    LevelManager, LevelDataProvider, BlockerManager,
    BoosterManager, ScoreCalculator, MoveTracker,
    UndoManager, HintProvider

Phase 2: Game/UI Layer (depends on Phase 0 + 1)
    TitleSceneController, HomeSceneController, GamePlaySceneController,
    BottleView, HUDController, LevelSelectPopup, SettingsPopup,
    GameOverPopup, WinPopup, BoosterPanel
```

---

## 11. Coding Conventions

### SerializeField Rule
```csharp
// GOOD - Inspector reference
[SerializeField] private Button playButton;

// BAD - Dynamic creation/lookup
var btn = FindObjectOfType<Button>(); // NEVER
```

### Null Safety
```csharp
// Always check before access
if (collection != null && collection.Count > 0)
{
    var item = collection[0];
}

// Use null-conditional
myObject?.DoSomething();
```

### Naming
- **Classes**: PascalCase (`BottleController`)
- **Public methods**: PascalCase (`PourWater()`)
- **Private fields**: _camelCase (`_currentLevel`)
- **SerializeField**: camelCase (`bottlePrefab`)
- **Constants**: UPPER_SNAKE_CASE (`MAX_BOTTLE_COUNT`)
- **Enums**: PascalCase values (`WaterColor.DarkBlue`)

### File Organization
```csharp
public class Example : MonoBehaviour
{
    #region Fields
    // [SerializeField] and private fields
    #endregion

    #region Properties
    // Public properties
    #endregion

    #region Unity Lifecycle
    // Awake, Start, OnDestroy, etc.
    #endregion

    #region Public Methods
    #endregion

    #region Private Methods
    #endregion
}
```

---

## 12. File Manifest (Phase 0)

| File | Namespace | Base Class | Role |
|------|-----------|------------|------|
| `Singleton.cs` | MagicSort.Core | MonoBehaviour | Helper |
| `DIContainer.cs` | MagicSort.Core | (plain C#) | Service |
| `ProjectContext.cs` | MagicSort.Core | Singleton<ProjectContext> | Context |
| `SceneContext.cs` | MagicSort.Core | MonoBehaviour | Context |
| `SignalBus.cs` | MagicSort.Core | (plain C#) | Service |
| `StateMachine.cs` | MagicSort.Core | (plain C#) | State |
| `ObjectPool.cs` | MagicSort.Core | (plain C#) | Pool |
| `SaveManager.cs` | MagicSort.Core | Singleton<SaveManager> | Manager |
| `SoundManager.cs` | MagicSort.Core | Singleton<SoundManager> | Manager |
| `CustomUpdater.cs` | MagicSort.Core | Singleton<CustomUpdater> | Manager |
| `PopUpConfig.cs` | MagicSort.Core | ScriptableObject | Config |
| `PopUpService.cs` | MagicSort.Core | Singleton<PopUpService> | Service |
| `SceneLoader.cs` | MagicSort.Core | Singleton<SceneLoader> | Service |
| `GameEnums.cs` | MagicSort.Core | (enums only) | Config |
| `GameSignals.cs` | MagicSort.Core | (structs only) | Config |
