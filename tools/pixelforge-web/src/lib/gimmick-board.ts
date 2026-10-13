import { spawn } from "child_process";
import { Db } from "mongodb";

// 기믹 배치 코어(Python)는 board를 stdin으로 받아 순수 변환만 수행 (DB 접근 없음).
// 보드 조회/저장은 TS(여기)가 담당 — 관심사 분리.
const PYTHON = process.env.GIMMICK_PYTHON || "/home/aimed/.hermes/watcher/venv/bin/python";
const CLI = process.env.GIMMICK_CLI || "/home/aimed/gimmick_placement/cli.py";

export type Balloon = { row: number; col: number; color: number; life: number };
export type Board = {
  field_rows: number;
  field_columns: number;
  balloons: Balloon[];
  gimmicks: unknown[];
};

/**
 * 최신 완성보드 조회 — pixelforge_field_complete_jobs.results[] 에서
 * 해당 level_number 의 가장 최근(finished_at) 성공 결과를 board 포맷으로 반환.
 * (designer 행 pixelforge_levels 에는 balloons 가 없음 — 워커 문서는 영구 분리됨)
 */
export async function getCompletedBoard(db: Db, levelNumber: number): Promise<Board | null> {
  const agg = await db
    .collection("pixelforge_field_complete_jobs")
    .aggregate([
      { $match: { status: "done" } },
      { $unwind: "$results" },
      { $match: { "results.level_number": levelNumber, "results.ok": true } },
      { $sort: { finished_at: -1 } },
      { $limit: 1 },
      { $project: { _id: 0, r: "$results" } },
    ])
    .toArray();
  if (!agg.length) return null;
  const r = agg[0].r as {
    balloons?: Balloon[];
    field_analysis?: { field_rows?: number; field_columns?: number };
  };
  if (!Array.isArray(r.balloons) || !r.balloons.length) return null;
  const fa = r.field_analysis || {};
  return {
    field_rows: Number(fa.field_rows),
    field_columns: Number(fa.field_columns),
    balloons: r.balloons,
    gimmicks: [],
  };
}

/** Python CLI(cli.py)를 child_process 로 호출 — payload(stdin) → JSON(stdout). */
export function runGimmickCli<T = unknown>(payload: unknown): Promise<T> {
  return new Promise((resolve, reject) => {
    const p = spawn(PYTHON, [CLI], { stdio: ["pipe", "pipe", "pipe"] });
    let out = "";
    let err = "";
    p.stdout.on("data", (d) => (out += d));
    p.stderr.on("data", (d) => (err += d));
    p.on("error", reject);
    p.on("close", (code) => {
      try {
        resolve(JSON.parse(out) as T);
      } catch {
        reject(new Error(`gimmick cli failed (exit=${code}): ${(err || out).slice(-500)}`));
      }
    });
    p.stdin.write(JSON.stringify(payload));
    p.stdin.end();
  });
}
