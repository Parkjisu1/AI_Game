# AI Game Code Generation Workflow

통합 워크플로우 문서. Agent Teams를 활용한 병렬 파이프라인.

---

## 전체 구조

```
E:\AI\
├── CLAUDE.md                    # 마스터 컨텍스트
├── .claude\
│   ├── commands\                # Slash Commands
│   │   ├── parse-source.md      # /parse-source
│   │   ├── generate-design.md   # /generate-design
│   │   ├── generate-code.md     # /generate-code
│   │   └── validate-code.md     # /validate-code
│   ├── skills\                  # Auto-trigger Skills
│   │   ├── unity-csharp\
│   │   ├── game-patterns\
│   │   └── db-search\
│   └── agents\                  # Custom Agent Definitions
│       ├── designer.md          # 기획 AI (Sonnet)
│       ├── main-coder.md        # 메인 코드 생성 AI (Opus)
│       ├── sub-coder.md         # 서브 코드 생성 AI (Sonnet)
│       ├── playable-coder.md    # 플레이어블 코드 생성 AI (Sonnet)
│       ├── validator.md         # 검증 AI (Sonnet)
│       └── db-builder.md        # DB 구축 AI (Sonnet)
├── db\                          # 코드 데이터베이스
│   ├── base\                    # Base Code (파싱 결과)
│   ├── expert\                  # 검증된 코드 (score >= 0.6)
│   └── rules\                   # 축적된 규칙
├── projects\                    # 프로젝트별 작업 폴더
└── docs\                        # 문서
```

---

## Agent Team 구조: AI-Game-Creator

```
                     ┌──────────────────────┐
                     │    Team Lead (Opus)   │
                     │   - 태스크 분배/조율   │
                     │   - 결과 통합          │
                     │   - 품질 게이트 관리    │
                     └──────────┬───────────┘
              ┌─────────────────┼─────────────────┐
        ┌─────┴──────┐   ┌──────────────────┐   ┌──────┴───────┐
        │  Designer  │   │  Main Coder      │   │  Validator   │
        │  (Sonnet)  │   │  (Opus)          │   │  (Sonnet)    │
        │  기획 전문  │   │  Core + 핵심     │   │  검증 전문    │
        └────────────┘   ├──────────────────┤   └──────────────┘
                         │  Sub Coder x2    │
                         │  (Sonnet) 병렬   │
                         ├──────────────────┤
                         │ Playable Coder   │
                         │  (Sonnet) HTML5  │
                         └──────────────────┘
                         ┌──────────────────┐
                         │   DB Builder     │  (필요 시)
                         │    (Sonnet)      │
                         └──────────────────┘
```

### Agent별 역할

| Agent | Model | 역할 | 비고 |
|-------|-------|------|------|
| **Lead** | Opus | PM - 태스크 분배, 결과 통합, 품질 관리 | delegate 모드 |
| **Designer** | Sonnet | 기획 - 기획서 → 명세서 → YAML 노드 | Unity + Playable 겸임 |
| **Main Coder** | Opus | 메인 개발 - Core 아키텍처, 핵심 시스템, _ARCHITECTURE.md | Unity 전용, Phase 0 전담 |
| **Sub Coder x2** | Sonnet | 서브 개발 - Main 패턴 따라 할당 노드 구현 | Unity 전용, 병렬 작업 |
| **Playable Coder** | Sonnet | HTML5 플레이어블 광고 코드 생성 (단일 파일) | Playable 전용 |
| **Validator** | Sonnet | QA - Unity 5단계 / Playable 4단계 검증 | platform별 분기 |
| **DB Builder** | Sonnet | DB 구축 - 소스 파싱 → 분류 → DB 저장 | 사용자 호출 시만 |

---

## 파이프라인 개요

```
[Phase 1: DB 구축] ─ (DB Builder) ──────────────────────┐
  소스 폴더 → /parse-source → db/base/                   │
                                                         │
[Phase 2: 기획서 생성] ─ (Designer) ─────────────────────┤
  게임 컨셉 → /generate-design → projects/{name}/designs │
                                                         │
[Phase 3: 코드 생성] ─ (Coder x N 병렬) ────────────────┤
  AI_기획서 → /generate-code → projects/{name}/output    │
                                                         │
[Phase 4: 검증 & 축적] ─ (Validator) ───────────────────┘
  생성 코드 → /validate-code → db/expert/
```

---

