# Hermes 자기개선 진실성 게이트 (Truth Gate) — 2026-06-29

목표: Hermes 재귀개선을 "더 똑똑하고, 시키는 업무를 더 잘하게(거짓 없이)".
근본 문제: 학습 신호가 **LLM이 LLM을 채점**(reviewer 점수)이라, 객관적 검증 없이
"성공"을 학습 → 환각 강화. 핵심 결함 5종(A~E)을 단일 개념 **'객관적 수용
(objective acceptance)'**으로 통합 해결.

## 핵심 개념
- **객관적 수용** = 작업이 모든 게이트를 통과해 실제 ship됨(`next_status=done`).
- 학습은 리뷰 시점이 아니라 이 수용 시점에만 확정. 사람이 나중에 거부하면 회수.

```
review  → defer_learning()          → hermes_learning_pending {pending}
done    → on_objective_acceptance() → grounded reflect + candidate 패치 승격
reject  → on_falsified()            → 원칙/RAG-good 회수 + pending 취소
```

## 변경 (commit 4ed28c4)
| 항목 | 내용 | 위치 |
|---|---|---|
| 신규 모듈 | `truth_gate.py` — defer_learning / on_objective_acceptance / on_falsified | `hermes/watcher/truth_gate.py` |
| 수용 훅 | done으로 ship 시 보류 학습 확정 | `projecthub_watcher.py:265` |
| 거부 훅 | 유저 거부 시 회수 | `hermes_executor.py` `_penalize_previous_reviewer` |
| **A** 귀속버그 | 리뷰어 거부를 reviewer→**coder**(`main_coder_role`) 실패로 학습 | reviewer reject 블록 |
| **B** 게이팅 | 시니어원칙/RAG-good을 수용시점 확정, 거부 시 회수 | truth_gate + `_record_quality_score` |
| **C** 그라운딩 | reflection에 실제 diff/파일 전달(빈 diff 제거) | `_record_quality_score` 시그니처 확장 |
| **D** candidate 패치 | 신규 패치=candidate로 적용·측정, 수용 N회+골든 통과해야 active | `prompt_self_improvement.promote_candidates_on_acceptance` / `_golden_ok` |
| **E** 컴파일 게이트 | 컴파일 미검증 APPROVED 자동 push 보류 | push 직전, `HERMES_REQUIRE_COMPILE` |

## 환경 변수 (튜닝)
- `HERMES_REQUIRE_COMPILE` = `block`(기본) | `warn` | `off`. **MCP 자주 다운 시 백로그 위험 → `warn`으로 완화.**
- `HERMES_PATCH_PROBATION_SAMPLES` = 3 (candidate→active 승격에 필요한 수용 작업 수).

## 신규 컬렉션
- `hermes_learning_pending` — 보류 학습 레코드(task_id+reviewer_role 키, status: pending/promoted/cancelled).
- `pixelforge_tasks.learning_verified` / `.falsified` — 수용/거짓 마크.
- `hermes_prompt_patches.status` 에 `candidate` 추가, `.accepted_samples` 필드.

## 검증
- py_compile 4파일 OK → swap → import/API 스모크 OK → watcher 재시작 active/NRestarts=0/정상 catch-up.
- 모든 게이트 방어적(try/except, 절대 작업흐름 비차단).

## 후속 (미완)
- **골든 eval 커버리지 확대**: `_golden_ok`는 best-effort(현재 `harness/eval.py`가 design_level_designer만 지원, 그 외 fail-open). 역할별 골든셋 추가 시 D가 전 역할에 실효.
- 리뷰어 캘리브레이션(P1-3): reviewer APPROVE 후 유저거부율로 reviewer 신뢰도 산출·하향가중 — 미구현.
- 실패 스킬 LLM 합성(P2-1), 실패 택소노미 구조화(P2-2), design_base 벡터 인덱스(P2-3) — 미구현.

## 관련
- 분석 보고서: 이 폴더 `2026-06-29_investigation_and_drift_reconciliation.md`
- git add -A 시크릿 하드닝: commit 2c3f0aa
