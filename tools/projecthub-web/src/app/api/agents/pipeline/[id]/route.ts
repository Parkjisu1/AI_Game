import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { ObjectId } from "mongodb";
import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";
import { notifyPipelineStage } from "@/lib/pipeline-notify";

export const runtime = "nodejs";

/**
 * Pipeline Session 상세 — 현재 stage 의 데이터 포함.
 *
 * GET /api/agents/pipeline/[id]
 *
 * 반환:
 *   - stage 별 자료 (art evaluation + PNG / curated field_maps / FC totals)
 *   - art_running 시: 최근 log tail (10 라인)
 *   - art_done 시: A/B PNG base64 (모달 큐레이션용)
 *   - field_done 시: FC totals + sample balloons
 *   - done 시: download path
 *
 * 부수효과: art_job/fc_job 의 최신 상태를 fetch 해서 session stage 자동 갱신.
 */

const COLL = "pixelforge_pipeline_sessions";

type Stage =
  | "csv" | "art_running" | "art_done"
  | "curated_pending" | "curated_done"
  | "field_running" | "field_done"
  | "download" | "done" | "failed";

export async function syncSessionStage(db: import("mongodb").Db, sess: Record<string, unknown>): Promise<Record<string, unknown>> {
  // art_job 의 최신 상태로 stage sync
  let updated = false;
  let notifyContext: { total_levels?: number; totals?: Record<string, number>; error?: string } | null = null;
  const updates: Record<string, unknown> = { updated_at: new Date().toISOString() };

  const artJob = sess.art_job as { job_id?: string; status?: string } | undefined;
  if (artJob?.job_id && (sess.stage === "art_running" || !sess.stage)) {
    try {
      const v = await db.collection("pixelforge_v43_jobs").findOne({ _id: new ObjectId(artJob.job_id) });
      if (v && v.status === "done") {
        updates.stage = (sess.auto_advance === false) ? "art_done" : "curated_pending";
        updates["art_job.status"] = "done";
        updates["art_job.finished_at"] = v.finished_at;
        updates["art_job.total_levels"] = v.total_levels;
        updated = true;
        notifyContext = { total_levels: v.total_levels as number | undefined };
      } else if (v && v.status === "failed") {
        updates.stage = "failed";
        updates["art_job.status"] = "failed";
        updates.error = `art job failed: ${v.error || "unknown"}`;
        updated = true;
        notifyContext = { error: String(v.error || "unknown") };
      }
    } catch { /* ignore */ }
  }

  const fcJob = sess.field_complete_job as { job_id?: string; status?: string } | undefined;
  if (fcJob?.job_id && sess.stage === "field_running") {
    try {
      const f = await db.collection("pixelforge_field_complete_jobs").findOne({ _id: new ObjectId(fcJob.job_id) });
      if (f && f.status === "done") {
        updates.stage = "field_done";
        updates["field_complete_job.status"] = "done";
        updates["field_complete_job.finished_at"] = f.finished_at;
        updates["field_complete_job.totals"] = f.totals;
        updated = true;
        notifyContext = { totals: f.totals as Record<string, number> };
      } else if (f && f.status === "failed") {
        updates.stage = "failed";
        updates["field_complete_job.status"] = "failed";
        updates.error = `field job failed: ${f.error || "unknown"}`;
        updated = true;
        notifyContext = { error: String(f.error || "unknown") };
      }
    } catch { /* ignore */ }
  }

  if (updated) {
    await db.collection(COLL).updateOne({ _id: sess._id as ObjectId }, { $set: updates });
    const merged = { ...sess, ...updates };
    // Slack 통지 — stage 전이 시 1회 발송 (dedup 플래그 pipeline-notify 내부 처리).
    // await 하지만 실패는 silently swallow — sync 흐름에 영향 X.
    try {
      await notifyPipelineStage({
        db,
        sess: merged,
        newStage: String(updates.stage),
        context: notifyContext || undefined,
      });
    } catch { /* ignore — 다음 sync 에서 retry */ }
    return merged;
  }
  return sess;
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  let objId: ObjectId;
  try { objId = new ObjectId(id); }
  catch { return NextResponse.json({ error: "invalid id" }, { status: 400 }); }

  const db = await getDb();
  let sess = await db.collection(COLL).findOne({ _id: objId });
  if (!sess) return NextResponse.json({ error: "not found" }, { status: 404 });

  // stage sync
  sess = await syncSessionStage(db, sess) as typeof sess;

  // stage 별 부수 자료
  const { _id: _drop, ...rest } = sess || {};
  void _drop;
  const out: Record<string, unknown> = {
    _id: String(sess?._id),
    ...rest,
  };

  // art_done / curated_pending — PNG + evaluation
  const stage = sess?.stage as Stage | undefined;
  if (stage && ["art_done", "curated_pending", "curated_done", "field_running", "field_done", "download", "done"].includes(stage)) {
    const artJobId = (sess?.art_job as { job_id?: string } | undefined)?.job_id;
    if (artJobId && ObjectId.isValid(artJobId)) {
      const v = await db.collection("pixelforge_v43_jobs").findOne({ _id: new ObjectId(artJobId) });
      if (v?.out_dir && existsSync(String(v.out_dir))) {
        const outDir = String(v.out_dir);
        const allowedBase = process.env.V43_OUT_BASE || "/home/aimed/.hermes/v43_out";
        if (outDir.startsWith(allowedBase)) {
          // evaluation.json
          const evalPath = join(outDir, "evaluation.json");
          if (existsSync(evalPath)) {
            try { out.evaluation = JSON.parse(readFileSync(evalPath, "utf-8")); } catch { /* ignore */ }
          }
          // PNGs (lv × A/B)
          const pngs: Array<{ filename: string; level: number; label: string; metaphor: string; base64: string }> = [];
          try {
            const files = readdirSync(outDir).filter((f) => f.endsWith(".png"));
            for (const f of files) {
              const m = f.match(/^level_(\d+)_(.+)_([A-E])\.png$/);
              if (!m) continue;
              const buf = readFileSync(join(outDir, f));
              pngs.push({
                filename: f, level: Number(m[1]),
                metaphor: m[2].replace(/_/g, " "),
                label: m[3], base64: buf.toString("base64"),
              });
            }
            pngs.sort((a, b) => a.level - b.level || a.label.localeCompare(b.label));
            out.pngs = pngs;
            out.png_count = pngs.length;
          } catch { /* ignore */ }
        }
      }
    }
  }

  // art_running 시 log tail
  if (stage === "art_running") {
    const artJobId = (sess?.art_job as { job_id?: string } | undefined)?.job_id;
    if (artJobId) {
      const logPath = `/home/aimed/.hermes/logs/v43/v43_${artJobId}.log`;
      if (existsSync(logPath)) {
        try {
          const text = readFileSync(logPath, "utf-8");
          const lines = text.split("\n");
          out.log_tail = lines.slice(-15).join("\n");
        } catch { /* ignore */ }
      }
    }
  }

  // field_done 시 — FC sample
  if (stage === "field_done" || stage === "download" || stage === "done") {
    const fcJobId = (sess?.field_complete_job as { job_id?: string } | undefined)?.job_id;
    if (fcJobId && ObjectId.isValid(fcJobId)) {
      const fc = await db.collection("pixelforge_field_complete_jobs").findOne({ _id: new ObjectId(fcJobId) });
      if (fc) {
        out.fc_totals = fc.totals;
        out.fc_results_summary = (fc.results || []).slice(0, 5).map((r: { level_number?: number; ok?: boolean; score?: number; balloons?: unknown[]; gimmicks?: { type?: string }[] }) => ({
          level_number: r.level_number,
          ok: r.ok,
          score: r.score,
          balloons: r.balloons?.length ?? 0,
          gimmicks: r.gimmicks?.length ?? 0,
          gimmick_types: [...new Set((r.gimmicks || []).map((g) => g.type))],
        }));
      }
    }
  }

  return NextResponse.json(out);
}