## Phase 1: DB 구축 (DB Builder)

### 목적
자사 프로젝트 소스를 파싱하여 AI가 참조할 Base Code DB 구축

### 실행
```
/parse-source E:\Projects\AshAndVeil\Scripts rpg
```

### 병렬화
- 여러 프로젝트 소스를 동시에 파싱 가능
- DB Builder 여러 명 투입 시 장르별 분담

### 분류 체계
```
Layer > Genre > Role > Tag

Layer: Core / Domain / Game
Genre: Generic / RPG / Idle / Merge / SLG / Tycoon / Simulation / Puzzle / Casual
Role: Manager / Controller / Calculator / ... / UX (21종)
Tag: Major (7종) + Minor (11종)
```

### 출력 구조
```
db/base/{genre}/{layer}/
├── index.json        # 경량 인덱스
└── files/
    └── {fileId}.json # 상세 정보
```

---

## Phase 2: 기획서 생성 (Designer)

### 목적
게임 컨셉을 AI가 사용할 수 있는 정규화된 기획서로 변환

### 실행
```
/generate-design "방치형 RPG, 자동 전투, 캐릭터 수집" rpg MyGame
```

### 3단계 변환
```
Layer 1: 게임 기획서 (인간 읽기용)
    ↓
Layer 2: 시스템 명세서 (시스템 목록, 연결 관계)
    ↓
Layer 3: AI_기획서 (YAML 노드, 코드 생성용)
    + build_order.yaml (Phase 할당)
```

### 출력 구조
```
projects/MyGame/designs/
├── game_design.yaml      # Layer 1
├── system_spec.yaml      # Layer 2
├── build_order.yaml      # 빌드 순서
└── nodes/                # Layer 3
    ├── Singleton.yaml
    ├── EventManager.yaml
    ├── BattleManager.yaml
    └── ...
```

---

## Phase 3: 코드 생성 (Coder x N 병렬)

### 목적
AI_기획서를 기반으로 DB를 참조하여 C# 코드 생성

### 실행
```
/generate-code BattleManager MyGame
```

### 병렬 실행 전략

```
시간 →  ──────────────────────────────────────────────→

Phase 0:  [Main Coder: Singleton + EventManager + ObjectPool]
(Core)    [Main Coder: _ARCHITECTURE.md 생성]
                      │
          [Validator: Phase 0 전체 검증]
                      │
Phase 1:  ├─[Main Coder: BattleManager (복잡)]──→[Validator]
(기반Dom) ├─[Sub Coder-1: DataManager       ]──→[Validator]  ← 병렬
          ├─[Sub Coder-2: ResourceManager   ]──→[Validator]
                      │
Phase 2:  ├─[Main Coder: SkillSystem (복잡) ]──→[Validator]
(상위Dom) ├─[Sub Coder-1: QuestManager      ]──→[Validator]  ← 병렬
          ├─[Sub Coder-2: ShopManager       ]──→[Validator]
                      │
Phase 3:  ├─[Sub Coder-1: MainMenuPage      ]──→[Validator]
(Game)    ├─[Sub Coder-2: SettingsPopup     ]──→[Validator]  ← 병렬
          ├─[Main Coder: GameManager (통합) ]──→[Validator]
```

**핵심 규칙:**
- **Phase 0**: Main Coder 단독 → Core + _ARCHITECTURE.md 생성
- **Phase 1+**: Main(복잡) + Sub x2(일반) 병렬 생성
- Sub Coder는 반드시 _ARCHITECTURE.md와 Core 코드를 먼저 읽음
- Phase 간 의존성 = Validator 검증 통과 후 다음 Phase 시작
- Validator는 완료되는 순서대로 즉시 검증

### DB 검색 우선순위
```
1. Expert DB (해당 장르) - score >= 0.6
2. Expert DB (Generic) - score >= 0.6
3. Genre Base DB
4. Generic Base DB
5. AI_기획서 logicFlow 기반 생성
```

### 자가 검증 (5단계)
```
1. Syntax: 문법, using, 타입
2. Dependency: 참조 클래스 존재
3. Contract: provides/requires 일치
4. NullSafety: null 체크
5. Logic: 비즈니스 로직
```

### 출력 구조
```
projects/MyGame/output/
├── *.cs              # 게임 소스코드
├── SDK/              # SDK 매니저 (조건부 컴파일)
└── Editor/           # 에디터 스크립트
```

---

