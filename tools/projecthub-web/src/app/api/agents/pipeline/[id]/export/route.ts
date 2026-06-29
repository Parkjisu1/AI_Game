import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { ObjectId } from "mongodb";
import JSZip from "jszip";

export const runtime = "nodejs";

/**
 * [2026-06-18] 단계별 레벨 다운로드 — Curate / Queue 결과물.
 * GET /api/agents/pipeline/[id]/export?stage=curate|queue
 *   - curate : field_map (보드만)
 *   - queue  : field_map + queue_data (큐 포함)
 *   - field(완성본)은 기존 /api/agents/field-complete/{fcJobId}/export 사용 (UI가 직접 링크).
 * target_levels 의 레벨 JSON 을 zip 으로 묶어 반환.
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  let objId: ObjectId;
  try { objId = new ObjectId(id); }
  catch { return NextResponse.json({ error: "invalid id" }, { status: 400 }); }

  const stage = new URL(req.url).searchParams.get("stage") || "curate";
  if (stage !== "curate" && stage !== "queue") {
    return NextResponse.json({ error: `unsupported stage: ${stage} (curate|queue). field는 field-complete export 사용` }, { status: 400 });
  }

  const db = await getDb();
  const sess = await db.collection("pixelforge_pipeline_sessions").findOne({ _id: objId });
  if (!sess) return NextResponse.json({ error: "session not found" }, { status: 404 });

  const targetLevels = (sess.target_levels as number[]) || [];
  const rows = await db.collection("pixelforge_levels")
    .find({ level_number: { $in: targetLevels }, status: { $exists: true } })
    .toArray();

  const zip = new JSZip();
  const manifest: { session: string; stage: string; generated_at: string; levels: number[] } = {
    session: String(objId), stage, generated_at: new Date().toISOString(), levels: [],
  };
  let count = 0;
  for (const r of rows) {
    const lv = Number(r.level_number);
    const fm = String(r.field_map ?? "");
    if (!fm.trim()) continue;
    const out: Record<string, unknown> = {
      level_number: lv,
      level_id: r.level_id ?? `BF_${String(lv).padStart(3, "0")}`,
      pkg: r.pkg ?? 0, pos: r.pos ?? 0, chapter: r.chapter ?? 0,
      purpose_type: r.purpose_type ?? "",
      num_colors: r.num_colors ?? 0,
      field_rows: r.field_rows ?? 0, field_columns: r.field_columns ?? 0,
      total_cells: r.total_cells ?? 0,
      queue_columns: r.queue_columns ?? 0, rail_capacity: r.rail_capacity ?? 0,
      color_distribution: r.color_distribution ?? "",
      designer_note: `[Stage ${stage}] Pipeline ${String(objId).slice(-6)}\n[FieldMap]\n${fm}`,
    };
    if (stage === "queue") {
      out.queue_data = r.queue_data ?? null;
      if (r.queue_data) out.has_queue = true;
    }
    zip.file(`Lv${String(lv).padStart(3, "0")}_${stage}.json`, JSON.stringify(out, null, 2));
    manifest.levels.push(lv);
    count++;
  }
  if (count === 0) return NextResponse.json({ error: "no levels with field_map" }, { status: 404 });
  zip.file("_manifest.json", JSON.stringify(manifest, null, 2));

  const buf = await zip.generateAsync({ type: "nodebuffer" });
  return new NextResponse(buf as unknown as BodyInit, {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="Pipeline_${String(objId).slice(-6)}_${stage}.zip"`,
    },
  });
}
