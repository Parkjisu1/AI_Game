# Hermes 노드그래프 아키텍처 매핑 (Blueprint 단일 엔진)

> 작성 2026-06-23. 5-AI 검수(run wf_233c7996-67e) 결론을 사용자가 제시한 Unreal Blueprint식
> 노드그래프 목표 아키텍처에 매핑한 설계. 모든 file:line은 검수에서 코드로 검증된 것.
> 관련 메모리: hermes_nodegraph_architecture, projecthub_progress, projecthub_unity_mcp_plan.

---

## 0. 통합 명제 (가장 중요)

**노드그래프는 검수가 지목한 결정성 수정과 별개의 신규 프로젝트가 아니다. 같은 수정의 구조적 구현체다.**

검수 메타진단: *Hermes의 모든 증상은 단 하나의 결함의 투영 — 결정론적 실행 경계의 부재(상태 전이가 원자적·관측가능·취소가능하지 않음).*

노드그래프는 정의상 실행 경계를 **명시적·원자적·관측가능·취소가능**으로 만든다. 즉:

| 검수 수정 | 노드그래프 속성 (= 같은 것) |
|---|---|
| A1 phase 멱등성(CAS) | 노드는 `(task, node_id)`당 정확히 1회 실행. 결과 저널 있으면 재생 시 skip = **멱등성 네이티브** |
| A3 lease/워커풀 | 노드가 **스케줄링 단위**. 러너가 노드를 lease로 클레임 |
| A5/A6 차단 게이트 | **check 노드 + AND-gate 노드**. 게이트 통과 전엔 하류 엣지가 발화 안 함. "비차단→차단"은 그냥 "AND-gate 엣지" |
| A7 모놀리스 분해 | `_handle_unity_modify` 1180줄 = **노드 서브그래프**. Stage 시퀀스가 곧 노드 시퀀스 |
| 취소(⛔ 백엔드) | 노드 경계마다 `check_cancelled()` = **러너가 노드 사이에서 stop 플래그 확인** (네이티브) |
| U3/U5/U6 관측성 | 그래프 자체가 관측 표면. 각 노드 상태(pending/running/done/failed/skipped)가 곧 UI 배지 |
| 유기적 연결 검증(사용자 요구3) | **그래프 정적 검증** (고아노드/끊긴엣지/미수렴 게이트) |

→ **로드맵의 through-line이 노드그래프다.** 결정성 수정을 "노드 러너를 만드는 일"로 하면, 버그픽스와 아키텍처 전환이 같은 작업이 된다.

---

## 1. 두 개의 그래프 (혼동 금지)

사용자 요구는 **두 그래프**에 걸쳐 있다. 분리해야 설계가 선명해진다.

### (G1) 실행 그래프 (Run-Graph / DAG) — "어떻게 실행하나"
당신이 그린 Blueprint. 태스크 1건이 흐르는 파이프라인을 노드로 표현.
`단일 입력 → 팬아웃 → 병렬 작업 → 대량 병렬 검증 → AND 게이트 → 출력`.

### (G2) 프로젝트 그래프 (Project-Graph / 거미줄) — "무엇을 건드리나"
BalloonFlow의 **실제 사용되는 소스/코드**를 연결한 그래프 — 클래스·호출자·계약·씬참조.
"실제 사용되는 소스를 거미줄처럼 연결"이 이것.

**관계**: G1의 **extract 노드(Break 노드)가 G2를 질의한다.** 수정 요청이 오면 extract 노드가
프로젝트 그래프에서 진짜 영향 범위를 뽑아 agent 노드에 먹인다.

> **✅ 결정됨 (2026-06-23)**: G2는 **유지되는 무거운 풀그래프가 아니라, 변경 범위로 한정해 `git grep`으로
> 실시간 계산하는 서브그래프**다. 이유 — 활성 임베딩(`delta_embed_bf_code.py:72-78`)이 그래프 필드를
> 매번 소실시키고, Unity 동적 디스패치로 정적 콜그래프가 거짓음성을 낸다(검수 §5 QA). 거미줄은
> **just-in-time, depth-1, 변경 한정**으로 만든다.
>
> **이 결정의 귀결**:
> - 유지형 그래프 컬렉션·BFS·정규화 사전·임베딩 의존 = **전부 안 만든다**.
> - 따라서 "데이터 진실성 감사(integration/usedBy 보유율)"는 **그래프의 차단 선결조건에서 강등** —
>   그래프가 DB 필드에 의존하지 않으므로. (단 `check.rule_lint`용 find_calls 오탐률 측정은 유효)
> - grep은 **Machine B 라이브 레포**(BalloonFlow 정본)에서 실행 — 로컬 미러는 stale 위험(검수/메모리 경고).
> - C# 호출자 grep + **`.prefab`/`.asset`/`.unity` 직렬화 참조 grep 병행** — UnityEvent/Button.onClick/
>   Inspector 하드코딩 값(동적 디스패치·값 소유자)을 일부 회수해 거짓음성 완화.
> - 출력은 **신뢰도 표기된 impact 블록**(타겟 정의 file:line + depth-1 호출자 + 직렬화 참조 + 값소유자 후보).
>
> **하위 결정 확정 (2026-06-23)**: 1-a grep은 Machine B 라이브 레포에서 SSH 실행 / 1-b C# + .prefab·.asset·.unity 병행 grep /
> 1-c depth-1 고정 (depth-2/사이클/자동 데드코드탐지 제외).

