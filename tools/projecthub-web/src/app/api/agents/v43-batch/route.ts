import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { spawn } from "child_process";
import { openSync, mkdirSync, writeFileSync } from "fs";
import { dirname, join } from "path";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";

/**
 * v43 batch — 디자이너 원본 `gen_43_pipeline.py` 를 그대로 spawn.
 * Wrapper 알고리즘 변경 0. 명령행 인자만 주입.
 *
 * POST body:
 *   { csv_path?: string, csv_text?: string, target_levels: number[] | string,
 *     n_seeds?: number, n_final?: number, label?: string }
 *
 * 흐름:
 *   1. CSV (path 또는 text 인라인) 저장
 *   2. pixelforge_v43_jobs 에 job 문서 insert
 *   3. v43_runner.py --job-id <id> 로 background spawn
 *   4. runner 가 gen_43_pipeline 함수 호출 → PNG + evaluation.json 출력
 *   5. 동시에 job 문서 status running → done/failed 업데이트
 *
 * GET ?id=...   : 단건 job 상세 + evaluation.json 내용 포함
 * GET           : 최근 30개 job 목록
 */

const JOBS_COLLECTION = "pixelforge_v43_jobs";
const V43_DIR = process.env.V43_DIR || "/home/aimed/.hermes/watcher/v43";
const PYTHON_BIN = process.env.WATCHER_PYTHON || "/home/aimed/.hermes/watcher/venv/bin/python";
const LOG_DIR = process.env.V43_LOG_DIR || "/home/aimed/.hermes/logs/v43";
const OUT_BASE = process.env.V43_OUT_BASE || "/home/aimed/.hermes/v43_out";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  const db = await getDb();
  const jobs = db.collection(JOBS_COLLECTION);

  if (id) {
    try {
      const doc = await jobs.findOne({ _id: new ObjectId(id) });
      if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });
      // evaluation.json 가 있으면 내용 함께 반환
      let evalContent: unknown = null;
      if (doc.eval_path) {
        try {
          const fs = await import("fs/promises");
          const txt = await fs.readFile(String(doc.eval_path), "utf-8");
          evalContent = JSON.parse(txt);
        } catch { /* 없으면 null */ }
      }
      const { _id: _drop, ...rest } = doc;
      void _drop;
      return NextResponse.json({
        _id: String(doc._id),
        ...rest,
        evaluation: evalContent,
      });
    } catch {
      return NextResponse.json({ error: "invalid id" }, { status: 400 });
    }
  }

  // 목록 (csv_text 제외 — 무거움)
  const recent = await jobs
    .find({}, { projection: { csv_text: 0 } })
    .sort({ created_at: -1 })
    .limit(30)
    .toArray();
  return NextResponse.json({
    jobs: recent.map((r) => ({ ...r, _id: String(r._id) })),
  });
}

