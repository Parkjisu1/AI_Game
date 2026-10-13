# 인수인계: BalloonFlow 시뮬레이터 × ProjectHub 연동 (2026-07-03)

> 작성: 별도 Claude 세션 (E:\Balloonflow 작업 세션).
> 대상: hermes/watcher 관리 중인 세션.
> 이 문서는 작업 흔적용 — **커밋 금지** (ad-hoc 문서 커밋 제외 원칙).

## 0. 한 줄 요약

ProjectHub(projecthub-web)에 **시뮬레이터 탭**을 추가했고, 그 요청을 처리하도록
`hermes_executor.py`의 `_handle_simulation`을 **BalloonFlowSim(머신 B) 기반으로 교체**했다.
웹/머신 B 배포는 끝났고, **남은 것은 Mother watcher 재시작 1개** (새 executor 로드).

## 1. 시뮬레이터가 뭔가

BalloonFlow 인게임 코어메카닉(레일/다트/기믹 16종/승패판정)을 Unity 없이 1:1 포팅한
헤드리스 클리어율 시뮬레이터. 소스 `E:\AI_Simualator\BalloonFlowSim` (.NET 8),
원본 코드 분석 명세 4종은 `E:\AI_Simualator\docs\SPEC_1~4.md`.

CLI (이번 연동에서 쓰는 모드 2개):
```
BalloonFlowSim.exe --levels 1-20 --runs 50 --policy smart --seed 12345 \
    --episodes <에피소드JSON폴더> --json <out.json>      # 배치: 레벨별 클리어율 JSON
BalloonFlowSim.exe --levels 16 --seed 12345 --policy smart \
    --episodes <...> --replay <out.json>                  # 리플레이: 틱 프레임 JSON (~0.7MB)
```

## 2. 전체 데이터 플로우

```
ProjectHub /simulator (Vercel, 모바일 포함)
  → POST /api/sim → pixelforge_tasks insert
      { assignee:"hermes", tags:["시뮬","balloonflow"], status:"todo",
        sim_params:{ levels:"1-20", runs:50, policy:"smart", seed:12345,
                     replay:true, replay_level:0 } }        # replay_level 0 = 최난 레벨 자동
  → Mother watcher Change Stream 감지
  → task_router: "시뮬" 태그/키워드 → action="simulation" (Stage 2, 기존 라우팅 그대로 — 라우터 무수정)
  → hermes_executor._handle_simulation  ★ 이번에 교체된 부분
      1) ssh 머신B: cd C:/projects/balloonflow && git pull   (레벨데이터 최신화)
      2) ssh 머신B: BalloonFlowSim.exe --json → scp 회수 (timeout 900s)
      3) replay=true면 최난(또는 지정) 레벨 1회 --replay → scp (timeout 300s)
      4) MongoDB aigame.bf_sim_results insert (레벨별 전체 결과 + summary)
         MongoDB aigame.bf_sim_replays insert (프레임 JSON, result가 replay_id로 참조)
      5) return summary(마크다운 표) → 기존 플로우가 태스크 코멘트 + status=review
  → /simulator 페이지가 bf_sim_results 를 10초 폴링해 시각화 (테이블 + 캔버스 리플레이)
```

자연어 태스크도 동작: sim_params 없으면 제목/설명에서 "레벨 47-52", "50회", 정책 파싱
(기본 levels=1-20, runs=50, policy=smart, replay=true).

## 3. 변경/배포된 것

| 항목 | 위치 | 상태 |
|---|---|---|
| `_handle_simulation` 교체 + `_bf_sim_params`/`_bf_run_on_machine_b` 추가 | `E:\AI\hermes\watcher\hermes_executor.py` (구 balance-simulator.js 호출부 대체, 라인 ~225-380) | 로컬 수정 + **Mother 배포됨** (`~/.hermes/watcher/hermes_executor.py`, py_compile 통과) |
| Mother 백업 | `~/.hermes/watcher/hermes_executor.py.bak_sim` | 롤백용 |
| 시뮬 exe | 머신 B `C:/tools/BalloonFlowSim/BalloonFlowSim.exe` (+`out/` 폴더) | 배포 + 원격 스모크 통과 (`--levels 1 --runs 3` OK) |
| 웹 페이지/API | `tools/projecthub-web/src/app/simulator/page.tsx`, `api/sim/route.ts`, `api/sim/results/[id]/route.ts`, 네비 3파일 | **E:\AI main `190daac` 커밋/푸시 → Vercel 자동배포됨** |
| 테스트 데이터 | Mongo `bf_sim_results`/`bf_sim_replays` 에 task_id="local-e2e-test" 1건 (레벨14-18 + L16 리플레이) | 페이지 데모용 — 지워도 무방 |

