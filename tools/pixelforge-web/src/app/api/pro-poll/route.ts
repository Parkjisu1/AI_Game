import { NextRequest, NextResponse } from "next/server";
import { pollBackgroundJob } from "@/lib/pixellab";
import { snapImageToGridAndPalette } from "@/lib/snapToGrid";
import { matrixToFieldMap } from "@/lib/matrixRenderer";
import { getDb } from "@/lib/mongodb";
import sharp from "sharp";

// generate-image-v2 job 1회 폴링 — 클라이언트가 5초마다 호출
// 완료 시: raw→PNG 변환 + snap-to-grid + DB 저장까지 처리
export async function GET(req: NextRequest) {
  try {
    const jobId = req.nextUrl.searchParams.get("jobId");
    const apiKey = req.headers.get("x-pixellab-pro-key") || req.headers.get("x-pixellab-key") || undefined;
    if (!jobId) return NextResponse.json({ ok: false, error: "jobId 필수" }, { status: 400 });

    const result = await pollBackgroundJob(jobId, apiKey, { maxWaitMs: 1000, intervalMs: 500 });

    if (result.status === "completed" && result.lastResponse) {
      const lr = result.lastResponse;

      // 이미지 추출 — raw pixel data → PNG 변환
      let base64 = "";

      async function rawToPng(img: { type?: string; width?: number; height?: number; base64?: string }): Promise<string> {
        if (!img.base64 || !img.width || !img.height) return "";
        const rawBuf = Buffer.from(img.base64, "base64");
        const w = img.width;
        const h = img.height;
        const expectedRgba = w * h * 4;
        const expectedRgb = w * h * 3;
        let channels: 3 | 4 = 4;
        if (rawBuf.length === expectedRgb) channels = 3;
        else if (rawBuf.length === expectedRgba) channels = 4;
        else if (rawBuf.length < expectedRgb) return "";
        const png = await sharp(rawBuf, { raw: { width: w, height: h, channels } })
          .png({ compressionLevel: 6 })
          .toBuffer();
        return png.toString("base64");
      }

      type RawImg = { type?: string; width?: number; height?: number; base64?: string };

      // 1) quantized_images 우선
      const qImages = lr.quantized_images as RawImg[] | undefined;
      if (Array.isArray(qImages) && qImages.length > 0) {
        base64 = await rawToPng(qImages[0]);
      }
      // 2) images fallback
      if (!base64) {
        const images = lr.images as RawImg[] | undefined;
        if (Array.isArray(images) && images.length > 0) {
          base64 = await rawToPng(images[0]);
        }
      }
      // 3) PNG 재귀 탐색
      if (!base64) {
        function findPng(obj: unknown, depth: number = 0): string {
          if (depth > 4) return "";
          if (typeof obj === "string" && obj.startsWith("iVBORw0K")) return obj;
          if (Array.isArray(obj)) { for (const v of obj) { const f = findPng(v, depth + 1); if (f) return f; } }
          if (obj && typeof obj === "object") { for (const v of Object.values(obj as Record<string, unknown>)) { const f = findPng(v, depth + 1); if (f) return f; } }
          return "";
        }
        base64 = findPng(lr);
      }

      if (base64.startsWith("data:")) base64 = base64.split(",")[1] || base64;

      if (!base64) {
        return NextResponse.json({ ok: true, status: "completed", base64: "", error: "이미지 데이터 없음" });
      }

      // ★ snap-to-grid + DB 저장 (job context에서 level 정보 읽기)
      const db = await getDb();
      const jobCtx = await db.collection("pixelforge_jobs").findOne({ jobId });

      if (jobCtx?.level_number) {
        let fieldMap = "";
        let generatedColors: number[] = [];
        try {
          const snapped = await snapImageToGridAndPalette(base64, {
            cols: jobCtx.field_cols || 20,
            rows: jobCtx.field_rows || 20,
            allowedIds: jobCtx.color_ids?.length > 0 ? jobCtx.color_ids : undefined,
            transparentBg: jobCtx.no_background === true,
            targetColorCount: jobCtx.target_color_count > 0 ? jobCtx.target_color_count : undefined,
          });
          fieldMap = matrixToFieldMap(snapped.matrix);
          generatedColors = snapped.stats.dominantColors;
          console.log(`[pro-poll] snap: ${snapped.stats.uniqueColorsBefore}→${snapped.stats.uniqueColorsAfter} colors`);
        } catch (e) {
          console.error("[pro-poll] snap error:", e);
        }

        // DB 저장: 원본 이미지 + fieldMap
        const saveData: Record<string, unknown> = {
          image_base64: base64,
          field_map: fieldMap,
          status: "generated",
          updated_at: new Date().toISOString(),
        };
        if (generatedColors.length > 0) {
          saveData.generated_colors = generatedColors.map((id) => `c${id}:1`).join(",");
          saveData.generated_num_colors = generatedColors.length;
        }
        await db.collection("pixelforge_levels").updateOne(
          { level_number: jobCtx.level_number },
          { $set: saveData },
          { upsert: true }
        );
        console.log(`[pro-poll] saved level ${jobCtx.level_number}, image ${base64.length} bytes`);
      }

      return NextResponse.json({ ok: true, status: "completed", base64 });
    }

    return NextResponse.json({ ok: true, status: result.status });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    if (msg.includes("timeout") || msg.includes("still processing")) {
      return NextResponse.json({ ok: true, status: "processing" });
    }
    return NextResponse.json({ ok: false, status: "error", error: msg }, { status: 500 });
  }
}