## Phase 4: 검증 & 축적 (Validator)

### 목적
생성된 코드를 검증하고, 품질 좋은 코드를 Expert DB에 축적

### 실행
```
/validate-code projects/MyGame/output/ MyGame
```

### 검증 → 피드백 루프

```
                ┌─────────────┐
                │  Validator   │
                │  5단계 검증   │
                └──────┬──────┘
                       │
              ┌────────┴────────┐
              │                 │
         [PASS]            [FAIL]
              │                 │
     ┌────────┴──────┐  ┌──────┴───────┐
     │ 점수 +0.2     │  │ 피드백 JSON  │
     │ Expert 승격?  │  │ → Lead 보고  │
     └───────────────┘  │ → Coder 재생성│
                        └──────────────┘
```

### 신뢰도 점수
```
초기 저장: 0.4
피드백 반영: +0.2
재사용 성공: +0.1
재사용 실패: -0.15
Expert 승격: score >= 0.6
```

### Rules 추출
반복되는 피드백 → db/rules/ 에 저장

---

## 태스크 의존성 (Task Graph)

Lead가 생성하는 태스크 구조 예시:

```
Task 1:  [Designer]     게임 기획서 생성
Task 2:  [Designer]     시스템 명세서 생성          (blockedBy: 1)
Task 3:  [Designer]     AI_기획서 노드 + 빌드오더   (blockedBy: 2)
─────────────────────────────────────────────────────
Task 4:  [Main Coder]   Phase 0 Core 전체 + _ARCHITECTURE.md  (blockedBy: 3)
Task 5:  [Validator]    Phase 0 검증               (blockedBy: 4)
─────────────────────────────────────────────────────
Task 6:  [Main Coder]   BattleManager.cs (복잡)    (blockedBy: 5, Phase 1)
Task 7:  [Sub Coder-1]  DataManager.cs             (blockedBy: 5, Phase 1)
Task 8:  [Sub Coder-2]  ResourceManager.cs         (blockedBy: 5, Phase 1)
Task 9:  [Validator]    Phase 1 검증               (blockedBy: 6, 7, 8)
─────────────────────────────────────────────────────
Task 10: [Main Coder]   SkillSystem.cs (복잡)      (blockedBy: 9, Phase 2)
Task 11: [Sub Coder-1]  QuestManager.cs            (blockedBy: 9, Phase 2)
Task 12: [Sub Coder-2]  ShopManager.cs             (blockedBy: 9, Phase 2)
Task 13: [Validator]    Phase 2 검증               (blockedBy: 10, 11, 12)
─────────────────────────────────────────────────────
... (Phase 3 반복)
```

---

## Platform 분기: Unity vs Playable

Designer가 생성한 기획서의 `platform` 필드에 따라 파이프라인이 분기됩니다.

```
                  [Phase 2: Designer]
                   game_design.yaml
                         │
                  platform 필드 확인
                    ┌─────┴─────┐
                    ▼           ▼
             unity (기존)   playable (신규)
                    │           │
        ┌───────────┤           │
        ▼           ▼           ▼
   [Main Coder] [Sub x2]  [Playable Coder]
   Phase 0~3 병렬          단일 HTML 생성
        │           │           │
        └─────┬─────┘           │
              ▼                 ▼
       [Validator]         [Validator]
       C# 5단계 검증       Playable 4단계 검증
              │                 │
              ▼                 ▼
        output/*.cs        output/playable.html
```

---

## Playable Pipeline (platform: playable)

### 개요
HTML5 단일 파일 플레이어블 광고를 생성하는 경량 파이프라인.
Unity 파이프라인과 팀 구조를 공유하되, Phase 분할 없이 단일 스텝으로 진행합니다.

### 팀 구성 (경량)

| Agent | Model | 역할 |
|-------|-------|------|
| **Lead** | Opus | PM - 태스크 분배/조율 |
| **Designer** | Sonnet | 기획 - 플레이어블 기획서 (YAML) |
| **Playable Coder** | Sonnet | HTML5 코드 생성 (단일 파일) |
| **Validator** | Sonnet | 규격 검증 (크기/격리/CTA) |

- Main Coder / Sub Coder는 **사용하지 않음**
- Playable Coder 1명이면 충분 (단일 파일 출력)

### 파이프라인 흐름