export async function POST(req: NextRequest) {
  const session = await auth();
  const email = session?.user?.email || "";
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; }
  catch { return NextResponse.json({ error: "invalid json" }, { status: 400 }); }

  let csvText = typeof body.csv_text === "string" ? body.csv_text : "";
  const csvPath = typeof body.csv_path === "string" ? body.csv_path : "";
  const generateFromDb = body.generate_csv_from_db === true;
  const useLatestCsv = body.use_latest_csv === true;
  if (!csvText && !csvPath && !generateFromDb && !useLatestCsv) {
    return NextResponse.json({ error: "csv_text/csv_path/generate_csv_from_db/use_latest_csv 중 하나 필요" }, { status: 400 });
  }

  // target_levels — number[] 또는 "1,3,5-10" 문자열
  let targetLevels: number[] = [];
  if (Array.isArray(body.target_levels)) {
    targetLevels = (body.target_levels as unknown[]).map(Number).filter((n) => Number.isFinite(n) && n > 0);
  } else if (typeof body.target_levels === "string") {
    for (const part of body.target_levels.split(",")) {
      const p = part.trim();
      if (!p) continue;
      if (p.includes("-")) {
        const [lo, hi] = p.split("-").map((x) => Number(x.trim()));
        if (Number.isFinite(lo) && Number.isFinite(hi)) {
          for (let n = lo; n <= hi; n++) targetLevels.push(n);
        }
      } else {
        const n = Number(p);
        if (Number.isFinite(n) && n > 0) targetLevels.push(n);
      }
    }
  }
  const uniqueTargetLevels = [...new Set(targetLevels)].sort((a, b) => a - b);
  if (uniqueTargetLevels.length === 0) {
    return NextResponse.json({ error: "target_levels 필요 (예: [1,3,5] 또는 \"1,3,5-10\")" }, { status: 400 });
  }
  if (uniqueTargetLevels.length > 500) {
    return NextResponse.json({ error: `target_levels 최대 500 (현재 ${uniqueTargetLevels.length})` }, { status: 400 });
  }

  const nSeeds = Math.max(2, Math.min(20, Number(body.n_seeds ?? 10) || 10));
  const nFinal = Math.max(1, Math.min(5, Number(body.n_final ?? 2) || 2));
  const label = typeof body.label === "string" ? body.label.substring(0, 64) : "v43 batch";

  const db = await getDb();
  const jobs = db.collection(JOBS_COLLECTION);

  // use_latest_csv 모드: pixelforge_csv_versions 에서 latest 가져옴
  let csvSourceLabel = "";
  if (useLatestCsv && !csvText) {
    const latest = await db.collection("pixelforge_csv_versions").findOne({ is_latest: true });
    if (!latest || !latest.csv_text) {
      return NextResponse.json({ error: "latest CSV 없음 — /api/agents/csv-latest 로 업로드 필요" }, { status: 400 });
    }
    csvText = String(latest.csv_text);
    csvSourceLabel = `latest CSV v${latest.version || "?"}`;
  }

  // generate_csv_from_db 모드: pixelforge_levels 에서 target_levels 조회 후 gen_43 가 읽을 51열 CSV 합성
  if (generateFromDb && !csvText) {
    const rows = await db.collection("pixelforge_levels")
      .find({ level_number: { $in: uniqueTargetLevels }, status: { $exists: true } },
            { projection: { level_number: 1, field_rows: 1, field_columns: 1,
                            num_colors: 1, bl_metaphor: 1, pf_metaphor: 1 } })
      .toArray();
    const byLv = new Map<number, Record<string, unknown>>();
    for (const r of rows) byLv.set(Number(r.level_number), r);
    const missing = uniqueTargetLevels.filter((lv) => !byLv.has(lv));
    if (missing.length === uniqueTargetLevels.length) {
      return NextResponse.json({ error: "pixelforge_levels 에서 target_levels 0건 매칭", missing_count: missing.length }, { status: 400 });
    }
    // 51 컬럼 CSV — gen_43 parse_csv_levels 가 col 0(lv), 8(nc), 11(W), 12(H), 50(bl_metaphor) 만 읽음
    const hdr1 = new Array(51).fill("").join(",");
    const hdr2 = (() => {
      const a = new Array(51).fill("");
      a[0] = "level_number"; a[8] = "num_colors"; a[11] = "field_columns"; a[12] = "field_rows"; a[50] = "bl_metaphor";
      return a.join(",");
    })();
    const hdr3 = hdr1;
    const lines = [hdr1, hdr2, hdr3];
    const escape = (v: unknown): string => {
      const s = String(v ?? "");
      return /[,"\n]/.test(s) ? JSON.stringify(s) : s;
    };
    for (const lv of uniqueTargetLevels) {
      const r = byLv.get(lv);
      if (!r) continue;
      const a = new Array(51).fill("");
      a[0] = String(lv);
      a[8] = String(r.num_colors ?? 3);
      a[11] = String(r.field_columns ?? 16);
      a[12] = String(r.field_rows ?? 16);
      a[50] = String(r.bl_metaphor ?? r.pf_metaphor ?? "");
      lines.push(a.map(escape).join(","));
    }
    csvText = lines.join("\n");
    console.log(`[v43-batch] CSV from DB: ${lines.length - 3} rows, missing ${missing.length}`);
  }

  // job 문서 먼저 insert (id 받아 out_dir 결정)
  const now = new Date().toISOString();
  const insertDoc: Record<string, unknown> = {
    created_at: now,
    created_by_email: email.toLowerCase(),
    status: "pending",
    label,
    target_levels: uniqueTargetLevels,
    n_seeds: nSeeds,
    n_final: nFinal,
    csv_source_label: csvSourceLabel || (generateFromDb ? "DB-synth" : "inline"),
  };
  const inserted = await jobs.insertOne(insertDoc);
  const id = String(inserted.insertedId);

  // CSV 저장 (path 모드 vs text 모드)
  const outDir = join(OUT_BASE, id);
  const finalCsvPath = csvPath || join(outDir, "input.csv");
  try {
    mkdirSync(outDir, { recursive: true });
    if (csvText) {
      writeFileSync(finalCsvPath, csvText, "utf-8");
    }
  } catch (e) {
    await jobs.updateOne({ _id: inserted.insertedId },
      { $set: { status: "failed", error: `dir/csv setup: ${e}`, finished_at: new Date().toISOString() } });
    return NextResponse.json({ error: `CSV 저장 실패: ${e}` }, { status: 500 });
  }

  // job 문서에 path 채우기
  await jobs.updateOne({ _id: inserted.insertedId }, {
    $set: { csv_path: finalCsvPath, out_dir: outDir },
  });

  // spawn — gen_43_pipeline.py 함수를 호출하는 runner. 알고리즘은 0 변경.
  try {
    const logPath = join(LOG_DIR, `v43_${id}.log`);
    try { mkdirSync(dirname(logPath), { recursive: true }); } catch { /* exists */ }
    const out = openSync(logPath, "a");
    const child = spawn(
      PYTHON_BIN,
      [join(V43_DIR, "v43_runner.py"), "--job-id", id],
      {
        cwd: V43_DIR,
        detached: true,
        stdio: ["ignore", out, out],
        env: {
          ...process.env,
          MONGODB_URI: process.env.MONGODB_URI,
          MONGODB_DB: process.env.MONGODB_DB || "aigame",
        },
      },
    );
    child.on("error", (e) => console.error(`[v43 ${id}] spawn:`, e));
    child.unref();
  } catch (e) {
    await jobs.updateOne({ _id: inserted.insertedId },
      { $set: { status: "failed", error: `spawn: ${e}`, finished_at: new Date().toISOString() } });
    return NextResponse.json({ error: `실행 실패: ${e}` }, { status: 500 });
  }

  return NextResponse.json({
    ok: true,
    id,
    target_levels: uniqueTargetLevels,
    out_dir: outDir,
    csv_path: finalCsvPath,
  });
}