---

## 2. 노드 카탈로그 (사용자 요구 1 — "각 노드에 어떤 기능이 있고")

모든 노드는 **타입 명세(NodeSpec)** 를 가진다. 이것이 노드 레지스트리.

```yaml
NodeSpec:
  id:            string            # 그래프 내 고유 (예: check.compile)
  type:          node_type         # 아래 분류
  label:         string            # UI 표시명
  inputs:        [{name, type}]     # 타입드 입력 포트
  outputs:       [{name, type}]     # 타입드 출력 포트
  effects:       [none|git_write|db_write|external]   # 부수효과 선언 (안전/검증용)
  idempotency_key: expr            # 같은 키면 재실행 skip (= A1 일반화)
  cancellable:   bool              # 노드 진입 전 stop 체크 대상
  on_fail:       route             # 실패 시 분기 (sink 또는 fix-loop)
  retry:         {max, backoff}    # H1 resilience 연계
  impl:          agent_role | tool_fn | check_fn
```

> **✅ 결정됨 (2026-06-23)**: 그래프 정의는 **(a) 코드로 시작 → Phase 2~3에 (b) 선언형 데이터(YAML/DB)로 승격.**
> 단 **NodeSpec(노드 명세)은 처음부터 데이터**로 두고, 그래프 토폴로지(노드 목록·엣지)도 모듈 상단에
> dict/list로 선언해 (b) 전환 비용을 미리 낮춘다. 처음부터 선언형 파서를 짜는 것은 결정성 작업 지연으로 기각.

### 노드 타입 (8종)

| 타입 | 역할 | 예시 노드 | 현재 코드 대응 |
|---|---|---|---|
| **source** | 좌측 단일 입력 | `task.intake` | `projecthub_watcher._dispatch_event` |
| **route** | 분류·분기 | `route.translator`(clarity/team), `route.pm`(sub_team) | `_run_translator_preflight`, `_run_pm` |
| **extract** | (Break 노드) G2 질의 → 영향범위 | `extract.changed_files`, `extract.callers`, `extract.value_owner`, `extract.contracts`, `extract.scene_refs` | `git diff --name-only`(`:3090`), 신규 |
| **agent** | LLM 작업 | `agent.lead`(팬아웃), `agent.main_coder`, `agent.sub_coder`×N | `invoke_agent`, `run_parallel_agents` |
| **tool** | 결정론적 부수효과 | `tool.git_branch`, `tool.git_commit`, `tool.mcp_compile`, `tool.pr_merge` | `_handle_unity_modify` git 블록 |
| **check** | (Nearly Equal 노드) 판정→bool | `check.compile`, `check.contract`, `check.rule_lint`, `check.regression`, `check.balance_tolerance`, `check.review_score` | Validator/Reviewer/MCP |
| **gate** | 수렴 게이트 | `gate.and`(전부 PASS), `gate.threshold`(점수≥N) | 신규 (현재 비차단 분기) |
| **sink** | 출력/종착 | `sink.merge`, `sink.done`, `sink.needs_input`, `sink.quality_blocked` | `update_status`, Slack |

### "Nearly Equal" = check 노드의 본질
당신 그림의 대량 `Nearly Equal(Float)` 비교는 Hermes에서 **독립 검증 노드들**이다. 특히 **밸런스 수치**
QA(다트 spacing, 큐 분포 등)는 문자 그대로 허용오차 비교 노드 `check.balance_tolerance(actual, expected, tol)`.
이게 plug-in 형태로 N개 꽂히고 전부 `gate.and`로 수렴 → **전부 PASS여야 머지**.

---

## 3. dev(unity_modify) 실행 그래프 — 당신 Blueprint의 Hermes 버전