```
[Phase 2: 기획서 생성] ─ (Designer)
  게임 컨셉 + 메카닉 → playable YAML 노드 1개

[Phase 3: 코드 생성] ─ (Playable Coder)
  YAML → HTML5 Canvas/JS → 단일 playable.html

[Phase 4: 검증] ─ (Validator)
  Playable 4단계: Isolation → Interaction → CTA → Size
```

### 태스크 구조 (단순)

```
Task 1:  [Designer]         플레이어블 기획서 생성
Task 2:  [Playable Coder]   HTML5 플레이어블 코드 생성   (blockedBy: 1)
Task 3:  [Validator]        플레이어블 검증              (blockedBy: 2)
```

### Playable 검증 4단계

| 단계 | 항목 | 기준 |
|------|------|------|
| 1 | Isolation | 외부 HTTP 요청 없음 |
| 2 | Interaction | 터치 + 마우스 이벤트 핸들러 존재 |
| 3 | CTA | Install 버튼 + URL + 표시 트리거 존재 |
| 4 | Size & Spec | 파일 크기 < 네트워크 제한, viewport 설정 |

### 출력 구조

```
E:\AI\projects\{project}\
├── designs\
│   ├── game_design.yaml          # platform: playable
│   └── nodes\
│       └── {GameName}Playable.yaml
├── output\
│   └── playable.html             # 최종 결과물 (단일 파일)
├── assets\                       # (선택) 사용자 제공 이미지
│   └── asset_spec.yaml
└── feedback\
    └── playable_feedback.json
```

### 에셋 처리

| 모드 | 설명 | 에셋 필요 |
|------|------|-----------|
| code_only | Canvas 도형 + CSS로 비주얼 표현 | 불필요 |
| provided | 사용자가 assets/에 PNG/SVG 제공 → Base64 인라인 | 필요 |

### 지원 메카닉

| 메카닉 | 설명 | code_only 가능 |
|--------|------|----------------|
| pin_pull | 핀 뽑기 + 물리 시뮬 | O |
| match3 | 3매치 퍼즐 | O |
| merge | 드래그&드롭 합성 | O |
| choice | 선택지 분기 | △ (이미지 의존) |
| runner | 자동 달리기 + 장애물 | △ (스프라이트 필요) |

---

## 실행 방법

### Unity 프로젝트 시작 (사용자)
```
RPG 방치형 게임을 만들어줘. 자동 전투, 캐릭터 수집 시스템.
Agent Team을 구성해서 기획-코드생성-검증을 병렬로 진행해줘.
Coder는 3명으로 구성해줘.
```

### Playable 프로젝트 시작 (사용자)
```
핀뽑기 플레이어블 광고를 만들어줘. 레벨 3개, 에셋 없이 코드만으로.
Agent Team으로 진행해줘.
```

### Lead 자동 수행 (Unity)
1. Team 생성: AI-Game-Creator
2. Designer에게 기획서 생성 태스크 할당
3. 기획서 완료 시 build_order 기반 Phase별 태스크 생성
4. 같은 Phase 노드들을 Coder 3명에게 분배
5. 완료 코드를 Validator가 즉시 검증
6. 검증 실패 시 해당 Coder에게 피드백 전달 (재생성)
7. 전체 완료 시 결과 보고 + 팀 정리

### Lead 자동 수행 (Playable)
1. Team 생성: AI-Game-Creator
2. Designer에게 플레이어블 기획서 생성 태스크 할당
3. 기획서 완료 시 Playable Coder에게 코드 생성 태스크 할당
4. 완료 HTML을 Validator가 검증
5. 검증 실패 시 Playable Coder에게 피드백 전달
6. 전체 완료 시 결과 보고 + 팀 정리

### DB 구축 (별도)
```
소스코드 DB를 구축해줘.
E:\Projects\AshAndVeil\Scripts를 RPG 장르로 파싱해줘.
DB Builder를 사용해서 병렬로 진행해줘.
```

---

## 명령어 요약

### Code Workflow
| 명령어 | 용도 | 담당 Agent |
|--------|------|-----------|
| `/parse-source` | 소스 파싱 → Code DB | DB Builder |
| `/generate-design` | 기획서 생성 | Designer |
| `/generate-code` | 코드 생성 | Main/Sub Coder |
| `/validate-code` | 코드 검증 | Validator |

