import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { spawn } from "child_process";
import { openSync, mkdirSync } from "fs";
import { dirname } from "path";

export const runtime = "nodejs";

/**
 * Batch level generation — pixelforge_batch_requests 관리.
 *
 * GET  : 최근 30개 request + 종합 통계 + dedup 비율
 * POST : 새 request 생성. 응답에 SSH 명령어 포함 → 사용자가 watcher에 SSH 들어가 직접 실행.
 *
 * batch_requests doc:
 *   _id, created_at, created_by_email,
 *   mood, style, count, size, n_colors, start_idx,
 *   width?, height? (size 빈 값일 때),
 *   status: "pending" | "running" | "done" | "failed",
 *   started_at, finished_at,
 *   totals: { ok, fail, dedup_skip, duration_sec },
 *   result_summary: [{label, ok, fail, dedup_skip, duration_sec}, ...],
 *   error?,
 */

const MOOD_OPTIONS = ["warm", "cool", "pastel", "vivid", "all", "random"] as const;
const STYLE_OPTIONS = ["", "kaleidoscope", "tile", "organic", "motif", "all"] as const;
const SIZE_OPTIONS = ["", "small", "medium", "large", "tall", "wide", "mixed", "custom"] as const;

type Mood = (typeof MOOD_OPTIONS)[number];
type Style = (typeof STYLE_OPTIONS)[number];
type Size = (typeof SIZE_OPTIONS)[number];

