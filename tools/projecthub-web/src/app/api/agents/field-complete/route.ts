import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { spawn } from "child_process";
import { openSync, mkdirSync } from "fs";
import { dirname } from "path";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";

/**
 * Field Completer job — pixelforge_field_complete_jobs 관리.
 *
 * POST  : 새 job 생성 + Mother watcher spawn (field_complete_levels.py)
 * GET   : 최근 30개 job + 종합 통계
 * GET ?id=... : 특정 job 결과
 *
 * 본 명세 §3-10 알고리즘을 Python watcher가 실행, 결과를 pixelforge_levels에 upsert.
 */

const JOBS_COLLECTION = "pixelforge_field_complete_jobs";

export async function GET(req: NextRequest) {
  const session = await auth();
  if (!session?.user?.email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = new URL(req.url);
  const id = url.searchParams.get("id");
  const db = await getDb();
  const jobs = db.collection(JOBS_COLLECTION);

  // 단건 조회
  if (id) {
    try {
      const doc = await jobs.findOne({ _id: new ObjectId(id) });
      if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });
      // csv_rows에서 image_base64 + level_number만 추출 (전체 전송은 무거움)
      // + CSV 명시 gimmick 카운트 (필드 + 큐) — 모달 표시용.
      const csvRowImages: { level_number?: number; image_base64?: string }[] = [];
      const csvRowGimmicks: Record<number, {
        bl_metaphor?: string;
        field: Record<string, number>;
        queue: Record<string, number>;
      }> = {};
      const FIELD_GIMS = ["gimmick_pinata", "gimmick_pin", "gimmick_surprise",
                          "gimmick_wall", "gimmick_pinata_box", "gimmick_ice",
                          "gimmick_curtain", "gimmick_snake"];
      const QUEUE_GIMS = ["gimmick_hidden", "gimmick_chain", "gimmick_glass_pipe",
                          "gimmick_spawner_o", "gimmick_spawner_t",
                          "gimmick_frozen_dart", "gimmick_lock_key"];
      for (const cr of ((doc.csv_rows as Record<string, unknown>[]) || [])) {
        const lv = Number(cr.level_number);
        if (!Number.isFinite(lv)) continue;
        if (cr.image_base64) {
          csvRowImages.push({ level_number: lv, image_base64: String(cr.image_base64) });
        }
        const field: Record<string, number> = {};
        const queue: Record<string, number> = {};
        for (const k of FIELD_GIMS) { const v = Number(cr[k] ?? 0); if (v > 0) field[k] = v; }
        for (const k of QUEUE_GIMS) { const v = Number(cr[k] ?? 0); if (v > 0) queue[k] = v; }
        csvRowGimmicks[lv] = {
          bl_metaphor: String(cr.bl_metaphor ?? ""),
          field, queue,
        };
      }
      return NextResponse.json({
        _id: String(doc._id),
        created_at: doc.created_at,
        created_by_email: doc.created_by_email,
        csv_source: doc.csv_source,
        status: doc.status,
        started_at: doc.started_at,
        finished_at: doc.finished_at,
        totals: doc.totals,
        results: doc.results,
        error: doc.error,
        row_count: (doc.csv_rows as unknown[] | undefined)?.length ?? 0,
        input_images: csvRowImages,
        csv_row_gimmicks: csvRowGimmicks,
      });
    } catch {
      return NextResponse.json({ error: "invalid id" }, { status: 400 });
    }
  }

  // Stale check — running 30분+ + 프로세스 없음 → auto-mark failed
  const staleThreshold = new Date(Date.now() - 30 * 60 * 1000).toISOString();
  await jobs.updateMany(
    {
      status: "running",
      started_at: { $lt: staleThreshold, $exists: true },
    },
    {
      $set: {
        status: "failed",
        error: "auto-cleanup: process died (running > 30min without progress)",
        finished_at: new Date().toISOString(),
        auto_cleaned: true,
      },
    },
  );

  // 목록 + 통계
  const recent = await jobs
    .find({}, { projection: { csv_rows: 0, results: 0 } })
    .sort({ created_at: -1 })
    .limit(30)
    .toArray();

  const agg = await jobs
    .aggregate([
      { $match: { totals: { $exists: true } } },
      {
        $group: {
          _id: null,
          jobs: { $sum: 1 },
          ok: { $sum: "$totals.ok" },
          fail: { $sum: "$totals.fail" },
          escalated: { $sum: "$totals.escalated" },
          avg_score: { $avg: "$totals.avg_score" },
        },
      },
    ])
    .toArray();
  const totals = agg[0] || { jobs: 0, ok: 0, fail: 0, escalated: 0, avg_score: 0 };

  return NextResponse.json({
    jobs: recent.map((r) => ({
      _id: String(r._id),
      created_at: r.created_at,
      created_by_email: r.created_by_email,
      csv_source: r.csv_source,
      status: r.status,
      started_at: r.started_at,
      finished_at: r.finished_at,
      totals: r.totals,
      error: r.error,
    })),
    stats: {
      jobs: totals.jobs || 0,
      ok: totals.ok || 0,
      fail: totals.fail || 0,
      escalated: totals.escalated || 0,
      avg_score: totals.avg_score || 0,
    },
  });
}

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

  const csvRows = Array.isArray(body.csv_rows) ? (body.csv_rows as Record<string, unknown>[]) : [];
  if (csvRows.length === 0) {
    return NextResponse.json({ error: "csv_rows required (1 or more rows)" }, { status: 400 });
  }
  if (csvRows.length > 1000) {
    return NextResponse.json({ error: `csv_rows too large (max 1000, got ${csvRows.length})` }, { status: 400 });
  }

  const csvSource = String(body.csv_source ?? "csv");
  const allowEscalation = body.allow_escalation !== false;  // default true
  const keepAllCandidates = body.keep_all_candidates === true;

  const db = await getDb();
  const jobs = db.collection(JOBS_COLLECTION);

  const now = new Date().toISOString();
  const doc = {
    created_at: now,
    created_by_email: email.toLowerCase(),
    csv_rows: csvRows,
    csv_source: csvSource,
    row_count: csvRows.length,
    allow_escalation: allowEscalation,
    keep_all_candidates: keepAllCandidates,
    status: "pending",
  };
  const inserted = await jobs.insertOne(doc);
  const id = String(inserted.insertedId);

  // Mother watcher spawn
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
      child.on("error", (e) => { console.error(`[field-complete ${id}] spawn error:`, e); });
      child.unref();
    } catch (e) {
      const msg = String(e);
      console.error(`[field-complete ${id}] failed to auto-spawn:`, e);
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
    log_path: autoRun ? `${logDir}/field_complete_${id}.log` : undefined,
  });
}