```
task.intake
   │
route.translator ──(needs_input)──→ sink.needs_input(Slack DM)
   │ (clear)        ──(cancel/rollback)──→ sink.*
route.pm
   │
agent.lead ───────────── 팬아웃 ─────────────┐
   ├─ extract.changed_files ─┐               │
   ├─ extract.callers ───────┤  (G2 거미줄)   │
   ├─ extract.value_owner ───┼─ impact_set ──┤
   ├─ extract.contracts ─────┤               │
   └─ extract.scene_refs ────┘               ▼
                                  agent.main_coder + agent.sub_coder×N (병렬 구현)
                                              │ changed files
              ┌───────────────────────────────┼─────────────────────────────┐
              ▼ (대량 병렬 검증 = Nearly Equal 팬)                            ▼
        check.compile   check.contract   check.rule_lint   check.regression
        check.review_score   check.balance_tolerance×K
              └───────────────────────────────┼─────────────────────────────┘
                                          gate.and
                              ┌───────────────┴───────────────┐
                          (fail)                            (pass)
                    fix-loop (≤2회 재구현)              tool.git_commit
                              │ 미달                          │
                       sink.quality_blocked            tool.pr → tool.pr_merge
                       (status=review,                       │
                        review_reason=quality_blocked)   sink.done
```

이게 정확히 당신 그림: **단일 소스 → 팬아웃 → Break/추출 → 대량 병렬 비교 → AND → 출력.**
차이는 검수 반영 — `gate.and`가 **차단형**(A5)이고, 실패 시 bounded fix-loop, MCP 도달실패는
`unreachable`로 구분(A6)해 'clean'과 안 섞임.

### ✅ 결정됨 (2026-06-23) — check 3등급 + 게이트 정책
| 등급 | 의미 | 해당 check | gate.and |
|---|---|---|---|
| 🔴 block | 실패 시 절대 머지 안 됨 | `check.compile`, `check.contract` | 직접 물림 |
| 🟡 fix-loop | 실패 시 ≤2회 재구현, 미달이면 `quality_blocked` | `check.review_score`(<50), `check.rule_lint` | 재시도 경유 후 물림 |
| ⚪ advisory | 코멘트만, 머지 허용 | 데드코드 감지, depth-2 영향 | 안 물림(기록만) |

- **4-a 컴파일 도달실패**: MCP 죽으면 `unreachable`로 **구분**(`clean`과 안 섞음) → `needs_human` 강등.
  batchmode 컴파일을 폴백 게이트로 승격해 도달실패 자체를 최소화. (검수 A6)
- **4-b 밸런스 tolerance**: Phase 1 보류. Phase 2 QA에서 **task 명시 기대값 추출(i)** 방식으로 도입
  (`check.balance_tolerance(actual, expected, tol)`, tol 작게 ±1%). 기획표준 의존(ii)은 design RAG 복구 후.

---

## 4. 수정 요청 → 그래프 참조 → 수정 (사용자 요구 2)

디렉터가 "X 고쳐줘"라고 하면:

1. `route.translator` → 개념 키워드 추출 (한글/영문/snake/camel 변형)
2. `extract.locate` → **실소스에 `git grep`** → 후보 심볼/파일 (G2 노드 생성)
3. `extract.value_owner` → **값이 실제로 읽히는 곳** 추적 (Spawner/Config/ScriptableObject/.asset).
   → 검수 진단·`MAIN_CODER_PROMPT`의 *"GameManager는 신뢰하지 말 것 — dead 필드 다수"* 함정을
   **그래프가 구조적으로 차단**. GameManager가 값을 위임만 하면 실제 소유자 노드를 타겟으로.
4. `extract.callers` → depth-1 직접 호출자 (`git grep -l 'X\.\|X\.Instance\|: X\b'`)
5. `impact_set` = 합집합 → `agent.main_coder`에 **"수정 타겟 + 영향 호출자"** 블록으로 주입
6. agent 편집 → `check.*` 노드가 **그 impact_set을 검증** (호출자 여전히 컴파일? 계약 유지?)
7. `gate.and` → 머지 또는 차단

→ "헤르메스가 그걸(그래프) 참조해서 수정"이 곧 **extract 서브그래프가 편집을 grounding** 하는 것.
지금처럼 "한 파일만 보고 GameManager만 고쳐 dead code라 동작 안 바뀜 → 재작업" 루프를 끊는다.

---

## 5. 유기적 연결 검증 (사용자 요구 3)

`graph.lint` 능력 — 두 그래프 모두 검증 가능하고 UI에 렌더.

