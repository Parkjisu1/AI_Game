---
description: C# 소스코드를 파싱하여 DB에 저장
arguments:
  - name: path
    description: 파싱할 폴더 경로
    required: true
  - name: genre
    description: "장르 (generic/rpg/idle/merge/slg/tycoon/simulation)"
    required: false
    default: "auto"
---

# Source Code Parsing

$path 폴더의 C# 파일들을 파싱하여 E:\AI\db\base\에 저장합니다.

## 실행 단계

### 1. 파일 스캔
- $path 폴더의 모든 *.cs 파일 목록 수집
- 제외: Editor/, Test/, Plugins/ 폴더

### 2. 각 파일 파싱
```
파일별로:
1. AST 생성 (클래스, 필드, 메서드, 프로퍼티 추출)
2. Layer 분류 (Core/Domain/Game)
3. Genre 분류 ($genre 또는 키워드 기반 자동)
4. Role 분류 (클래스명 패턴 기반)
5. Tag 분류 (메서드명 패턴 기반)
6. 의존성 추출 (uses, usedBy, publishes, subscribes)
7. Contract 추출 (provides, requires)
```

### 3. 오인식 방지 규칙
**필드 추출 시:**
- 클래스 레벨 선언만 (중괄호 깊이 = 1)
- 메서드 내부 지역 변수 제외

**uses 추출 시:**
- Unity 생명주기 메서드 제외 (Awake, Start, Update 등)
- 공통 메서드명 제외 (Init, Get, Set 등)

### 4. DB 저장
```
E:\AI\db\base\{genre}\{layer}\
├── index.json (경량 인덱스 업데이트)
└── files\
    └── {fileId}.json (상세 정보)
```

### 5. 인덱스 형식
```json
{
  "fileId": "클래스명",
  "layer": "Core|Domain|Game",
  "genre": "장르",
  "role": "21종 Role",
  "system": "시스템 분류",
  "score": 0.4,
  "provides": ["public API 목록"],
  "requires": ["의존성 목록"]
}
```

## 출력
- 파싱된 파일 수
- 장르별 분류 통계
- 오류 발생 파일 목록 (있는 경우)
