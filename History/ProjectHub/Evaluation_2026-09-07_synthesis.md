# ProjectHub 자체 LLM 재조립 아키텍처 — 평가 통합 리포트 (2026-09-07)

평가 대상: 설계서 아티팩트 3bcd9935 (§0~§12 + 리뷰 로그 R1~R17)
방식: 2-Reviewer 병렬 (Product Quality + Business Feasibility) + Lead 통합
평가자 주의: 이 설계는 구현 전이며 실험 E0~E14가 전부 미측정. "설계 문서로서의 완결성"과 "실행 현실성"을 분리 평가함.

## Executive Summary
- Product Grade: **B+** (Conditional Pass, C 기준 2개: 재현성·실패복구)
- Business Grade: **D**
- Reality Gate: **BLOCK** (#16 리소스 FAIL, #18 운영 FAIL / #15 기술 PASS, #17 시장 PASS)
- **Final Verdict: NO-GO (전면 실행 기준) → 복구 우선 조건부 GO로 재정의**

핵심 해석: 막는 것은 설계가 아니라 실행 주체다. 문서는 근거·검증가능성에서 우수하지만(83 참조·42 file:line 실측), 실행 주체(3인 팀)와 현재 라이브 시스템(2개월째 붕괴)이 실현 가능성을 제약한다.

## Reality Gate (Business Reviewer)
| # | 기준 | 판정 | 근거 |
|---|------|------|------|
| 15 | 기술 실현성 | PASS (B+) | 스택·하드웨어가 설계 범위 감당. 단 로컬 모델 미연결(P2) 구현 갭 |
| 16 | 리소스 현실성 | **FAIL (D)** | 필요 ~5MM > 게임 병행 시 가용 ~2.88MM. ML 전문 역량 미확인(train_qlora.py eval 코드 없음) |
| 17 | 시장 현실성 | PASS (C+) | 내부도구 ROI 성립(연 절감 $3.9K~$11.4K). 단 "사람 검사 0 출시" 가치 명제 미입증 |
| 18 | 운영 현실성 | **FAIL (F)** | 이미 붕괴: hermes 배정 8~9월 0건, gate_events 7/6 이후 없음, 골든 0/120, LiteLLM 14일 0요청 |

## Score Table
| # | 기준 | 축 | Reviewer | 점수 |
|---|------|-----|----------|------|
| 3 | 단계완결성 | Result | Product | A- |
| 4 | 전문성 | Result | Product | A |
| 5 | 정합성 | Result | Product | B |
| 6 | 파생가능성 | Result | Product | B+ |
| 7 | 재현성 | Trust | Product | C+ |
| 8 | 검증가능성 | Trust | Product | S |
| 10 | 인간개입 | Operation | Product | B+ |
| 11 | 실패복구 | Operation | Product | C |
| 12 | 데이터축적 | Operation | Product | B |
| 15 | 기술실현성 | Reality | Business | PASS B+ |
| 16 | 리소스현실성 | Reality | Business | FAIL D |
| 17 | 시장현실성 | Reality | Business | PASS C+ |
| 18 | 운영현실성 | Reality | Business | FAIL F |
| 1,2,9,13,14 | — | — | Business | 게이트 BLOCK으로 평가 중단 |

## Convergent Findings (두 Reviewer 동의)
- **강점**: 문제 진단(P1~P11)·해결 방향(S1~S11)이 근거로 탄탄. 검증가능성 최상급(Product S, Business도 실측 인용 신뢰).
- **약점 1**: 데이터 플라이휠의 입력이 이미 사망. gate_events 2건·골든 0/120 → PROD-002와 BIZ-001이 같은 결함을 가리킴. "통과=학습 샘플" 원칙이 2개월째 무효.
- **약점 2**: 학습 준비 미비. eval 코드·중간 체크포인트 없음(PROD-003), ML 전문 역량 미확인(BIZ-003).

## Divergent Findings (진짜 인사이트)
- Product는 문서를 B+ Pass로 본다("설계로서 우수").
- Business는 같은 설계를 NO-GO로 본다("실행 현실 미달").
- **Lead 해석**: 둘 다 옳다. 설계 품질과 실행 가능성은 다른 축이다. 결론은 "설계를 버려라"가 아니라 "순서를 바꿔라"다. 값싸고 확실한 복구(Phase 0~2)를 먼저 해 바닥을 증명하고, 비싸고 불확실한 학습(Phase 5)·무검사 출시는 그 뒤로 미룬다.

## Critical Issues (통합·우선순위)
1. **[CRIT] gate_events·골든 사망** (PROD-002 + BIZ-001) — 복구 없이 학습 진입 시 두 번째 붕괴. Phase 0에서 role 버그(agent_team.py:223)·gate 기록 같은 PR로.
2. **[HIGH] E0 단일 실패점** (PROD-001) — E0 다양성 검증 기준이 없음. 역할×프로젝트×난이도 층위 비율 명시 필요.
3. **[HIGH] 3인 팀 이중 부하 + ML 역량** (BIZ-003 + PROD-003) — 게임 제작 병행 시 인프라 가용 공수 부족. ML 파트타임 1인 또는 Phase 5 연기.
4. **[HIGH] "사람 검사 0" 목표와 품질 괴리** (BIZ-002) — 격차 12~25pp + 골든 0통과. 골든 70% 전까지 무검사 출시는 리스크 무제한.

## Conditions for GO (조건부 전환)
1. Phase 0~2 복구 실증: gate_events 주 5건 이상 4주 연속 + 골든 role 수정·통과율 20%+.
2. ML 역량 확보: QLoRA~골든 일관 결과를 낼 인력 최소 1인(외주·계약 포함).
3. "사람 검사 0" 하향: 골든 70% 도달 전까지 최소 30% 샘플 인간 리뷰 의무화.
4. (추가) E0 다양성 검증 항목을 §9에 명시 후 D1 진입.

## 권고 실행 순서
- **지금 시작 (조건 무관, 저비용·고가치)**: Phase 0 측정 + Phase 1 라우터 통합 + Phase 2 검증 복구. 게이트가 다시 살아나고 데이터가 쌓이는 것을 4주 관찰.
- **조건 충족 후**: Phase 3 검색 → Phase 5 학습.
- **v2 모델(D5 완료) 이후**: "사람 검사 0" 풀사이클 목표 재개.

## Next Review
- Trigger: E0 완료 + Phase 2 gate_events 기록 복구(주 5건 4주)
- Scope: gate-only (Reality Gate #16·#18 재판정) → PASS 시 full

---
평가 근거는 전부 설계서 실측·인용에서 도출. Reviewer 원본: tasks/a310e5c473d02cfb4(product), aeda5c610c315345c(business).
