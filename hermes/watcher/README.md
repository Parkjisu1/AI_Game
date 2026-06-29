# ProjectHub Watcher

Mother 서버에서 24/7 돌아가는 Python 서비스. MongoDB Change Streams로 **ProjectHub의 작업 생성/업데이트를 실시간 감지**하여 Hermes로 전달.

## 구성

```
watcher/
├── projecthub_watcher.py   # 메인 엔트리 — Change Stream 루프
├── projecthub_writer.py    # MongoDB 쓰기 (status/comment 업데이트)
├── user_name_resolver.py   # 이름 → user_registry.yaml 매칭
├── scoped_memory_loader.py # 팀/롤/프로젝트 메모리 계층 로드
├── context_builder.py      # Task + 스코프 + 관련 DB 문서 번들링
├── task_router.py          # 태그/키워드 → action 결정
├── hermes_executor.py      # action별 실제 실행 (db/sim/apk/chat)
├── requirements.txt
├── .env.example
└── README.md  ← 이 파일
```

## 동작 흐름

```
팀원이 ProjectHub 작업 생성 (assignee=hermes)
  → MongoDB aigame.pixelforge_tasks insert
  → projecthub_watcher.py가 Change Stream으로 감지
  → 필터: assignee=hermes && status in {todo, in_progress}
  → context_builder로 스코프 추론 + 메모리 로드 + 관련 DB 문서 프리패치
  → task_router로 action 결정 (db_query/simulation/apk_build/chat)
  → hermes_executor로 실행
  → projecthub_writer로 status 및 comment 업데이트
  → ProjectHub UI가 실시간 반영
```

## Stage 제어 (환경변수)

`HERMES_ACTIVE_STAGES=1,2,3` → Stage 1~3만 자동 실행. Stage 4~6(GameForge 본격 호출)은 비활성, review_needed로 라우팅.

| Stage | 활성 조건 | 예시 | 
|---|---|---|
| 1 | `1` 포함 | db 조회, chat | 
| 2 | `2` 포함 | 시뮬레이션 | 
| 3 | `3` 포함 | APK 빌드 | 
| 4~6 | `4,5,6` 추가 | GameForge Designer/Coder | 

**지금은 1,2,3만 활성 권장**. 2주 무사고 운영 후 4 추가.

## 설치 & 실행 (Mother 기준)

### 1. 디렉토리 준비
```bash
mkdir -p ~/.hermes/watcher
cd ~/.hermes/watcher
```

### 2. 코드 복사 (자리 PC에서 rsync)
```powershell
# 자리 PC PowerShell
scp E:\AI\hermes\watcher\*.py aimed@100.77.190.68:~/.hermes/watcher/
scp E:\AI\hermes\watcher\requirements.txt aimed@100.77.190.68:~/.hermes/watcher/
scp E:\AI\hermes\watcher\.env.example aimed@100.77.190.68:~/.hermes/watcher/
```

### 3. Python venv + 의존성
```bash
# Mother SSH
cd ~/.hermes/watcher
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. 환경 변수 설정
```bash
cp .env.example .env
nano .env   # MONGODB_URI 채우기 (ProjectHub의 .env.local에서 복사)
chmod 600 .env   # 키 보호
```

### 5. 수동 테스트
```bash
source venv/bin/activate
export $(cat .env | grep -v '^#' | xargs)
python projecthub_watcher.py
# → "Watching aigame.pixelforge_tasks for hermes tasks..." 나오면 OK
# → ProjectHub에서 assignee=hermes 태스크 하나 만들어 테스트
# → Ctrl+C로 중지
```

### 6. systemd 서비스 등록
`../systemd/projecthub-watcher.service` 사용 (별도 파일).

```bash
sudo cp ~/.hermes/systemd/projecthub-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now projecthub-watcher
sudo systemctl status projecthub-watcher    # active (running) 확인
journalctl -u projecthub-watcher -f         # 실시간 로그
```

## 트러블슈팅

### Change Stream 에러
```
pymongo.errors.OperationFailure: The $changeStream stage is only supported on replica sets
```
→ MongoDB Atlas는 기본적으로 Replica Set이라 문제 없음. 자체 MongoDB라면 `replSet` 구성 필요.

### assignee 필터 검증
ProjectHub에서 `assignee="hermes"`로 태스크 만들고 `mongosh`로 확인:
```
use aigame
db.pixelforge_tasks.find({ assignee: "hermes" }).pretty()
```

### watcher가 감지 안 함
1. `journalctl -u projecthub-watcher -f`로 로그 확인
2. `HERMES_ASSIGNEE_NAMES` 환경변수에 실제 assignee 값이 포함됐는지
3. MongoDB 연결 되는지: `mongosh "$MONGODB_URI" --eval 'db.adminCommand({ping:1})'`

### 메모리 파일 인식 안 함
1. `HERMES_MEMORY_ROOT` 경로가 실제 존재하는지
2. `~/.hermes/memories/user_registry.yaml` 있는지
3. YAML 문법 에러: `python -c "import yaml; yaml.safe_load(open('user_registry.yaml'))"`

## Phase 로드맵

| Phase | 내용 | 상태 |
|---|---|---|
| 1.1 | Stage 1~3 자동화 | **현재** — 배포 대기 |
| 1.2 | projecthub_settings.hermes_sessions로 세션 링크 | 구현됨 |
| 1.3 | 관련 DB 문서 프리패치 정교화 | 구현됨 (기본) |
| 2.1 | Stage 4 활성 (GameForge Designer) | 대기 |
| 2.2 | Stage 5 활성 (Coder + Validator) | 대기 |
| 2.3 | Hermes 서브에이전트 체이닝 | 대기 |
| 3.x | 스킬 자가 진화 | 장기 |
