---
name: unity-csharp-patterns
description: Unity C# 게임 개발 코딩 규칙 및 패턴
version: 1.0.0
triggers:
  - "*.cs"
  - "Unity"
  - "C#"
  - "MonoBehaviour"
  - "코드 생성"
  - "generate"
---

# Unity C# 코딩 규칙

이 스킬은 C# 코드 작성, 검토, 리팩토링 시 자동으로 활성화됩니다.

---

## 필수 패턴

### Singleton
```csharp
public class GameManager : Singleton<GameManager>
{
    protected override void Awake()
    {
        base.Awake();
        // 초기화
    }
}
```

### Null Safety
```csharp
// BAD
var first = list.First();

// GOOD
var first = list.FirstOrDefault();
if (first != null) { ... }

// GOOD - 컬렉션 체크
if (list != null && list.Count > 0)
{
    var first = list[0];
}
```

### Async/Await (UniTask)
```csharp
// BAD
async Task DoSomething() { ... }

// GOOD
async UniTask DoSomething() { ... }
async UniTask<T> GetSomething() { ... }
```

### Object Pooling
```csharp
// BAD
var obj = Instantiate(prefab);
Destroy(obj);

// GOOD
var obj = poolManager.Get(prefab);
poolManager.Return(obj);
```

---

## Layer 분류 규칙

### Core (장르 무관 기반)
키워드: Singleton, Pool, Event, Util, Extension, Base
```
예: Singleton<T>, ObjectPool, EventBus, MathUtil
```

### Domain (재사용 도메인)
키워드: Battle, Character, Inventory, Quest, Skill, Item, Shop, UI, Audio, Network
```
예: BattleManager, CharacterController, InventorySystem
```

### Game (프로젝트 특화)
키워드: Page, Popup, Element, Win, partial class 확장
```
예: MainPage, SettingsPopup, ItemElement, BattleManager_Tower
```

---

## Role 분류 규칙

클래스명 패턴으로 자동 분류:

| 패턴 | Role | 책임 |
|------|------|------|
| *Manager | Manager | 시스템 총괄, 전체 흐름 제어 |
| *Controller | Controller | 개별 개체 제어, 입력 처리 |
| *Calculator | Calculator | 수치 연산, 공식 적용 |
| *Processor | Processor | 데이터 가공, 일괄 처리 |
| *Handler | Handler | 이벤트 수신 및 처리 |
| *Factory | Factory | 객체 생성 담당 |
| *Service | Service | 외부 연동, API 통신 |
| *Validator | Validator | 유효성 검사 |
| *Pool | Pool | 객체 풀링 관리 |
| *State | State | 상태 정의 및 전환 |

---

## Genre별 패턴

### RPG
- 전투: DamageCalculator, BuffSystem, SkillManager
- 캐릭터: CharacterStat, Equipment, Inventory

### Idle
- 오프라인 보상: OfflineRewardCalculator
- 자동 진행: AutoBattleController

### Merge
- 그리드: GridManager, CellController
- 머지: MergeProcessor, CombineValidator

---

## Contract 작성 규칙

### provides (제공 API)
- public 메서드만 포함
- 시그니처 정확히 기술
```yaml
provides:
  - "void StartBattle(int stageId)"
  - "bool IsBattleActive { get; }"
```

### requires (필요 API)
- 외부 Singleton 접근
- 다른 시스템 의존성
```yaml
requires:
  - "DataManager.Instance"
  - "CharacterPlayer.Instance"
```

---

## 피해야 할 패턴

1. **God Class** - Manager가 모든 것을 담당
2. **Magic Number** - 상수 정의 없이 숫자 사용
3. **Deep Nesting** - 3단계 이상 중첩
4. **String Comparison** - enum 대신 문자열 비교
5. **Update Polling** - 매 프레임 불필요한 체크
