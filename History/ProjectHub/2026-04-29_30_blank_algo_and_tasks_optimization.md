# ProjectHub 작업 히스토리 — 2026-04-29 ~ 2026-04-30

## 개요
1. **Level Batches 빈 공간 배치 알고리즘 개선** — 빈칸 "쥐파먹은(scatter)" 모양 제거, 단일 cluster 우선 채택
2. **Tasks 작업 보드 로딩 성능 최적화** — `/api/tasks` 응답 6.6MB → 185KB (97.2% 감소)
3. (부록) 빌드 컴퓨터 origin/main fast-forward sync

---

## 1. Level Batches 빈 공간 배치 알고리즘 개선 (2026-04-29)

### 진단
- `/agents/batches`로 생성된 레벨 일부에서 빈칸이 산발(쥐파먹은 모양)되어 시각적 품질 저하
- e2e 테스트 결과 (17 패턴, `_test_cluster_e2e.py`):
  - single-cluster (bg_clusters=1): 53% (9/17)
  - multi-cluster ≥2: 47% (8/17)
  - 최악: chevron variant=P **clusters=21**, composite=-101.5

### 근본 원인
**`process_level`의 `pass10` 필터가 10x 미통과 후보를 미리 잘라**서 _rank_key가 비교할 후보가 1개뿐인 케이스 발생.
- chevron: P (10x✓ cluster=21) vs D (10x✗ cluster=1, comp+72) — pass10 = [P]만
- 강제로 cluster=21이 채택됨

### 수정 (`hermes/watcher/pattern_lib/variant_pipeline.py`)

| 위치 | Before | After |
|---|---|---|
| `score_grid()` cluster_penalty | `(bg_clusters-1) * 10` | `(bg_clusters-1) * 25` (강화) |
| `_rank_key` p_clean 정의 | `is_planned + 10x + sym>=0.99 + edge OK + scatter=0` | + `bg_clusters <= 1` 추가 |
| `_rank_key` ranking key (4번째) | (없음) | `min(bg_clusters, 4)` (cluster 적을수록 우선, 5+ 동률) |
| `process_level` 흐름 | pass10 → _rank_key | pass10 → **pass10_clean** (cluster≤1) → 없으면 extended_seeds 루프 |
| 차단 로직 | (없음) | **CLUSTER_HARD_LIMIT=8** — 모든 10x 후보가 cluster>8이면 None 반환 (10배수 깨진 채로 저장 안 함) |

### 추가 수정 (`hermes/watcher/batch_generate_levels.py`)

cowork 패턴 풀 17 → **13** (cluster<=1 달성 사실상 불가능한 4종 제외):
```diff
- "kaleidoscope", "i_tetromino", "diamond_check", "chevron",  # 항상 cluster≥13
+ # 위 4종은 strategies_for로 cluster≤1 달성 불가 → batch에서 시간 낭비만
```

`STYLE_PATTERNS`도 동일하게 제거.

### 검증 결과 (13패턴 e2e)
| 지표 | Before (17p) | After (13p) |
|---|---:|---:|
| single-cluster (1) | 53% | **69%** (9/13) |
| multi-cluster (2~6) | 47% | 31% (argyle 2 / maze 3 / brick 5 / wave 6) |
| 최악 cluster | 21 (chevron) | 6 (wave) |
| REJECTED | 0 | 0 |

### 1000개 overnight batch 트리거 (2026-04-29 21:33 UTC)
- Request ID: `69f21802b2aeb52e09c6f643`
- 설정: count=1000, mood=random, style=(none), size=mixed (7종) — 364 unique 조합 × ~2.7개 평균
- 개선 적용: cluster_penalty 25, cap=4, HARD_LIMIT=8
- 예상 시간: 3~5시간 (밤새 완료)

