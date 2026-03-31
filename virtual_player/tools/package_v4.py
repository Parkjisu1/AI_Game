"""
LevelDesignExtractor v4 ZIP 패키징 스크립트
"""
import shutil
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
DIST_DIR = TOOLS_DIR / "dist"
SAMPLE_DIR = TOOLS_DIR / "dist" / "LevelDesignExtractor_v2.0" / "LevelDesignExtractor_v2.0" / "LevelDesignExtractor"

OUTPUT_NAME = "LevelDesignExtractor_v4.0"
PACK_DIR = DIST_DIR / OUTPUT_NAME / OUTPUT_NAME

def main():
    print("=== LevelDesignExtractor v4 패키징 ===\n")

    # 정리
    final_dir = DIST_DIR / OUTPUT_NAME
    if final_dir.exists():
        shutil.rmtree(final_dir)
    PACK_DIR.mkdir(parents=True)

    # 1) exe 복사
    cli_exe = DIST_DIR / "LevelDesignExtractor_CLI.exe"
    gui_exe = DIST_DIR / "LevelDesignExtractor.exe"

    if cli_exe.exists():
        shutil.copy2(cli_exe, PACK_DIR / "LevelDesignExtractor_CLI.exe")
        print(f"  [OK] CLI exe: {cli_exe.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print(f"  [SKIP] CLI exe 없음 — 소스만 포함")

    if gui_exe.exists():
        shutil.copy2(gui_exe, PACK_DIR / "LevelDesignExtractor_GUI.exe")
        print(f"  [OK] GUI exe: {gui_exe.stat().st_size / 1024 / 1024:.1f} MB")

    # 2) Python 소스
    src_dir = PACK_DIR / "src"
    src_dir.mkdir()
    for f in ["level_design_extractor_tmux.py",
              "level_design_extractor.py",
              "level_design_extractor_gui.py",
              "build_level_extractor.py",
              "game_profiles.json"]:
        src = TOOLS_DIR / f
        if src.exists():
            shutil.copy2(src, src_dir / f)
            print(f"  [OK] src/{f}")

    # 3) 모델
    models_dir = PACK_DIR / "models"
    models_dir.mkdir()
    model_src = SAMPLE_DIR / "models" / "best.pt"
    if model_src.exists():
        shutil.copy2(model_src, models_dir / "best.pt")
        print(f"  [OK] models/best.pt ({model_src.stat().st_size / 1024 / 1024:.1f} MB)")

    # 4) 샘플 데이터
    sample_src = SAMPLE_DIR / "sample_data"
    if sample_src.exists():
        shutil.copytree(sample_src, PACK_DIR / "sample_data")
        print(f"  [OK] sample_data/")

    # 5) game_profiles.json (루트에도)
    gp = TOOLS_DIR / "game_profiles.json"
    if gp.exists():
        shutil.copy2(gp, PACK_DIR / "game_profiles.json")

    # 6) README
    readme = PACK_DIR / "README.txt"
    readme.write_text(r"""============================================================
  Level Design Extractor v4.0
  게임 녹화 프레임에서 스테이지 시작 보드를 자동 추출
============================================================

■ 실행 방법

  A. CLI (Tmux 모드) — 권장
    LevelDesignExtractor_CLI.exe ^
      --frames-dir <프레임폴더> ^
      --model models\best.pt ^
      --output-dir output ^
      --recording <recording.json> ^
      --game balloonflow ^
      --crop-board --ocr --html-report ^
      --preset recall

  B. GUI
    LevelDesignExtractor_GUI.exe 실행

  C. Python 소스
    python src\level_design_extractor_tmux.py --help

■ 프리셋
  --preset default    균형
  --preset recall     누락 최소화 (권장)
  --preset precision  정확도 우선

■ 주요 기능 (21개)
  감지: 멀티프레임 투표, OCR, 이벤트 로그 교차검증, 시작버튼 좌표 인식
  크롭: 게임별 프로필, FFT 그리드 감지, fallback 크롭
  출력: FieldMap JSON, 그리드 크기 판별, HTML 리포트, diff 리포트
  QA:   연번 누락, 보드 유효성, 플레이중 오탐, 인터랙티브 확인
  인프라: watch 모드, resume 캐시, 병렬 분류

■ 추가 옵션
  --watch             폴더 감시 (실시간 추출)
  --resume            이전 분류 캐시 재사용
  --parallel          병렬 분류 (대량 프레임)
  --diff-dir <폴더>   이전 결과와 비교
  --interactive-qa    QA 이슈 수동 확인

■ 출력 구조
  output\
  ├── level_001.png           스테이지 전체 스크린샷
  ├── boards\level_001.png    보드만 크롭
  ├── json\level_001.json     FieldMap JSON
  ├── index.json              메타데이터 + QA 이슈
  ├── report.html             브라우저 미리보기 리포트
  └── frame_classifications.json

■ 빠른 테스트
  LevelDesignExtractor_CLI.exe ^
    --frames-dir sample_data\frames ^
    --model models\best.pt ^
    --output-dir output ^
    --recording sample_data\recording.json ^
    --crop-board --preset recall --html-report
""", encoding="utf-8")
    print(f"  [OK] README.txt")

    # 7) ZIP
    zip_path = DIST_DIR / OUTPUT_NAME
    shutil.make_archive(str(zip_path), "zip", str(DIST_DIR / OUTPUT_NAME))
    final_zip = Path(str(zip_path) + ".zip")
    print(f"\n  ZIP: {final_zip}")
    print(f"  크기: {final_zip.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"\n=== 완료 ===")


if __name__ == "__main__":
    main()
