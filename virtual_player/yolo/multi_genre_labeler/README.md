# Multi-Genre Label Editor

AI Tester YOLO 학습용 이미지 라벨링 도구. 기존 `virtual_player/yolo/pixelflow/label_editor.py`와 **동일한 GUI/단축키/저장 형식**이며, 시작 시 장르(puzzle / slg / idle)를 선택하면 해당 `classes.txt`가 로드됩니다.

**라벨링 방식 (기존과 동일)**: 이미지에서 **마우스 드래그로 영역 지정 → 우측에서 클래스 선택**. Pascal VOC XML로 저장 (labelImg 호환). 메뉴에서 YOLO `.txt` 형식 일괄 변환 가능.

---

## 빠른 실행

```cmd
dist\LabelEditor.exe
```

시작 다이얼로그에서:
1. **장르 선택** — puzzle (12 cls) / slg (180 cls) / idle (53 cls) / Custom classes.txt
2. **이미지 폴더** — `*.png / *.jpg / *.bmp` 가 들어있는 폴더
3. **라벨 저장 폴더** — XML 출력 폴더 (없으면 자동 생성)

이후 GUI는 기존 `label_editor.py`와 동일.

CLI로 다이얼로그 건너뛰기:

```cmd
LabelEditor.exe --genre slg --dir "D:\screenshots\rok" --labels "D:\screenshots\rok_labels"
LabelEditor.exe --classes my_classes.txt --dir ... --labels ...
```

---

## 사용법 (기존 label_editor.py 그대로)

### 모드
| 키 | 모드 | 동작 |
|:---:|------|------|
| **S** | Select | 클릭 = 단일 선택, 드래그 = 영역 선택, 핸들 드래그 = 크기조정/이동 |
| **W** | Draw | 드래그 = 현재 선택된 클래스로 새 bbox 생성 |
| **R** | Reclassify | 드래그 영역의 bbox 모두 현재 클래스로 변경 |
| **E** | Erase | 드래그 영역의 bbox 모두 삭제 |

**우클릭 드래그 = 모드 무관 즉시 삭제**

### 단축키
| 단축키 | 동작 |
|--------|------|
| D / A | 다음 / 이전 이미지 |
| Ctrl+S | 저장 |
| Ctrl+Z / Ctrl+Y | Undo / Redo |
| Delete / Backspace | 선택 bbox 삭제 |
| Ctrl+A | 전체 선택 |
| Ctrl+Shift+A | 같은 클래스 일괄 선택 |
| Ctrl+D | 복제 |
| F | 창에 맞춤 |
| Ctrl+1 | 100% |
| Ctrl++/Ctrl+- | 줌 인/아웃 |
| Ctrl+Shift+X | 휴지통으로 이동 |
| Esc | 선택 해제 |

### 저장 형식
Pascal VOC XML (labelImg / 기존 PixelFlow 도구 100% 호환):

```xml
<annotation>
  <filename>screenshot_001.png</filename>
  <size><width>1080</width><height>1920</height><depth>3</depth></size>
  <object>
    <name>building_hq</name>
    <bndbox><xmin>312</xmin><ymin>880</ymin><xmax>520</xmax><ymax>1080</ymax></bndbox>
  </object>
</annotation>
```

### YOLO 변환
**File → Export to YOLO labels...** → 출력 폴더 선택. 모든 XML이 YOLO normalized `.txt`로 변환되며 `classes.txt` 도 함께 출력.

---

## 번들된 classes.txt

| 장르 | 파일 | 클래스 수 | 내용 |
|------|------|----------:|------|
| **puzzle** | `classes/puzzle.txt` | 12 | 기존 PixelFlow `classes.txt` 그대로 (block_purple ~ gimmick) |
| **slg** | `classes/slg.txt` | **180** | 월드맵·도시뷰·건물·유닛·영웅·동맹·전투·이벤트·BM·튜토리얼·HUD·OCR·광고 |
| **idle** | `classes/idle.txt` | 53 | 생산라인·업그레이드·매니저·보상·프리스티지·메타+공통 UI |

