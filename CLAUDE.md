# AI Game Code Generation System

## 프로젝트 개요
게임 소스코드 자동 생성 파이프라인.
Unity C# 게임 코드 및 HTML5 플레이어블 광고를 지원합니다.
기획과 시스템을 분리하여 단계별로 프로그램화하여 진행.

## 핵심 원칙
1. **3-AI 분리** - DB 가공 AI, 기획 AI, 코드 생성 AI
2. **환각 방지** - 정규화된 분류 체계 + DB 참조 필수
3. **병렬 작업** - Agent Teams로 Phase 내 노드 병렬 생성

---

## Agent Team: AI-Game-Creator

### 팀 구성 (7명 + 호출형 3명)
| Agent | Model | 역할 | Custom Agent 파일 | Platform |
|-------|-------|------|-------------------|----------|
| **Lead** | claude-opus-4-6 | PM - 태스크 분배/조율/평가, delegate 모드 | `.claude/agents/lead.md` | 공통 |
| **Designer** | claude-sonnet-4-6 | 기획 - 기획서 생성 | `.claude/agents/designer.md` | 공통 |
| **Main Coder** | claude-opus-4-6 | 메인 개발 - Core 아키텍처, 핵심 시스템 | `.claude/agents/main-coder.md` | Unity |
| **Sub Coder x2** | claude-sonnet-4-6 | 서브 개발 - Main 패턴 따라 노드 구현 | `.claude/agents/sub-coder.md` | Unity |
| **Playable Coder** | claude-sonnet-4-6 | HTML5 플레이어블 광고 코드 생성 | `.claude/agents/playable-coder.md` | Playable |
| **Validator** | claude-sonnet-4-6 | QA - Unity 5+1단계 / Playable 4단계 검증 | `.claude/agents/validator.md` | 공통 |
| **Design Validator** | claude-sonnet-4-6 | 기획 QA - Quality Gates 소유, 6단계 검증 | `.claude/agents/design-validator.md` | 공통 |
| **DB Builder** | claude-sonnet-4-6 | Code DB 구축 - 사용자 호출 시에만 | `.claude/agents/db-builder.md` | 공통 |
| **Design DB Builder** | claude-sonnet-4-6 | Design DB 구축 - 사용자 호출 시에만 | `.claude/agents/design-db-builder.md` | 공통 |

### 병렬 실행 규칙
- **Phase 0**: Main Coder가 Core 전담 → _ARCHITECTURE.md → _CONTRACTS.yaml → _ASSET_MANIFEST.yaml 생성
- **Phase 1+**: Main Coder(복잡한 시스템) + Sub Coder x2(일반 노드) 병렬
- Phase 간 의존성 → 이전 Phase 완료(Validator 검증 통과) 후 진행
- Validator는 코드 완료 순서대로 즉시 검증 (Stage 5.5 Integration Validation 포함)
- 검증 실패 → 해당 Coder에게 피드백 전달 → 재생성
- 에러 수정 시 → Error Fix Protocol 필수 적용 (기획 의도 이탈 방지)

### 실행 방법
```
# Unity 게임
게임을 만들어줘. [게임 설명]. Agent Team으로 병렬 진행해줘. Coder N명.

# 플레이어블 광고
[메카닉] 플레이어블 광고를 만들어줘. [설명]. Agent Team으로 진행해줘.
```

### 런타임 코드 규칙 (게임 실행 중)
- **금지**: `new GameObject()` + `AddComponent<T>()` — CPU 부담, 런타임에 즉석 생성 지양
- **금지**: `Find()`, `FindObjectOfType()`, `GameObject.FindWithTag()` — 매 프레임 탐색 비용
- **필수**: 오브젝트는 Resources.Load / Addressables / AssetBundle로 미리 로드하여 사용
- **필수**: 반복 생성·파괴 오브젝트는 ObjectPool 패턴 사용 (Instantiate/Destroy 루프 금지)
- **필수**: UI 참조는 `[SerializeField]`로 Inspector 연결, 코드에서 동적 생성하지 않음
- **참조**: DB에 ObjectPool, ObjectPoolManager 패턴 존재 (generic/core, rpg/core, puzzle/core)

### 에디터 코드 규칙 (씬 세팅·프리팹 제작용)
- **허용**: `new GameObject()`, `AddComponent<T>()`, `PrefabUtility`, `AssetDatabase` — 1회성 셋업에 사용
- **목적**: 씬 자동 구성, 프리팹 자동 생성, SerializeField 자동 연결, Build Settings 자동 설정
- **조건**: `[InitializeOnLoad]` + `EditorPrefs` 체크로 **1회만 실행** (매번 재실행 금지)
- **조건**: 에디터 스크립트는 반드시 `output/Editor/` → `Assets/Editor/`에 배치
- **UI 세팅**: Canvas, RectTransform의 pivot/anchor/해상도 관련 값은 기획서 입력 정보에 맞춰 설정
  - 기본: CanvasScaler Scale With Screen Size, Reference Resolution은 기획서 지정값 (기본 1080×1920)
  - pivot/anchor는 UI 요소 용도에 맞게 설정 (상단 고정 = top-center, 전체 채움 = stretch 등)
- **에셋**: 머티리얼, 고퀄리티 이미지, 아트 리소스는 생성하지 않음 — 사용자가 별도 제공

