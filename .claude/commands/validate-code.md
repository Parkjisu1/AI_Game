---
description: 생성된 코드 검증 및 피드백 처리
arguments:
  - name: path
    description: "검증할 코드 파일 또는 폴더 경로"
    required: true
  - name: project
    description: "프로젝트 이름"
    required: true
---

# Code Validation

$path의 코드를 검증하고 피드백을 처리합니다.

## 검증 단계

### 1. Syntax 검증
```
체크 항목:
- 모든 using 문 존재
- 타입 선언 정확
- 괄호 짝 맞음
- 세미콜론 누락 없음
```

### 2. Dependency 검증
```
체크 항목:
- 참조 클래스가 이전 Phase에 존재
- 순환 참조 없음
- 네임스페이스 정확
```

### 3. Contract 검증
```
체크 항목:
- provides 메서드 시그니처 일치
- requires 의존성 충족
- public API 구현 완료
```

### 4. NullSafety 검증
```
체크 항목:
- 컬렉션 접근 전 null/Count 체크
- First() 대신 FirstOrDefault()
- ?. 연산자 사용
- null 반환 가능 메서드 체크
```

### 5. Pattern 검증
```
체크 항목:
- Role에 맞는 패턴 사용
- 금지 패턴 미사용
- Unity 최적화 규칙 준수
```

## 피드백 형식

### 피드백 파일 생성
```
E:\AI\projects\$project\feedback\
└── {nodeId}_feedback.json
```

### 피드백 JSON 구조
```json
{
  "nodeId": "BattleManager",
  "genre": "RPG",
  "role": "Manager",
  "feedbacks": [
    {
      "category": "LOGIC.NULL_REF",
      "line": 85,
      "description": "pieces 배열 null 체크 누락",
      "severity": "error",
      "suggestion": "if (pieces != null && pieces.Count > 0)"
    }
  ],
  "contractChanged": false,
  "timestamp": "2024-02-02T12:00:00Z"
}
```

### 피드백 카테고리
| 카테고리 | 하위 분류 |
|----------|-----------|
| PERF | GC_ALLOC, LOOP_OPT, CACHE, ASYNC |
| LOGIC | NULL_REF, OFF_BY_ONE, RACE_COND, WRONG_CALC |
| PATTERN | API_MISMATCH, NAMING, STRUCTURE, DI |
| READABLE | COMMENT, FORMATTING, COMPLEXITY |
| SECURITY | INPUT_VALID, DATA_LEAK, INJECTION |
| CONTRACT | SIGNATURE_MISMATCH, MISSING_METHOD |
| ROLE | WRONG_ROLE, ROLE_VIOLATION |

## 자동 수정

### severity: warning
```
자동 수정 시도:
1. 패턴 적용
2. 코드 재생성
3. 재검증
```

### severity: error
```
피드백 파일 생성 후 대기:
1. 사용자 확인 요청
2. 수정 지시 대기
3. 지시에 따라 재생성
```

## 점수 업데이트

### 검증 통과 시
```
score += 0.2 (피드백 반영 완료)
→ score >= 0.6이면 Expert DB 승격
```

### 검증 실패 시
```
피드백 파일 생성
재생성 대기
```

## Rules 추출

반복되는 피드백 패턴 저장:
```
E:\AI\db\rules\
├── generic_rules.json
└── genre_rules.json
```

```json
{
  "ruleId": "null-check-collection",
  "type": "Generic",
  "category": "LOGIC.NULL_REF",
  "pattern": "list.First()",
  "solution": "list.FirstOrDefault()",
  "frequency": 15
}
```
