---
description: 기획 문서를 파싱하여 Design DB에 저장
arguments:
  - name: path
    description: 파싱할 폴더/파일 경로
    required: true
  - name: genre
    description: "장르 (generic/rpg/idle/merge/slg/tycoon/simulation/puzzle/casual)"
    required: false
    default: "auto"
---

# Design Document Parsing

$path 의 기획 문서를 파싱하여 E:\AI\db\design\base\에 저장합니다.

## 실행 단계

### 1. 파일 스캔
- $path 폴더의 모든 기획 문서 수집
- 지원 형식: *.yaml, *.yml, *.md, *.json
- 제외: temp/, draft/, .backup/ 폴더

### 2. 포맷 감지
파일 유형에 따라 파서 선택:
```
*.yaml / *.yml → YAML 파서
*.md           → Markdown 파서 (섹션 추출)
*.json         → JSON 파서
C10+_spec*     → C10+ spec 파서 (c10-to-design-db.js)
```

### 3. 데이터 정규화

각 기획 요소에서 추출:
```
domain:       InGame | OutGame | Balance | Content | BM | UX | Social | Meta | LiveOps
system:       시스템명
data_type:    constant | formula | range | flag | unknown
balance_area: combat | progression | economy | gacha | equipment | content | ux
provides:     핵심 수치/공식 목록
tags:         formula, rate, cost, count, unlock, verified, estimated
```

### 4. 장르 분류
- $genre 가 'auto'이면 파일 내용 키워드 기반 자동 감지
- 감지 우선순위: 파일 내 genre 필드 → 파일명 키워드 → 기본값(generic)

### 5. DB 저장
```
E:\AI\db\design\base\{genre}\{domain}\
├── index.json          (경량 인덱스 업데이트)
└── files\
    └── {designId}.json (상세 정보)
```

### Design DB Index Entry 형식
```json
{
  "designId": "project__domain__system__name",
  "domain": "InGame",
  "genre": "RPG",
  "system": "BattleSystem",
  "score": 0.4,
  "source": "observed",
  "data_type": "formula",
  "balance_area": "combat",
  "version": "1.0.0",
  "project": "MyGame",
  "provides": [],
  "requires": [],
  "tags": []
}
```

### C10+ 파라미터 신뢰도 → 정확도 변환
| confidence | accuracy_estimate |
|------------|-------------------|
| confirmed  | 0.95 |
| high       | 0.85 |
| medium     | 0.70 |
| low        | 0.40 |
| null       | 0.0  |

## 출력
- 파싱된 파일 수
- 도메인별 분류 통계
- 저장된 엔트리 수
- 오류 발생 파일 목록 (있는 경우)

## 참고 스크립트
- C10+ spec: `node E:/AI/scripts/c10-to-design-db.js --game <name> --genre <genre>`
- 일반 기획서: `node E:/AI/scripts/design-parser.js --path $path --genre $genre`
