import { NextRequest, NextResponse } from "next/server";
import {
  generateImageV2Start,
  pollBackgroundJob,
} from "@/lib/pixellab";
import { snapImageToGridAndPaletteV2 } from "@/lib/snapToGridV2";
import { koToEn } from "@/lib/translate";
import { getDb } from "@/lib/mongodb";
import sharp from "sharp";

export const runtime = "nodejs";
export const maxDuration = 300; // PixelLab v2 polling typically 30~120s

// Hermes 전용 — PixelLab generate-image-v2 → poll → snap-to-grid 후 cells matrix를 반환.
// 인증: Bearer HERMES_INTERNAL_API_KEY
//
// Request body:
//   { prompt: string, width?: number (default 20), height?: number (default 20),
//     num_colors?: number (default 5), allowed_ids?: number[] (PixelForge 1..28),
//     transparent_bg?: boolean }
//
// Response:
//   { ok: true, cells: number[][] (-1=empty, 0..23=BalloonFlow color),
//     palette_balloonflow: number[], width, height, filled,
//     image_base64: string (snapped PNG), pipeline: string, pixellab_job_id }

export async function POST(req: NextRequest) {
  // 1) Auth
  const authH = (req.headers.get("authorization") || "").trim();
  const presented = authH.toLowerCase().startsWith("bearer ") ? authH.slice(7).trim() : "";
  const expected = process.env.HERMES_INTERNAL_API_KEY || "";
  if (!expected || presented !== expected) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  // 2) Parse body
  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }
  const prompt = String(body.prompt || "").trim();
  if (!prompt) {
    return NextResponse.json({ ok: false, error: "prompt required" }, { status: 400 });
  }
  const width = Math.max(16, Math.min(64, Number(body.width) || 20));
  const height = Math.max(16, Math.min(64, Number(body.height) || 20));
  const numColors = body.num_colors ? Math.max(2, Math.min(16, Number(body.num_colors))) : 5;
  // PixelForge 1..28 / BalloonFlow 첫 24색만 안전 (id 25..28은 BalloonFlow에 없음)
  const allowedPF: number[] = Array.isArray(body.allowed_ids) && (body.allowed_ids as unknown[]).length > 0
    ? (body.allowed_ids as number[]).filter(n => Number.isInteger(n) && n >= 1 && n <= 24)
    : Array.from({ length: 24 }, (_, i) => i + 1);
  const transparentBg = Boolean(body.transparent_bg);

  // 3) Get PixelLab key from settings
  const db = await getDb();
  const keyDoc = await db.collection("pixelforge_settings").findOne({ key: "pixellab_api_key" });
  const apiKey = (keyDoc?.value as string) || "";
  if (!apiKey) {
    return NextResponse.json(
      { ok: false, error: "pixellab_api_key not in pixelforge_settings — upsert first" },
      { status: 500 },
    );
  }

  // 4) Style image (옵션)
  const styleDoc = await db.collection("pixelforge_settings").findOne({ key: "style_image" });
  const hasStyle = Boolean(styleDoc?.base64);

  // 5) Start PixelLab generate-image-v2 (한국어 prompt는 영문으로 자동 번역)
  const promptEn = await koToEn(prompt);
  let jobId: string;
  try {
    const r = await generateImageV2Start(promptEn, width, height, {
      apiKey,
      noBackground: transparentBg,
      styleImageBase64: hasStyle ? (styleDoc!.base64 as string) : undefined,
      styleImageWidth: hasStyle ? ((styleDoc!.width as number) || 64) : undefined,
      styleImageHeight: hasStyle ? ((styleDoc!.height as number) || 64) : undefined,
    });
    jobId = r.jobId;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: `pixellab start: ${msg}` }, { status: 502 });
  }

  // 6) Poll until completed (or 3 min timeout)
  const startMs = Date.now();
  const maxWaitMs = 180_000;
  let lastResp: Record<string, unknown> | null = null;
  while (Date.now() - startMs < maxWaitMs) {
    let r: { status: string; lastResponse: Record<string, unknown> | null };
    try {
      r = await pollBackgroundJob(jobId, apiKey, { maxWaitMs: 5000, intervalMs: 2000 });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return NextResponse.json({ ok: false, error: `pixellab poll: ${msg}`, jobId }, { status: 502 });
    }
    if (r.status === "completed") {
      lastResp = r.lastResponse;
      break;
    }
    if (r.status === "failed" || r.status === "error") {
      return NextResponse.json({ ok: false, error: "pixellab job failed", jobId, status: r.status }, { status: 502 });
    }
    // still processing — 다음 폴
  }
  if (!lastResp) {
    return NextResponse.json({ ok: false, error: "pixellab timeout (3min)", jobId }, { status: 504 });
  }

  // 7) raw → PNG base64 추출
  type RawImg = { width?: number; height?: number; base64?: string };
  async function rawToPng(img?: RawImg): Promise<string> {
    if (!img?.base64 || !img.width || !img.height) return "";
    const rawBuf = Buffer.from(img.base64, "base64");
    const expRgba = img.width * img.height * 4;
    const expRgb = img.width * img.height * 3;
    let channels: 3 | 4 = 4;
    if (rawBuf.length === expRgb) channels = 3;
    else if (rawBuf.length !== expRgba) return "";
    const png = await sharp(rawBuf, { raw: { width: img.width, height: img.height, channels } })
      .png({ compressionLevel: 6 })
      .toBuffer();
    return png.toString("base64");
  }

  let pngB64 = "";
  const qImages = lastResp.quantized_images as RawImg[] | undefined;
  if (Array.isArray(qImages) && qImages[0]) pngB64 = await rawToPng(qImages[0]);
  if (!pngB64) {
    const images = lastResp.images as RawImg[] | undefined;
    if (Array.isArray(images) && images[0]) pngB64 = await rawToPng(images[0]);
  }
  if (!pngB64) {
    return NextResponse.json({ ok: false, error: "no image data from pixellab", jobId }, { status: 502 });
  }

  // 8) Snap to grid → matrix (PixelForge id: 0=empty, 1..28=color)
  let snapped: Awaited<ReturnType<typeof snapImageToGridAndPaletteV2>>;
  try {
    snapped = await snapImageToGridAndPaletteV2(pngB64, {
      cols: width, rows: height,
      allowedIds: allowedPF,
      transparentBg,
      targetColorCount: numColors,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: `snap failed: ${msg}` }, { status: 500 });
  }

  // 9) PixelForge matrix → BalloonFlow cells 변환 (1-based 1..28 → 0-based 0..23, 0→-1=empty)
  // 25..28은 BalloonFlow에 없는 색 — empty(-1)로 떨어뜨림 (allowedIds로 이미 1..24 제한)
  const cells: number[][] = snapped.matrix.map(row =>
    row.map(v => (v === 0 || v > 24 ? -1 : v - 1)),
  );
  let filled = 0;
  const usedBF = new Set<number>();
  for (const row of cells) for (const v of row) if (v >= 0) { filled++; usedBF.add(v); }
  const palette_balloonflow = Array.from(usedBF).sort((a, b) => a - b);

  return NextResponse.json({
    ok: true,
    cells,
    palette_balloonflow,
    width,
    height,
    filled,
    image_base64: pngB64,
    pipeline: snapped.stats.pipeline,
    pixellab_job_id: jobId,
    prompt_translated: promptEn,
  });
}