### G1 (실행 그래프) 정적 검증
- **고아 노드**: source 외 인바운드 엣지 없는 노드
- **끊긴 출력 포트**: 어디에도 안 연결된 output
- **미수렴 check**: gate에 안 물린 check 노드 (검증이 무의미하게 떠 있음)
- **롤백 없는 effect**: `effects=git_write`인데 보상(rollback) 엣지 없음
- **도달 불가 sink** / **수렴 없는 사이클**

### G2 (프로젝트 거미줄) 검증 — ICS를 그래프-네이티브로 승격
- 계약 publisher 있는데 subscriber 0 (또는 역) — `_CONTRACTS.yaml` events 교차
- pool_key 소비하는데 prefab 미생성 — `_ASSET_MANIFEST.yaml` 교차
- `[SerializeField]` 선언했는데 SceneBuilder WireField 없음 (또는 역)
- 호출자가 없어진 심볼 참조
- **데드 값 감지** (필드가 자기참조만 = GameManager dead-code) — **단 advisory만**
  (동적 디스패치 거짓양성 때문에 차단 아님, 검수 §5 채택)

### UI (사용자 요구 핵심: "확인 가능하게") — ✅ 결정됨 (2026-06-23)
**ProjectHub nav에 `/balloonflow` 전용 섹션 신설** (AI팀 `/agents` 🤖 와 동급, `layout.tsx:23-31`).
태스크모달+/agents 분리안은 기각 — 모든 그래프/무결성 화면을 이 "BalloonFlow 커맨드 센터"에 집중.
담길 내용:
- **거미줄 무결성 지도 (G2 + graph.lint)**: 빨간엣지=깨진연결, 노란노드=고아/경고 (끊긴 계약·고아 이벤트·pool_key↔prefab·값소유자).
- **노드그래프 실행 뷰 (G1)**: 최근 태스크의 노드 흐름(done/running/failed/skipped·막힌 지점).
- **운영 지표**: Machine B 빌드/컴파일 상태, 게이트 통과율, 임베딩 신선도, RAG 적중.
- **시점**: 노드 엔진이 노드 상태를 저장하는 **Phase 1 이후**(P2). Phase 0은 배관이라 표시할 상태가 아직 없음.
- **일반화**: 이후 게임 추가 시 섹션 복제 → "BalloonFlow 우선 → 일반화" 노선과 정합.

---

## 6. 마이그레이션 (Strangler-Fig — 모놀리스를 안 멈추고 노드로 전환)

검수 정직성 경고: **비결정 기반 위에 화려한 엔진을 얹지 말 것.** 그래서 엔진을 만드는 행위 자체가
결정성을 획득하는 순서로 간다.

> **✅ 결정됨 (2026-06-23)**: 결정성 우선. 보이는 AND-게이트 그래프(extract/check 팬)는 Phase 1~2로 미루고,
> Phase 0의 결정성 primitive(저널·lease·stop체크·필터)부터. vertical-slice(작은 파이프라인 먼저 시각화) 대안 기각.

### Phase 0 — 노드 러너의 뼈대 = 검수 Quick Win (이번 주, 전부 S)
기존 stage를 안 건드리고 **얇은 노드 러너**만 두른다. 이게 곧 결정성 primitive:
- **노드 결과 저널** (`hermes_node_runs`: task_id, node_id, status, result_hash) = A1 멱등성 일반화
- **원자적 claim** (`findOneAndUpdate` lease) = A3 토대
- **노드 경계 stop 체크** = U1/U2 ⛔ 백엔드 (삭제 tombstone + 존재 가드 포함)
- **self-trigger $match 필터** = A4
- **scoped memory 사문화 결판** = A8 (러너 도입 시 context 주입 지점 명확화)

→ 이 5개가 폭주를 즉시 멈추고, 동시에 노드 엔진의 상태머신을 깐다.

### Phase 1 — 기존 stage를 노드로 래핑 (P1, M)
- `_handle_unity_modify` 1180줄을 `[Claim, Route, Plan, Extract, Implement, Check, Gate, Git, Advance]`
  노드로 분해 (A7). 각 stage 함수를 node `impl`로 그대로 감싼다 (로직 재작성 아님).
- 비차단 분기 → `gate.and` 차단형 (A5) + `review_reason` 배지 (U4)
- 태스크/phase별 고유 브랜치 + force-with-lease (A2)