### Design Workflow
| 명령어 | 용도 | 담당 Agent |
|--------|------|-----------|
| `/parse-design` | 기획 문서 → Design DB 파싱 저장 | Design DB Builder |
| `/generate-design-v2` | 8단계 기획 워크플로우 전체 실행 | Designer (design mode) |
| `/validate-design` | 기획 교차 검증 + 밸런스 시뮬 | Design Validator |
| `/sync-live` | 라이브 지표 → Design DB 동기화 | Design DB Builder |

---

## Skills (자동 트리거)

| Skill | 트리거 조건 | 역할 |
|-------|-------------|------|
| unity-csharp | *.cs, Unity, C# | 코딩 규칙, 패턴 |
| game-patterns | 기획, 설계, 아키텍처 | 설계 패턴, 구조 |
| db-search | DB 검색, 파싱 | 검색 규칙, 점수 |

---

## 핵심 원칙

1. **3-AI 분리** - Designer, Coder, Validator 각 단계 전문화
2. **정규화된 분류** - Layer/Genre/Role/Tag로 환각 방지
3. **DB 참조 필수** - 코드 생성 시 기존 코드 참조
4. **점진적 축적** - 피드백 반영 → Expert DB 승격
5. **병렬 작업** - Agent Teams로 같은 Phase 내 노드 동시 생성
6. **품질 게이트** - Validator 검증 통과 후 다음 Phase 진행

---

## UX (연출) Role

### 정의
UX Role은 **코드로 구현하는 동적 연출**을 담당하는 분류입니다.
UI 배치/위치가 아닌, 런타임에 동작하는 시각적 연출 로직을 의미합니다.

**핵심**: 커졌다/작아졌다, 합쳐졌다/나눠졌다, 날아갔다, 흔들렸다, 사라졌다/나타났다 등
오브젝트의 동적 변화를 코드로 제어하는 모든 연출 코드.

### 클래스명 패턴
`*Effect`, `*Tweener`, `*Performer`, `*Presenter`

### UX 연출 유형
| 유형 | 설명 | 구현 예시 |
|------|------|-----------|
| Scale | 확대/축소, 펀치 스케일, 등장/퇴장 | DOTween: `transform.DOScale()`, `DOPunchScale()` |
| Move | 이동, 날아감, 슬라이드, 바운스 | DOTween: `transform.DOMove()`, `DOJump()`, `DOPath()` |
| Merge | 여러 오브젝트가 한 지점으로 합쳐짐 | Sequence: 복수 Move → 도착 시 Scale + Destroy |
| Split | 하나가 여러 개로 분리/퍼짐 | Spawn + 각각 DOMove 분산 |
| Fade | 페이드인/아웃, 알파 변화 | `canvasGroup.DOFade()`, `spriteRenderer.DOFade()` |
| Shake | 화면 흔들림, 오브젝트 떨림 | `DOShakePosition()`, `DOShakeRotation()` |
| Rotate | 회전, 스핀 | `transform.DORotate()`, `DOLocalRotate()` |
| Color | 색상 변화, 점멸, 하이라이트 | `spriteRenderer.DOColor()`, `image.DOColor()` |
| Particle | 파티클 재생/정지 제어 | `ParticleSystem.Play()`, Pool 기반 이펙트 |
| Sequence | 위 연출들의 조합/체이닝 | DOTween Sequence: `Append`, `Join`, `Insert` |

### UX Role 규칙
- **Layer**: Domain 또는 Game (Core 아님 — 연출은 게임 특화 로직)
- **로직과 분리**: Manager/Controller에서 연출 코드 직접 작성 금지 → UX 클래스로 분리 위임
- **이벤트 트리거**: EventManager 구독으로 연출 시작 (직접 참조 최소화)
- **파라미터 노출**: duration, ease, delay, curve 등은 `[SerializeField]`로 Inspector 조정 가능하게
- **풀링**: 빈번한 이펙트는 ObjectPool 사용 (Instantiate/Destroy 금지)
- **금지**: Update()에서 매 프레임 연출 → 이벤트 기반 트리거로 전환

### 코드 패턴 예시
```csharp
// UX Role 예시: 매칭 성공 연출
public class MatchEffect : MonoBehaviour
{
    [SerializeField] private float scaleUpDuration = 0.15f;
    [SerializeField] private float flyDuration = 0.4f;
    [SerializeField] private Ease flyEase = Ease.InBack;
    [SerializeField] private ParticleSystem mergeParticle;

    public void PlayMerge(Transform[] sources, Vector3 targetPos, Action onComplete)
    {
        var seq = DOTween.Sequence();
        foreach (var src in sources)
        {
            seq.Join(src.DOScale(1.2f, scaleUpDuration));
            seq.Append(src.DOMove(targetPos, flyDuration).SetEase(flyEase));
        }
        seq.OnComplete(() =>
        {
            mergeParticle.transform.position = targetPos;
            mergeParticle.Play();
            onComplete?.Invoke();
        });
    }
}
```