수정/확장은 텍스트 에디터로 `classes/{genre}.txt` 직접 편집 후 재빌드, 또는 GUI 내 **+ New Class** 버튼 (실행 중 `classes.txt`에 영구 저장).

### SLG classes.txt 주요 카테고리

이름 접두사로 그룹 식별:
- `btn_*` — UI 컨트롤 (play/back/close_x/settings 등)
- `hud_*` — 상단 자원·전투력·왕국명·실드 타이머 등
- `ocr_*` — 좌표/전투력/병력수/행군시간 등 텍스트 인식 영역
- `ad_*` `popup_*` — 광고·결제 팝업
- `map_*` `minimap*` `coord_*` `teleport_*` — 월드맵 좌표 / 지형
- `city_*` `building_*` — 도시뷰 / 건물 22종
- `troop_*` — 병력 9종
- `hero_*` — 영웅·사령관 카드·스킬·탤런트 13종
- `marker_*` — 맵 마커 (적/동맹/랠리/실드/공격받는중 등) 13종
- `resource_*` — 자원 노드 + 보상 박스
- `alliance_*` — 동맹 패널·채팅·도움 요청·랠리 10종
- `combat_*` — 전투 리포트·결과화면·행군 타이머 9종
- `event_*` — 시즌 패스·KvK·달력 8종
- `bm_*` — 결제 패키지·VIP 10종
- `tutorial_*` — 튜토리얼 화살표·NPC·하이라이트 6종

---

## 소스에서 실행

```cmd
cd E:\AI\virtual_player\yolo\multi_genre_labeler
C:\Users\user\AppData\Local\Programs\Python\Python313\python.exe label_editor.py
```

의존성:
```
PySide6 >= 6.5
Pillow >= 10.0
```

---

## 빌드

```cmd
cd E:\AI\virtual_player\yolo\multi_genre_labeler
build\build_exe.bat
```

스펙: `build/label_tool.spec`. `classes/` 폴더가 데이터로 번들되어 exe 실행 시 `sys._MEIPASS/classes`로 추출됩니다.

---

## 디렉토리 구조

```
multi_genre_labeler/
├── README.md
├── label_editor.py              # 메인 에디터 (단일 파일, ~1500줄)
├── requirements.txt
├── classes/
│   ├── puzzle.txt               # 12 cls (기존 PixelFlow 그대로)
│   ├── slg.txt                  # 180 cls
│   └── idle.txt                 # 53 cls
├── build/
│   ├── label_tool.spec          # PyInstaller spec
│   └── build_exe.bat            # 빌드 스크립트
└── dist/
    └── LabelEditor.exe          # 빌드 결과 (~52 MB)
```

---

## 기존 도구와의 차이점

기존 `virtual_player/yolo/pixelflow/label_editor.py`에서 제거된 것:
- **Auto-Detect Cells** — PixelFlow cell_profile.json 기반 자동 셀 탐지 (puzzle 전용)
- **YOLO Predict** — 학습된 puzzle YOLO 모델로 자동 예측
- **Board Region** — 자동탐지용 보드 영역 지정 모드
- `_paths.py` / `auto_label_v2.py` / `cell_aware_analyzer.py` 의존성

유지된 것 (사실상 100%):
- 4모드 (Select / Draw / Reclassify / Erase) + 우클릭 즉시삭제
- 모든 단축키
- Pascal VOC XML 저장 형식
- Undo/Redo (50 step)
- 클래스 색상 (puzzle 12종은 원본과 동일 RGB, 그 외는 이름 해시로 자동 생성)
- + New Class 런타임 추가
- 통계 / 선택 정보 패널
- 이미지 휴지통 이동

기존 puzzle XML 라벨과 100% 호환 — 같은 도구로 열어서 계속 작업 가능.
