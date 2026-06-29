import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { spawn } from "child_process";
import { openSync, mkdirSync } from "fs";
import { dirname } from "path";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";

/**
 * 컬렉션 직접 import — pixelforge_levels에서 docs를 가져와 field-complete job 생성.
 *
 * Body (둘 중 하나):
 *   { source: "pixelforge_levels", filter: { status: "draft" } }     ← Mongo filter 그대로
 *   { source: "pixelforge_levels", ids: ["<oid1>", ...] }              ← _id 리스트
 *   { source: "pixelforge_levels", level_numbers: [1, 2, 3] }          ← level_number 리스트
 *
 * 추가:
 *   max_rows: 1000 (default 100, hard limit 1000)
 *   allow_escalation: true
 */

const JOBS_COLLECTION = "pixelforge_field_complete_jobs";

const ALLOWED_SOURCES = ["pixelforge_levels"];

export async function POST(req: NextRequest) {
  const session = await auth();
  const email = session?.user?.email || "";
  if (!email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const source = String(body.source ?? "pixelforge_levels");
  if (!ALLOWED_SOURCES.includes(source)) {
    return NextResponse.json({ error: `source must be one of ${ALLOWED_SOURCES.join(", ")}` }, { status: 400 });
  }

  const maxRows = Math.min(1000, Math.max(1, parseInt(String(body.max_rows ?? "100"), 10) || 100));
  const allowEscalation = body.allow_escalation !== false;
  const keepAllCandidates = body.keep_all_candidates === true;
  const ironWallMode = String(body.iron_wall_mode ?? "bl_outline");

  const db = await getDb();
  const sourceColl = db.collection(source);

  // 필터 구축
  let filter: Record<string, unknown> = {};
  if (Array.isArray(body.ids) && body.ids.length > 0) {
    try {
      filter = { _id: { $in: (body.ids as string[]).map((s) => new ObjectId(s)) } };
    } catch {
      return NextResponse.json({ error: "invalid id format" }, { status: 400 });
    }
  } else if (Array.isArray(body.level_numbers) && body.level_numbers.length > 0) {
    filter = { level_number: { $in: (body.level_numbers as unknown[]).map((n) => Number(n)).filter((n) => !isNaN(n)) } };
  } else if (body.filter && typeof body.filter === "object") {
    filter = body.filter as Record<string, unknown>;
  } else {
    return NextResponse.json({ error: "specify one of: ids, level_numbers, filter" }, { status: 400 });
  }

  // 가져오기 (필드 화이트리스트로 가볍게)
  const projection: Record<string, 0 | 1> = {
    level_number: 1, pkg: 1, pos: 1, chapter: 1, purpose_type: 1,
    field_rows: 1, field_columns: 1, total_cells: 1,
    num_colors: 1, color_distribution: 1, queue_columns: 1, rail_capacity: 1,
    designer_note: 1, emotion_curve: 1, dart_capacity_range: 1,
    // 핵심: 기존 풍선 배치 보존을 위한 필드
    field_map: 1, palette_mapping: 1, generated_colors: 1, generated_num_colors: 1,
    // 이미지 기반 검증
    image_base64: 1, bl_metaphor: 1,
    gimmick_hidden: 1, gimmick_chain: 1, gimmick_pinata: 1, gimmick_glass_pipe: 1,
    gimmick_pin: 1, gimmick_lock_key: 1, gimmick_surprise: 1, gimmick_wall: 1,
    gimmick_spawner_o: 1, gimmick_spawner_t: 1, gimmick_pinata_box: 1,
    gimmick_ice: 1, gimmick_frozen_dart: 1, gimmick_curtain: 1,
  };
  const docs = await sourceColl
    .find(filter, { projection })
    .limit(maxRows)
    .toArray();

  if (docs.length === 0) {
    return NextResponse.json({ error: "no docs matched filter", filter }, { status: 404 });
  }

  // CSV row 형태로 정규화 (gimmick_lock_key=0 강제, lock_key는 1.0 SKIP)
  const csvRows = docs.map((d) => {
    const row: Record<string, unknown> = {};
    for (const k of Object.keys(projection)) {
      if (k in d) row[k] = d[k];
    }
    // lock_key 1.0 SKIP — 자동 정정
    row.gimmick_lock_key = 0;
    // iron_wall_mode=pf_wall 시 designer_note에 [mode=pf_wall] inject
    if (ironWallMode === "pf_wall") {
      row.designer_note = String(row.designer_note || "") + "\n[mode=pf_wall]";
    }
    return row;
  });

  const jobs = db.collection(JOBS_COLLECTION);
  const now = new Date().toISOString();
  const doc = {
    created_at: now,
    created_by_email: email.toLowerCase(),
    csv_rows: csvRows,
    csv_source: `${source} (n=${docs.length}${ironWallMode === "pf_wall" ? ", pf_wall" : ""})`,
    source_collection: source,
    source_filter: filter,
    row_count: csvRows.length,
    allow_escalation: allowEscalation,
    keep_all_candidates: keepAllCandidates,
    iron_wall_mode: ironWallMode,
    status: "pending",
  };
  const inserted = await jobs.insertOne(doc);
  const id = String(inserted.insertedId);

  // Mother watcher spawn (field-complete API와 동일 로직)
  const watcherDir = process.env.WATCHER_DIR || "/home/aimed/.hermes/watcher";
  const pythonBin = process.env.WATCHER_PYTHON || "/home/aimed/.hermes/watcher/venv/bin/python";
  const logDir = process.env.FIELD_COMPLETE_LOG_DIR || "/home/aimed/.hermes/logs";
  const autoRun = (process.env.FIELD_COMPLETE_AUTO_RUN ?? "1") !== "0";

  if (autoRun) {
    try {
      const logPath = `${logDir}/field_complete_${id}.log`;
      try { mkdirSync(dirname(logPath), { recursive: true }); } catch { /* exists */ }
      const out = openSync(logPath, "a");
      const child = spawn(
        pythonBin,
        ["field_complete_levels.py", "--request", id],
        {
          cwd: watcherDir,
          detached: true,
          stdio: ["ignore", out, out],
          env: process.env,
        },
      );
      child.on("error", (e) => { console.error(`[fc-from-coll ${id}] spawn error:`, e); });
      child.unref();
    } catch (e) {
      const msg = String(e);
      await jobs.updateOne(
        { _id: inserted.insertedId },
        { $set: { status: "failed", error: `spawn failed: ${msg}`, finished_at: new Date().toISOString() } },
      );
      return NextResponse.json({ error: `실행 실패: ${msg}` }, { status: 500 });
    }
  }

  return NextResponse.json({
    ok: true,
    id,
    row_count: csvRows.length,
    source: doc.csv_source,
    log_path: autoRun ? `${logDir}/field_complete_${id}.log` : undefined,
  });
}