### DB 분류 시 주의
- **UX vs Handler**: 시각적 연출 목적이면 UX, 이벤트/데이터 처리 목적이면 Handler
- **UX vs Controller**: 오브젝트 자체의 상태 제어면 Controller, 연출 동작이면 UX
- 예: `MatchEffect` → UX (합체 연출) / `MatchChecker` → Validator (매칭 판정 로직)

---

## KPI 보고 체계

프로젝트 완료 시 `E:\AI\History\{ProjectName}\` 폴더에 KPI 보고서를 작성합니다.
템플릿: `E:\AI\History\KPI_Template.md`

### KPI 측정 항목
| 지표 | 설명 | 측정 시점 |
|------|------|-----------|
| 디버깅 시간 | 검증 실패 → 재생성 완료까지 소요 시간 | Phase별 검증 후 |
| 작성 피드백 횟수 | Validator가 생성한 피드백 JSON 수 | Phase별 검증 후 |
| 베이스 코드 편입 비율 | DB 참조 사용 노드 / 전체 노드 | 코드 생성 완료 후 |
| 데이터셋 수 | Base DB + Expert DB 항목 수 변화 | 프로젝트 전후 비교 |
| 데이터 코드 내부 수 | 신뢰도 점수 분포, Role별 분포 변화 | 프로젝트 전후 비교 |
| UX 구현율 | UX 노드 구현 수 / 기획된 UX 노드 수 | 프로젝트 완료 시 |

### 보고서 파일 규칙
```
E:\AI\History\{ProjectName}\KPI.md
E:\AI\History\{ProjectName}\Project_History.md
```

---

## Design Workflow Pipeline (8단계)

게임 기획을 데이터화하고 검증하는 독립 파이프라인입니다.
Code Workflow와 병렬 또는 선행 실행 가능합니다.

### 파이프라인 다이어그램

```
Stage 1: DB 가공 (Design DB Builder)
  기존 기획 문서 / AI Tester 관찰 자료 → /parse-design → db/design/base/
              ↓
Stage 2: 기획 생성 (Designer - design mode)
  2-1 컨셉 정의 → 2-2 시스템 기획 → 2-3 밸런스 기획 ─┐
                                    → 2-4 콘텐츠 기획 ─┤ (2-3, 2-4 병렬 가능)
                                                      ↓
                                    → 2-5 BM/LiveOps 기획 (2-3 완료 후)
              ↓
Stage 3: 통합 검증 (Design Validator)
  교차 일관성 체크 → 유저 여정 시뮬레이션 → 누락 검출 → 자가 검증
              ↓
Stage 4: 디렉터 검수 (사람)
  기획 리뷰 → 피드백 없으면 Stage 6, 피드백 있으면 재생성 요청
              ↓
Stage 5: 재생성 평가 (Design Validator 보조)
  피드백 반영 확인 → 히스토리 분석 → 이전 버전 차이 기록
              ↓
Stage 6: DB 축적 (Design DB Builder)
  신뢰도 점수 산출 → score >= 0.6 시 Expert DB 승격 → Rules 추출
              ↓ (코드 Workflow 연결)
Stage 7: 플레이 검증 (AI Tester + play-verification.js)
  7-1 자사 가속 테스트 → 7-2 장기 테스트 → 7-3 대규모 가상 유저 시뮬
              ↓
Stage 8: 라이브 동기화 (Design DB Builder)
  밸런스 패치 → 버전 추가 → KPI 기록 → 다음 프로젝트 입력으로 순환