export async function GET() {
  const db = await getDb();
  const requests = db.collection("pixelforge_batch_requests");
  const levels = db.collection("pixelforge_grid_levels");

  // Stale check — running 60분+ + 프로세스 없음 → auto-mark failed
  // (Art batch는 cowork process_level이 오래 걸리므로 60분으로 늘림)
  const staleThreshold = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  await requests.updateMany(
    {
      status: "running",
      started_at: { $lt: staleThreshold, $exists: true },
    },
    {
      $set: {
        status: "failed",
        error: "auto-cleanup: process died (running > 60min without progress)",
        finished_at: new Date().toISOString(),
        auto_cleaned: true,
      },
    },
  );

  // csv_rows는 클라이언트로 안 내림 — 메타데이터만 (count는 보존)
  const recent = await requests
    .find({}, { projection: { csv_rows: 0 } })
    .sort({ created_at: -1 })
    .limit(30)
    .toArray();

  // 전체 dedup 통계 — pixelforge_grid_levels의 structure_hash 분포
  // 같은 structure_hash 그룹에 2건 이상 있을 수는 없음(저장 단계에서 차단).
  // 단, 그룹별 카운트는 항상 1. 대신 batch_meta.style/mood/size 별 분포 집계.
  const totalLevels = await levels.estimatedDocumentCount();
  const bySize = await levels
    .aggregate([
      { $group: { _id: { w: "$width", h: "$height" }, count: { $sum: 1 } } },
      { $sort: { count: -1 } },
    ])
    .toArray();
  const byStyle = await levels
    .aggregate([
      { $match: { "batch_meta.style": { $ne: null } } },
      { $group: { _id: "$batch_meta.style", count: { $sum: 1 } } },
      { $sort: { count: -1 } },
    ])
    .toArray();
  const byMood = await levels
    .aggregate([
      { $match: { mood: { $ne: null } } },
      { $group: { _id: "$mood", count: { $sum: 1 } } },
      { $sort: { count: -1 } },
    ])
    .toArray();

  // request 전체 dedup 비율
  const reqAgg = await requests
    .aggregate([
      { $match: { totals: { $exists: true } } },
      {
        $group: {
          _id: null,
          ok: { $sum: "$totals.ok" },
          dedup: { $sum: "$totals.dedup_skip" },
          fail: { $sum: "$totals.fail" },
        },
      },
    ])
    .toArray();
  const totals = reqAgg[0] || { ok: 0, dedup: 0, fail: 0 };

  return NextResponse.json({
    requests: recent.map((r) => ({
      _id: String(r._id),
      created_at: r.created_at,
      created_by_email: r.created_by_email,
      mood: r.mood,
      style: r.style,
      size: r.size,
      width: r.width,
      height: r.height,
      count: r.count,
      n_colors: r.n_colors,
      start_idx: r.start_idx,
      status: r.status,
      started_at: r.started_at,
      finished_at: r.finished_at,
      totals: r.totals,
      result_summary: r.result_summary,
      error: r.error,
    })),
    stats: {
      total_levels: totalLevels,
      by_size: bySize.map((b) => ({
        width: b._id?.w,
        height: b._id?.h,
        count: b.count,
      })),
      by_style: byStyle.map((b) => ({ style: b._id, count: b.count })),
      by_mood: byMood.map((b) => ({ mood: b._id, count: b.count })),
      request_totals: {
        ok: totals.ok || 0,
        dedup_skip: totals.dedup || 0,
        fail: totals.fail || 0,
      },
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

  // CSV 모드: csv_rows[]가 있으면 mood/style/size 무시
  const csvRows = Array.isArray(body.csv_rows) ? (body.csv_rows as Record<string, unknown>[]) : [];
  const csvSource = String(body.csv_source ?? "csv");

  const mood = String(body.mood ?? "random") as Mood;
  const style = String(body.style ?? "") as Style;
  const size = String(body.size ?? "medium") as Size;
  const count = Math.max(1, Math.min(2000, parseInt(String(body.count ?? "100"), 10) || 100));
  const n_colors = Math.max(2, Math.min(8, parseInt(String(body.n_colors ?? "4"), 10) || 4));
  const start_idx = Math.max(0, parseInt(String(body.start_idx ?? "0"), 10) || 0);
  const width = Math.max(5, Math.min(60, parseInt(String(body.width ?? "25"), 10) || 25));
  const height = Math.max(5, Math.min(60, parseInt(String(body.height ?? "25"), 10) || 25));
  const allow_duplicate = body.allow_duplicate === true;

  if (csvRows.length === 0) {
    if (!MOOD_OPTIONS.includes(mood)) {
      return NextResponse.json({ error: `invalid mood: ${mood}` }, { status: 400 });
    }
    if (!STYLE_OPTIONS.includes(style)) {
      return NextResponse.json({ error: `invalid style: ${style}` }, { status: 400 });
    }
    if (!SIZE_OPTIONS.includes(size)) {
      return NextResponse.json({ error: `invalid size: ${size}` }, { status: 400 });
    }
  } else if (csvRows.length > 5000) {
    return NextResponse.json({ error: `csv_rows too large (max 5000, got ${csvRows.length})` }, { status: 400 });
  }

  const db = await getDb();
  const requests = db.collection("pixelforge_batch_requests");

  const now = new Date().toISOString();
  const doc: Record<string, unknown> = {
    created_at: now,
    created_by_email: email.toLowerCase(),
    status: "pending",
  };
  doc.allow_duplicate = allow_duplicate;
  if (csvRows.length > 0) {
    doc.csv_rows = csvRows;
    doc.csv_source = csvSource;
    doc.count = csvRows.length;
  } else {
    // 'custom'은 watcher에서 W/H 직접 사용 (size 빈 값 동치)
    const effectiveSize = size === "custom" ? "" : size;
    doc.mood = mood;
    doc.style = style;
    doc.size = effectiveSize;
    doc.count = count;
    doc.n_colors = n_colors;
    doc.start_idx = start_idx;
    if (!effectiveSize) {
      doc.width = width;
      doc.height = height;
    }
  }
  const inserted = await requests.insertOne(doc);
  const id = String(inserted.insertedId);

  const watcherDir = process.env.WATCHER_DIR || "/home/aimed/.hermes/watcher";
  const pythonBin = process.env.WATCHER_PYTHON || "/home/aimed/.hermes/watcher/venv/bin/python";
  const logDir = process.env.BATCH_LOG_DIR || "/home/aimed/.hermes/logs";

  // 자동 실행 — projecthub-web도 Mother에서 도니까 같은 머신에서 spawn
  const autoRun = (process.env.BATCH_AUTO_RUN ?? "1") !== "0";

  if (autoRun) {
    try {
      const logPath = `${logDir}/batch_${id}.log`;
      try { mkdirSync(dirname(logPath), { recursive: true }); } catch { /* exists */ }
      const out = openSync(logPath, "a");
      const child = spawn(
        pythonBin,
        ["batch_generate_levels.py", "--request", id],
        {
          cwd: watcherDir,
          detached: true,
          stdio: ["ignore", out, out],
          env: process.env,
        },
      );
      child.on("error", (e) => { console.error(`[batch ${id}] spawn error:`, e); });
      child.unref();
    } catch (e) {
      const msg = String(e);
      console.error(`[batch ${id}] failed to auto-spawn:`, e);
      await requests.updateOne(
        { _id: inserted.insertedId },
        { $set: { status: "failed", error: `spawn failed: ${msg}`, finished_at: new Date().toISOString() } },
      );
      return NextResponse.json({ error: `실행 실패: ${msg}` }, { status: 500 });
    }
  }

  return NextResponse.json({
    ok: true,
    id,
    log_path: autoRun ? `${logDir}/batch_${id}.log` : undefined,
  });
}
