# ProjectHub 조사·분석 + 드리프트 정본화 (2026-06-29)

조사 범위: ProjectHub Web (`E:\AI\tools\projecthub-web`, Next.js 16, ~24K줄) + Hermes Watcher
(`E:\AI\hermes\watcher`, Python, ~26K줄) + Mother 라이브 서버(`100.77.190.68`) 실측 검증.

---

## 0. 헤드라인: 버전관리 부재 + 3-way 드리프트 (최대 리스크)

- 유일한 git repo = 로컬 `E:\AI` → GitHub `Parkjisu1/AI_Game`. `tools/projecthub-web`는 이 repo 일부.
- **`hermes/watcher/`는 git 전혀 미추적**(`git ls-files hermes/` = 0). 이력·롤백·리뷰 불가.
- **Mother의 `~/projecthub-web`, `~/.hermes/watcher`는 git repo가 아님**(scp 배포).
- 권위 순위(실측): **Mother 라이브 > 로컬 작업본 > GitHub 커밋(가장 오래됨)**.
  - "git이 최신본"은 사실이 아님 — git 기준 수정·배포 시 라이브 보안/런타임 회귀 위험.

### 3-way 드리프트 맵 (md5 실측)
| 영역 | 동일 | 라이브가 최신 | 로컬 전용 |
|---|---|---|---|
| Web (`src/`+next.config) | 82 | 3 (`auth.ts`,`proxy.ts`,`next.config.ts` = 5/4 보안) | 0 |
| Watcher (venv 제외) | 52 | 8 (`batch_generate_levels`,`hermes_atlas_retrieval`,`pattern_lib/blank_engine`,`user_name_resolver` + 로컬 부재 `field_complete_levels`,`tracing`,`v43/v43_runner`,`zone_pipeline`) | 18 (`_check_*`/`_test_*`/`_seed_*` 운영·테스트 스크립트, 라이브 미배포) |

### 정본화 조치 (2026-06-29 실행)
- ✅ 라이브가 최신인 11개 파일을 로컬로 내려받음(tar stream) → **로컬 == 라이브** 달성.
- ⏳ 미실행(권고): 전체를 git 커밋(`hermes/watcher` 포함, `.env`/`*.bak`/`node_modules`/`venv` gitignore) → git을 정본화.

---

## 1. 아키텍처 / 현재 상태
- **Web**: Next.js 16(미들웨어=`proxy.ts`). 페이지 11종, API 54 라우트(쓰기 31개). Mongo `aigame` 21개 컬렉션 직접 접근. SSE 2종(tasks/sessions)은 Change Stream. `/pixelforge/*`→`:3002` 프록시.
- **Hermes**: `projecthub_watcher.py`(change stream)→`_dispatch_event`→`hermes_executor.execute_task`(9 핸들러)→`agent_team`(역할/페르소나). LLM: Claude=Claude Code CLI, OpenAI=LiteLLM 프록시, 임베딩만 OpenAI SDK. harness 5레이어, RAG(Atlas vector), MCP(SSH→빌드컴 Unity), 무LLM 레벨 생성, failure_learning·prompt_self_improvement.

## 2. 기술부채
- God-object: `hermes_executor.py` 4214줄/59 def(특히 `_handle_unity_modify` ~1,580줄). `agents/batches/page.tsx` 3787줄/useState 75개.
- 양호: Web 타입안전 우수(실질 any 0), TODO/FIXME 거의 없음, 시크릿 하드코딩 없음.
- 정리 필요: Hermes 런타임 디렉토리에 일회성 스크립트 ~24개 혼재 → `scripts/ops/` 분리 권고.

## 3. 미해결 이슈 triage (백엔드 과거 치명 3대 루프 = 모두 해결 확인)
- (a) Phantom loop ✅ FIXED `hermes_executor.py:120-134` (삭제 task abort)
- (b) Phase 폭주/중복PR ✅ FIXED `:3864-3867` 원자적 CAS
- (c) MCP 다운→게이트 스킵 ✅ caught/non-fatal `:3336-3347`
- (d) Validator 게이트 advisory(설계상) — 차단은 reviewer 게이트(`HERMES_MERGE_GATE` 기본 block)
- (e) stop/resume 가드 ✅ VERIFIED

## 4. 보안/운영 (라이브 검증)
- 라이브 적용 확인: auth fail-closed / 보안헤더(HSTS·X-Frame·CSP) / rate limit(429). (로컬은 stale였음 → 동기화 완료)
- 실재 리스크: `hermes_executor.py:3611` `git add -A` 전체 스테이징(과거 PR#92 토큰 유출). `slack/events`는 `SLACK_SIGNING_SECRET` 미설정 시 서명검증 스킵. `settings` POST admin 게이트 없음(영향 낮음).

---

## 5. 본 세션 적용한 수정 (B) — 로컬, tsc 통과(EXIT=0), **라이브 미배포**
1. `tasks/page.tsx:1358` 무가드 `priorityStyles[task.priority].badge` → `(...|| priorityStyles.medium).badge` (crash 제거)
2. `api/tasks/stream/route.ts` SSE error 핸들러 → 단일 `cleanup()`(ping clearInterval + changeStream.close + abort 리스너 제거)
3. `api/agents/sessions/stream/route.ts` 동일 cleanup 적용

### 미적용(확인 필요)
- `hermes_executor.py:3611` `git add -A` → 경로지정/시크릿스캔(프로덕션 커밋동작 변경이라 확인 후)
- `slack/events` 시크릿 미설정 시 401, queue-generator 2D 가드, settings POST admin 게이트, 11개 API try/catch

---

## 6. GUI(웹)로 업데이트 가능한 항목 (코드수정 없이)
- **AI팀 역할/모델/페르소나**: `/agents` → POST `/api/agents/roles` (role/tool/**model**/persona/team/sub_team). 분과 자유 확장.
- **작업보드**: `/tasks` task CRUD·우선순위·담당자, hermes ⛔중단/▶️재개, 설명요청.
- **설정**: `/settings` Slack webhook/bot token.
- **로드맵**: `/roadmap` POST. **레벨**: `/levels` 편집/export.
- **갤러리/디자인**: 코멘트·inpaint·9slice·generate(`/designs/*`).
- **배치 생성**: `/agents/batches`, field-complete, v43-batch, pipeline advance/curate.
- **음성지시**: `/voice` 녹음→STT→task 자동 생성(자동분류 query/meeting).
- **허용 사용자(admin)**: `/api/admin/allowed-users`.
