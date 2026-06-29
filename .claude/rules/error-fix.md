# Error Fix Protocol (Shared Rule)

> 컴파일 에러 수정 시 기획 의도 이탈 방지를 위한 필수 프로토콜.
> 이 규칙은 Main Coder, Sub Coder, Playable Coder에 공통 적용되며, Lead는 이 규칙 위반 여부를 검증합니다.

---

## 왜 필요한가

에러 수정 시 흔한 실수:
- 에러 메시지만 보고 즉각 수정 → 기획 의도 이탈
- Null 체크 추가로 에러 회피 → 필수 로직 건너뜀
- Public API 메서드 삭제 → 다른 파일 계약 깨짐
- [SerializeField] 제거 → SceneBuilder 와이어링 깨짐

**모든 에러 수정은 3단계 프로토콜을 거쳐야 한다.**

---

## 1단계: 컨텍스트 로드 (수정 전 필수)

수정 시작 전, 반드시 다음 파일들을 **실제로 읽어야** 한다 (메모리 의존 금지):

### 필수 로드 항목
- [ ] 에러가 발생한 파일 자체
- [ ] 해당 L3 YAML 노드 (`design_workflow/layer3/nodes/{nodeId}.yaml`)
- [ ] `_CONTRACTS.yaml` 중 해당 파일 관련 항목:
  - events (publishers / subscribers 목록)
  - pool_keys (consumers 목록)
  - serialized_fields
  - method_calls (caller / target)
  - asset_requirements
- [ ] 해당 파일을 참조하는 모든 파일 (callers) — Grep으로 검색
- [ ] 해당 파일이 참조하는 모든 파일 (dependencies) — using/import 기준
- [ ] `_ASSET_MANIFEST.yaml` — 해당 파일이 생성·소비하는 에셋

### 컨텍스트 로드 완료 체크
다음 질문에 모두 답할 수 있어야 다음 단계 진행:
1. 이 파일의 public API 중 무엇이 외부에서 호출되는가?
2. 이 파일이 발행/구독하는 이벤트는 무엇인가?
3. 이 파일이 사용하는 pool_key는 무엇이며, 어떤 프리팹을 요구하는가?
4. 기획 의도(L3 YAML `logicFlow`)는 무엇인가?

---

## 2단계: 수정 제약 (절대 규칙)

### 금지 항목 (위반 시 Validator 자동 거부)

1. **❌ Public API 삭제 금지**
   - `contract.provides`에 등록된 public 메서드/프로퍼티 삭제 금지
   - 이름 변경도 금지 (caller 전부 동시 수정 시에만 허용)

2. **❌ [SerializeField] 속성 제거 금지**
   - SceneBuilder의 WireField 호출이 깨짐
   - 필드가 불필요해도 제거 금지 → Lead에 보고

3. **❌ 로직 우회형 null 체크 금지**
   ```csharp
   // 금지 — 필수 로직 건너뜀
   if (target == null) return;

   // 허용 — 의미 있는 분기
   if (target == null) {
       Debug.LogError("Target missing");
       RaiseError();
       return;
   }
   ```

4. **❌ 메서드 시그니처 변경 시 caller 미수정 금지**
   - 시그니처 변경 시 모든 호출처를 동시에 수정해야 함
   - Grep으로 caller 전수 확인 필수

5. **❌ 이벤트·pool key·serialized_field 임의 추가 금지**
   - 새로 추가한 계약은 반드시 `_CONTRACTS.yaml`에 등록
   - 등록 없이 코드에만 있으면 Validator Stage 5.5 FAIL

### 허용 항목

✅ 로직 내부 수정 (입력·출력 시그니처 불변)
✅ private 필드 추가·삭제
✅ using 문 추가 (단, SDK는 `#if` 블록 안에)
✅ 에러 메시지 개선
✅ 성능 최적화 (외부 가시 동작 불변)

### 애매한 경우 → Lead 보고

- Public API 변경이 정말 필요한가?
- 계약을 깨뜨려야만 해결되는가?
- 기획 의도와 어긋나는 것 아닌가?

→ **독단 결정 금지**. Lead에 판단 위임.

---

## 3단계: 수정 후 검증

수정 완료 후 다음을 모두 확인:

### 계약 검증
- [ ] `_CONTRACTS.yaml`의 모든 계약이 여전히 충족되는가?
- [ ] 새로 추가된 이벤트/pool key/field가 `_CONTRACTS.yaml`에 등록되었는가?
- [ ] `_ASSET_MANIFEST.yaml`이 최신인가?

### 기획 정합성 검증
- [ ] L3 YAML `logicFlow`의 단계가 코드에 모두 구현되어 있는가?
- [ ] `patterns`에 명시된 디자인 패턴을 사용하는가?
- [ ] `contracts.provides`의 모든 메서드가 실제로 public으로 노출되어 있는가?

### 자가 검증 재실행
- [ ] 5단계 자가 검증 재실행 (Validator 기준)
- [ ] 영향 받는 caller 파일 컴파일 에러 없음 확인
- [ ] Stage 5.5 Integration Validation 통과 예상되는가?

---

## 에러 수정 실패 시 에스컬레이션

3단계 검증에서 실패 항목이 발생하면:
1. **즉시 수정 중단**
2. 실패 항목 + 원인 분석을 Lead에 보고
3. Lead가 설계 변경 여부 결정 (Designer 재작업 필요 여부)

---

## 참조 체인

```
Error 발견
  ↓
Context Load (1단계) ← L3 YAML + _CONTRACTS.yaml + callers
  ↓
Constrained Fix (2단계) ← 금지 항목 준수
  ↓
Verification (3단계) ← 계약·기획·자가 검증
  ↓
Success → Validator Stage 5.5 → 통과
Failure → Lead 보고 → 재설계
```

---

## 관련 규칙

- `.claude/rules/db-search.md` — DB 참조 우선순위
- `.claude/rules/hallucination-prevention.md` — 환각 방지 체크리스트
- `CLAUDE.md` §Integration Contract System — ICS 전체 구조
