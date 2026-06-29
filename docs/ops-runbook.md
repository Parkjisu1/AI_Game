# Operations Runbook — AI Workflow (Internal Tool)

> 내부 도구 운영 최소 체크리스트. 상업 배포는 별도 런북 필요.

최종 업데이트: 2026-04-15

---

## 1. MongoDB Atlas 백업

### 자동 백업 활성화 (일일 스냅샷)

Atlas는 기본 제공되는 Cloud Backup 기능으로 일일 자동 스냅샷을 지원합니다.

**설정 절차:**
1. Atlas 콘솔 접속: https://cloud.mongodb.com
2. 프로젝트 `aigame` 선택
3. 좌측 메뉴 → **Backup** 클릭
4. **Cloud Backup** 탭 → **Configure Policy** 선택
5. 다음 정책 적용:
   ```
   Snapshot schedule:
     Daily snapshot:  Retain 7 days
     Weekly snapshot: Retain 4 weeks
     Monthly snapshot: Retain 12 months
   ```
6. **Save** 클릭

**확인:**
- 24시간 후 **Backup** → **Snapshots** 탭에서 최초 스냅샷 생성 확인
- 이후 매일 동일 시각(UTC 기준 클러스터 생성 시각)에 자동 스냅샷

### 복구 절차

**시나리오 A — 특정 컬렉션만 복구:**
1. **Backup** → **Snapshots** → 원하는 스냅샷 선택
2. **Restore** → **Download** 선택 (압축 .tar.gz 다운로드)
3. 로컬에서 `mongorestore` 실행:
   ```bash
   mongorestore --uri="$MONGO_URI" --nsInclude="aigame.code_base" --dir=./restored-dump
   ```

**시나리오 B — 클러스터 전체 롤백:**
1. **Backup** → **Snapshots** → 스냅샷 선택 → **Restore**
2. **Restore to cluster** → 대상 클러스터 선택
3. ⚠️ **주의**: 이 작업은 현재 DB를 덮어씀. 사전에 현 상태 스냅샷 수동 생성 권장

### 월간 백업 점검 체크리스트
- [ ] 최근 7일 스냅샷 모두 존재 확인
- [ ] 무작위 1개 스냅샷 다운로드 테스트 (실제 데이터 열어보기)
- [ ] `design_expert`, `code_expert` 컬렉션 문서 수 기록 (회귀 감지용)

---

## 2. 토큰 사용량 모니터링

### 로깅 방법

각 에이전트 실행 후 `scripts/track-tokens.js`로 기록:

```bash
node scripts/track-tokens.js log \
  --project BalloonFlow \
  --agent designer \
  --model claude-sonnet-4-6 \
  --input 15200 \
  --output 3400 \
  --note "Stage 2 design generation"
```

**로그 위치:** `E:\AI\logs\token-usage.jsonl`

### 주간 집계

매주 월요일 실행하여 전주 사용량 점검:

```bash
# 지난 7일
node scripts/track-tokens.js summary --since 2026-04-08

# 프로젝트별
node scripts/track-tokens.js summary --project BalloonFlow

# 전체
node scripts/track-tokens.js summary
```

### 예산 기준 (내부 가이드라인)

| 게임 규모 | 기획 예상 비용 | 코드 예상 비용 | 비고 |
|----------|--------------|--------------|------|
| 소형 (Playable) | $5-15 | $10-30 | Sonnet 위주 |
| 중형 (모바일 캐주얼) | $20-50 | $50-150 | Opus 일부 사용 |
| 대형 (RPG/Idle) | $80-200 | $200-500 | Opus 다수 사용 |

⚠️ 2주 이상 프로젝트는 **중간 예산 점검 필수** (초기 추정 대비 1.5배 초과 시 scope 재검토)

---

## 3. 에이전트 장애 대응

### Claude API 장애 시
1. **Anthropic Status Page** 확인: https://status.anthropic.com
2. 부분 장애:
   - Sonnet 장애 시 → Opus로 일시 폴백 (비용 증가 감수)
   - Opus 장애 시 → 중요 작업 중단, Sonnet 가능 작업만 진행
3. 전면 장애:
   - 진행 중 Phase 스냅샷 저장 후 대기
   - History에 장애 시점 기록 (재개 시 컨텍스트 복원용)

### MongoDB 연결 실패 시
1. `.env`의 `MONGO_URI` 유효성 확인
2. Atlas IP Allowlist 확인 (`0.0.0.0/0` 또는 현재 IP)
3. 로컬 DB 폴백: `E:\AI\db\base\{genre}\` 파일 기반 검색 (제한 기능)

---

## 4. 정기 점검 주기

| 주기 | 작업 |
|------|------|
| **매일** | 토큰 사용량 급증 여부 확인 (전일 대비 3배 초과 시 원인 조사) |
| **매주 (월)** | `track-tokens.js summary --since <지난 월요일>` 실행 |
| **매월** | MongoDB 스냅샷 무결성 체크 (위 §1 체크리스트) |
| **분기** | Claude API 가격·모델 변경 여부 확인 (Anthropic 공지) |

---

## 5. 비상 연락처 / 리소스

- **Anthropic Status**: https://status.anthropic.com
- **Atlas Console**: https://cloud.mongodb.com
- **Atlas Docs**: https://www.mongodb.com/docs/atlas/backup/cloud-backup/
- **내부 관리자**: (프로젝트 오너)

---

## 변경 이력

| 날짜 | 변경 | 담당 |
|------|------|------|
| 2026-04-15 | 초판 작성 (내부 도구 최소 수준) | AI Workflow Team |