### 분업 요약
```
AI가 생성하는 것:
  ├── Runtime 코드     — MonoBehaviour, 이벤트, 상태 관리, ObjectPool
  ├── Editor 스크립트   — 씬 구성, 프리팹 생성, SerializeField 연결, Build Settings
  └── ScriptableObject — 게임 데이터 에셋 (레벨, 아이템 테이블 등)

사용자가 하는 것:
  ├── 아트 에셋        — 스프라이트, 3D 모델, 이펙트, 사운드
  ├── Placeholder 교체  — AI가 만든 기본 구조에 최종 에셋 교체
  └── 최종 검수        — 레이아웃 미세 조정, 빌드 테스트
```

---

## Integration Contract System (ICS)

코드 생성 시 **파일 간 연결 계약**을 명시적으로 추적·검증하는 시스템.
"코드 조각"이 아닌 "작동하는 시스템"을 보장하기 위한 핵심 메커니즘.

### 3대 산출물

| 산출물 | 생성 시점 | 생성 주체 | 소비 주체 |
|--------|-----------|-----------|-----------|
| `_ARCHITECTURE.md` | Phase 0 완료 후 | Main Coder | Sub Coder, Validator |
| `_CONTRACTS.yaml` | Phase 0 완료 후, Phase마다 갱신 | Main Coder | 모든 Coder, Validator |
| `_ASSET_MANIFEST.yaml` | Phase 0 완료 후, Phase마다 갱신 | Main Coder | Validator, Editor 스크립트 |

### _CONTRACTS.yaml 구조
```yaml
project: "{ProjectName}"
version: 1
last_updated: "2026-03-12"

# 이벤트 계약: 누가 발행하고 누가 구독하는지
events:
  - name: OnBalloonPopped
    struct_file: GameEvents.cs
    fields:
      balloonId: int
      color: int
      position: Vector3
    publishers: [BalloonController]
    subscribers: [PopProcessor, ScoreManager, BoardStateManager]

# ObjectPool 키 계약: 어떤 키가 어떤 프리팹을 필요로 하는지
pool_keys:
  - key: "Balloon"
    prefab_path: "Resources/Prefabs/Balloon"
    consumers: [BalloonController]
    required_components: [BalloonIdentifier, SpriteRenderer, CircleCollider2D]
    initial_size: 30

# SerializeField 와이어링 계약: 어떤 필드가 씬의 어떤 오브젝트에 연결되는지
serialized_fields:
  - class: GameBootstrap
    field: _titlePage
    type: CanvasGroup
    wired_by: SceneBuilder
    scene_object_name: "TitlePage"

# 크로스 클래스 메서드 호출 계약: 누가 누구의 메서드를 호출하는지
method_calls:
  - caller: "GameBootstrap.OnPlayClicked"
    target: "LevelManager.LoadLevel(int)"
    requires: "LevelDataProvider must be initialized"

# 에셋 요구사항: 런타임에 필요한 에셋 목록
asset_requirements:
  - path: "Resources/Prefabs/Balloon"
    type: GameObject
    created_by: "Editor/PrefabBuilder.cs"
    required_for: [ObjectPoolManager]
```

### _ASSET_MANIFEST.yaml 구조
```yaml
project: "{ProjectName}"
version: 1

prefabs:
  - name: Balloon
    path: "Assets/Resources/Prefabs/Balloon.prefab"
    components: [SpriteRenderer, CircleCollider2D, BalloonIdentifier]
    pool_key: "Balloon"
    created_by: "Editor/PrefabBuilder.cs"

scenes:
  - name: GameScene
    path: "Assets/Scenes/GameScene.unity"
    created_by: "Editor/SceneBuilder.cs"
    manager_objects:
      - name: Mgr_ObjectPool
        component: ObjectPoolManager
      - name: GameBootstrap
        component: GameBootstrap
    serialized_field_wiring:
      - target: GameBootstrap._titlePage
        source_object: "TitlePage"
        source_component: CanvasGroup

editor_scripts:
  - name: SceneBuilder
    path: "Editor/SceneBuilder.cs"
    creates: [scenes, manager_objects, ui_hierarchy, serialized_field_wiring]
    version_key: "BalloonFlow_SceneBuilt_v4"
  - name: PrefabBuilder
    path: "Editor/PrefabBuilder.cs"
    creates: [prefabs, sprites]
    version_key: "BalloonFlow_PrefabsBuilt_v1"

resources:
  - path: "Resources/Sprites/BalloonSprite.png"
    type: Sprite
    created_by: "Editor/PrefabBuilder.cs"
```

### Error Fix Protocol (에러 수정 시 필수)

컴파일 에러 수정 시 기획 의도 이탈을 방지하기 위한 필수 프로토콜.

**1단계: 컨텍스트 로드 (수정 전 필수)**
```
- 깨진 파일 자체
- 해당 L3 YAML 노드 (design_workflow/layer3/nodes/)
- _CONTRACTS.yaml 중 해당 파일 관련 항목
- 해당 파일을 참조하는 모든 파일 (callers)
- 해당 파일이 참조하는 모든 파일 (dependencies)
```

**2단계: 수정 제약 (절대 규칙)**
```
- contract.provides에 있는 public 메서드/프로퍼티 삭제 금지
- [SerializeField] 속성 제거 금지 (SceneBuilder 와이어링 깨짐)
- 메서드 시그니처 변경 시 모든 caller 동시 수정 필수
- 로직 우회형 null 체크 금지 (if(x==null) return; 으로 필수 로직 건너뛰기)
- public API 변경 필요 시 → Lead에 보고, 독단 결정 금지
```

**3단계: 수정 후 검증**
```
- _CONTRACTS.yaml 모든 계약 여전히 충족되는가?
- L3 YAML 기획 의도가 보존되었는가?
- 5단계 자가 검증 재실행
```

