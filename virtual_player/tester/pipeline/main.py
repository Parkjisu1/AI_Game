"""
AI Game Tester v3 — 통합 실행 프로그램
=======================================
Black-box APK 기반 자율 게임 테스트 시스템.

사용법:
  # 1. 인간 플레이 데이터 적재
  python -m tester.pipeline.main ingest \\
    --data-dir <디바이스데이터폴더> --game balloonflow

  # 2. 여러 디바이스 일괄 동기화
  python -m tester.pipeline.main sync \\
    --devices <폴더1> <폴더2> ... --game balloonflow

  # 3. 패턴 추출
  python -m tester.pipeline.main learn --game balloonflow

  # 4. AI 자율 플레이
  python -m tester.pipeline.main play \\
    --game balloonflow --model <YOLO.pt> --levels 10

  # 5. DB 통계 확인
  python -m tester.pipeline.main stats --game balloonflow

  # 6. 저장소 정리
  python -m tester.pipeline.main cleanup --hot-days 7 --warm-days 90
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tester.db.play_db import PlayDB
from tester.db.sync_manager import SyncManager
from tester.pipeline.ai_player import AIPlayer


DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "play_data.db"


def cmd_ingest(args):
    """인간 플레이 데이터 적재."""
    print(f"\n{'='*50}")
    print(f"  데이터 적재: {args.data_dir}")
    print(f"  게임: {args.game}")
    print(f"{'='*50}\n")

    db = PlayDB(args.db or DEFAULT_DB)
    data_dir = Path(args.data_dir)

    # session_log.jsonl 또는 recording.json 찾기
    files = list(data_dir.rglob("session_log.jsonl")) + list(data_dir.rglob("recording.json"))

    if not files:
        print("  [ERROR] 데이터 파일 없음")
        return

    total = {"sessions": 0, "turns": 0, "actions": 0}

    for i, f in enumerate(files):
        print(f"  [{i+1}/{len(files)}] {f.name} ({f.parent.name}/)")

        # recording.json → 변환 필요
        if f.name == "recording.json":
            sm = SyncManager.__new__(SyncManager)
            converted = sm._convert_recording_json(f)
            if converted:
                f = converted
            else:
                print(f"    [SKIP] 변환 실패")
                continue

        r = db.ingest_session_log(f, args.game, args.device or "default", f.parent)
        total["sessions"] += r["sessions"]
        total["turns"] += r["turns"]
        total["actions"] += r["actions"]
        print(f"    세션={r['sessions']} 턴={r['turns']}")

    print(f"\n  완료: 세션={total['sessions']} 턴={total['turns']}")
    print(f"  DB: {args.db or DEFAULT_DB}")
    db.close()


def cmd_sync(args):
    """여러 디바이스 일괄 동기화."""
    print(f"\n{'='*50}")
    print(f"  디바이스 동기화 ({len(args.devices)}개)")
    print(f"{'='*50}\n")

    sm = SyncManager(args.db or DEFAULT_DB)

    def progress(cur, tot, msg):
        print(f"  [{cur}/{tot}] {msg}")

    r = sm.sync_from_multiple_devices(
        args.devices, args.game, mode=args.mode, progress_cb=progress)

    print(f"\n  결과:")
    print(f"    디바이스: {r['devices']}개")
    print(f"    세션: {r['sessions']}개")
    print(f"    패턴: {r['patterns']}개")
    if r["errors"]:
        print(f"    오류: {len(r['errors'])}건")
        for e in r["errors"]:
            print(f"      {e}")

    sm.central_db.close()


def cmd_learn(args):
    """DB에서 행동 패턴 추출."""
    print(f"\n{'='*50}")
    print(f"  패턴 학습: {args.game}")
    print(f"{'='*50}\n")

    db = PlayDB(args.db or DEFAULT_DB)
    r = db.extract_patterns(args.game, min_occurrences=args.min_occur)

    print(f"  신규 패턴: {r['inserted']}")
    print(f"  갱신 패턴: {r['updated']}")
    print(f"  총 그룹: {r['total_groups']}")

    if args.cleanup:
        cleaned = db.cleanup_low_patterns()
        print(f"  정리된 저성과 패턴: {cleaned}")

    stats = db.get_stats(args.game)
    print(f"\n  DB 현황: 세션={stats['sessions']} 턴={stats['turns']} 패턴={stats['patterns']}")
    db.close()


def cmd_play(args):
    """AI 자율 플레이."""
    print(f"\n{'='*50}")
    print(f"  AI 자율 플레이")
    print(f"  게임: {args.game}")
    print(f"  레벨 수: {args.levels}")
    print(f"{'='*50}\n")

    player = AIPlayer(
        db_path=args.db or DEFAULT_DB,
        game_id=args.game,
        yolo_model_path=args.model,
        adb_path=args.adb,
        adb_device=args.device,
        temp_dir=args.temp_dir,
    )

    if not player.adb.is_connected():
        print("  [ERROR] ADB 디바이스 연결 안 됨")
        print(f"  ADB: {player.adb.adb_path}")
        print(f"  Device: {player.adb.device or 'auto'}")
        return

    print(f"  ADB 연결됨: {player.adb.screen_size}")
    print(f"  YOLO: {'로드됨' if player.yolo_model else '없음'}")

    db_stats = player.db.get_stats(args.game)
    print(f"  DB 패턴: {db_stats['patterns']}개\n")

    results = []
    for level_num in range(1, args.levels + 1):
        print(f"  --- 레벨 {level_num}/{args.levels} ---")
        r = player.play_level(max_turns=args.max_turns, timeout_sec=args.timeout)
        results.append(r)

        outcome = r.get("outcome", "?")
        turns = r.get("turns", 0)
        icons = {"clear": "O", "fail": "X", "stuck": "!", "timeout": "T", "crash": "C"}
        icon = icons.get(outcome, "?")

        print(f"    [{icon}] {outcome} (턴={turns})")

        stats = player.get_stats()
        print(f"    패턴 적중률: {stats['pattern_hit_rate']}%\n")

        # 레벨 간 대기
        time.sleep(1)

    # 결과 요약
    clears = sum(1 for r in results if r.get("outcome") == "clear")
    fails = sum(1 for r in results if r.get("outcome") == "fail")
    print(f"\n{'='*50}")
    print(f"  결과: {clears}승 / {fails}패 / {len(results) - clears - fails}기타")
    print(f"  클리어율: {clears / max(len(results), 1) * 100:.1f}%")
    print(f"  최종 통계: {json.dumps(player.get_stats(), indent=2, ensure_ascii=False)}")
    print(f"{'='*50}")

    # 결과 저장
    report_path = Path(args.temp_dir or "temp_ai_player") / "play_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "stats": player.get_stats()},
                  f, indent=2, ensure_ascii=False)
    print(f"  리포트: {report_path}")

    player.db.close()


def cmd_stats(args):
    """DB 통계."""
    db = PlayDB(args.db or DEFAULT_DB)
    stats = db.get_stats(args.game)

    print(f"\n  DB: {args.db or DEFAULT_DB}")
    print(f"  게임: {args.game or '전체'}")
    print(f"  ────────────────")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 레벨별 통계
    if args.game:
        rows = db.conn.execute("""
            SELECT * FROM v_level_stats WHERE game_id = ? ORDER BY level_id
        """, (args.game,)).fetchall()
        if rows:
            print(f"\n  레벨별 통계 ({len(rows)}개):")
            print(f"  {'Lv':>5} {'시도':>5} {'클리어':>5} {'성공률':>7} {'평균턴':>7}")
            for r in rows[:20]:
                print(f"  {r['level_id']:>5} {r['attempts']:>5} "
                      f"{r['clears']:>5} {r['clear_rate']:>6.1f}% "
                      f"{r['avg_turns']:>7.1f}")
            if len(rows) > 20:
                print(f"  ... 외 {len(rows) - 20}개")

    db.close()


def cmd_cleanup(args):
    """저장소 정리."""
    sm = SyncManager(args.db or DEFAULT_DB)
    r = sm.apply_storage_policy(args.hot_days, args.warm_days)

    print(f"\n  저장소 정리 완료:")
    print(f"  Warm 처리: {r['warm_processed']}건")
    print(f"  Cold 처리: {r['cold_processed']}건")
    print(f"  절약: {r['bytes_freed_mb']} MB")

    est = sm.estimate_storage()
    print(f"\n  현재 추정:")
    print(f"  DB: {est['db_size_mb']} MB")
    print(f"  이미지: ~{est['estimated_images_gb']} GB")
    print(f"  권장 모드: {est['recommendation']}")

    sm.central_db.close()


def main():
    parser = argparse.ArgumentParser(
        description="AI Game Tester v3",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--db", help="DB 경로 (기본: data/db/play_data.db)")

    sub = parser.add_subparsers(dest="command", help="명령어")

    # ingest
    p = sub.add_parser("ingest", help="인간 플레이 데이터 적재")
    p.add_argument("--data-dir", required=True, help="데이터 폴더")
    p.add_argument("--game", required=True, help="게임 ID")
    p.add_argument("--device", help="디바이스 ID")

    # sync
    p = sub.add_parser("sync", help="디바이스 일괄 동기화")
    p.add_argument("--devices", nargs="+", required=True, help="디바이스 폴더들")
    p.add_argument("--game", required=True, help="게임 ID")
    p.add_argument("--mode", choices=["full", "patterns_only", "incremental"],
                   default="patterns_only", help="동기화 모드")

    # learn
    p = sub.add_parser("learn", help="패턴 학습")
    p.add_argument("--game", required=True, help="게임 ID")
    p.add_argument("--min-occur", type=int, default=2, help="최소 출현 횟수")
    p.add_argument("--cleanup", action="store_true", help="저성과 패턴 정리")

    # play
    p = sub.add_parser("play", help="AI 자율 플레이")
    p.add_argument("--game", required=True, help="게임 ID")
    p.add_argument("--model", help="YOLO 모델 경로")
    p.add_argument("--levels", type=int, default=1, help="플레이할 레벨 수")
    p.add_argument("--max-turns", type=int, default=200, help="레벨당 최대 턴")
    p.add_argument("--timeout", type=int, default=300, help="레벨당 타임아웃(초)")
    p.add_argument("--adb", help="ADB 경로")
    p.add_argument("--device", help="ADB 디바이스")
    p.add_argument("--temp-dir", help="임시 파일 폴더")

    # stats
    p = sub.add_parser("stats", help="DB 통계")
    p.add_argument("--game", help="게임 필터")

    # cleanup
    p = sub.add_parser("cleanup", help="저장소 정리")
    p.add_argument("--hot-days", type=int, default=7)
    p.add_argument("--warm-days", type=int, default=90)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "ingest": cmd_ingest,
        "sync": cmd_sync,
        "learn": cmd_learn,
        "play": cmd_play,
        "stats": cmd_stats,
        "cleanup": cmd_cleanup,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
