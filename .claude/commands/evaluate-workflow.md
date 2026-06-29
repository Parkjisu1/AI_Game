---
description: AI 워크플로우 2-Reviewer 평가 (Product PM + Business PM 병렬 평가 + Lead 통합 리포트)
arguments:
  - name: project
    description: 평가 대상 프로젝트 이름 (예: BalloonFlow, IdleMoney)
    required: true
  - name: mode
    description: "평가 모드 — full(기본) / product-only / business-only / gate-only"
    required: false
---

# Evaluate Workflow — 2-Reviewer 평가 시스템

Lead 오케스트레이션으로 Reviewer Product + Reviewer Business 2개 에이전트를 병렬 실행하여 AI 워크플로우를 18개 기준으로 평가합니다.

## 평가 기준 (18개, 2-Reviewer 분담)

### Reviewer Product (10개 기준)
```
[Result]        #3 단계완결성, #4 전문성, #5 정합성, #6 파생가능성
[Trust]         #7 재현성, #8 검증가능성
[Operation]     #10 인간개입, #11 실패복구, #12 데이터축적
```

### Reviewer Business (9개 기준)
```
[Reality Gate⭐] #15 기술실현성, #16 리소스현실성, #17 시장현실성, #18 운영현실성
[Business]      #1 효율성, #2 사업연결성
[Speed]         #9 리드타임
[Risk]          #13 의존성
[Market]        #14 시장피드백루프
```

## 실행 모드

| 모드 | 동작 | 소요 시간 |
|------|------|----------|
| `full` (기본) | 2 Reviewer 병렬 + Lead 통합 리포트 | ~90분 |
| `product-only` | Product PM만 실행 | ~60분 |
| `business-only` | Business PM만 실행 | ~45분 |
| `gate-only` | Business PM의 Reality Gate 4개만 (#15-18) | ~15분 |

## 실행 흐름 (Lead 오케스트레이션)

### Step 1: 사전 준비
```
1. 프로젝트 경로 확인: E:\AI\projects\$project\
2. 평가 대상 파일 수집:
   - design_workflow/**/*.yaml
   - docs/*.docx
   - .claude/agents/*.md
   - .claude/rules/*.md
   - History/$project/ (과거 평가 이력)
3. 타임스탬프: YYYY-MM-DD_HHmm
```

### Step 2: Reviewer 병렬 실행

**full 모드**: Lead가 2개 Reviewer를 동일 메시지에서 병렬 호출
```
Agent(subagent_type=reviewer-product, prompt="Evaluate {project} per your 10 criteria")
Agent(subagent_type=reviewer-business, prompt="Evaluate {project} per your 9 criteria, Reality Gate first")
```

**business-only / gate-only**: Reviewer Business만 실행
**product-only**: Reviewer Product만 실행

### Step 3: 산출물 수집

각 Reviewer가 개별 리포트 작성:
```
E:\AI\History\$project\
├── Evaluation_{date}_product.yaml    (Reviewer Product 산출)
└── Evaluation_{date}_business.yaml   (Reviewer Business 산출)
```

### Step 4: Lead 통합 리포트 (full 모드만)

Lead가 두 리포트를 diff 분석 + synthesis:
```
E:\AI\History\$project\Evaluation_{date}_synthesis.md
```

**통합 리포트 포맷**:
```markdown
# {Project} Workflow Evaluation — {date}

## Executive Summary
- Product Grade: A-
- Business Grade: B+
- Reality Gate: PASS
- **Final Verdict: CONDITIONAL GO**

## Reality Gate Status (Business Reviewer)
[Reality Gate 4개 세부 결과 인용]

## Score Table
| # | Criterion | Axis | Reviewer | Score |
|---|-----------|------|----------|-------|
| 1 | 효율성 | Business | B | ... |
| ... | ... | ... | ... | ... |

## Convergent Findings (두 Reviewer가 동의하는 사항)
- Strength: ...
- Weakness: ...

## Divergent Findings (두 Reviewer 의견 차이 — 진짜 리스크)
- Product sees X as strength, Business sees implication as weakness
- → Lead interpretation: ...

## Critical Issues (통합)
- PROD-001, BIZ-001 등 우선순위 재정렬

## Conditions for GO (CONDITIONAL인 경우)
1. Condition A (deadline, owner)
2. Condition B

## Next Review
- Trigger: {e.g., 2 weeks after conditions met}
- Scope: {full or gate-only}
```

## Gate 로직 (Business Reviewer 자체 판정)

Business Reviewer는 #15-18 Reality Gate 4개를 먼저 실행:
- **ALL PASS** → #1, #2, #9, #13, #14 평가 진행
- **ANY FAIL** → 즉시 `gate_result: BLOCK` + 나머지 평가 중단 + NO-GO 리포트

Lead는 Business Reviewer의 BLOCK 리포트를 받으면:
- Product Reviewer 결과와 무관하게 **최종 NO-GO** 처리
- 단, "품질은 양호하나 현실성 미달" 패턴을 Synthesis 리포트에 명시

## Output 구조 예시

```
E:\AI\History\BalloonFlow\
├── Evaluation_2026-04-15_product.yaml
├── Evaluation_2026-04-15_business.yaml
└── Evaluation_2026-04-15_synthesis.md   ← Lead 최종 리포트
```

## Lead 행동 지침 (이 명령 실행 시)

1. **직접 평가 금지** — Lead는 조정자. 평가는 Reviewer가 수행
2. **병렬 실행 필수** (full 모드) — Agent 호출 2개를 단일 메시지에서 보냄
3. **Reality Gate 우선 확인** — Business Reviewer 결과 도착 시 gate_result 먼저 체크
4. **Divergent Findings 강조** — 두 Reviewer 의견 충돌 지점이 진짜 인사이트
5. **History 저장 필수** — synthesis 리포트는 `E:\AI\History\{project}\`에 반드시 저장
6. **최종 Verdict 명시** — GO / CONDITIONAL / NO-GO 중 하나 선택, 근거 제시

## 사용 예시

```bash
# BalloonFlow 전체 평가
/evaluate-workflow BalloonFlow

# Reality Gate만 빠르게 (15분)
/evaluate-workflow BalloonFlow gate-only

# Product 품질만
/evaluate-workflow BalloonFlow product-only

# 사업성만
/evaluate-workflow IdleMoney business-only
```

## 반복 평가 권장 주기

- **Kickoff 직후**: full 평가 → baseline 확보
- **주요 마일스톤 (Stage 4, Phase Gate)**: gate-only + product-only
- **소프트런칭 전**: full 재평가
- **출시 후 D30**: 실측 KPI 대입하여 business-only 재평가