### Integration Validation (Validator Stage 5.5)

기존 5단계 검증 후 추가 실행되는 **파일 간 통합 검증**.

| 체크 항목 | 검증 방법 | 실패 시 |
|-----------|-----------|---------|
| 이벤트 계약 | events 항목별 publisher/subscriber 파일에 실제 Publish/Subscribe 코드 존재 확인 | error |
| Pool 키 계약 | pool_keys 항목별 prefab 파일 + consumer 파일의 Get/Return 코드 확인 | error |
| SerializeField 계약 | serialized_fields 항목별 해당 클래스에 [SerializeField] 존재 + SceneBuilder에 WireField 호출 존재 확인 | error |
| 메서드 호출 계약 | method_calls 항목별 caller에 실제 호출 코드 + target에 해당 메서드 존재 확인 | error |
| 에셋 요구사항 | asset_requirements 항목별 PrefabBuilder 또는 SceneBuilder에 생성 코드 존재 확인 | error |
| 양방향 일관성 | 코드에서 발견된 EventBus.Publish/Subscribe가 _CONTRACTS.yaml에 등록되어 있는지 역방향 확인 | warning |

### 계약 갱신 규칙

- Phase 0 완료 시: Main Coder가 초기 _CONTRACTS.yaml + _ASSET_MANIFEST.yaml 생성
- Phase N 완료 시: 해당 Phase에서 추가된 이벤트/pool key/SerializeField를 Main Coder가 갱신
- 에러 수정으로 public API 변경 시: _CONTRACTS.yaml 동시 갱신 필수
- Lead는 Phase Gate 검증 시 _CONTRACTS.yaml 갱신 여부 확인

---

## DB (MongoDB Atlas)

모든 DB는 MongoDB Atlas (`aigame` 데이터베이스)에 저장됩니다.
접속 정보: `.env` 파일의 `MONGO_URI` / 클라이언트: `scripts/lib/db-client.js`

| Collection | 내용 | 주요 필드 |
|------------|------|-----------|
| `code_base` | 파싱된 소스코드 (928건) | fileId, genre, layer, role, system, score |
| `code_expert` | 검증된 코드 (score ≥ 0.6) | 상동 |
| `design_base` | 기획 데이터 (108건) | designId, genre, domain, system, score |
| `design_expert` | 검증된 기획 (score ≥ 0.6) | 상동 |
| `rules` | 피드백 규칙 | ruleId, category, genre |

---

## 분류 체계 (Layer > Genre > Role > Tag)

### Layer (3종)
| Layer | 정의 | 키워드 |
|-------|------|--------|
| Core | 장르 무관 기반 | Singleton, Pool, Event, Util, Base |
| Domain | 재사용 도메인 | Battle, Character, Inventory, Quest, Skill |
| Game | 프로젝트 특화 | Page, Popup, Element, partial class |

### Genre (9종)
Generic, RPG, Idle, Merge, SLG, Tycoon, Simulation, Puzzle, Casual

### Role (21종) - 클래스명 패턴으로 분류
| Role | 정의 | 패턴 |
|------|------|------|
| Manager | 시스템 총괄, 전체 흐름 제어 | *Manager |
| Controller | 개별 개체 제어, 입력 처리 | *Controller |
| Calculator | 수치 연산, 공식 적용 | *Calculator, *Calc |
| Processor | 데이터 가공, 일괄 처리 | *Processor |
| Handler | 이벤트 수신 및 처리 | *Handler |
| Listener | 이벤트 감지 및 반응 | *Listener |
| Provider | 데이터/리소스 제공 | *Provider |
| Factory | 객체 생성 담당 | *Factory |
| Service | 외부 연동, API 통신 | *Service |
| Validator | 유효성 검사, 조건 판정 | *Validator |
| Converter | 데이터 형식 변환 | *Converter |
| Builder | 복잡한 객체 단계별 생성 | *Builder |
| Pool | 객체 풀링 관리 | *Pool, *Pooler |
| State | 상태 정의 및 전환 | *State |
| Command | 실행 가능한 명령 단위 | *Command, *Cmd |
| Observer | 변화 감지 및 알림 | *Observer |
| Helper | 보조 기능, 유틸리티 | *Helper, *Util |
| Wrapper | 외부 라이브러리 래핑 | *Wrapper |
| Context | 실행 환경/상태 정보 보관 | *Context, *Ctx |
| Config | 설정값 정의 및 관리 | *Config, *Settings |
| UX | 코드 기반 동적 연출 (스케일, 이동, 합체, 분리, 비산 등) | *Effect, *Tweener, *Performer, *Presenter |

### Tag - 대기능 (7종)
StateControl, ValueModification, ConditionCheck, ResourceTransfer, DataSync, FlowControl, ResponseTrigger

### Tag - 소기능 (11종)
Compare, Calculate, Find, Validate, Assign, Notify, Delay, Spawn, Despawn, Iterate, Aggregate

---

## DB 검색 우선순위
코드 생성 시 참조할 기존 코드 검색 순서:

| 순위 | 검색 대상 | 조건 |
|------|-----------|------|
| 1 | Expert DB (해당 장르) | genre 일치 AND score >= 0.6 |
| 2 | Expert DB (Generic) | genre = Generic AND score >= 0.6 |
| 3 | Genre Base DB | genre 일치 |
| 4 | Generic Base DB | genre = Generic |
| 5 | AI_기획서 기반 생성 | 참조 코드 없음 |

---

## 신뢰도 점수 체계

