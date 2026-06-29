import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { ObjectId } from "mongodb";
import { readFileSync, existsSync } from "fs";
import { join } from "path";
// pngjs는 dynamic import (운영 환경에서 lazy load)

export const runtime = "nodejs";

/**
 * 큐레이션 — v43/v47 job 의 A/B 후보 중 하나 선택 → pixelforge_levels 갱신.
 *
 * POST /api/agents/v43-batch/[id]/curate
 * body: { selections: { [level_number]: "A" | "B" | null } }
 *   - "A"/"B": 해당 후보의 PNG 를 grid 디코드 → field_map text → pixelforge_levels 저장
 *   - null: 큐레이션 미선택 (스킵)
 *
 * 처리:
 *   1. PNG 파일 디코드 (각 픽셀의 RGB → BL palette index 매핑)
 *   2. field_map 텍스트 생성 ("01 02 .. 03\n...")
 *   3. pixelforge_levels[level_number].field_map / field_map_source / field_map_pipeline 갱신
 *   4. pixelforge_v43_jobs 에 curated_at / curations 기록
 */

// BalloonFlow 28색 팔레트 (PALETTE order: BL palette ID 1-based = PALETTE.index + 1)
const BL_PALETTE = [
  "#FC6AAF", "#50E8F6", "#8950F8", "#FED555", "#73FE66", "#FDA14C",
  "#FFFFFF", "#414141", "#6EA8FA", "#39AE2E", "#FC5E5E", "#326BF8",
  "#3AA58B", "#E7A7FA", "#B7C7FB", "#6A4A30", "#FEE3A9", "#FDB7C1",
  "#9E3D5E", "#A7DD94", "#592E7E", "#DC7881", "#D9D9E7", "#6F727F",
  "#FC38A5", "#FDB458", "#890A08", "#6FAFB1",
];

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
const PALETTE_RGB = BL_PALETTE.map(hexToRgb);

function nearestPaletteId(r: number, g: number, b: number, a: number): number {
  if (a < 128) return 0; // 투명 → 빈 셀
  let bestIdx = 0, bestDist = Infinity;
  for (let i = 0; i < PALETTE_RGB.length; i++) {
    const [pr, pg, pb] = PALETTE_RGB[i];
    const d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2;
    if (d < bestDist) { bestDist = d; bestIdx = i; }
  }
  return bestIdx + 1; // 1-based
}

async function pngToFieldMap(pngBuffer: Buffer): Promise<{ field_map: string; rows: number; cols: number }> {
  // dynamic import — pngjs 가 설치 안 됐을 가능성 고려
  let PNG: typeof import("pngjs").PNG;
  try {
    PNG = (await import("pngjs")).PNG;
  } catch {
    throw new Error("pngjs 미설치 — npm install pngjs 필요");
  }
  const png = PNG.sync.read(pngBuffer);
  const { width, height, data } = png;
  const rows: string[] = [];
  for (let y = 0; y < height; y++) {
    const cells: string[] = [];
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
      const palId = nearestPaletteId(r, g, b, a);
      cells.push(palId === 0 ? ".." : String(palId).padStart(2, "0"));
    }
    rows.push(cells.join(" "));
  }
  return { field_map: rows.join("\n"), rows: height, cols: width };
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  const email = session?.user?.email || "";
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  let jobObjId: ObjectId;
  try { jobObjId = new ObjectId(id); }
  catch { return NextResponse.json({ error: "invalid id" }, { status: 400 }); }

  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; }
  catch { return NextResponse.json({ error: "invalid json" }, { status: 400 }); }

  const selections = (body.selections || {}) as Record<string, "A" | "B" | null>;
  if (!selections || typeof selections !== "object") {
    return NextResponse.json({ error: "selections required: { [lv]: A|B|null }" }, { status: 400 });
  }

  const db = await getDb();
  const job = await db.collection("pixelforge_v43_jobs").findOne({ _id: jobObjId });
  if (!job) return NextResponse.json({ error: "job not found" }, { status: 404 });
  if (!job.out_dir) return NextResponse.json({ error: "job out_dir missing" }, { status: 400 });

  // 보안: out_dir 가 V43_OUT_BASE 하위인지
  const allowedBase = process.env.V43_OUT_BASE || "/home/aimed/.hermes/v43_out";
  const outDir = String(job.out_dir);
  if (!outDir.startsWith(allowedBase)) return NextResponse.json({ error: "out_dir not allowed" }, { status: 403 });

  // evaluation.json 에서 lv → metaphor 매핑
  let evalArr: Array<{ level: number; metaphor?: string }> = [];
  if (job.eval_path && existsSync(String(job.eval_path))) {
    try { evalArr = JSON.parse(readFileSync(String(job.eval_path), "utf-8")); } catch { /* ignore */ }
  }
  const metaByLv = new Map<number, string>();
  for (const e of evalArr) metaByLv.set(Number(e.level), e.metaphor || "");

  const results: Array<{ level: number; label: string | null; ok: boolean; error?: string;
                         rows?: number; cols?: number }> = [];

  for (const [lvStr, label] of Object.entries(selections)) {
    const lv = Number(lvStr);
    if (!Number.isFinite(lv) || lv <= 0) continue;
    if (!label) { results.push({ level: lv, label: null, ok: false, error: "no selection" }); continue; }
    const meta = (metaByLv.get(lv) || "").replace(/\//g, "_").replace(/ /g, "_").substring(0, 25);
    // 파일명 매칭 — `level_NNN_메타포_X.png`
    const lvPadded = String(lv).padStart(3, "0");
    const candidatePath = join(outDir, `level_${lvPadded}_${meta || "no_meta"}_${label}.png`);
    let pngBuf: Buffer;
    try {
      pngBuf = readFileSync(candidatePath);
    } catch (e) {
      results.push({ level: lv, label, ok: false, error: `PNG not found: ${(e as Error).message}` });
      continue;
    }
    try {
      const { field_map, rows: pngRows, cols: pngCols } = await pngToFieldMap(pngBuf);
      // pixelforge_levels 갱신
      await db.collection("pixelforge_levels").updateOne(
        { level_number: lv, status: { $exists: true } },
        {
          $set: {
            field_map,
            field_rows: pngRows,
            field_columns: pngCols,
            field_map_source: `v47_curated:${label}`,
            field_map_pipeline: "v47_curated",
            field_map_curated_from: { job_id: id, label, png: `level_${lvPadded}_${meta}_${label}.png` },
            field_map_curated_at: new Date().toISOString(),
            field_map_curated_by: email.toLowerCase(),
            updated_at: new Date().toISOString(),
          },
        },
        { upsert: false },
      );
      results.push({ level: lv, label, ok: true, rows: pngRows, cols: pngCols });
    } catch (e) {
      results.push({ level: lv, label, ok: false, error: (e as Error).message });
    }
  }

  // 큐레이션 기록 v43 job 에
  await db.collection("pixelforge_v43_jobs").updateOne(
    { _id: jobObjId },
    {
      $set: {
        curated_at: new Date().toISOString(),
        curated_by: email.toLowerCase(),
        curations: selections,
        curation_results: results,
      },
    },
  );

  const okCount = results.filter((r) => r.ok).length;
  return NextResponse.json({
    ok: true,
    total: results.length,
    success: okCount,
    failed: results.length - okCount,
    results,
  });
}
