import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { spawn } from "child_process";
import { openSync, mkdirSync, writeFileSync } from "fs";
import { dirname, join } from "path";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";

/**
 * Pipeline Session — Art→Curate→Field→Download 단일 세션 모델.
 *
 * GET   목록 (최근 50)
 * POST  세션 생성 + Art job 자동 spawn
 *
 * 세션 stage:
 *   csv → art_running → art_done → curated_pending → curated_done
 *       → field_running → field_done → download → done
 *
 * 백엔드 동작:
 *   POST 시 v43-batch 직접 spawn (별도 endpoint 호출 X) — Art job 결과를
 *   pipeline_sessions 의 art_job 필드에 link.
 */

const COLL = "pixelforge_pipeline_sessions";
const V43_DIR = process.env.V43_DIR || "/home/aimed/.hermes/watcher/v43";
const PYTHON_BIN = process.env.WATCHER_PYTHON || "/home/aimed/.hermes/watcher/venv/bin/python";
const LOG_DIR = process.env.V43_LOG_DIR || "/home/aimed/.hermes/logs/v43";
const OUT_BASE = process.env.V43_OUT_BASE || "/home/aimed/.hermes/v43_out";

function parseLevels(spec: string | unknown): number[] {
  if (Array.isArray(spec)) return (spec as unknown[]).map(Number).filter((n) => Number.isFinite(n) && n > 0);
  if (typeof spec !== "string") return [];
  const out: number[] = [];
  for (const part of spec.split(/[,\s]+/)) {
    const p = part.trim();
    if (!p) continue;
    if (p.includes("-")) {
      const [lo, hi] = p.split("-").map((x) => Number(x.trim()));
      if (Number.isFinite(lo) && Number.isFinite(hi)) {
        for (let n = lo; n <= hi; n++) out.push(n);
      }
    } else {
      const n = Number(p);
      if (Number.isFinite(n) && n > 0) out.push(n);
    }
  }
  return [...new Set(out)].sort((a, b) => a - b);
}

export async function GET(_req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const db = await getDb();
  const sessions = await db.collection(COLL)
    .find({}, { projection: { csv_text: 0 } })
    .sort({ created_at: -1 })
    .limit(50)
    .toArray();

  // active session (art_running / field_running) 들은 list polling 시점에서도 sync 시도 —
  // 사용자가 detail modal 안 열어도 stage 전이를 감지해서 Slack 통지가 발송되도록.
  const { syncSessionStage } = await import("./[id]/route");
  const activeStages = new Set(["art_running", "field_running"]);
  const refreshed = await Promise.all(sessions.map(async (s) => {
    if (!activeStages.has(String(s.stage))) return s;
    try { return await syncSessionStage(db, s); }
    catch { return s; }
  }));

  return NextResponse.json({
    sessions: refreshed.map((s) => ({ ...s, _id: String(s._id) })),
  });
}