```

### Design Agent 역할

| Agent | Model | 역할 | 단계 |
|-------|-------|------|------|
| **Design DB Builder** | Sonnet | 기획 문서 파싱 → Design DB 저장, 라이브 데이터 동기화 | 1, 6, 8 |
| **Designer (design mode)** | Sonnet | 기획 생성 (2-1~2-5 sub-steps), 도메인별 YAML 생성 | 2 |
| **Design Validator** | Sonnet | 기획 교차 검증, 밸런스 시뮬, 일관성 점검, 점수 관리 | 3, 5 보조 |
| **디렉터 (사람)** | - | 기획 검수, 피드백 제공, 최종 승인 | 4 |

### Design Task Graph 템플릿

```
Task D1:  [Design DB Builder]  기획 문서 파싱 → Design DB (Stage 1)
Task D2:  [Designer]           컨셉 정의 (2-1)                             (blockedBy: D1)
Task D3:  [Designer]           시스템 기획 (2-2)                            (blockedBy: D2)
Task D4:  [Designer]           밸런스 기획 (2-3)                            (blockedBy: D3)
Task D5:  [Designer]           콘텐츠 기획 (2-4)                            (blockedBy: D3, D4와 병렬 가능)
Task D6:  [Designer]           BM/LiveOps 기획 (2-5)                       (blockedBy: D4, D5)
─────────────────────────────────────────────────────────────────────────────
Task D7:  [Design Validator]   통합 검증 — 교차 일관성 + 여정 시뮬 (Stage 3) (blockedBy: D6)
Task D8:  [디렉터 (사람)]      디렉터 검수 및 피드백 (Stage 4)               (blockedBy: D7)
Task D9:  [Design Validator]   재생성 평가 (Stage 5, 피드백 있을 시)         (blockedBy: D8)
Task D10: [Design DB Builder]  DB 축적 — score 산출 + Expert 승격 (Stage 6) (blockedBy: D9)
─────────────────────────────────────────────────────────────────────────────
Task D11: [AI Tester]          플레이 검증 (Stage 7, 빌드 필요)             (blockedBy: D10 + 코드 빌드)
Task D12: [Design DB Builder]  라이브 동기화 (Stage 8, 출시 후)             (blockedBy: D11)
```

### Design Verification (Stage 7)

| 모드 | 설명 | 출력 |
|------|------|------|
| **7-1 Accelerated** | APK를 BlueStacks에 배포 → Virtual Player ADB 모드 → 예측 vs 실측 비교 | prediction_vs_actual 배열 |
| **7-2 Long-term** | Day-1 예측 모델 → 일별 diff → Day-30 대조 | daily_diffs 배열 + day30_reconciliation |
| **7-3 Mass Simulation** | 페르소나 유형별 × N 인스턴스 집계 (casual 70%, hardcore 15%, whale 5%, newbie 8%, returning 2%) | persona_distribution + outlier_flags |

**페르소나 구성:**

| 페르소나 | 비율 | 특성 |
|---------|------|------|
| casual | 70% | 짧은 세션, 저소비, 이탈 빠름 |
| hardcore | 15% | 긴 세션, 중소비, 높은 참여도 |
| whale | 5% | 고소비, LTV 기여 집중 |
| newbie | 8% | 신규, 튜토리얼 집중, 높은 이탈 |
| returning | 2% | 복귀 유저, 중간 소비 |

**출력 경로:**
```
E:\AI\projects\{project}\feedback\design\play_verification_results.json
```

**실행 예시:**
```bash
# 7-1 Accelerated
node E:/AI/scripts/play-verification.js --project MyGame --mode accelerated --build path/to/build.apk

# 7-2 Long-term (30일)
node E:/AI/scripts/play-verification.js --project MyGame --mode longterm --days 30

# 7-3 Mass Simulation (100 페르소나)
node E:/AI/scripts/play-verification.js --project MyGame --mode mass --personas 100
```

### Design ↔ Code 역방향 피드백 경로

코드 Workflow 또는 플레이 검증에서 기획 이슈 발견 시 역방향 피드백:

```
기획 7단계 플레이 검증 실패 시:

  밸런스 이슈 → 기획 2-3단계(밸런스)만 수정 → 코드 Calculator만 재생성
  시스템 이슈 → 기획 2-2단계(시스템) 수정 → 코드 해당 Phase부터 재시작
  양쪽 이슈  → 기획 2단계 전체 수정 → 코드 전체 재생성

코드 Workflow 검증 실패 시:

  구현 불가 판정 → 기획 L3 logicFlow 수정 요청 → Designer 재생성
  계약 불일치   → 기획 L2 relations 수정 → L3 의존성 재검증
  밸런스 이상치 → 기획 Balance 도메인 수정 → Calculator만 재생성
```

### Design → Code Workflow 통합

Design Workflow 완료 후 Code Workflow와 연결되는 방식:

```
[Design Workflow 완료]
  db/design/base/{genre}/{domain}/
    ↓
