---
description: AI_기획서를 기반으로 C# 코드 생성
arguments:
  - name: yaml
    description: "AI_기획서 YAML 파일 경로 또는 nodeId"
    required: true
  - name: project
    description: "프로젝트 이름"
    required: true
  - name: phase
    description: "생성할 Phase (all 또는 숫자)"
    required: false
    default: "all"
---

# Code Generation

$yaml 기획서를 기반으로 코드를 생성합니다.

## 실행 단계

### 1. AI_기획서 로드
```
경로: E:\AI\projects\$project\designs\nodes\$yaml.yaml
또는: 직접 파일 경로
```

### 2. DB 검색 (우선순위 준수)
```
순위 1: Expert DB (해당 장르) - score >= 0.6
순위 2: Expert DB (Generic) - score >= 0.6
순위 3: Genre Base DB
순위 4: Generic Base DB
순위 5: AI_기획서 logicFlow 기반 생성
```

### 3. 참조 코드 선정
```yaml
referencePatterns에서:
  - source: "Expert:BattleManager_Tower"
  - pattern: "웨이브 기반 전투"

DB 검색 결과에서:
  - Role 일치 (+0.3)
  - System 일치 (+0.2)
  - majorFunctions 일치 (+0.2)
  - provides 유사도 (+0.3)
```

### 4. 코드 생성
```csharp
// 템플릿 적용
// - Layer에 따른 기본 구조
// - Role에 따른 패턴
// - contract.provides 구현
// - contract.requires 주입

namespace {project}.{system}
{
    public class {nodeId} : {baseClass}
    {
        // fields from states

        // methods from logicFlow

        // contract.provides implementation
    }
}
```

### 5. 자가 검증
| 단계 | 검증 항목 | 실패 시 |
|------|-----------|---------|
| 1 | Syntax (문법, using, 타입) | 자동 수정 |
| 2 | Dependency (참조 클래스 존재) | 자동 수정 |
| 3 | Contract (시그니처 일치) | 자동 수정 |
| 4 | NullSafety (null 체크) | 자동 수정 |
| 5 | Logic (비즈니스 로직) | 피드백 요청 |

### 6. 저장
```
E:\AI\projects\$project\generated\
├── {phase}\
│   └── {nodeId}.cs
└── build_log.json
```

## 출력 형식
```csharp
using System;
using System.Collections.Generic;
using UnityEngine;
using UniRx;
// ... 필요한 using

namespace {Project}.{System}
{
    /// <summary>
    /// {purpose}
    /// </summary>
    /// <remarks>
    /// Layer: {layer}
    /// Genre: {genre}
    /// Role: {role}
    /// Phase: {phase}
    /// </remarks>
    public class {NodeId} : {BaseClass}
    {
        #region Fields
        // ...
        #endregion

        #region Properties
        // contract.provides 프로퍼티
        #endregion

        #region Public Methods
        // contract.provides 메서드
        #endregion

        #region Private Methods
        // logicFlow 구현
        #endregion
    }
}
```

## 병렬 생성 (Worktree)
```bash
# 동일 Phase의 독립 노드들은 병렬 생성 가능
# 각 Worktree에서 별도 Claude 세션 실행
git worktree add ../gen-battle feature/battle
git worktree add ../gen-inventory feature/inventory
```
