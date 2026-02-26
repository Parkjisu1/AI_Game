---
description: 기획 문서를 파싱하여 Design DB에 저장 (설계 분석 + 디렉터 큐레이션 포함)
arguments:
  - name: path
    description: 파싱할 폴더/파일 경로
    required: true
  - name: genre
    description: "장르 (generic/rpg/idle/merge/slg/tycoon/simulation/puzzle/casual)"
    required: false
    default: "auto"
  - name: auto
    description: "store 권장 항목 자동 저장 (대량 투입 시 사용, 큐레이션 생략)"
    required: false
    default: "false"
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

### 5. 설계 의도 분석 + 품질 평가
각 파싱된 기획 요소에 대해 AI가 자동 분석:
```yaml
design_analysis:
  design_intent: "이 설계의 의도 (왜 이렇게 설계했는가)"
  context: "맥락, 제약조건, 전제 조건"
  strengths: ["강점 목록"]
  concerns: ["약점/리스크 목록"]
  db_recommendation: "store | store_with_caveat | skip | needs_context"
  reasoning: "판단 근거"
```

### 6. 큐레이션 리포트 생성
디렉터에게 제출할 요약 리포트:
```
총 파싱: N건
├── store 권장: X건 (바로 저장 가능)
├── store_with_caveat: Y건 (약점 확인 필요)
├── skip 권장: Z건 (투입 부적합)
└── needs_context: W건 (맥락 보충 필요)

[상세] 항목별 design_intent + concerns + recommendation
```

- 기본 동작: 리포트 생성 후 디렉터 확인 대기
- `$auto` = true 시: store 권장 항목 자동 저장 (store_with_caveat, skip, needs_context는 리포트만 생성)

### 7. DB 저장 (큐레이션 승인분만)
```
E:\AI\db\design\base\{genre}\{domain}\
├── index.json          (경량 인덱스 업데이트)
└── files\
    └── {designId}.json (상세 정보 + design_analysis 포함)
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
