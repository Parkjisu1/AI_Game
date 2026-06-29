#!/usr/bin/env python3
"""v43 파이프라인 runner — gen_43_pipeline.py 의 __main__ 흐름을 명령행 인자로 wrap.

핵심 원칙:
- gen_43_pipeline.py 의 함수들을 그대로 import 해서 호출
- 알고리즘 코드 한 줄도 안 건드림 (designer 파일 보존)
- CSV 경로 / OUT_DIR / TARGET_LEVELS / N_SEEDS / N_FINAL 만 외부에서 주입

2026-05-27 패치:
- 컬럼 인덱스를 row[50] 하드코드 → 헤더 이름 lookup 으로 변경
  (이전: 50번 컬럼 = pf_category("Geometric") 가 bl_meta 로 잘못 들어가서
   resolve_zone_metaphor 가 fuzzy 매칭 실패 → 모든 레벨이 zone_concentric_rect fallback)
- 모든 seed 가 anchor metaphor 사용 (single-motif anchor-only mode).
  A/B 차이는 RNG 색상 순열만 — 사용자가 cross-motif 변화는 원하지 않음.
  (이전 시도: 카테고리 풀 분산 — 같은 카테고리 다른 모티프로 B 채움. revert 됨.)

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
    import gen_43_pipeline as g43  # noqa
except ImportError as e:
    print(f"[v43_runner] gen_43_pipeline import 실패: {e}", file=sys.stderr)
    sys.exit(2)


LIFE_ADJUSTABLE_GIMMICKS = {"gimmick_pinata", "gimmick_pin", "gimmick_pinata_box"}


# ────────────────────────────────────────────────────────────────
# CATEGORY → MOTIF POOL
#   bl_category 값마다 METAPHOR_ZONE_MAP key 후보 풀.
#   keys 는 gen_43_pipeline.py 의 _make_zone_map_entry() (L1982-) 한국어 키와 일치해야 함.
# ────────────────────────────────────────────────────────────────
CATEGORY_MOTIF_POOL: dict[str, list[str]] = {
    "geometric": [
        "헤링본", "도형 조합", "체크 패턴", "삼각 패턴", "6각형 격자",
        "줄무늬 그리드", "색조 분할", "컬러 블록 패턴", "픽셀 모자이크",
    ],
    "abstract": [
        "추상 라인", "추상 형상", "추상 모자이크", "추상 그라데",
        "물방울 무늬", "도트 패턴",
    ],
    "linear": [
        "헤링본", "색조 분할", "삼각 패턴", "줄무늬 그리드", "색상 띠",
    ],
    "organic": [
        "꽃 만다라 (Snake 가드)", "구름 그라데", "눈송이 만다라",
        "우주 성운", "불꽃만 (해골 제거)",
    ],
    "natural": [
        "구름 그라데", "눈송이 만다라", "우주 성운", "불꽃만 (해골 제거)",
        "꽃 만다라 (Snake 가드)",
    ],
    "radial": [
        "나선", "방사 패턴", "광선 패턴", "광선 다발", "빛 산란",
        "빛의 분산", "빛 입자", "컬러 휠",
    ],
    "mandala": [
        "나선", "방사 패턴", "꽃 만다라 (Snake 가드)", "눈송이 만다라",
        "빛 입자", "컬러 휠",
    ],
    "concentric": [
        "4단 동심 사각 (주황-녹-보라-주황)", "6색 동심 사각",
        "3색 그라데 직사각형 + 가운데 빈 픽셀",
        "그라데이션 사각", "5단 다채 동심 사각 + 외곽 체크",
        "다단 동심 사각 + 중앙 4 holder (의자형)",
    ],
}
# 한국어 alias
CATEGORY_ALIASES: dict[str, str] = {
    "기하": "geometric", "기하학": "geometric", "기하학적": "geometric",
    "추상": "abstract",
    "선형": "linear",
    "유기": "organic", "유기적": "organic",
    "자연": "natural", "자연적": "natural",
    "방사": "radial", "방사형": "radial",
    "만다라": "mandala",
    "동심": "concentric", "동심형": "concentric",
}


def _resolve_category(category_raw: str) -> list[str]:
    if not category_raw:
        return []
    key = category_raw.strip().lower()
    key = CATEGORY_ALIASES.get(key, key)
    val = CATEGORY_MOTIF_POOL.get(key)
    return list(val) if val else []


def build_motif_list(bl_metaphor: str, bl_category: str, n_seeds: int) -> list[str]:  # bl_category unused
    """모든 seed 가 anchor metaphor 사용 (anchor-only mode).

    A/B 차이는 generate_zone_seeds 내부 RNG(level*1000+seed_id) 의 색상 순열만.
    bl_category 는 메타데이터로만 보존 (evaluation.json) — 모티프 선택에 영향 X.
    """
    del bl_category  # noqa — 변수 보존 위한 dummy
    anchor = (bl_metaphor or "").strip()
    return [anchor] * n_seeds


def parse_csv_levels(csv_path: str, target_levels: set[int]) -> list[tuple]:
    """CSV → [(lv, W, H, n_colors, bl_meta, bl_cat, has_life_gimmick), ...]

    헤더 이름으로 컬럼 인덱스를 동적 lookup (row[50] 하드코드 폐기).
    """
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))

    if len(reader) < 4:
        print(f"[v43_runner] CSV 4행 미만 ({len(reader)} 행)", file=sys.stderr)
        return []

    # row 0 = 카테고리, row 1 = 영문 헤더, row 2 = 한글 헤더, row 3+ = 데이터
    en_header = [(c or "").strip().lower() for c in reader[1]]
    kr_header = [(c or "").strip() for c in (reader[2] if len(reader) > 2 else [])]

    def col_idx(en_name: str, kr_name: str | None = None) -> int:
        n = en_name.lower()
        for i, h in enumerate(en_header):
            if h == n:
                return i
        if kr_name:
            for i, h in enumerate(kr_header):
                if h == kr_name:
                    return i
        return -1

    idx_lv = col_idx("level_number", "레벨 번호")
    idx_w = col_idx("field_columns", "필드 열 수")
    idx_h = col_idx("field_rows", "필드 행 수")
    idx_nc = col_idx("num_colors", "색상 수")
    idx_bl_meta = col_idx("bl_metaphor", "BL 메타포")
    idx_bl_cat = col_idx("bl_category", "BL 카테고리")
    idx_pf_meta = col_idx("pf_metaphor", "PF 메타포")
    idx_pf_cat = col_idx("pf_category", "PF 카테고리")

    missing = []
    if idx_lv < 0: missing.append("level_number")
    if idx_w < 0: missing.append("field_columns")
    if idx_h < 0: missing.append("field_rows")
    if idx_nc < 0: missing.append("num_colors")
    if missing:
        print(f"[v43_runner] CSV 필수 헤더 누락: {missing}", file=sys.stderr)
        return []

    # fallback: BL 메타포/카테고리 없으면 PF 메타포/카테고리 사용
    if idx_bl_meta < 0:
        idx_bl_meta = idx_pf_meta
    if idx_bl_cat < 0:
        idx_bl_cat = idx_pf_cat

    print(f"[v43_runner] column map: lv={idx_lv} W={idx_w} H={idx_h} nc={idx_nc} "
          f"bl_meta={idx_bl_meta} bl_cat={idx_bl_cat}", flush=True)

    gimmick_col_indices: dict[str, int] = {}
    for i, name in enumerate(en_header):
        if name.startswith("gimmick_"):
            gimmick_col_indices[name] = i

    levels: list[tuple] = []
    for row in reader[3:]:
        if not row or idx_lv >= len(row) or not row[idx_lv].strip():
            continue
        try:
            lv = int(row[idx_lv].strip())
        except (ValueError, IndexError):
            continue
        if target_levels and lv not in target_levels:
            continue
        try:
            W = int(row[idx_w].strip())
            H = int(row[idx_h].strip())
            n_colors = int(row[idx_nc].strip())
        except (ValueError, IndexError):
            continue

        bl_meta = (row[idx_bl_meta].strip() if 0 <= idx_bl_meta < len(row) else "") or ""
        bl_cat = (row[idx_bl_cat].strip() if 0 <= idx_bl_cat < len(row) else "") or ""

        has_life_gimmick = False
        for gname in LIFE_ADJUSTABLE_GIMMICKS:
            i = gimmick_col_indices.get(gname)
            if i and i < len(row):
                try:
                    if int((row[i] or "0").strip()) > 0:
                        has_life_gimmick = True
                        break
                except ValueError:
                    pass
        levels.append((lv, W, H, n_colors, bl_meta, bl_cat, has_life_gimmick))
    return levels


def run_levels(levels: list[tuple], out_dir: str, n_seeds: int, n_final: int, block: int) -> dict:
    """gen_43.__main__ 의 STAGE 1~3 + 렌더 + evaluation.json 저장 로직 재현.

    2026-05-27: 모티프별 1 seed 씩 생성 (build_motif_list 분산) → multi-motif candidates.
    """
    os.makedirs(out_dir, exist_ok=True)
    all_results: list[dict] = []

    print(f"{'Lv':>4} | {'Size':>7} | {'C':>2} | {'M':>1} | {'BL Metaphor':<25} | {'Cat':<12} | Best Seeds", flush=True)
    print("=" * 130, flush=True)

    for lv, W, H, n_colors, bl_meta, bl_cat, has_life_gimmick in sorted(levels, key=lambda x: x[0]):
        t0 = time.monotonic()
        try:
            # STAGE 1: anchor metaphor 로 n_seeds 시드 한 번에 생성.
            # gen_43.generate_zone_seeds 가 내부에서 seed_id 0..n-1 RNG 분리 처리.
            # bl_category 는 메타데이터로 evaluation.json 에 보존만.
            anchor_meta = (bl_meta or "").strip()
            seeds = g43.generate_zone_seeds(W, H, n_colors, anchor_meta, lv, n_seeds=n_seeds)
            for s in seeds:
                s["effective_metaphor"] = anchor_meta

            if not seeds:
                raise RuntimeError("seed 생성 0건")

            # STAGE 2: top5 선별 (gen_43 score 기반)
            top5 = g43.select_top5(seeds, W, H, has_life_gimmick)

            # STAGE 3: 평가
            candidates = []
            for s in top5:
                eval_result = g43.evaluate_candidate(s, s["grid"], W, H, has_life_gimmick)
                eval_result["effective_metaphor"] = anchor_meta
                candidates.append(eval_result)

            candidates.sort(key=lambda c: -c["total_score"])
            final = candidates[:n_final]

            labels = ["A", "B", "C", "D", "E"][:n_final]
            # PNG 파일명은 anchor metaphor 유지 (curate route 호환).
            safe_meta = (bl_meta or "no_meta").replace("/", "_").replace(" ", "_")[:25]
            for i, c in enumerate(final):
                img = g43.make_image(c["grid"], c["colors"], W, H, block)
                fname = f"level_{lv:03d}_{safe_meta}_{labels[i]}.png"
                img.save(os.path.join(out_dir, fname))

            result = {
                "level": lv,
                "metaphor": bl_meta,
                "category": bl_cat,
                "board_size": [W, H],
                "num_colors": n_colors,
                "has_life_gimmick": has_life_gimmick,
                "duration_sec": round(time.monotonic() - t0, 2),
                "final_candidates": final,
            }
            all_results.append(result)

            status = "✓" if all(c.get("x10_pass") for c in final) else "✗"
            cands_str = " | ".join(
                f"s{c['seed_idx']}={c['total_score']:.2f}{status}({(c.get('effective_metaphor') or '?')[:10]})"
                for c in final
            )
            sym = g43.resolve_zone_metaphor(bl_meta, n_colors)[0][0].upper()
            print(f"{lv:>4} | {W:>2}×{H:<3} | {n_colors:>2} | {sym} | {bl_meta:<25} | {bl_cat:<12} | {cands_str}", flush=True)

        except Exception as e:
            print(f"{lv:>4} | ERROR: {e}", flush=True)
            traceback.print_exc()
            all_results.append({
                "level": lv,
                "metaphor": bl_meta,
                "category": bl_cat,
                "error": str(e),
                "final_candidates": [],
            })

    # evaluation.json 저장 (grid 필드 제거)
    eval_path = os.path.join(out_dir, "evaluation.json")
    save_data = []
    for r in all_results:
        rd = dict(r)
        rd["final_candidates"] = [{k: v for k, v in c.items() if k != "grid"}
                                  for c in r.get("final_candidates", [])]
        save_data.append(rd)
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    print("=" * 130, flush=True)
    print(f"완료: {len(levels)} 레벨, 각 {n_final}개 후보 → {out_dir}")
    print(f"평가 결과: {eval_path}")

    return {
        "total_levels": len(levels),
        "results": all_results,
        "out_dir": out_dir,
        "eval_path": eval_path,
    }


def parse_target_levels(spec: str | None) -> set[int]:
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
    ap.add_argument("--csv", required=False)
    ap.add_argument("--out", required=False)
    ap.add_argument("--levels", default="")
    ap.add_argument("--n-seeds", type=int, default=10, dest="n_seeds")
    ap.add_argument("--n-final", type=int, default=2, dest="n_final")
    ap.add_argument("--block", type=int, default=1)
    ap.add_argument("--job-id", default="", dest="job_id")
    args = ap.parse_args()

    if args.job_id:
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
                {"$set": {"status": "running",
                          "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}},
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

    print(f"[v43_runner] csv={args.csv} out={args.out} n_levels={len(levels)} "
          f"n_seeds={args.n_seeds} n_final={args.n_final}")

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
