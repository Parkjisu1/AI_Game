# Hallucination Prevention Template (Shared Rule)

> 모든 에이전트가 공통으로 준수해야 하는 환각 방지 6가지 체크리스트.
> 개별 에이전트의 Hallucination Prevention 섹션은 이 규칙을 확장한다.

---

## 왜 필요한가

AI 에이전트 환각(hallucination)은 다음 형태로 나타남:
- 존재하지 않는 파일·함수·필드를 있다고 주장
- 읽지 않은 문서 내용을 추측으로 기술
- 기존 구현과 다른 방식을 "동일하다"고 주장
- 과거 컨텍스트를 현재로 오인

**공통 6체크**로 대부분의 환각을 사전 차단할 수 있다.

---

## 6가지 핵심 규칙

### 1. 📍 파일:라인 인용 필수 (File:Line Citation)

**원칙**: 모든 주장은 파일 경로 + 라인 번호로 뒷받침되어야 한다.

✅ **Good**:
- "`lead.md:45`에 따르면 Lead는 코드를 작성하지 않는다"
- "`_CONTRACTS.yaml:23-27`에 OnBalloonPopped 이벤트가 정의됨"

❌ **Bad**:
- "Lead는 보통 코드 작성 안 함"
- "이벤트가 계약에 정의되어 있음 (경로 없음)"

**적용 범위**: 모든 에이전트의 보고서, 평가, 피드백

---

### 2. 🔀 크로스 레퍼런스 파일 (Cross-Reference Files)

**원칙**: 두 파일의 일관성을 판단하려면 **두 파일 모두 실제로 읽어야** 한다.

✅ **Good**:
```
Read(file=A.cs) → Read(file=B.yaml) → 두 내용 비교 → 판정
```

❌ **Bad**:
```
Read(file=A.cs) → 기억으로 B.yaml 추정 → 판정
```

**대표 사례**:
- `_CONTRACTS.yaml` ↔ 실제 코드 (Validator Stage 5.5)
- `system_spec.yaml` ↔ `layer3/nodes/*.yaml` (Design Validator)
- `main-coder.md` vs `sub-coder.md` 패턴 일관성

---

### 3. ⏸️ 불확실 시 보류 (Defer if Uncertain)

**원칙**: 판단 근거가 부족하면 **추측하지 말고 Lead/User에 질문**한다.

✅ **Good**:
- "이 필드의 용도가 불명확. L3 YAML `{path}` 확인 후 진행 요청"
- "계약에 등록되지 않은 이벤트 발견. Lead에게 등록 여부 확인"

❌ **Bad**:
- "아마 이런 의도일 듯" (근거 없는 추정)
- "일반적으로 이렇게 함" (현 프로젝트와 무관한 관례 적용)

**Lead 에스컬레이션 트리거**:
- Public API 변경 필요 판단 시
- 기획 의도 해석에 2가지 이상 가능성 있을 때
- 계약 위반이 필요해 보일 때

---

### 4. 🔗 ICS 기반 검증 (Validate Against ICS)

**원칙**: Integration Contract System은 **Single Source of Truth**.
코드/기획 판정 시 ICS 엔트리를 먼저 확인한다.

**ICS 문서 위치**:
- `_CONTRACTS.yaml` — events, pool_keys, serialized_fields, method_calls, asset_requirements
- `_ASSET_MANIFEST.yaml` — prefabs, scenes, editor_scripts, resources
- `_ARCHITECTURE.md` — 전체 구조 설명

**검증 순서**:
1. ICS 엔트리 존재 확인
2. 엔트리와 실제 구현 일치 확인
3. 엔트리 누락 시 → 계약 미등록 상태 (Error)
4. 구현 누락 시 → 계약 미이행 상태 (Error)

**CLAUDE.md §Integration Contract System** 참조 필수.

---

### 5. 🔁 주장 전 재확인 (Re-read Before Claiming)

**원칙**: "이 파일에 X가 있다"라고 주장하기 전, **바로 직전에 해당 파일을 다시 읽어라**.

**왜?**
- 다른 에이전트가 파일을 수정했을 수 있음
- 이전 대화의 기억은 현재 파일 상태가 아닐 수 있음
- 특히 병렬 작업 중 race condition 주의