### Code 점수
| 이벤트 | 점수 변동 |
|--------|-----------|
| 초기 저장 | 0.4 |
| 피드백 반영 완료 | +0.2 |
| 재사용 성공 (1회당) | +0.1 |
| 재사용 실패 (1회당) | -0.15 |
| 다른 장르에서 재사용 성공 | +0.1 (Generic 승격 검토) |
| Expert DB 승격 임계값 | >= 0.6 |

### Design 점수
자동 점수 3종(논리 완결성, 밸런스 안정성, 구현 복잡도) 평균 → 신뢰도 초기값 결정

| 이벤트 | 점수 변동 |
|--------|-----------|
| 초기 저장 (자동 점수 평균 >= 0.5) | 0.4 |
| 초기 저장 (자동 점수 평균 < 0.5) | 0.3 |
| 디렉터 검증 통과 (피드백 없이 승인) | +0.2 |
| 피드백 반영 완료 후 승인 | +0.1 |
| 다른 프로젝트에서 구조 참조 성공 | +0.1 |
| 참조 부적합 판정 | -0.1 |
| 다른 장르에서 참조 성공 | +0.1 (Generic 승격 검토) |
| Expert Design DB 승격 임계값 | >= 0.6 |

---

## 명령어

### Code Workflow
- `/parse-source [path]` - 소스코드 파싱 후 DB 저장
- `/generate-design [input]` - 기획서/명세서 생성
- `/generate-code [yaml]` - 코드 생성
- `/validate-code [path]` - 코드 검증

### Design Workflow
- `/parse-design [path]` - 기획 문서 파싱 후 Design DB 저장
- `/generate-design-v2 [input]` - 8단계 기획 워크플로우 실행
- `/validate-design [path]` - 기획서 통합 검증 (교차 검증, 밸런스 시뮬)
- `/sync-live [project]` - 라이브 데이터 동기화

---

## 자주 하는 실수 (피해야 할 것)
1. BattleManager를 Core로 분류 → **Domain**이 맞음
2. 메서드 내부 지역 변수를 필드로 파싱
3. Awake, Start 등 Unity 생명주기 메서드를 uses에 포함
4. provides/requires Contract 추출 누락
5. 대용량 JSON 한 번에 로드 → 인덱스 먼저 검색

---

## 파이프라인 단계

### 전체 게임 제작 흐름 (Design → Code 통합)
```
설계 표준 정의 (장르 최초 1회)
               구성요소 맵 → 파라미터 정의(상세도 기준 포함)
               → 데이터 스키마 정의(프로그래머 싱크) → 도메인별 우선순위 → DB 스키마
               + 디렉션 히스토리 자동 축적 시작
    ↓
DB 구축 (1회)  Code DB: 소스 파싱 → MongoDB code_base
               Design DB: 기획 문서 / AI Tester → MongoDB design_base (0단계 스키마 참조)
    ↓
Design Stage 2~6: 기획 생성 → 통합 검증 → 디렉터 검수 → 재생성 → DB 축적
    ↓ (Stage 6 완료 = 기획 확정)
Code Phase 2~4:  기획서 변환 → 코드 생성 (병렬) → 검증 & 축적
    ↓ (빌드 완료)
Design Stage 7:  플레이 검증 (AI Tester)
Design Stage 8:  라이브 동기화 (출시 후)
```

### Code Workflow (Phase 1~4)

#### Phase 1: DB 구축 (1회)
소스 폴더 → 파싱 → Layer/Genre/Role/Tag 분류 → MongoDB 저장

#### Phase 2: 기획서 변환 (프로젝트마다)
Design Stage 6 완료된 기획서 → 시스템 명세서 → AI_기획서 (YAML)

#### Phase 3: 코드 생성 (프로젝트마다)
AI_기획서 → DB 검색 → 코드 생성 → 자가 검증 → 피드백 반영

#### Phase 4: 지식 축적 (자동)
검증 완료 → 점수 계산 → Expert DB 승격 → Rules 추출

### Design Workflow (Stage 0~8)
```
Stage 0: 설계 표준       — 구성요소 맵 + 파라미터(상세도 기준) + 데이터 스키마(프로그래머 싱크) + 도메인별 우선순위 + DB 스키마 + 디렉션 히스토리 (장르 최초 1회)
Stage 1: DB 가공          — 기획 문서 / AI Tester 관찰 → Design DB (0단계 스키마 참조)
Stage 2: 기획 생성        — 2-1 컨셉(Core Fun+필러) → 0단계 Tier 순서로 도메인별 생성 (2-3/2-4 병렬 가능) → 2-5 BM
Stage 3: 통합 검증        — 교차 일관성 + 유저 여정 시뮬 + 누락 검출
Stage 4: 디렉터 검수      — 사람이 검수, 피드백 없으면 Stage 6으로
Stage 5: 재생성 평가      — 피드백 반영 확인 + 히스토리 분석
Stage 6: DB 축적          — score 산출 → Expert DB 승격 (>= 0.6) → Rules 추출
    ↓ Code Workflow Phase 2~4 실행 ↓
Stage 7: 플레이 검증      — AI Tester (7-1 가속 / 7-2 장기 / 7-3 대규모 시뮬) + metadata 지표 기반 판단
Stage 8: 라이브 동기화    — 밸런스 패치 → 버전 추가 → KPI 기록
```

---

## Playable 광고 (HTML5)

### Platform 분기
Designer가 생성한 `game_design.yaml`의 `platform` 필드로 파이프라인이 분기됩니다.
- `platform: unity` → 기존 Unity C# 파이프라인
- `platform: playable` → HTML5 플레이어블 광고 파이프라인

