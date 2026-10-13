# 게임 데이터 분석 · 로그 요청서 — 셋업 현황

사내 공지(2026-07) 반영. 두 가지 업무가 게임팀으로 이관됐다.

1. **게임 지표 분석** — UA팀이 아니라 게임팀이 직접. Claude Code로 BigQuery를 자연어로 조회.
2. **로그 요청서 작성** — 각 개발팀 메인 기획자가 직접 작성.

---

## 이 폴더의 파일

| 파일 | 용도 |
|---|---|
| `CLAUDE.md` | **분석 지침.** 이 폴더에서 여는 모든 Claude Code 세션에 자동 적용된다. 회사 공용 추출 규칙 + 우리 팀 보충 규칙 |
| `로그요청서_템플릿.md` | 신규 타이틀용 작성 양식 + 자가 점검표 |
| `로그요청서_초안.md` | 우리 퍼즐 공용 스키마를 양식으로 옮긴 초안 |

분석 작업은 **이 폴더(`E:\AI\analytics`)를 Claude Code로 열고** 진행한다.
데스크톱 앱 "채팅"에서 한 작업은 KB에 환류되지 않는다 — 반드시 **Code 메뉴 / 폴더 기반 세션**을 쓴다.

---

## 셋업 진행 상황

### 완료 (로컬)

- [x] `C:\claude\config\` · `C:\claude\scripts\` 폴더 생성
- [x] `C:\claude\_bootstrap_lite.py` — 가이드 Step 3 스크립트 배치 (프로젝트 ID만 채우면 실행 가능)
- [x] `C:\claude\config\kb_sources_target.json` — Step 4 설정 파일 골격
- [x] `E:\AI\analytics\CLAUDE.md` — Step 7 분석 지침 설치
- [x] 로그 요청서 템플릿 + 초안 작성

### 막혀 있음 — 외부 처리 필요

| # | 항목 | 필요한 것 | 담당 |
|---|---|---|---|
| 1 | **Python 3.12 미설치** | 이 PC에 Python 3.12 설치 후 `pip install google-cloud-bigquery google-auth pandas db-dtypes cryptography` | 본인 PC |
| 2 | **서비스 계정 없음** | GCP 콘솔에서 게임 프로젝트 → 서비스 계정 생성 → 역할 **BigQuery 데이터 편집자 + BigQuery 작업 사용자** → JSON 키를 `C:\claude\config\service_account_key.json`로 저장 | 본인 (GCP 콘솔) |
| 3 | **게임 프로젝트 ID 미정** | `_bootstrap_lite.py`의 `BILLING`, `kb_sources_target.json`의 `billing_project`에 기입 | 본인 |
| 4 | **staging 테이블 주소** | 다솜님이 게임당 1회 생성 후 알려주는 주소 → `kb_sources_target.json`의 `sources_table` | 다솜님 |
| 5 | **`ua_game_rules` 뷰어 권한** | 서비스 계정에 `aimed-warehouse.ua_game_rules` 데이터 뷰어 부여 (부트스트랩 실행에 필요) | 임형철님 |
| 6 | **규칙 view** | 게임별 `<게임>_rules` view 생성 | 다솜님 |
| 7 | **로그 요청서 링크** | 기존 타이틀 요청서 + 회사 공식 템플릿 | 다솜님 |
| 8 | **계정 권한 부여** | 회사 이메일(jisu.park@gameberry.co.kr) 전달 → 권한 부여 | 공지 작성자 |

> 🔒 서비스 계정 JSON 키는 비밀번호와 동일하다. 슬랙·메일로 공유하지 말고 본인 PC에만 둔다.

### 셋업 순서 (막힌 것 풀리는 대로)

```
2·3 (서비스 계정 + 프로젝트 ID)
  → 1 (Python + 패키지)
  → 5 (임형철님 권한)
  → C:\claude\_bootstrap_lite.py 실행       # 수집 스크립트 6종 내려받기
  → 4 (staging 주소) → kb_sources_target.json 채우기
  → python C:\claude\scripts\kb_setup_collect_filters.py   # 이 폴더를 수집 범위로 등록
  → schtasks 로 일일 백업 등록 (가이드 Step 6)
  → 6·7 (규칙 view + 로그 요청서) → CLAUDE.md §3 표 채우기
  → 완료 테스트: "지침과 로그 요청서를 읽고, 최근 한 달간 유입한 유저들의 D1~D7 리텐션을 구해서 그래프로 나타내줘"
```

정상 동작 기준: ① 규칙 view 조회가 **먼저** 실행되고 ② BQ 조회가 서비스 계정으로 성공하며 ③ 게임 추출 규칙(유저 판별 등)이 적용된 결과가 나옴. 403이면 권한 반영 5~10분 대기 후 재시도.

---

## 로그 요청서 업무

기존: UA팀 작성 → 개발팀 전달
변경: **각 개발팀 메인 기획자가 직접 작성** → UA팀은 이후 검토·운영 단계에서 확인

우리는 이미 `design_standard/puzzle/schema/`에 퍼즐 공용 Raw Data Schema(이벤트 7종 + 스냅샷 1종)를 정리해 뒀다.
따라서 새로 설계하는 게 아니라 **그 스키마를 회사 양식으로 옮기고, 빠진 항목을 보강**하면 된다.

초안에서 확인된 **보강 필요 4건**:
1. `campaign_id` — UA 캠페인별 분해에 필요한데 기존 스키마에 없음
2. 누적 결제 분위 — 상위 25%/중위/하위 분해용
3. 상품군 구분 — 월정액/패키지/가챠 재화 분해용
4. 뽑기 시점 스냅샷 — 가챠가 있다면 필수 (사후 복원 불가)

---

## 참고 문서 원본

- `C:\Users\user\Downloads\game_planner_onboarding_lite.md` — 온보딩 가이드 (2026-07-24 개정, 관리: 임형철)
- `C:\Users\user\Downloads\[Guide]데이터 리터러시_로그 요청서 작성 참고용.pdf` — 5쪽, 이미지 PDF
  (텍스트 추출 불가라 이미지로 렌더해 읽음. 요지는 `CLAUDE.md` §4~§7에 반영)