[Code Workflow Phase 2: Designer]
  design YAML → system_spec.yaml → AI_기획서 (코드 노드 YAML)
    ↓
[Code Workflow Phase 3: Coder]
  YAML 노드 → C# 코드 생성 (DB 참조)
```

Design Validator의 `domain → code system` 매핑:

| Design Domain | Code System | 대표 Role |
|---------------|-------------|-----------|
| InGame | Battle, Skill, Character | Manager, Calculator |
| OutGame | Inventory, Shop | Manager, Provider |
| Balance | 수치 공식 클래스 | Calculator, Processor |
| Content | Quest, Stage | Manager, Factory |
| BM | Shop, IAP | Service, Manager |
| LiveOps | Config, Scheduler, EventCalendar | Service, Config |
| UX | UI Flow | Controller, UX |
| Social | Guild, PvP | Manager, Service |
| Meta | Achievement | Manager, Observer |

### AI Tester 시스템 연계

AI Tester는 Design Workflow와 두 가지 역할로 연계됩니다:

**PRIMARY: 외부 게임 분석 → Design DB 데이터 수집 (Stage 1 입력)**
- 외부 레퍼런스 게임을 10명 AI 전문 관찰로 분석
- 32개 파라미터 추정 결과를 Base Design DB로 가공 (source: observed)
- 패턴 카드 방식 미사용 (법적 리스크 회피)
- 소스코드 접근 없이 순수 관찰만 활용, 약 85~89.5% 정확도

**SECONDARY: 자사 게임 플레이 검증 (Stage 7)**
- 자사 빌드를 BlueStacks + ADB로 가속 테스트
- 밸런스 예측값 vs 실측값 비교 → 기획 피드백 생성
- 7-1 가속 / 7-2 장기 / 7-3 대규모 시뮬레이션

| AI Tester 출력 | Design DB 필드 | Domain |
|----------------|---------------|--------|
| 화면 구성 관찰 | UX flow 데이터 | UX |
| 전투 수치 추출 | 데미지/스탯 formula | Balance |
| 재화 흐름 관찰 | economy source/sink | Balance |
| 가챠 확률 관찰 | gacha probability table | OutGame |
| 스테이지 구성 | stage content_data | Content |
| 상점 가격 관찰 | IAP/package config | BM |
| 소셜 기능 관찰 | social system rule | Social |

### 명령어 (Design Workflow)

| 명령어 | 용도 | 담당 Agent |
|--------|------|-----------|
| `/parse-design` | 기획 문서 → Design DB 파싱 저장 | Design DB Builder |
| `/generate-design-v2` | 8단계 기획 워크플로우 전체 실행 | Designer (design mode) |
| `/validate-design` | 기획 교차 검증 + 밸런스 시뮬 | Design Validator |
| `/sync-live` | 라이브 지표 → Design DB 동기화 | Design DB Builder |

### 라이브 데이터 동기화 (Live Sync)

서비스 출시 후 실제 데이터를 Design DB에 반영하는 워크플로우:

```
라이브 지표 수집 (Analytics 내보내기)
    ↓
/sync-live → Design DB Builder
    ↓
기존 기획 예측값 vs 실측값 비교
    ↓
design-version.js --phase post_launch → 버전 이력 기록
    ↓
피드백 카테고리 분류 → feedback/design/ 저장
    ↓
virtual-player-bridge.js → VP 세션 → Design 피드백 변환
    ↓
score 업데이트 → Expert 승격 검토
```

**버전 관리 예시:**
```bash
# 라이브 출시 후 버전 기록 (절대 덮어쓰지 않음 — versions[] 배열에 append)
node E:/AI/scripts/design-version.js \
  --designId BattleSystem \
  --genre rpg \
  --domain ingame \
  --version 1.1.0 \
  --phase post_launch \
  --note "밸런스 패치: 보스 HP 20% 감소" \
  --trigger "D7 retention 22% → 목표 30%" \
  --kpi-before '{"retention_d7": 0.22, "session_length": 280}' \
  --kpi-after  '{"retention_d7": 0.31, "session_length": 310}'

# 전체 프로젝트 스냅샷
node E:/AI/scripts/design-version.js \
  --snapshot \
  --project MyGame \
  --genre rpg \
  --version 1.0.0 \
  --note "v1.0 출시 시점 스냅샷"
```