### Playable 파이프라인 (경량)
```
Designer → 플레이어블 기획 YAML (노드 1개)
Playable Coder → HTML5 단일 파일 (playable.html)
Validator → 규격 검증 (Isolation/Interaction/CTA/Size)
```

### 기술 스택
- 순수 Canvas API (기본) 또는 Phaser.js 인라인 (복잡한 게임)
- 외부 요청 금지 (CDN, 외부 이미지 등 일체 불가)
- 에셋은 Base64 인라인 또는 코드 도형

### 에셋 모드
| 모드 | 설명 |
|------|------|
| code_only | Canvas 도형 + CSS 그라디언트 (에셋 불필요) |
| provided | 사용자가 assets/ 폴더에 PNG/SVG 제공 → Base64 인라인 |

### 광고 네트워크 규격
| 네트워크 | 최대 크기 | 최대 시간 |
|----------|-----------|-----------|
| Facebook/Meta | 2MB | 제한없음 |
| Google Ads | 5MB | 60초 |
| IronSource | 5MB | 30초 |
| AppLovin | 5MB | 30초 |

### Playable 검증 4단계
| 단계 | 항목 |
|------|------|
| 1 | Isolation: 외부 HTTP 요청 없음 |
| 2 | Interaction: 터치 + 마우스 이벤트 존재 |
| 3 | CTA: Install 버튼 + URL + 표시 트리거 |
| 4 | Size: 파일 크기 < 네트워크 제한 |

### 지원 메카닉
pin_pull, match3, merge, choice, runner

---

## SDK 통합 가이드

### Firebase Unity SDK
| 버전 | 최소 Android SDK | 주의사항 |
|------|------------------|----------|
| 13.7.0 | 24 | `ParameterItemId` → `"item_id"` 문자열 사용 |

### 조건부 컴파일 패턴
```csharp
// using 문도 조건부 블록 안에 포함해야 함
#if FIREBASE_ANALYTICS
using Firebase;
using Firebase.Analytics;
#endif

namespace Game
{
    public class FirebaseManager : Singleton<FirebaseManager>
    {
#if FIREBASE_ANALYTICS
        // 실제 Firebase 코드
#else
        // 시뮬레이션 코드
#endif
    }
}
```

### 플러그인 충돌 검사
빌드 전 확인사항:
- `googlemobileads-unity.aar`와 `GoogleMobileAdsPlugin.androidlib` 중복 금지
- 동일 네임스페이스 사용 플러그인은 하나만 유지

---

## Android 빌드 설정

### 아키텍처 값 (AndroidTargetArchitectures)
| 값 | 의미 | 용도 |
|----|------|------|
| 1 | ARMv7 | 구형 기기 |
| 2 | ARM64 | 최신 기기 |
| 4 | x86 | 에뮬레이터 |
| 5 | ARMv7 + ARM64 | **프로덕션 권장** |
| 7 | ARMv7 + ARM64 + x86 | 개발/테스트 |

### Gradle packagingOptions
**절대 exclude 금지:**
- `arm64-v8a` (최신 기기 필수)
- `armeabi-v7a` (구형 기기 지원)
- `x86` (에뮬레이터 테스트 시)

**안전한 exclude:**
- `armeabi` (구형, 거의 사용 안함)
- `mips`, `mips64` (지원 중단)

---

## 빌드 에러 패턴 및 해결

### 1. Manifest merger failed - 네임스페이스 충돌
```
Namespace 'com.google.unity.ads' used in: A, B
```
**해결:** 중복 플러그인 중 하나 삭제 (`.aar` 또는 `.androidlib`)

### 2. minSdkVersion 충돌
```
minSdkVersion 22 cannot be smaller than version 24
```
**해결:** `ProjectSettings.asset`에서 `AndroidMinSdkVersion` 상향

### 3. 에뮬레이터(BlueStacks) 설치 불가
**원인:** APK에 x86 아키텍처 미포함
**해결:**
- `AndroidTargetArchitectures: 7` (x86 포함)
- `packagingOptions`에서 x86 exclude 제거

### 4. CS0246 Firebase 네임스페이스 에러
**원인:** Firebase SDK 미설치 또는 using 문 위치 오류
**해결:**
- Firebase Unity SDK 설치
- using 문을 `#if` 블록 안에 포함

### 5. CS0117 ParameterItemId 에러
**원인:** Firebase SDK 버전에서 상수 제거됨
**해결:** `FirebaseAnalytics.ParameterItemId` → `"item_id"`

---

## 자주 하는 실수 (추가)
6. using 문을 조건부 컴파일 블록 밖에 배치
7. Firebase minSdkVersion 요구사항 미확인 (24 이상)
8. Android 플러그인 중복 (.aar + .androidlib)
9. 에뮬레이터 테스트 시 x86 아키텍처 누락
10. 프리팹 스케일 변경 시 Collider 크기 미조정

---

## 씬 구성 규칙 (Scene Composition)

### 필수 씬 (3개)
| 씬 | 용도 | 필수 요소 |
|----|------|-----------|
| Title.unity | 로딩/스플래시 | 로고, 로딩바, Main으로 자동 전환 |
| Main.unity | 메인 메뉴 | Play/Settings 버튼, 점수 표시 |
| GameScene.unity | 게임 플레이 | 게임 보드, UI, 매니저 오브젝트 |

### 각 씬 기본 구성
모든 씬에 반드시 포함:
- Main Camera
- Canvas (Screen Space - Overlay, CanvasScaler: Scale With Screen Size, 기획서 지정 해상도)
- EventSystem

