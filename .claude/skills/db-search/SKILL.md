---
name: db-search-patterns
description: Base Code DB 검색 및 참조 규칙
version: 1.0.0
triggers:
  - "DB 검색"
  - "코드 참조"
  - "Base Code"
  - "Expert DB"
  - "파싱"
  - "임베딩"
---

# DB 검색 및 참조 규칙

이 스킬은 코드 생성 시 DB 검색, 파싱 작업 시 자동으로 활성화됩니다.

---

## DB 구조

```
E:\AI\db\
├── base\                    # Base Code DB
│   ├── generic\             # 장르 무관 공통
│   │   ├── core\            # Core Layer
│   │   │   ├── index.json   # 경량 인덱스
│   │   │   └── files\       # 개별 파일 상세
│   │   └── domain\
│   ├── rpg\
│   │   └── domain\
│   ├── idle\
│   ├── merge\
│   ├── slg\
│   ├── tycoon\
│   └── simulation\
├── expert\                  # 검증된 코드 (score >= 0.6)
│   ├── index.json
│   └── files\
└── rules\                   # 축적된 피드백 규칙
    ├── generic_rules.json
    └── genre_rules.json
```

---

## 검색 우선순위

코드 생성 시 반드시 이 순서로 검색:

| 순위 | 대상 | 경로 | 조건 |
|------|------|------|------|
| 1 | Expert DB (해당 장르) | db/expert/ | genre 일치 AND score >= 0.6 |
| 2 | Expert DB (Generic) | db/expert/ | genre = Generic AND score >= 0.6 |
| 3 | Genre Base DB | db/base/{genre}/ | genre 일치 |
| 4 | Generic Base DB | db/base/generic/ | 항상 |
| 5 | AI_기획서 기반 생성 | - | 참조 코드 없음 |

---

## 인덱스 파일 형식

### index.json (경량)
```json
[
  {
    "fileId": "BattleManager",
    "layer": "Domain",
    "genre": "RPG",
    "role": "Manager",
    "system": "Battle",
    "score": 0.7,
    "provides": ["StartBattle", "EndBattle"],
    "requires": ["DataManager", "CharacterPlayer"]
  }
]
```

### 개별 파일 (상세)
```json
{
  "fileId": "BattleManager",
  "filePath": "Battle/BattleManager.cs",
  "layer": "Domain",
  "genre": "RPG",
  "role": "Manager",
  "system": "Battle",
  "score": 0.7,

  "classes": [{
    "className": "BattleManager",
    "baseClass": "Singleton<BattleManager>",
    "role": "Manager",

    "fields": [...],
    "properties": [...],
    "methods": [...],

    "contract": {
      "provides": [...],
      "requires": [...]
    },

    "dependencies": {
      "uses": [...],
      "usedBy": [...],
      "publishes": [...],
      "subscribes": [...]
    }
  }],

  "fullCode": "..."
}
```

---

## 검색 알고리즘

### 1단계: 인덱스 검색
```
1. 요청 장르의 Expert DB index.json 로드
2. score >= 0.6 AND 태그 일치 필터링
3. 없으면 Generic Expert DB 검색
4. 없으면 Base DB 검색
```

### 2단계: 상세 로드
```
1. 인덱스에서 fileId 추출
2. 해당 파일만 로드
3. contract.provides 확인
4. 참조 코드로 사용
```

### 3단계: 유사도 평가
```
1. Role 일치: +0.3
2. System 일치: +0.2
3. majorFunctions 일치: +0.2
4. provides 시그니처 유사: +0.3
```

### CLI 자동 검색 (권장)
DB 검색을 CLI로 자동화할 수 있습니다:
```bash
# 기본 검색 (pretty-print)
node E:/AI/scripts/db-search.js --genre Rpg --role Manager --system Battle

# 에이전트용 JSON 출력
node E:/AI/scripts/db-search.js --genre Rpg --role UX --provides "void PlayEffect" --json

# 상위 3개만
node E:/AI/scripts/db-search.js --genre Idle --role Manager --top 3
```

**옵션:**
- `--genre <genre>` - 장르 (필수): Rpg, Idle, Merge, SLG, Tycoon, Simulation, Puzzle, Generic
- `--role <role>` - Role 필터: Manager, Controller, UX, Handler 등
- `--system <system>` - System 필터: Battle, Inventory, Quest 등
- `--provides <sig>` - provides 시그니처 검색 (부분 일치)
- `--layer <layer>` - Layer 필터: Core, Domain, Game
- `--top <n>` - 상위 N개 결과 (기본: 5)
- `--json` - JSON 출력 (에이전트 파이프라인용)

---

## 파싱 규칙

### 필드 추출 (오인식 방지)
```
INCLUDE:
- 클래스 레벨 선언 (중괄호 깊이 = 1)
- [SerializeField] 필드
- public/private/protected 필드

EXCLUDE:
- 메서드 내부 지역 변수
- for/foreach 루프 변수
- using 블록 변수
- out/ref 파라미터
```

### uses 추출 (오인식 방지)
```
INCLUDE:
- 필드/변수 타입
- Singleton.Instance 접근
- new ClassName() 생성
- 상속 클래스

EXCLUDE:
- Unity 생명주기: Awake, Start, Update, OnEnable, OnDisable
- 공통 메서드: Init, Refresh, Set, Get, Add, Remove
- 프리미티브: int, float, string, bool, void
- Unity 기본: MonoBehaviour, GameObject, Transform
```

### Contract 추출
```
provides:
- public 메서드 시그니처
- public 프로퍼티 getter/setter
- public 이벤트

requires:
- *.Instance 접근 (Singleton)
- 생성자 주입 파라미터
- [Inject] 어트리뷰트
```

---

## 신뢰도 점수

### 점수 계산
| 이벤트 | 변동 |
|--------|------|
| 초기 저장 | 0.4 |
| 피드백 반영 | +0.2 |
| 재사용 성공 | +0.1 |
| 재사용 실패 | -0.15 |
| Generic 승격 | +0.1 |

### 승격 조건
```
Base DB → Expert DB: score >= 0.6
Genre → Generic: 다른 장르에서 재사용 성공 2회 이상
```

---

## Rules DB 형식

```json
{
  "ruleId": "null-check-collection",
  "type": "Generic",
  "genre": null,
  "category": "LOGIC.NULL_REF",
  "pattern": "list.First()",
  "solution": "list.FirstOrDefault() 사용",
  "frequency": 15
}
```