export async function POST(req: NextRequest) {
  const session = await auth();
  const email = session?.user?.email || "";
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; }
  catch { return NextResponse.json({ error: "invalid json" }, { status: 400 }); }

  const label = String(body.label || `Pipeline ${new Date().toISOString().slice(0, 19)}`).substring(0, 128);
  const targetLevels = parseLevels(body.target_levels);
  if (targetLevels.length === 0) {
    return NextResponse.json({ error: "target_levels 필요 (예: [1,3] 또는 \"1-10\")" }, { status: 400 });
  }
  if (targetLevels.length > 500) {
    return NextResponse.json({ error: `target_levels 최대 500 (현재 ${targetLevels.length})` }, { status: 400 });
  }
  const artMode = (body.art_mode === "cowork" ? "cowork" : "v47") as "v47" | "cowork";
  const autoAdvance = body.auto_advance !== false; // default true
  const gimmickPreset = (["pf_grounded", "light", "medium", "heavy", "none"].includes(String(body.gimmick_preset))
    ? String(body.gimmick_preset) : "pf_grounded") as "pf_grounded" | "light" | "medium" | "heavy" | "none";
  const nSeeds = Math.max(2, Math.min(20, Number(body.n_seeds ?? 10) || 10));
  const nFinal = Math.max(1, Math.min(5, Number(body.n_final ?? 2) || 2));

  const db = await getDb();

  // 최신 CSV 가져오기 (있으면)
  const csvDoc = await db.collection("pixelforge_csv_versions").findOne({ is_latest: true });

  const now = new Date().toISOString();
  const insert = await db.collection(COLL).insertOne({
    created_at: now,
    updated_at: now,
    created_by_email: email.toLowerCase(),
    label,
    target_levels: targetLevels,
    art_mode: artMode,
    auto_advance: autoAdvance,
    gimmick_preset: gimmickPreset,
    n_seeds: nSeeds,
    n_final: nFinal,
    csv_version_id: csvDoc ? String(csvDoc._id) : null,
    csv_version_label: csvDoc ? `${csvDoc.version} ${csvDoc.label}` : "(no CSV — DB synth)",
    stage: "art_running",
    stage_history: [{ stage: "art_running", at: now, by: email.toLowerCase() }],
  } as Record<string, unknown>);
  const sessionId = String(insert.insertedId);

  // Art job spawn (v47 only for now — cowork 모드는 후속)
  if (artMode !== "v47") {
    await db.collection(COLL).updateOne({ _id: insert.insertedId }, {
      $set: { stage: "failed", error: `art_mode '${artMode}' 미지원 (현재 v47만). 추후 cowork 추가.` },
    });
    return NextResponse.json({ error: `art_mode '${artMode}' 미지원` }, { status: 400 });
  }

  // v43_jobs 문서 생성 → runner spawn
  const v43Insert = await db.collection("pixelforge_v43_jobs").insertOne({
    created_at: now,
    created_by_email: email.toLowerCase(),
    status: "pending",
    label: `[Pipeline ${sessionId.slice(-6)}] ${label}`,
    source_pipeline: sessionId,
    target_levels: targetLevels,
    n_seeds: nSeeds,
    n_final: nFinal,
    pipeline_version: "v47 (gen_42 with v47 zones)",
  });
  const artJobId = String(v43Insert.insertedId);
  const outDir = join(OUT_BASE, artJobId);
  mkdirSync(outDir, { recursive: true });

  // CSV 합성 (latest CSV 또는 DB synth)
  let csvText = "";
  if (csvDoc?.csv_text) {
    csvText = String(csvDoc.csv_text);
  } else {
    // DB 합성 — pixelforge_levels 에서 lv 메타데이터 가져옴
    const rows = await db.collection("pixelforge_levels")
      .find({ level_number: { $in: targetLevels }, status: { $exists: true } },
            { projection: { level_number: 1, field_rows: 1, field_columns: 1, num_colors: 1, bl_metaphor: 1, pf_metaphor: 1 } })
      .toArray();
    const byLv = new Map(rows.map((r) => [Number(r.level_number), r]));
    const cols = new Array(51).fill("");
    cols[0] = "level_number"; cols[8] = "num_colors"; cols[11] = "field_columns"; cols[12] = "field_rows"; cols[50] = "bl_metaphor";
    const lines = [new Array(51).fill("").join(","), cols.join(","), new Array(51).fill("").join(",")];
    const escape = (v: unknown) => { const s = String(v ?? ""); return /[,"\n]/.test(s) ? JSON.stringify(s) : s; };
    for (const lv of targetLevels) {
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
  }
  const csvPath = join(outDir, "input.csv");
  writeFileSync(csvPath, csvText, "utf-8");

  await db.collection("pixelforge_v43_jobs").updateOne({ _id: v43Insert.insertedId }, {
    $set: { csv_path: csvPath, out_dir: outDir },
  });

  // session → art_job link
  await db.collection(COLL).updateOne({ _id: insert.insertedId }, {
    $set: {
      art_job: { type: "v47", job_id: artJobId, status: "running", started_at: now },
      updated_at: now,
    },
  });

  // spawn runner
  try {
    mkdirSync(LOG_DIR, { recursive: true });
    const logPath = join(LOG_DIR, `v43_${artJobId}.log`);
    try { mkdirSync(dirname(logPath), { recursive: true }); } catch { /* exists */ }
    const out = openSync(logPath, "a");
    const child = spawn(
      PYTHON_BIN,
      [join(V43_DIR, "v43_runner.py"), "--job-id", artJobId],
      {
        cwd: V43_DIR, detached: true, stdio: ["ignore", out, out],
        env: {
          ...process.env,
          MONGODB_URI: process.env.MONGODB_URI,
          MONGODB_DB: process.env.MONGODB_DB || "aigame",
        },
      },
    );
    child.on("error", (e) => console.error(`[pipeline ${sessionId} art] spawn:`, e));
    child.unref();
  } catch (e) {
    await db.collection(COLL).updateOne({ _id: insert.insertedId }, {
      $set: { stage: "failed", error: `art spawn: ${e}` },
    });
    return NextResponse.json({ error: `art spawn 실패: ${e}` }, { status: 500 });
  }

  return NextResponse.json({
    ok: true,
    id: sessionId,
    art_job_id: artJobId,
    target_levels: targetLevels,
    label,
  });
}