### 에디터 자동화 범위 (SceneBuilder가 수행)

SceneBuilder.cs는 `[InitializeOnLoad]`로 1회 실행되며 아래를 자동 수행:

```
1. 씬 생성        — EditorSceneManager.NewScene()로 3씬 생성 + 저장
2. 기본 오브젝트   — Camera, Canvas, EventSystem, Managers 오브젝트 배치
3. Canvas 설정    — CanvasScaler: Scale With Screen Size, referenceResolution = 기획서 값
4. UI 계층구조    — Panel, Button, Text 등 기본 UI 오브젝트 생성 (pivot/anchor 기획서 기준)
5. Manager 배치   — "Managers" 빈 오브젝트에 Manager 싱글톤 컴포넌트 부착 + DontDestroyOnLoad
6. 프리팹 생성    — PrefabUtility.SaveAsPrefabAsset()로 프리팹 자동 생성
7. SerializeField — SerializedObject.FindProperty()로 Inspector 참조 자동 연결
8. Build Settings — EditorBuildSettings.scenes에 3씬 등록
9. Player Settings — companyName, minSdkVersion, targetArchitectures 등 자동 설정
```

### UI pivot/anchor 규칙
| UI 용도 | Anchor | Pivot | 예시 |
|---------|--------|-------|------|
| 상단 HUD (체력, 재화) | top-stretch | (0.5, 1) | HP 바, 골드 표시 |
| 하단 메뉴 | bottom-stretch | (0.5, 0) | 네비게이션 바 |
| 센터 팝업 | center | (0.5, 0.5) | 결과 팝업, 설정 |
| 전체 채움 배경 | stretch-stretch | (0.5, 0.5) | 배경 이미지, 오버레이 |
| 좌측 사이드바 | left-stretch | (0, 0.5) | 스킬 슬롯 |

기획서에 해상도/pivot 정보가 명시되면 해당 값을 우선 사용. 미명시 시 위 기본값 적용.

### 씬 빌더 패턴
```csharp
// Editor/SceneBuilder.cs
[InitializeOnLoad]
public class SceneBuilder
{
    static SceneBuilder()
    {
        EditorApplication.delayCall += () =>
        {
            // EditorPrefs로 1회만 실행
            if (EditorPrefs.GetBool("GameForge_SceneBuilt_ProjectName")) return;
            BuildScenes();
            EditorPrefs.SetBool("GameForge_SceneBuilt_ProjectName", true);
        };
    }
}
```

### Manager 싱글톤 배치
- GameScene에 "Managers" 빈 게임오브젝트 생성
- 모든 Manager 싱글톤 컴포넌트를 해당 오브젝트에 부착
- DontDestroyOnLoad 설정

### 런타임 오브젝트 로딩 규칙
런타임에 오브젝트가 필요할 때는 반드시 아래 방식 사용 (new GameObject 금지):
```csharp
// 1순위: Resources.Load (소규모 프로젝트)
var prefab = Resources.Load<GameObject>("Prefabs/Enemy");
var instance = Instantiate(prefab, spawnPoint, Quaternion.identity);

// 2순위: Addressables (대규모 프로젝트, 에셋 번들 관리)
var handle = Addressables.InstantiateAsync("Enemy", spawnPoint, Quaternion.identity);

// 3순위: ObjectPool (반복 생성·파괴 오브젝트)
var bullet = ObjectPool.Instance.Get("Bullet");
// ... 사용 후
ObjectPool.Instance.Return("Bullet", bullet);
```

---

## SDK 조건부 컴파일 규칙

### 필수 패턴
```csharp
// using 문도 반드시 #if 블록 안에!
#if FIREBASE_ANALYTICS
using Firebase;
using Firebase.Analytics;
#endif
```

### SDK 목록
| SDK | 전처리기 심볼 | 출력 경로 |
|-----|---------------|-----------|
| Firebase Analytics | `FIREBASE_ANALYTICS` | output/SDK/FirebaseManager.cs |
| Google AdMob | `GOOGLE_MOBILE_ADS` | output/SDK/AdMobManager.cs |
| Unity IAP | `UNITY_IAP` | output/SDK/IAPManager.cs |

### 시뮬레이션 모드
SDK가 설치되지 않은 환경에서도 빌드 가능하도록 `#else` 블록에 시뮬레이션 구현 필수:
```csharp
#if FIREBASE_ANALYTICS
    // 실제 Firebase 코드
#else
    // Debug.Log로 시뮬레이션
    public void LogEvent(string name) => Debug.Log($"[Firebase Sim] Event: {name}");
#endif
```

---

