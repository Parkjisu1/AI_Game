# 퍼즐 레벨 데이터 JSON 포맷

> **출처**: 퍼즐 기획자 제공 (2026-03)
> **용도**: Stage 0 데이터 스키마 정의, Code Workflow 1단계 기획↔코드 매핑

## JSON 구조

```json
{
    "author": "string",
    "index": "int (레벨 번호와 동일)",
    "bubbles": [
        {
            "x": "int (x좌표, 0=좌상단)",
            "y": "int (y좌표, 0=좌상단)",
            "c": "int (버블 컬러 enum)",
            "t": "int (버블 타입 enum)"
        }
    ],
    "covers": [
        {
            "x": "int",
            "y": "int",
            "c": "int (항상 0)",
            "t": "int (41=Fairy만 사용)"
        }
    ],
    "boardCondition": {
        "color": "[int] (사용 색상 배열, 길이=색상 수)",
        "startColor": "[int] (초기 슈터 색상)",
        "starScore": "[int, int, int] (별 1/2/3개 점수 기준)",
        "moveCount": "int (제공 무브 수)"
    },
    "d": "int",
    "isHardLevel": "bool (하드 레벨 여부)",
    "levelNumber": "int (레벨 번호, index와 동일)",
    "sparkSpawnRate": "float",
    "maxSparkRateFromNormal": "float"
}
```

## 좌표 체계
- (0, 0) = 좌상단
- width: y % 2 == 0 → 11칸 / y % 2 == 1 → 10칸 (허니컴 그리드)
- 비어있는 칸은 데이터에 포함하지 않음 (None 채우기 없음)

## 버블 타입 (t) Enum

### 게임용 (0~73)
| 값 | 이름 | 값 | 이름 |
|----|------|----|------|
| -1 | None | 0 | Normal |
| 1 | Metal | 2 | Ice |
| 3 | Spike | 4 | Morph |
| 5 | Lightning | 7 | Fire |
| 8 | Rainbow | 9 | Cloud |
| 10 | Wood | 11 | Duo |
| 12 | Beam | 13 | Chain |
| 14 | Minibomb | 20 | GhostEnable |
| 21 | GhostDisable | 22 | Magic |
| 30 | SpikeEnable | 31 | SpikeDisable |
| 32 | Waterballoon | 41 | Fairy |
| 50 | Event | 60 | Plus |
| 61 | Minus | 62 | Paint |
| 70 | ArrowLeft | 71 | ArrowLeftUp |
| 72 | ArrowRightUp | 73 | ArrowRight |

### 에디터 전용 (1000+)
| 값 | 이름 |
|----|------|
| 1000 | Baby |
| 1100 | Wolf |
| 1101 | WolfNeighbor |
| 1200 | Carrot |

## 버블 컬러 (c) Enum
| 값 | 컬러 | 값 | 컬러 |
|----|------|----|------|
| 0 | Red | 1 | Green |
| 2 | Blue | 3 | Orange |
| 4 | Pink | 5 | Sky |
| 6 | Yellow | 7 | Purple |
| 8 | Count | 99 | RandomColor |

### 듀오 컬러 규칙
- 작은 값이 뒤로 감
- 예: Red(0) + Green(1) = 10
- 예: Purple(7) + Sky(5) = 75

## covers 규칙
- bubbles와 동일한 구조
- t=41 (Fairy)만 사용
- c=0 (고정)

## 기획 파라미터 ↔ 코드 필드 매핑
| 기획 (level_meta) | 코드 (JSON) | 변환 |
|-------------------|-------------|------|
| num_colors | boardCondition.color.length | 배열 길이 |
| moves_limit | boardCondition.moveCount | 직접 대응 |
| hard_tier | isHardLevel | bool→int (false=0, true=1) |
| level_number | index (또는 levelNumber) | 직접 대응 |
| special_mechanics | bubbles[].t 고유값 집합 | 사용된 타입 추출 |