### Phase 2 — extract/check 노드 = QA 신기능 착지 (P1~P2, M)
- `extract.callers`/`extract.value_owner` (G2 거미줄, git grep depth-1)
- `check.rule_lint` (output-runtime.md 정밀 패턴) + `check.compile`(MCP 결정론, A6)
- **선결 게이트**: 데이터 진실성 감사 0.5일 + find_calls 오탐률 측정 (검수 QA PoC 시작점)
- `delta_embed_bf_code.py:72-78`이 `integration` 보존하도록 수정 (안 하면 어떤 그래프든 노후화)

### Phase 3 — 선언형 그래프 + UI (P2~P3, L)
- 그래프를 데이터(YAML/DB)로 정의 → 코드 수정 없이 노드 추가/재배선
- `/agents` 그래프 뷰 (G1 실행 흐름 + G2 거미줄 + lint 결과)
- 게임별 그래프 (BalloonFlow 우선, 이후 일반화)

---

## 7. 검수 변경안 → 노드 매핑 색인

| 검수 ID | 노드그래프에서의 형태 | Phase |
|---|---|---|
| A1 멱등성 CAS | 노드 결과 저널 + idempotency_key | 0 |
| A3 lease 워커풀 | 노드 = 스케줄링 단위, claim | 0→1 |
| A4 self-trigger 차단 | source 노드 $match 필터 | 0 |
| A5 차단 게이트 | `gate.and` + fix-loop | 1 |
| A6 MCP 결정론 | `check.compile` (unreachable≠clean) | 2 |
| A7 모놀리스 분해 | stage→노드 래핑 | 1 |
| A8 scoped memory | context 주입 노드 명확화 | 0 |
| U1 삭제 tombstone | 노드 경계 존재 가드 | 0 |
| U2 ⛔ 해방 | cancellable 노드 + 카드 버튼 | 0 |
| U3 phase 가시성 | 노드 상태 배지 | 1 |
| U4 review_reason | sink 노드 분리 | 1 |
| QA 거미줄(경량) | extract/check 노드 (G2) | 2 |

---

## 결정 로그 (2026-06-23 — 6개 결정점 합의 완료)

| # | 결정점 | 확정 |
|---|---|---|
| 1 | 거미줄(G2) 성격 | **`git grep` 실시간 서브그래프**. 1-a Machine B 라이브 grep / 1-b C#+.prefab·.asset·.unity 병행 / 1-c depth-1 고정. 유지형 풀그래프·임베딩의존·데이터진실성 차단게이트 모두 폐기 |
| 2 | 실행 순서 | **결정성 먼저**. Phase 0 결정성 primitive = 이번 주 버그픽스. 보이는 그래프는 Phase 1~2. vertical-slice 대안 기각 |
| 3 | 그래프 정의 방식 | **(a) 코드 시작 → (b) 선언형 승격**. NodeSpec은 처음부터 데이터, 토폴로지도 dict/list 선언으로 전환비용 선제 절감 |
| 4 | AND-게이트 엄격도 | check **3등급**(🔴block / 🟡fix-loop≤2 / ⚪advisory). 4-a 컴파일 도달실패=unreachable 구분+batchmode 폴백 / 4-b 밸런스 tolerance는 Phase 2 task추출(i) |
| 5 | 무결성 UI 위치 | **`/balloonflow` 전용 섹션 신설**(AI팀 스타일). G1 실행뷰+G2 거미줄lint+운영지표 집중. P2 시점. 게임추가 시 섹션 복제 |
| 6 | 검수 잔여 쟁점 | 6-a 큐=**기존 필드 추가(M)**(별도 컬렉션 기각) / 6-b self-consistency **P3 후순위** / 6-c design RAG는 **계측(S) 선행** 후 벡터화 |

**다음 단계 (구현 시작 시) — Phase 0, 전부 S, 선결조건 없음:**
1. 노드 결과 저널(`hermes_node_runs`) = A1 멱등성 → PR churn 차단
2. 원자적 claim(findOneAndUpdate lease) = A3 토대
3. 노드경계 stop체크 + 삭제 tombstone + 존재가드 = U1/U2 ⛔ 백엔드
4. self-trigger $match 필터 = A4
5. scoped memory 사문화 결판(주입 or 제거) = A8

---

## 한 줄 요약
**노드그래프 = 검수가 요구한 결정성의 구현체.** 두 그래프(실행 DAG + 프로젝트 거미줄)로 나누되
거미줄은 git grep 기반 just-in-time. 노드별 NodeSpec(요구1) → extract 노드가 수정을 grounding(요구2)
→ graph.lint가 연결 무결성 검증(요구3). Phase 0의 노드 러너 뼈대가 곧 이번 주 Quick Win(폭주 정지)이라,
버그픽스와 아키텍처 전환이 같은 작업이 된다.