## Unity 프로젝트 경로
```
E:\AI_WORK_FLOW_TEST\{project}\   # Unity 프로젝트 루트
```
- output/*.cs, output/SDK/*.cs → Assets/Scripts/
- output/Editor/*.cs → Assets/Editor/

## 출력 폴더 구조

### Unity (platform: unity)
```
E:\AI\projects\{project}\output\
├── *.cs            # 게임 소스코드 (런타임)
├── Data\           # ScriptableObject 에셋 정의 (런타임 데이터)
├── SDK\            # SDK 매니저 (조건부 컴파일)
│   ├── FirebaseManager.cs
│   ├── AdMobManager.cs
│   └── IAPManager.cs
└── Editor\         # 에디터 스크립트 (Assets/Editor/에 복사)
    ├── SceneBuilder.cs       # 씬 자동 구성 + 프리팹 생성 + SerializeField 연결
    ├── ProjectConfigurator.cs # Build Settings + Player Settings 자동 설정
    └── PrefabBuilder.cs      # 프리팹 자동 생성 (필요 시 분리)
```

### Design Workflow (platform: design)
```
E:\AI\projects\{project}\
├── design_workflow\         # YAML (AI-readable)
│   ├── concept.yaml
│   ├── layer1\game_design.yaml
│   ├── layer2\system_spec.yaml, build_order.yaml
│   ├── systems\*.yaml       # Domain system specs
│   ├── balance\*.yaml       # Difficulty curve, economy
│   ├── content\*.yaml       # Beat chart, level design, progression
│   ├── bm\*.yaml            # Monetization
│   ├── liveops\*.yaml       # Operations
│   ├── layer3\nodes\*.yaml  # AI spec nodes
│   └── standards\*.yaml     # Stage 0 design standards
├── docs\                    # Docx (Human-readable) + generation scripts
│   ├── generate_docs.py     # YAML → Docx converter
│   ├── embed_to_mongodb.py  # YAML → MongoDB design_base
│   ├── normalize_and_promote.py  # Normalize + Expert DB promotion
│   ├── {Project}_게임기획서.docx
│   ├── {Project}_시스템설계서.docx
│   ├── {Project}_밸런스설계서.docx
│   ├── {Project}_콘텐츠설계서.docx
│   ├── {Project}_BM_LiveOps설계서.docx
│   └── {Project}_빌드오더.docx
└── feedback\design\         # Validation reports + feedback
```

**듀얼 출력 규칙**: YAML 변경 시 반드시 Docx도 재생성. YAML은 AI 에이전트가, Docx는 디렉터/기획자가 사용.

### Playable (platform: playable)
```
E:\AI\projects\{project}\output\
└── playable.html   # 최종 결과물 (단일 HTML 파일)

E:\AI\projects\{project}\assets\     # (선택) 사용자 제공 이미지
└── asset_spec.yaml
```

### Unity 프로젝트 복사 규칙
- `output/*.cs`, `output/SDK/*.cs` → `Assets/Scripts/`
- `output/Editor/*.cs` → `Assets/Editor/` (Scripts가 아님!)

---

## 자주 하는 실수 (추가 2)
11. Editor 스크립트를 Assets/Scripts/에 복사 → **Assets/Editor/**가 맞음
12. [InitializeOnLoad]에서 EditorApplication.delayCall 없이 직접 실행
13. 씬 빌더에서 EditorPrefs 체크 누락 (매번 재실행됨)
14. SDK using 문을 #if 블록 밖에 배치 → 빌드 에러
15. 런타임 코드에서 new GameObject() 사용 → Resources.Load/ObjectPool 사용해야 함
16. Editor 스크립트에서 pivot/anchor 미설정 → 기획서 해상도 기준으로 설정 필수
17. SerializedObject.ApplyModifiedProperties() 호출 누락 → Inspector 값 반영 안 됨

## 자주 하는 실수 (추가 3 — Integration Contract System)
18. ObjectPool 키를 코드에 사용하면서 프리팹 미생성 → _ASSET_MANIFEST.yaml에 등록 + PrefabBuilder에서 생성 필수
19. [SerializeField] 제거하여 에러 수정 → SceneBuilder WireField 깨짐 → Error Fix Protocol 위반
20. EventBus.Publish만 하고 Subscribe 없음 → _CONTRACTS.yaml에서 양방향 검증
21. 에러 수정 시 L3 YAML 참조 안 함 → 기획 의도 이탈 (로직 우회형 null 체크)
22. Phase 완료 후 _CONTRACTS.yaml 미갱신 → 다음 Phase Coder가 잘못된 계약 참조
23. SceneBuilder에 WireField 추가하면서 대응하는 [SerializeField] 누락 (또는 반대)
24. Resources.Load 경로와 실제 파일 경로 불일치 → _ASSET_MANIFEST.yaml로 크로스 체크
25. 40개 파일 동시 생성 시 파일 간 메서드 시그니처 불일치 → _CONTRACTS.yaml method_calls로 사전 정의

---

## 히스토리 및 피드백 경로
```
E:\AI\
├── History\                          # 프로젝트별 개발 히스토리
│   ├── KPI_Template.md               # KPI 공용 템플릿
│   └── {ProjectName}\                # 프로젝트별 하위 폴더
│       ├── KPI.md                    # KPI 보고서
│       └── Project_History.md        # 프로젝트 히스토리
└── Feedback\                         # 워크플로우 개선 피드백
```

---

## Design DB (기획 데이터베이스)

### DB 저장소
MongoDB Atlas (`aigame` DB) — `design_base`, `design_expert`, `pending` 컬렉션 사용.
접속: `scripts/lib/db-client.js` (`findDesign`, `upsertDesign`, `searchDesignByPriority`) 또는 `pymongo`

### 설계 표준 저장소 (Stage 0)
파일 시스템: `E:\AI\design_standard\{genre}\` (component_map, parameters, schema, domain_priority)
예: `E:\AI\design_standard\puzzle\schema\` — SQL 스키마, 레벨 데이터 포맷, BM 파라미터 등

### Design 분류 체계 (Domain 9종)
| Domain | 정의 |
|--------|------|
| InGame | 인게임 시스템 (전투, 스킬, 캐릭터) |
| OutGame | 아웃게임 시스템 (인벤토리, 상점) |
| Balance | 밸런스 (성장, 전투, 경제, 확률) |
| Content | 콘텐츠 (스테이지, 퀘스트, 몬스터) |
| BM | 비즈니스 모델 (결제, 패키지, LTV) |
| LiveOps | 라이브 운영 (이벤트, 시즌, 업데이트) |
| UX | 사용자 경험 (UI 플로우, 튜토리얼) |
| Social | 소셜 (길드, PvP, 친구) |
| Meta | 메타 (업적, 컬렉션, 도감) |

### Design 데이터 유형
formula, table, rule, flow, config, content_data

### Design 소스 유형 (6종)
internal_original, internal_produced, internal_live, observed, community, generated

### Design DB 검색 우선순위
| 순위 | 검색 대상 | 조건 |
|------|-----------|------|
| 1 | Expert DB (해당 장르) | genre 일치 AND score >= 0.6 |
| 2 | Expert DB (Generic) | genre = Generic AND score >= 0.6 |
| 3 | Genre Base DB | genre 일치 |
| 4 | Generic Base DB | genre = Generic |
| 5 | AI 생성 (참조 없음) | 기획서 기반 신규 생성 |

### Design 피드백 카테고리 (14종)
| 그룹 | 타입 |
|------|------|
| SYSTEM | RULE_CONFLICT, MISSING_FEATURE, OVER_COMPLEXITY |
| BALANCE | CURVE_TOO_STEEP, CURVE_TOO_FLAT, ECONOMY_IMBALANCE, FORMULA_ERROR |
| CONTENT | PACING_ISSUE, LOGIC_ERROR |
| BM | PAY_WALL_TOO_HARD, VALUE_MISMATCH |
| UX | FLOW_BROKEN, TUTORIAL_GAP |
| DIRECTION | OFF_TARGET |

### Design → Code 매핑
| Design Domain | Code System |
|---------------|-------------|
| InGame | Battle, Skill, Character, Stage |
| OutGame | Inventory, Shop, Item |
| Balance | Calculator/Processor Roles |
| Content | Quest, Stage, Reward |
| BM | Shop, IAP |
| LiveOps | Config + Service + Scheduler Role |
| UX | UI, Audio |
| Social | Network, Guild |
| Meta | Achievement, Collection |

### Design Workflow 명령어
| 명령어 | 용도 | 담당 Agent |
|--------|------|-----------|
| /parse-design | 기획 문서 → Design DB | Design DB Builder |
| /generate-design-v2 | 8단계 기획 워크플로우 | Designer (design mode) → Lead 오케스트레이션 |
| /validate-design | 기획 통합 검증 | Design Validator |
| /sync-live | 라이브 데이터 동기화 | Design DB Builder |

### Design Workflow Agent
| Agent | Model | 역할 |
|-------|-------|------|
| Lead | Opus | Design Workflow 오케스트레이션 (Stage 2→3→4→5→6 흐름 관리, 피드백 라우팅) |
| Designer | Sonnet | Stage 2 기획 생성 (YAML + Docx 듀얼 출력), Expert DB 참조 |
| Design Validator | Sonnet | Stage 3/5 검증, 점수 산출, Expert 승격 판단 |
| Design DB Builder | Sonnet | Stage 1/6 DB 저장, 정규화, Expert DB 실행 |

### Design Workflow 에이전트 간 흐름
```
Designer → (YAML + integration check) → Lead → Design Validator
Design Validator → (stage_report.json + score) → Lead → [User for Stage 4]
[User feedback] → Lead → Designer (수정) → Design Validator (Stage 5)
Design Validator → (promotion_eligible) → Lead → Design DB Builder (Stage 6)
```

### 듀얼 출력 표준 (2026-03-12 확립)
- **YAML** (`design_workflow/`): AI 에이전트가 검증/코드생성/DB 저장에 사용
- **Docx** (`docs/`): 디렉터/기획자가 검수에 사용 (`generate_docs.py`로 자동 생성)
- YAML 변경 시 Docx 반드시 재생성
- BalloonFlow (Puzzle, Expert DB) 구조가 기준 템플릿

### Play Verification (Stage 7)
| 모드 | 설명 | 스크립트 |
|------|------|---------|
| 7-1 accelerated | BlueStacks ADB → Virtual Player → 예측 vs 실측 비교 | play-verification.js |
| 7-2 longterm | Day-1 예측 → 일별 diff → Day-30 대조 | play-verification.js |
| 7-3 mass | 페르소나 × N 인스턴스 대규모 시뮬레이션 | play-verification.js |

```
# 예시 실행
node E:/AI/scripts/play-verification.js --project MyGame --mode accelerated --build path/to/build.apk
node E:/AI/scripts/virtual-player-bridge.js --input vp_export.yaml --project MyGame
node E:/AI/scripts/design-version.js --designId BattleSystem --genre rpg --domain ingame --version 1.1.0 --phase post_launch
```

---

## AI Tester 시스템

AI Tester는 Design Workflow와 두 가지 역할로 연계됩니다.

### PRIMARY: 외부 게임 → Design DB 데이터 수집 (Stage 1 입력)
- 외부 레퍼런스 게임을 10명 AI 전문 관찰로 분석 (소스코드 접근 없음)
- 32개 파라미터 추정 결과를 Base Design DB로 가공 (source: observed)
- 정확도 약 85~89.5%, 나머지 10~15%는 자체 설계로 채움 (차별화 요소)
- 변환: AI Tester JSON → design-parser.js --source-type observed → Design DB

### SECONDARY: 자사 게임 빌드 검증 (Stage 7)
- BlueStacks + ADB 인프라로 자사 빌드 가속 테스트
- 밸런스 예측값 vs 실측값 비교 → 기획 피드백 생성
- 7-1 가속 테스트 / 7-2 장기 테스트 / 7-3 대규모 가상 유저 시뮬레이션
