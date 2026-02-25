# DB Rebuild v3.0 프로젝트 개발 히스토리

## 프로젝트 개요
- **프로젝트명**: DB_Rebuild_v3
- **유형**: DB 인프라 개선 (파서 업그레이드 + DB 재구축 + UI 메타데이터 신규)
- **작업 일자**: 2026-02-11

---

## 1. 작업 배경

기존 DB(2,989건)의 문제점:
1. **Tag 분류 없음** - CLAUDE.md에 정의된 대기능 7종 + 소기능 11종이 DB에 미반영
2. **Generic 장르 비어있음** - Singleton, ObjectPool 등 공통 코드가 각 장르 Core에 분산
3. **index.json에 Tag 필드 없음** - 코드 생성 시 Tag 기반 검색 불가
4. **UI 메타데이터 없음** - 프리팹/씬의 버튼 크기, 스크롤 설정 등 미추출
5. **장르 간 중복** - 동일 파일이 여러 장르에 분류 (88건)

---

## 2. 수정된 파일 목록

### 2.1 업그레이드
| 파일 | 변경 내용 | 줄 수 변화 |
|------|----------|-----------|
| `E:\AI\scripts\parser.js` | v2.0→v3.0: Tag 분류(Major 7+Minor 11), Generic 자동 분류, index 스키마 확장, 메서드별 Tag | 890→977줄 |
| `E:\AI\parsing\unity_prefab_parser.py` | 전면 개편: Button/ScrollRect/LayoutGroup/Text/Image/Canvas 상세 추출, 프로젝트별/집계 출력 | 273→1,201줄 |
| `E:\AI\scripts\analyze.js` | v3.0: Tag 통계(emptyTags, byMajorTag, byMinorTag) 추가 | 91→99줄 |
| `E:\AI\db\rules\ui_spec_reference.yaml` | 버튼/텍스트/스크롤/레이아웃 실측 데이터 반영, 스크롤/레이아웃 섹션 추가 | 626→660줄 |

### 2.2 신규 생성
| 경로 | 내용 |
|------|------|
| `E:\AI\db\ui_meta\FantaPuzzle\` | summary.json, buttons.json, scrolls.json, layouts.json, texts.json, canvas_settings.json, prefabs/ |
| `E:\AI\db\ui_meta\TamplePuzzle\` | 위와 동일 구조 |
| `E:\AI\db\ui_meta\Luffy\` | 위와 동일 구조 |
| `E:\AI\db\ui_meta\aggregated\` | button_standards.json, scroll_standards.json, text_standards.json, layout_standards.json |

### 2.3 재생성
| 경로 | 내용 |
|------|------|
| `E:\AI\db\base\**` | 전체 재파싱 (780 고유 파일, 9개 장르 x 3개 레이어) |

### 2.4 GitHub 클론 (신규 소스)
| 레포 | 경로 | 파일 수 |
|------|------|---------|
| Unity.SortPuzzleBase | `E:\AIMED\Unity.SortPuzzleBase\` | 15 .cs |
| Mobile_Sorting_Game | `E:\AIMED\Mobile_Sorting_Game\` | 3 .cs |

---

## 3. parser.js v3.0 변경 상세

### 3.1 Tag 분류 추가
- `MAJOR_TAG_PATTERNS`: 7종 (StateControl, ValueModification, ConditionCheck, ResourceTransfer, DataSync, FlowControl, ResponseTrigger)
- `MINOR_TAG_PATTERNS`: 11종 (Compare, Calculate, Find, Validate, Assign, Notify, Delay, Spawn, Despawn, Iterate, Aggregate)
- 메서드명 prefix로 패턴 매칭 → 클래스 레벨에서 빈도 상위 3개 집계
- 메서드별 `majorTag`, `minorTag` 필드 추가
- 파일별 `tags: { major: [], minor: [] }` 필드 추가 (index + detail 모두)

### 3.2 Generic 자동 분류
```
기존: genre = determineGenre() || defaultGenre
변경: Layer=Core && 장르 키워드 점수=0 → genre = 'Generic'
```
- 결과: Generic/Core에 34건 (Singleton, ObjectPool, EventBus, TableBase 등)

### 3.3 index.json 스키마 확장
기존 필드(fileId, layer, genre, role, system, score, provides, requires)에 `tags` 추가

---

## 4. unity_prefab_parser.py 변경 상세

### 4.1 추출 컴포넌트
| 컴포넌트 | ClassID | 추출 필드 |
|----------|---------|----------|
| RectTransform | 224 | m_SizeDelta, m_AnchoredPosition, m_AnchorMin/Max, m_Pivot |
| Canvas | 223 | m_RenderMode, m_SortingOrder |
| CanvasScaler | 226 | m_ReferenceResolution, m_MatchWidthOrHeight, m_UiScaleMode |
| Button | 114 | m_Colors (Normal/Highlighted/Pressed/Disabled), m_Navigation |
| ScrollRect | 114 | m_Horizontal/Vertical, m_Inertia, m_DecelerationRate |
| Image | 114 | m_Type, m_Color, m_Sprite |
| Text/TMP | 114 | m_FontSize, m_Alignment, m_Color |
| LayoutGroup | 114 | m_Spacing, m_Padding, m_CellSize, m_Constraint |
| ContentSizeFitter | 114 | m_HorizontalFit, m_VerticalFit |

### 4.2 출력 구조
```
E:\AI\db\ui_meta\
├── {project_name}\
│   ├── summary.json
│   ├── canvas_settings.json
│   ├── buttons.json
│   ├── scrolls.json
│   ├── layouts.json
│   ├── texts.json
│   └── prefabs\
│       └── {PrefabName}.json
└── aggregated\
    ├── button_standards.json   (min/max/avg/median/mode)
    ├── scroll_standards.json
    ├── text_standards.json
    └── layout_standards.json