**적용 순간**:
- Validator가 "계약 위반 발견"을 보고하기 직전
- Lead가 "Phase 완료" 판정하기 직전
- Reviewer가 "파일에 X 없음" 주장하기 직전

**예외**: 같은 응답 내에서 이미 읽은 파일은 재읽기 불필요.

---

### 6. 🚫 메모리 단독 의존 금지 (No Memory-Alone Claims)

**원칙**: auto memory, 이전 대화 기억, 훈련 데이터 지식은 **보조용**이며 **단독 근거가 되어서는 안 된다**.

**메모리 사용 가능**:
- ✅ 컨텍스트 힌트 ("이 프로젝트는 Puzzle 장르였던 것 같다 → 확인 필요")
- ✅ 탐색 시작점 ("MongoDB 사용 중 → `.env` 먼저 확인")

**메모리 단독 사용 금지**:
- ❌ 최종 판정 근거 ("기억하기로 설정값은 40")
- ❌ 사용자 보고 ("이전에 이렇게 했으니 지금도 그대로일 것")

**검증 패턴**:
```
메모리에서 가설 → 실제 파일 확인 → 일치하면 메모리 사용, 불일치하면 파일 우선
```

**auto memory 특별 주의**:
- 메모리는 **시점 스냅샷**. 현재 상태와 다를 수 있음
- 최근 변경 가능성 있는 항목(파일 경로, 함수명, 설정값)은 **반드시 현재 파일 재확인**

---

## 에이전트별 추가 적용 예시

### Designer
- Balance 수치 생성 시 → Balance DB 검색 (§ DB Search Rule) → 결과 인용
- 시스템 이름 결정 전 → 기존 시스템명 Grep으로 중복 확인

### Coder (Main/Sub/Playable)
- 메서드 시그니처 결정 전 → `_CONTRACTS.yaml` method_calls 섹션 확인
- 이벤트 발행/구독 구현 전 → events 섹션 교차 확인

### Validator / Design Validator
- 피드백 항목마다 YAML path 또는 파일 라인 명시
- 공식 검증 시 실제 값 대입 (수치 계산 수행)

### Lead
- 에이전트 산출물 평가 전 → 실제 파일 존재·크기 확인 (Glob)
- Phase Gate 판정 전 → 계약 파일 의미적 완결성 확인 (YAML 파싱)

### Reviewer (Product/Business)
- 점수 제시 전 → 인용 파일 실제 존재 확인
- "파일에 X 없음" 주장 시 → Grep으로 역검증

---

## 체크리스트 (출력 전 자가 점검)

산출물 제출 전 다음을 확인:

- [ ] 모든 주요 주장에 파일:라인 또는 명령 출력 인용이 있는가?
- [ ] 두 파일 비교 주장 시 두 파일 모두 이 대화에서 실제로 Read 했는가?
- [ ] 불확실한 부분이 있으면 명시적으로 "확인 필요" 표시했는가?
- [ ] ICS 관련 판정 시 `_CONTRACTS.yaml`/`_ASSET_MANIFEST.yaml` 실제로 참조했는가?
- [ ] 최근 변경 가능성 있는 파일은 이 응답 직전에 재확인했는가?
- [ ] 메모리 기반 주장이 있다면 현재 파일 상태로 검증했는가?

---

## 환각 발생 시 대응

**Validator/Reviewer가 환각을 발견한 경우**:
1. 해당 주장을 즉시 정정 (파일 실제 상태로 대체)
2. 환각 원인 로그 (메모리 의존 / 파일 미읽기 / 추정 등)
3. 해당 패턴이 반복되면 Rule로 추출 (`db/rules/`)

**자가 발견 시**:
1. 응답 중이라면 즉시 "정정: 실제로는 X" 명시
2. 산출물이 저장된 후라면 수정 커밋 + 커밋 메시지에 "hallucination fix" 표시

---

## 관련 규칙

- `.claude/rules/error-fix.md` — 에러 수정 시 3단계 프로토콜
- `.claude/rules/db-search.md` — DB 검색 우선순위
- `CLAUDE.md` §Integration Contract System — ICS 상세
