# DB Search Priority (Shared Rule)

> 코드/기획 생성 시 기존 DB 참조 우선순위. **필수 규칙 — 선택 아님.**
> Main Coder, Sub Coder, Designer, Playable Coder 공통 적용.

---

## 핵심 원칙

**모든 생성 작업은 DB 검색을 선행해야 한다.**

환각 방지의 첫 번째 방어선은 "기존 검증된 자산 재사용"입니다.
DB를 검색하지 않고 바로 생성하는 것은 **환각 위험**으로 간주되며, Validator/Design Validator가 거부할 수 있습니다.

---

## 5-Tier 검색 순서

다음 순서대로 검색하며, **상위 Tier에서 적합한 항목을 찾으면 하위 Tier는 건너뜁니다**.

### Code DB (코드 생성 시)

| 순위 | 검색 대상 | 조건 | 명령 |
|-----|----------|------|------|
| **1** | Expert DB (해당 장르) | `genre == {target}` AND `score >= 0.6` | `node scripts/db-search.js --collection code_expert --genre {target}` |
| **2** | Expert DB (Generic) | `genre == generic` AND `score >= 0.6` | `node scripts/db-search.js --collection code_expert --genre generic` |
| **3** | Genre Base DB | `genre == {target}` | `node scripts/db-search.js --collection code_base --genre {target}` |
| **4** | Generic Base DB | `genre == generic` | `node scripts/db-search.js --collection code_base --genre generic` |
| **5** | AI 생성 (참조 없음) | 위 4개 검색 결과 적합 항목 없음 | AI_기획서 기반 신규 생성 |

### Design DB (기획 생성 시)

| 순위 | 검색 대상 | 조건 | 명령 |
|-----|----------|------|------|
| **1** | Expert Design DB (해당 장르) | `genre == {target}` AND `score >= 0.6` | `node scripts/design-db-search.js --collection design_expert --genre {target}` |
| **2** | Expert Design DB (Generic) | `genre == generic` AND `score >= 0.6` | `node scripts/design-db-search.js --collection design_expert --genre generic` |
| **3** | Genre Base Design DB | `genre == {target}` | `node scripts/design-db-search.js --collection design_base --genre {target}` |
| **4** | Generic Base Design DB | `genre == generic` | `node scripts/design-db-search.js --collection design_base --genre generic` |
| **5** | AI 신규 생성 (참조 없음) | 위 4개 결과 적합 항목 없음 | 기획서 기반 신규 생성 |

---

## 검색 필수 타이밍

### Designer (기획 생성)
- **MUST**: Stage 2 시작 전 (도메인별 시스템 생성 직전)
- **MUST**: 특정 시스템 생성 시 유사 사례 먼저 검색
- **예**: `design-db-search.js --genre puzzle --domain balance --system booster`

### Main Coder (아키텍처/핵심 시스템)
- **MUST**: Phase 0 Core 설계 전
- **MUST**: 복잡 시스템 생성 전 유사 패턴 검색
- **예**: `db-search.js --genre idle --layer Core --role Manager`

### Sub Coder (노드 구현)
- **MUST**: 각 노드 구현 시작 전
- **MUST**: Contract 매칭되는 기존 코드 검색
- **예**: `db-search.js --genre puzzle --role Processor --tag Calculate`

### Playable Coder (HTML5 광고)
- **MUST**: 메카닉 구현 전 동일 메카닉 기존 사례 검색
- **예**: `db-search.js --collection code_base --tag pin_pull`

---

## 검색 결과 활용

### 적합도 판정 기준

검색 결과를 참조할지는 다음 기준으로 판정:

| 판정 | 조건 | 행동 |
|-----|------|------|
| **완전 재사용** | score ≥ 0.6 AND contract 일치 | 해당 코드/기획을 그대로 참조 |
| **부분 참조** | score ≥ 0.4 AND 구조 유사 | 패턴만 차용, 세부 구현은 신규 |
| **참고만** | score < 0.4 OR 도메인 다름 | 참고 수준, 환각 주의 |
| **부적합** | 검색 결과 없거나 전혀 다름 | Tier 5 (AI 신규 생성) |

### 참조 시 필수 기록

재사용 또는 부분 참조 시, 생성물에 출처 명시:

```csharp
// Source: code_expert / puzzle / BalloonFlow / BalloonController.cs (score: 0.8)
// Reuse: ObjectPool pattern adapted for dart pool
```

```yaml
# Design Source: design_expert / puzzle / BalloonFlow / dart_rail_capacity (score: 0.7)
# Reuse: 4-tier capacity structure adapted for target genre
```

---

## 환각 위험 신호

다음 상황은 환각 발생 가능성이 높으므로 **특별 주의**:

⚠️ **Tier 5 (AI 신규 생성) 도달 시**
- 검색 결과 없음 = 선례 없음
- 생성물을 Validator가 특히 엄격히 검증
- 가능하면 Director 사전 검토 권장

⚠️ **장르 불일치**
- 장르 A 프로젝트에서 장르 B 코드 참조 시
- "이 패턴이 장르 A에서도 유효한가?" 재검토 필수

⚠️ **score 낮은 항목 참조**
- score < 0.4 항목은 검증 부족 상태
- 참조보다 재설계가 나을 수 있음

---

## 검색 건너뛰기 허용 예외

다음 경우에만 DB 검색 건너뛰기 허용:

1. **매우 단순한 유틸리티** (10줄 미만, 단일 목적)
   - 예: `Mathf.Clamp` 래퍼, 간단한 확장 메서드
2. **프로젝트 특화 로직** (장르 무관, 프로젝트 고유)
   - 예: 특정 캐릭터 이름 매핑, 프로젝트 고유 enum
3. **Lead 명시적 승인**
   - Lead가 "기존 DB에 없음을 확인했으므로 신규 생성 진행"을 선언한 경우

→ 위 3개 예외 외에는 **반드시 검색**해야 합니다.

---

## 관련 도구

```bash
# 코드 DB 검색
node scripts/db-search.js --genre puzzle --layer Domain --role Manager

# 기획 DB 검색
node scripts/design-db-search.js --genre idle --top 10 --json

# 포맷별 검색 (class/function/pattern)
node scripts/format-search.js --pattern "ObjectPool"
```

---

## 관련 규칙

- `.claude/rules/error-fix.md` — 에러 수정 시 컨텍스트 로드
- `.claude/rules/hallucination-prevention.md` — 환각 방지 체크리스트
- `CLAUDE.md` §DB 검색 우선순위 — 원본 명세
