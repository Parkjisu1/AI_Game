import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";
export const maxDuration = 300; // 5분 — 큐 생성 41건이 보통 30~60초

/**
 * FC job 의 ok 레벨들에 대해 PixelForge queue-generator 를 호출하여
 * pixelforge_levels.queue_data 를 채움.
 *
 * 호출 흐름 (per level):
 *   1) POST http://127.0.0.1:3002/pixelforge/api/queue/generate { level_number, seed }
 *   2) POST http://127.0.0.1:3002/pixelforge/api/queue/confirm { level_number, queue }
 *
 * Body (optional): { seedBase?: number, force?: boolean, levels?: number[] }
 *   - seedBase: 시작 시드 (없으면 0). 각 레벨 시드 = seedBase + idx
 *   - force: 이미 queue_data 있는 레벨도 재생성 (기본 false → 미생성만)
 *   - levels: 특정 레벨만 대상 (기본 = ok 전체)
 */
const PIXELFORGE_INTERNAL = process.env.PIXELFORGE_INTERNAL_URL || "http://127.0.0.1:3002";

interface FCResult { level_number: number; ok: boolean; balloons?: unknown[]; }

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const { id } = await params;
  let jobObjId: ObjectId;
  try { jobObjId = new ObjectId(id); }
  catch { return NextResponse.json({ error: "invalid id" }, { status: 400 }); }

  const body = (await req.json().catch(() => ({}))) as { seedBase?: number; force?: boolean; levels?: number[] };
  const seedBase = Number(body.seedBase) || 0;
  const force = !!body.force;
  const explicitLevels = Array.isArray(body.levels) ? body.levels.map(Number).filter(Number.isFinite) : null;

  const db = await getDb();
  const job = await db.collection("pixelforge_field_complete_jobs").findOne({ _id: jobObjId });
  if (!job) return NextResponse.json({ error: "job not found" }, { status: 404 });

  const okResults = ((job.results as FCResult[]) || [])
    .filter((r) => r.ok && Array.isArray(r.balloons) && r.balloons.length > 0);
  if (okResults.length === 0) {
    return NextResponse.json({ ok: false, error: "no ok results in this job" }, { status: 400 });
  }

  // 대상 결정 — explicit > job ok 전체
  const targetLevels = explicitLevels
    ? okResults.filter((r) => explicitLevels.includes(r.level_number))
    : okResults;

  // queue_data 보유 여부 필터 (force=false 시 미생성만)
  const designerRows = await db.collection("pixelforge_levels")
    .find({ level_number: { $in: targetLevels.map((r) => r.level_number) } }, { projection: { level_number: 1, queue_data: 1, field_map: 1 } })
    .toArray();
  const designerByLv = new Map(designerRows.map((r) => [Number(r.level_number), r]));

  const toProcess = targetLevels.filter((r) => {
    const row = designerByLv.get(r.level_number);
    if (!row) return false; // 디자이너 행 없으면 스킵
    if (!row.field_map || typeof row.field_map !== "string" || !row.field_map.trim()) return false;
    if (force) return true;
    return !row.queue_data;
  });

  const skipped: Array<{ level_number: number; reason: string }> = [];
  const failed: Array<{ level_number: number; error: string }> = [];
  let generated = 0;
  const startedAt = Date.now();

  for (let idx = 0; idx < toProcess.length; idx++) {
    const r = toProcess[idx];
    const lv = r.level_number;
    const seed = seedBase + idx;
    try {
      // 1) generate
      const genUrl = `${PIXELFORGE_INTERNAL}/pixelforge/api/queue/generate`;
      const genRes = await fetch(genUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level_number: lv, seed }),
      });
      const genJson = await genRes.json();
      if (!genJson.ok) {
        failed.push({ level_number: lv, error: `gen: ${genJson.error || `HTTP ${genRes.status}`}` });
        continue;
      }

      // 2) confirm
      const confUrl = `${PIXELFORGE_INTERNAL}/pixelforge/api/queue/confirm`;
      const confRes = await fetch(confUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level_number: lv, queue: genJson.queue }),
      });
      const confJson = await confRes.json();
      if (!confJson.ok) {
        failed.push({ level_number: lv, error: `confirm: ${confJson.error || `HTTP ${confRes.status}`}` });
        continue;
      }
      generated++;
    } catch (e) {
      failed.push({ level_number: lv, error: (e as Error).message });
    }
  }

  // not-eligible 대상 기록
  for (const r of targetLevels) {
    if (toProcess.includes(r)) continue;
    const row = designerByLv.get(r.level_number);
    if (!row) skipped.push({ level_number: r.level_number, reason: "no designer row" });
    else if (!row.field_map) skipped.push({ level_number: r.level_number, reason: "no field_map" });
    else if (row.queue_data && !force) skipped.push({ level_number: r.level_number, reason: "already has queue_data (use force)" });
  }

  return NextResponse.json({
    ok: true,
    total_targets: targetLevels.length,
    processed: toProcess.length,
    generated,
    failed,
    skipped,
    duration_sec: (Date.now() - startedAt) / 1000,
  });
}