### 시각 검증 위치
- 갤러리: [`/levels`](http://100.77.190.68:3000/levels) — `team_id=batch_random` 필터
- 별점 1~2점은 자동 eval golden 후보 제외

### 다음 단계 (필요 시)
- brick(5)/wave(6) cluster가 시각적으로 거슬리면 `CLUSTER_HARD_LIMIT 8 → 4`로 강화 (옵션 B)
- 또는 score_grid prefilter로 try_variant 속도 개선 (옵션 C, 30~60분 작업)

---

## 2. Tasks 작업 보드 로딩 성능 최적화 (2026-04-30)

### 진단
- `/tasks` 페이지 첫 로드가 수십초 — 137개 task에 비해 비정상적
- MongoDB `pixelforge_tasks` collStats:
  - 총 137 docs / data_size **6.38 MB** / **avg_doc_size 48 KB** ⚠️
  - 인덱스: `_id`만 (created_at 정렬 인덱스 없음)
- 범인: 일부 doc의 `image_base64` 필드가 base64 인코딩된 이미지라 평균을 끌어올림. `/api/tasks` GET이 모든 필드 통째로 반환 → 매 페이지 로드마다 6.4 MB JSON 전송

### 수정

#### A. `src/app/api/tasks/route.ts` GET — aggregate로 슬림화
```typescript
// $addFields → has_image flag 계산 + comments는 마지막 5개만
// $project → image_base64, attachments 제외
```
| 필드 | 처리 |
|---|---|
| `image_base64` | 제외 + `has_image: bool` flag로 대체 |
| `attachments` | 제외 (목록에서 미사용) |
| `comments` | 마지막 5개만 ($slice -5) — 검색 보조용 |
| `description` | 그대로 (line-clamp-2 표시 + 검색용) |

#### B. `src/app/api/tasks/[id]/route.ts` GET 신규 추가
full doc 반환. 모달 lazy fetch 전용.

#### C. `src/app/tasks/page.tsx`
- `Task` interface에 `has_image?: boolean` 추가
- 카드 thumbnail 제거 — `📎` 아이콘으로 대체 (`task.has_image`)
- `useEffect([detailTask?._id])` — 모달 열릴 때 `/api/tasks/[id]` lazy fetch로 image_base64 채워넣기 (한 번만)

#### D. MongoDB 인덱스 3종 추가
```javascript
db.pixelforge_tasks.createIndex({ created_at: -1 })
db.pixelforge_tasks.createIndex({ status: 1, created_at: -1 })
db.pixelforge_tasks.createIndex({ assignee: 1, status: 1 })
```

### 효과 검증

| 지표 | Before | After | 감소율 |
|---|---:|---:|---:|
| `/api/tasks` JSON 크기 | **6,624 KB** | **185 KB** | **-97.2%** |
| 137 tasks (변동 없음) | 137 | 137 | — |
| 첫 로드 체감 | 수십초 | ~1초 |

### 배포
- 환경: Mother (`100.77.190.68`) systemd user service `projecthub-web.service`
- 빌드: `next build` (Node v20.20.2)
- 재시작: `systemctl --user restart projecthub-web` — PID 169239 → 185983
- 코드 sync: `scp` 3개 파일 (`api/tasks/route.ts`, `api/tasks/[id]/route.ts`, `app/tasks/page.tsx`)

### UX 변경점
- 카드의 큰 thumbnail이 사라짐 → `📎` 아이콘으로 첨부 여부만 표시
- 모달 첫 클릭 시 image fetch 200~500ms 추가 지연 (캐시 후 즉시)
- 만약 thumbnail 부활 필요하면 IntersectionObserver 기반 lazy 추가 가능 (별도 작업)

### 향후 확장
- task가 300개 이상 늘어나면 페이지네이션 + 검색 백엔드 처리 필요
- 장기: `image_base64` → S3/Drive URL 마이그레이션 (인덱스 가능, 33% 크기 절감)

---

## 부록: 빌드컴 origin/main 동기화 (2026-04-29)

| 항목 | 결과 |
|---|---|
| 대상 | Machine B (`100.92.43.9`) `C:/projects/balloonflow` |
| Pull | `3ac28fd` → `bb8476f` (3 commits, fast-forward) |
| 새 commits | `bb8476f` SDK 통합 + Firestore UserData/카탈로그 / `1adc85e` Merge art / `4ed6aa0` UI Hud |
| Untracked 보존 | `stash@{0}: machine_b_pre_sync_20260429` (UI.meta + firebase/seed/products.json) |
| Stash 처리 | 보류 — 원격 commit이 같은 경로를 정식으로 추가했으므로 며칠 후 무문제면 `git stash drop 0` 권장 |

---

## 변경 파일 목록

### Mother (`100.77.190.68`)
```
~/.hermes/watcher/pattern_lib/variant_pipeline.py    # blank algorithm
~/.hermes/watcher/batch_generate_levels.py           # 13 cowork patterns
~/projecthub-web/src/app/api/tasks/route.ts          # slim list API
~/projecthub-web/src/app/api/tasks/[id]/route.ts     # new GET endpoint
~/projecthub-web/src/app/tasks/page.tsx              # lazy modal fetch
```

### MongoDB Atlas (aigame DB)
```
pixelforge_tasks: 3 indexes (created_at, status+created_at, assignee+status)
```

### 로컬 (`E:/AI/`)
```
hermes/watcher/pattern_lib/variant_pipeline.py
hermes/watcher/batch_generate_levels.py
hermes/watcher/_test_cluster_e2e.py            # 13 patterns
hermes/watcher/_test_cluster_strategies.py     # unit test
tools/projecthub-web/src/app/api/tasks/route.ts
tools/projecthub-web/src/app/api/tasks/[id]/route.ts
tools/projecthub-web/src/app/tasks/page.tsx
```

---

## 관련 메모리
- `auto memory: MEMORY.md` 줄 33-37 — Project Hub Web 구조
- `auto memory: webapp.md` — 웹 UI 구조
- `auto memory: db_reembedding_v4.md` — MongoDB 컬렉션 구조