```

### 4.3 CLI
```bash
python unity_prefab_parser.py <assets_path> <project_name> [genre]
python unity_prefab_parser.py --aggregate
```

---

## 5. 파싱 실행 기록

### 5.1 Code DB 파싱 결과
| 프로젝트 | 소스 경로 | 장르 | 총 파일 | 파싱 | 실패 | Generic |
|----------|----------|------|---------|------|------|---------|
| FantaPuzzle | E:\AIMED\FantaPuzzle\PuzzleAutomation2\Assets\2.Scripts | Puzzle | 164 | 164 | 0 | 20 |
| TamplePuzzle | E:\AIMED\TamplePuzzle\PuzzleAutomation\Assets\2.Scripts | Puzzle | 142 | 142 | 0 | 10 |
| Luffy | E:\AIMED\Luffy\IdleMoney1\Project\Assets\IdleMoney\Scripts | Idle | 575 | 575 | 0 | 13 |
| Unity.SortPuzzleBase | E:\AIMED\Unity.SortPuzzleBase\Assets\Scripts | Puzzle | 15 | 15 | 0 | 0 |
| Mobile_Sorting_Game | E:\AIMED\Mobile_Sorting_Game\Assets\Scripts | Puzzle | 3 | 3 | 0 | 0 |
| **합계** | | | **899** | **899** | **0** | **43** |

> DB 고유 파일: 780 (프로젝트 간 동일 fileId 파일은 덮어쓰기)

### 5.2 UI 메타데이터 추출 결과
| 프로젝트 | Prefab | Scene | Button | Scroll | Layout | Text | Image |
|----------|--------|-------|--------|--------|--------|------|-------|
| FantaPuzzle | 227 | 5 | 147 | 7 | 14 | 279 | 2,162 |
| TamplePuzzle | 189 | 7 | 126 | 7 | 15 | 231 | 2,119 |
| Luffy | 388 | 18 | 308 | 2 | 5 | 47 | 1,237 |

---

## 6. 집계된 실측 규격

### 버튼 (581개)
- Width: min=-1.1, max=10000, **avg=300.5, median=200, mode=150**
- Height: min=0, max=10000, **avg=197.7, median=119, mode=120**
- 분포: 소형(49.4%) > 대형(26.2%) > 중형(24.4%)

### 텍스트 (557개)
- FontSize: min=10, max=160, **avg=42.7, median=40, mode=40**
- 정렬: MiddleCenter(74.5%) > UpperLeft(11.5%)

### 스크롤 (16개)
- 방향: 세로 100%
- 관성: 100% 활성, decelerationRate=0.14 통일

### 레이아웃 (34개)
- 유형: Vertical/Horizontal(76.5%) > Grid(23.5%)
- Spacing mode=0, ChildAlignment: UpperLeft(52.9%)

---

## 7. 삭제 항목
| 항목 | 사유 |
|------|------|
| `E:\AI\db\base_backup_20260211` | 재파싱 완료 후 사용자 요청으로 삭제 |
