import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { ObjectId } from "mongodb";
import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

export const runtime = "nodejs";

/**
 * v43 job 상세 + 모든 PNG base64 — 모달 미리보기용.
 * GET /api/agents/v43-batch/[id]/preview
 *
 * 보안: 로그인 + 디렉토리 트래버설 방지 (out_dir 외부 파일 거부).
 */
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  let jobObjId: ObjectId;
  try { jobObjId = new ObjectId(id); }
  catch { return NextResponse.json({ error: "invalid id" }, { status: 400 }); }

  const db = await getDb();
  const job = await db.collection("pixelforge_v43_jobs").findOne({ _id: jobObjId });
  if (!job) return NextResponse.json({ error: "not found" }, { status: 404 });

  // evaluation.json 로드
  let evaluation: unknown = null;
  if (job.eval_path && existsSync(String(job.eval_path))) {
    try { evaluation = JSON.parse(readFileSync(String(job.eval_path), "utf-8")); }
    catch { /* ignore */ }
  }

  // out_dir 의 PNG 들 base64 로 (필요 시 무거우니 lv별 list 만)
  const pngs: Array<{ filename: string; level: number; label: string; metaphor: string; base64: string }> = [];
  if (job.out_dir && existsSync(String(job.out_dir))) {
    const dir = String(job.out_dir);
    // 보안: dir 가 V43_OUT_BASE 하위인지 검증
    const allowedBase = process.env.V43_OUT_BASE || "/home/aimed/.hermes/v43_out";
    if (!dir.startsWith(allowedBase)) {
      return NextResponse.json({ error: "out_dir not allowed" }, { status: 403 });
    }
    const files = readdirSync(dir).filter((f) => f.endsWith(".png"));
    for (const f of files) {
      const m = f.match(/^level_(\d+)_(.+)_([A-E])\.png$/);
      if (!m) continue;
      const level = Number(m[1]);
      const metaphor = m[2].replace(/_/g, " ");
      const label = m[3];
      const buf = readFileSync(join(dir, f));
      pngs.push({
        filename: f, level, label, metaphor,
        base64: buf.toString("base64"),
      });
    }
    pngs.sort((a, b) => a.level - b.level || a.label.localeCompare(b.label));
  }

  return NextResponse.json({
    _id: String(job._id),
    status: job.status,
    label: job.label,
    source_job: job.source_job,
    created_at: job.created_at,
    started_at: job.started_at,
    finished_at: job.finished_at,
    created_by_email: job.created_by_email,
    target_levels: job.target_levels,
    n_seeds: job.n_seeds,
    n_final: job.n_final,
    total_levels: job.total_levels,
    out_dir: job.out_dir,
    error: job.error,
    evaluation,
    pngs,
    png_count: pngs.length,
  });
}
