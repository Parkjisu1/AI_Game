#!/usr/bin/env python3
"""v43 파이프라인 runner — gen_43_pipeline.py 의 __main__ 흐름을 명령행 인자로 wrap.

핵심 원칙:
- gen_43_pipeline.py 의 함수들을 그대로 import 해서 호출
- 알고리즘 코드 한 줄도 안 건드림
- CSV 경로 / OUT_DIR / TARGET_LEVELS / N_SEEDS / N_FINAL 만 외부에서 주입

사용:
  python v43_runner.py --csv <path> --out <dir> [--levels 1,3,5,...] [--n-seeds 10] [--n-final 2]
  python v43_runner.py --job-id <projecthub_job_id>   # MongoDB pixelforge_v43_jobs 에서 가져옴

종료 코드:
  0  성공
  1  CSV/입력 실패
  2  gen_43 ImportError
  3  처리 중 fatal 에러
"""
import argparse
import csv
import json
import os
import sys
import time
import traceback
from pathlib import Path

# gen_43_pipeline.py 가 있는 경로를 sys.path 에 추가 (cwd 우선)
GEN43_DIR = Path("/home/aimed/.hermes/watcher/v43")
if GEN43_DIR.exists():
    sys.path.insert(0, str(GEN43_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    # gen_43_pipeline.py 를 그대로 import — __main__ 우회 위해 모듈 가드 확인.
    # gen_43 자체는 __main__ 안에서만 CSV 로드 + 루프, 함수는 top-level.
    import gen_43_pipeline as g43  # noqa
except ImportError as e:
    print(f"[v43_runner] gen_43_pipeline import 실패: {e}", file=sys.stderr)
    sys.exit(2)


LIFE_ADJUSTABLE_GIMMICKS = {"gimmick_pinata", "gimmick_pin", "gimmick_pinata_box"}


def parse_csv_levels(csv_path: str, target_levels: set[int]) -> list[tuple]:
    """gen_43.__main__ 의 CSV 파싱 로직 그대로 재현 (변경 0)."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header = reader[2] if len(reader) > 2 else []
    gimmick_col_indices: dict[str, int] = {}
    for i, col_name in enumerate(header):
        cn = (col_name or "").strip().lower()
        if cn.startswith("gimmick_"):
            gimmick_col_indices[cn] = i

    levels = []
    for row in reader[3:]:
        if not row or not row[0].strip():
            continue
        try:
            lv = int(row[0].strip())
        except (ValueError, IndexError):
            continue
        if target_levels and lv not in target_levels:
            continue
        try:
            W = int(row[11].strip())
            H = int(row[12].strip())
            n_colors = int(row[8].strip())
        except (ValueError, IndexError):
            continue
        bl_meta = row[50].strip() if len(row) > 50 else ""
        has_life_gimmick = False
        for gname in LIFE_ADJUSTABLE_GIMMICKS:
            idx = gimmick_col_indices.get(gname)
            if idx and idx < len(row):
                try:
                    if int((row[idx] or "0").strip()) > 0:
                        has_life_gimmick = True
                        break
                except ValueError:
                    pass
        levels.append((lv, W, H, n_colors, bl_meta, has_life_gimmick))
    return levels


def run_levels(levels: list[tuple], out_dir: str, n_seeds: int, n_final: int, block: int) -> dict:
    """gen_43.__main__ 의 STAGE 1~3 + 렌더 + evaluation.json 저장 로직 그대로 재현."""
    os.makedirs(out_dir, exist_ok=True)
    all_results: list[dict] = []

    print(f"{'Lv':>4} | {'Size':>7} | {'C':>2} | {'M':>1} | {'BL Metaphor':<35} | Best Seeds")
    print("=" * 110)

    for lv, W, H, n_colors, bl_meta, has_life_gimmick in sorted(levels, key=lambda x: x[0]):
        t0 = time.monotonic()
        try:
            # STAGE 1: 존 기반 시드 생성 (gen_43 함수 호출 — 변경 0)
            seeds = g43.generate_zone_seeds(W, H, n_colors, bl_meta, lv, n_seeds)

            # STAGE 2: 선별 (top5)
            top5 = g43.select_top5(seeds, W, H, has_life_gimmick)

            # STAGE 3: 평가
            candidates = []
            for s in top5:
                eval_result = g43.evaluate_candidate(s, s["grid"], W, H, has_life_gimmick)
                candidates.append(eval_result)

            # 최종 N_FINAL 개 선택
            candidates.sort(key=lambda c: -c["total_score"])
            final = candidates[:n_final]

            # 렌더링 (gen_43.make_image 그대로)
            labels = ["A", "B", "C", "D", "E"][:n_final]
            safe_meta = (bl_meta or "no_meta").replace("/", "_").replace(" ", "_")[:25]
            for i, c in enumerate(final):
                img = g43.make_image(c["grid"], c["colors"], W, H, block)
                fname = f"level_{lv:03d}_{safe_meta}_{labels[i]}.png"
                img.save(os.path.join(out_dir, fname))

            result = {
                "level": lv,
                "metaphor": bl_meta,
                "board_size": [W, H],
                "num_colors": n_colors,
                "has_life_gimmick": has_life_gimmick,
                "duration_sec": round(time.monotonic() - t0, 2),
                "final_candidates": final,
            }
            all_results.append(result)

            status = "✓" if all(c["x10_pass"] for c in final) else "✗"
            cands_str = " | ".join(
                f"s{c['seed_idx']}={c['total_score']:.2f}{status}(T={c['t_cells']})"
                for c in final
            )
            sym = g43.resolve_zone_metaphor(bl_meta, n_colors)[0][0].upper()
            print(f"{lv:>4} | {W:>2}×{H:<3} | {n_colors:>2} | {sym} | {bl_meta:<35} | {cands_str}")

        except Exception as e:
            print(f"{lv:>4} | ERROR: {e}")
            traceback.print_exc()
            all_results.append({
                "level": lv,
                "metaphor": bl_meta,
                "error": str(e),
                "final_candidates": [],
            })

    # evaluation.json 저장 (gen_43 그대로)
    eval_path = os.path.join(out_dir, "evaluation.json")
    save_data = []
    for r in all_results:
        rd = dict(r)
        if "final_candidates" in rd:
            rd["final_candidates"] = []
            for c in r.get("final_candidates", []):
                cd = {k: v for k, v in c.items() if k != "grid"}
                rd["final_candidates"].append(cd)
        save_data.append(rd)
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    print("=" * 110)
    print(f"완료: {len(levels)} 레벨, 각 {n_final}개 후보 → {out_dir}")
    print(f"평가 결과: {eval_path}")

    return {
        "total_levels": len(levels),
        "results": all_results,
        "out_dir": out_dir,
        "eval_path": eval_path,
    }


def parse_target_levels(spec: str | None) -> set[int]:
    """\"1,3,5-10,50\" → {1,3,5,6,7,8,9,10,50}. None/빈문자열 → 빈셋 (전체)."""
    if not spec:
        return set()
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        else:
            out.add(int(part))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=False, help="CSV 입력 경로 (또는 --job-id)")
    ap.add_argument("--out", required=False, help="출력 디렉토리")
    ap.add_argument("--levels", default="", help="대상 lv (예: 1,3,5-10). 비우면 전체")
    ap.add_argument("--n-seeds", type=int, default=10, dest="n_seeds")
    ap.add_argument("--n-final", type=int, default=2, dest="n_final")
    ap.add_argument("--block", type=int, default=1, help="셀당 픽셀 (1=원본 그리드)")
    ap.add_argument("--job-id", default="", dest="job_id",
                    help="MongoDB pixelforge_v43_jobs 의 _id (이게 있으면 CSV+OUT 자동)")
    args = ap.parse_args()

    if args.job_id:
        # job 문서에서 CSV/OUT/levels 가져옴
        try:
            from pymongo import MongoClient
            from bson import ObjectId
            uri = os.environ.get("MONGODB_URI")
            db_name = os.environ.get("MONGODB_DB", "aigame")
            if not uri:
                print("MONGODB_URI 환경변수 필요 (--job-id 모드)", file=sys.stderr)
                return 1
            db = MongoClient(uri, serverSelectionTimeoutMS=4000)[db_name]
            doc = db["pixelforge_v43_jobs"].find_one({"_id": ObjectId(args.job_id)})
            if not doc:
                print(f"job {args.job_id} not found", file=sys.stderr)
                return 1
            args.csv = doc.get("csv_path") or args.csv
            args.out = doc.get("out_dir") or args.out
            tl = doc.get("target_levels")
            if tl:
                args.levels = ",".join(str(x) for x in tl)
            args.n_seeds = int(doc.get("n_seeds") or args.n_seeds)
            args.n_final = int(doc.get("n_final") or args.n_final)
            db["pixelforge_v43_jobs"].update_one(
                {"_id": ObjectId(args.job_id)},
                {"$set": {"status": "running", "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}},
            )
        except Exception as e:
            print(f"job 로드 실패: {e}", file=sys.stderr)
            return 1

    if not args.csv or not args.out:
        print("--csv 와 --out 모두 필요 (또는 --job-id)", file=sys.stderr)
        return 1

    target_levels = parse_target_levels(args.levels)
    levels = parse_csv_levels(args.csv, target_levels)
    if not levels:
        print(f"CSV 에서 target_levels 매칭 0건 (csv={args.csv}, levels={args.levels})", file=sys.stderr)
        return 1

    print(f"[v43_runner] csv={args.csv} out={args.out} n_levels={len(levels)} n_seeds={args.n_seeds} n_final={args.n_final}")

    try:
        summary = run_levels(levels, args.out, args.n_seeds, args.n_final, args.block)
    except Exception as e:
        traceback.print_exc()
        if args.job_id:
            try:
                from pymongo import MongoClient
                from bson import ObjectId
                uri = os.environ.get("MONGODB_URI")
                db_name = os.environ.get("MONGODB_DB", "aigame")
                MongoClient(uri, serverSelectionTimeoutMS=4000)[db_name]["pixelforge_v43_jobs"].update_one(
                    {"_id": ObjectId(args.job_id)},
                    {"$set": {"status": "failed", "error": str(e),
                              "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}},
                )
            except Exception:
                pass
        return 3

    if args.job_id:
        try:
            from pymongo import MongoClient
            from bson import ObjectId
            uri = os.environ.get("MONGODB_URI")
            db_name = os.environ.get("MONGODB_DB", "aigame")
            db = MongoClient(uri, serverSelectionTimeoutMS=4000)[db_name]
            db["pixelforge_v43_jobs"].update_one(
                {"_id": ObjectId(args.job_id)},
                {"$set": {
                    "status": "done",
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "total_levels": summary["total_levels"],
                    "eval_path": summary["eval_path"],
                    "out_dir": summary["out_dir"],
                }},
            )
        except Exception as e:
            print(f"job status 업데이트 실패: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