## 4. ★ 남은 작업 (이 세션에 부탁)

1. **watcher 재시작** — 새 executor는 재시작 후 반영. 그쪽에서 watcher 재시작 플로우를
   관리 중이길래 파일만 올려두고 재시작은 안 했다 (충돌 방지).
2. 재시작 후 **E2E 1회 검증**:
   - ProjectHub /simulator 에서 "시뮬 요청" (또는 작업보드에서 assignee=hermes,
     제목 "레벨 1-3 시뮬 10회" 태스크 생성)
   - 기대: 수 분 내 태스크에 📈 요약 코멘트 + status=review,
     `bf_sim_results` 에 새 문서, /simulator 페이지에 결과 카드 등장
   - 실패 시 watcher 로그에서 `hermes-executor` 로거 확인

## 5. 설정 노브 (Mother .env, 기본값으로 동작하게 맞춰둠)

```
BF_SIM_EXE_B=C:/tools/BalloonFlowSim/BalloonFlowSim.exe
BF_SIM_OUT_DIR_B=C:/tools/BalloonFlowSim/out
BF_EPISODES_DIR_B=C:/projects/balloonflow/BalloonFlow/Assets/EditorData/Episodes
# (MACHINE_B_HOST 등 기존 값 그대로 사용)
```

## 6. 주의/알려진 리스크

- **같은 파일 동시 수정**: 그쪽 세션도 watcher 파일들을 만질 수 있음. 로컬
  `E:\AI\hermes\watcher\hermes_executor.py` 는 이미 커밋됨(`190daac`) — 그쪽 미커밋
  변경과 머지 충돌 시 이 커밋 기준으로 `_handle_simulation` 블록만 보존하면 됨.
- **runs 상한 200 / 레벨수 무제한**: 300레벨×200회는 900s 타임아웃에 걸릴 수 있음.
  대량 분석은 레벨 범위를 쪼개서 요청하는 게 안전.
- **scp 임시파일**: 머신 B `C:/tools/BalloonFlowSim/out/` 에 남는 json은 실행 후
  del 처리하지만, 실패 경로에선 잔존 가능 — 쌓이면 정리.
- **bf_sim_replays 문서 크기**: 리플레이 ~0.7-3MB/건 (16MB 한도 여유). 장기적으로
  오래된 리플레이 정리 잡 고려.
- exe 재배포가 필요해지면(시뮬 로직 업데이트): 자리 PC에서
  `scp E:/AI_Simualator/publish/BalloonFlowSim.exe user@100.92.43.9:C:/tools/BalloonFlowSim/`
  (자리 PC→머신 B ssh 키 이미 동작 확인됨).

## 7. 검증에 쓸 수 있는 로컬 재현 커맨드

```powershell
# 머신 B와 동일한 배치 실행을 자리 PC에서 재현
E:\AI_Simualator\publish\BalloonFlowSim.exe --levels 1-3 --runs 10 --policy smart --json out.json
# 리플레이 생성
E:\AI_Simualator\publish\BalloonFlowSim.exe --levels 16 --replay rep.json
# WinForms GUI 뷰어 (시뮬 동작 눈으로 확인)
E:\AI_Simualator\publish\BalloonFlowSim.exe --gui --levels 16
```

## 8. 참고: 결과 문서 스키마

`bf_sim_results`:
```json
{ "task_id": "...", "params": {"levels":"1-20","runs":50,"policy":"smart","seed":12345},
  "results": [ { "levelId":1, "purpose":"Normal", "numColors":2, "balloonCount":180,
    "totalDarts":180, "runs":50, "clearRate":1.0, "targetClearRate":0,
    "avgClearTime":15.4, "medianClearTime":15.1,
    "failRailOverflow":0, "failNoMoves":0, "failTimeout":0,
    "avgPeakOccupancy":1.0, "avgDartsFired":180, "avgDartsWasted":0,
    "avgMagazineLeftOnClear":0, "difficultyScore":16.3 }, ... ],
  "summary": { "levelCount":20, "avgClearRate":0.93, "below50Count":1,
    "worstLevels":[{"levelId":18,"clearRate":0.35}, ...] },
  "replay_id": "<bf_sim_replays _id>", "replay_level": 18, "created_at": "ISO" }
```
실패 사유 의미: RailOverflow=레일 만석(색 밸런스/순서 문제), NoMoves=다트 소진(제로슬랙),
Timeout=교착(안전한 수 없음 ≒ 실질 패배). difficultyScore 70↑ = 밸런스 점검 후보.
CSV/컬럼 상세 해설: `E:\AI_Simualator\docs\CSV_컬럼설명.md`.
