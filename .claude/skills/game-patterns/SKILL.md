---
name: game-design-patterns
description: 게임 개발 설계 패턴 및 아키텍처 가이드
version: 1.0.0
triggers:
  - "기획"
  - "설계"
  - "아키텍처"
  - "시스템"
  - "design"
  - "architecture"
---

# 게임 설계 패턴

이 스킬은 기획서 작성, 시스템 설계, 아키텍처 결정 시 자동으로 활성화됩니다.

---

## 기획서 구조

### Layer 1: 게임 기획서 (인간 읽기용)

**공통 섹션 (필수)**
- 게임 개요: 제목, 장르, 플랫폼, 타겟 유저
- 핵심 경험: 주요 재미, 감정 목표, 핵심 동사
- 핵심 루프: 메인/일일/장기 루프
- 세션 구조: 시작/진행/종료 조건
- 수익 모델: BM 유형, 수익원

**장르별 섹션**
| 장르 | 필수 섹션 |
|------|-----------|
| RPG | 전투, 성장, 캐릭터, 콘텐츠 |
| Idle | 오프라인, 자동진행, 방치보상 |
| Merge | 그리드, 머지규칙, 생성 |
| SLG | 영토, 병력, 동맹 |
| Tycoon | 비즈니스, 고객, 직원 |
| Puzzle | 보드, 매칭, 스테이지 |

---

### Layer 2: 시스템 명세서 (AI 변환용)

```yaml
시스템_목록:
  Core: [EventBus, ObjectPool, DataManager]
  Domain: [BattleManager, CharacterSystem, InventoryManager]
  Game: [MainPage, BattleHUD, SettingsPopup]

시스템_상세:
  BattleManager:
    목적: 전투 흐름 제어
    책임: [전투 시작/종료, 적 스폰, 데미지 처리]
    상태: [isBattle, currentWave, enemyList]
    행위:
      - trigger: OnStageEnter
        action: StartBattle
        result: 전투 시작, UI 활성화
    연결_관계:
      uses: [CharacterPlayer, EnemySpawner, DataManager]
      usedBy: [StageManager, QuestSystem]
      publishes: [OnBattleStart, OnBattleEnd]
```

---

### Layer 3: AI_기획서 (YAML 노드)

```yaml
metadata:
  nodeId: BattleManager
  version: 1.0.0
  phase: 2
  role: Manager

dependencies:
  internal: [CharacterSystem, EnemySpawner]
  external: [DataManager, UIManager]

contract:
  provides:
    - "void StartBattle(int stageId)"
    - "void EndBattle(bool isWin)"
    - "bool IsBattleActive { get; }"
  requires:
    - "DataManager.Instance"
    - "CharacterPlayer.Instance"

tags:
  layer: Domain
  genre: RPG
  role: Manager
  system: Battle
  majorFunctions: [FlowControl, StateControl]
  minorFunctions: [Spawn, Despawn, Notify]

logicFlow:
  - step: 1
    tag: FlowControl
    action: "전투 초기화"
    next: 2
  - step: 2
    tag: Spawn
    action: "적 스폰"
    next: 3

referencePatterns:
  - source: "Expert:BattleManager_Tower"
    pattern: "웨이브 기반 전투"

codeHints:
  patterns: [Singleton, Observer, State]
  avoidPatterns: [GodClass, DeepNesting]
```

---

## 시스템 연결 관계

### 관계 유형
| 관계 | 의미 | 예시 |
|------|------|------|
| uses | 직접 호출/참조 | BattleManager uses CharacterPlayer |
| usedBy | 호출됨 | BattleManager usedBy StageManager |
| extends | 상속 | BattleManager_Tower extends BattleManager |
| publishes | 이벤트 발행 | BattleManager publishes OnBattleEnd |
| subscribes | 이벤트 구독 | RewardSystem subscribes OnBattleEnd |

### 의존성 그래프 예시
```
[Core Layer]
    EventBus ←─────────────────────┐
    ObjectPool ←───────────┐       │
                           │       │
[Domain Layer]             │       │
    DataManager ←──────────┼───────┤
         ↑                 │       │
    CharacterSystem ───────┤       │
         ↑                 │       │
    BattleManager ─────────┴───────┘
         ↑
[Game Layer]
    BattleHUD
    StageManager
```

---

## 빌드 오더 결정

의존성 기반으로 Phase 결정:

| Phase | 시스템 | 조건 |
|-------|--------|------|
| 0 | Core 시스템 | 의존성 없음 |
| 1 | 기반 Domain | Core만 의존 |
| 2 | 상위 Domain | Domain 의존 |
| 3 | Game Layer | Domain 의존 |

---

## 장르별 핵심 시스템

### RPG
```
Core: Singleton, ObjectPool, EventBus
Domain: BattleManager, CharacterSystem, SkillManager, BuffSystem,
        InventoryManager, QuestManager, ShopManager
Game: BattleHUD, CharacterPage, InventoryPopup
```

### Idle
```
Core: Singleton, TimeManager, SaveManager
Domain: IdleRewardCalculator, AutoBattleController,
        OfflineProgressManager, PrestigeSystem
Game: MainHUD, RewardPopup, SettingsPage
```

### Merge
```
Core: Singleton, GridManager
Domain: MergeProcessor, GeneratorManager, ItemCombiner,
        LevelManager, OrderManager
Game: GameBoard, ItemPopup, ShopPage
```
