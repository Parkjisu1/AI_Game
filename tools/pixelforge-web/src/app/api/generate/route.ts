import { NextRequest, NextResponse } from "next/server";
import {
  generateImageV2Start,
  generateImagePixflux,
  getBalance,
  type PixelLabView,
  type PixelLabDirection,
  type PixelLabOutline,
  type PixelLabShading,
  type PixelLabDetail,
} from "@/lib/pixellab";
import { parseColorDist } from "@/lib/palette";
import { koToEn } from "@/lib/translate";
import { getDb } from "@/lib/mongodb";
import { snapImageToGridAndPalette } from "@/lib/snapToGrid";
import { matrixToFieldMap } from "@/lib/matrixRenderer";

export const maxDuration = 60;
const BUILD_VERSION = "v5-generate-image-v2";

export async function POST(req: NextRequest) {
  try {
    const {
      level_number, prompt, width, height, color_distribution, level_data, no_background,
      use_color_limit,
      mode: clientMode,
      view, direction, outline, shading, detail, isometric,
      text_guidance_scale: clientGuidance,
    } = await req.json();
    const rawKeyHeader = req.headers.get("x-pixellab-key");
    const apiKey = rawKeyHeader || undefined;
    const proApiKey = req.headers.get("x-pixellab-pro-key") || undefined;

    if (!apiKey && !proApiKey) {
      return NextResponse.json({
        ok: false,
        error: "API 키가 없음 — 우상단 ⚙️에서 키 입력 필요",
      }, { status: 400 });
    }

    const translatedPrompt = await koToEn(prompt || "pixel art");
    const colorIds = parseColorDist(color_distribution || "");
    const applyColorLimit = use_color_limit !== false;
    const targetColorCount = applyColorLimit ? (Number(level_data?.num_colors) || 0) : 0;
    const db = await getDb();

    const fieldCols = level_data?.field_columns || 20;
    const fieldRows = level_data?.field_rows || 20;

    // generate-image-v2: max 792×688 — 그리드 배수로 최대한 크게
    const maxW = 792;
    const maxH = 688;
    const ppcW = Math.floor(maxW / fieldCols);
    const ppcH = Math.floor(maxH / fieldRows);
    const ppc = Math.max(2, Math.min(ppcW, ppcH)); // 양쪽 다 맞는 최대 ppc
    const genW = Math.min(maxW, fieldCols * ppc);
    const genH = Math.min(maxH, fieldRows * ppc);

    // style_image 조회
    const styleDoc = await db.collection("pixelforge_settings").findOne({ key: "style_image" });
    const hasStyleImage = Boolean(styleDoc?.base64);

    // ★ generate-image-v2 사용 (Pro key 우선, 없으면 Free key)
    const effectiveKey = proApiKey || apiKey;

    console.log("[Generate] v2", {
      level_number, genW, genH, ppc, fieldCols, fieldRows,
      hasStyleImage, keyType: proApiKey ? "pro" : "free",
      translated: translatedPrompt,
    });

    try {
      // generate-image-v2 (async) — style_options.color_palette: false
      const { jobId, usage } = await generateImageV2Start(
        translatedPrompt, genW, genH,
        {
          apiKey: effectiveKey,
          noBackground: no_background === true,
          styleImageBase64: hasStyleImage ? (styleDoc!.base64 as string) : undefined,
          styleImageWidth: hasStyleImage ? (styleDoc!.width as number) || 64 : undefined,
          styleImageHeight: hasStyleImage ? (styleDoc!.height as number) || 64 : undefined,
        }
      );

      // level context를 DB에 저장 (pro-poll에서 snap할 때 사용)
      await db.collection("pixelforge_jobs").updateOne(
        { jobId },
        { $set: {
          jobId,
          level_number,
          field_cols: fieldCols,
          field_rows: fieldRows,
          color_ids: colorIds,
          target_color_count: targetColorCount,
          no_background: no_background === true,
          created_at: new Date().toISOString(),
        }},
        { upsert: true }
      );

      return NextResponse.json({
        ok: true,
        mode: "v2_async",
        proJobId: jobId,
        usage,
        level_number,
        _v: BUILD_VERSION,
        _gen_size: `${genW}x${genH}`,
      });
    } catch (v2Error) {
      // v2 실패 시 pixflux fallback
      const v2Msg = v2Error instanceof Error ? v2Error.message : String(v2Error);
      console.warn("[Generate] v2 failed, falling back to pixflux:", v2Msg);

      // pixflux: max 400px
      const pxPpc = Math.max(2, Math.floor(384 / Math.max(fieldCols, fieldRows)));
      const pxW = Math.min(400, Math.max(64, fieldCols * pxPpc));
      const pxH = Math.min(400, Math.max(64, fieldRows * pxPpc));

      // 패턴/모티프 분류
      const mode = clientMode === "pattern" || clientMode === "motif"
        ? clientMode : detectMode(prompt || "");

      const style = mode === "pattern"
        ? { view: (view as PixelLabView) ?? ("high top-down" as const), outline: (outline as PixelLabOutline) ?? ("single color outline" as const), shading: (shading as PixelLabShading) ?? ("flat shading" as const), detail: (detail as PixelLabDetail) ?? ("medium detail" as const), isometric: typeof isometric === "boolean" ? isometric : false, textGuidanceScale: typeof clientGuidance === "number" ? clientGuidance : 12 }
        : { view: (view as PixelLabView) ?? ("side" as const), direction: (direction as PixelLabDirection) ?? ("south" as const), outline: (outline as PixelLabOutline) ?? ("selective outline" as const), shading: (shading as PixelLabShading) ?? ("basic shading" as const), detail: (detail as PixelLabDetail) ?? ("highly detailed" as const), textGuidanceScale: typeof clientGuidance === "number" ? clientGuidance : 12 };

      const result = await generateImagePixflux(translatedPrompt, pxW, pxH, {
        apiKey: effectiveKey,
        noBackground: no_background === true,
        ...style,
      });

      // snap-to-grid
      const displayBase64 = result.base64;
      let fieldMap = "";
      let finalColorIds: number[] = colorIds;
      try {
        const snapped = await snapImageToGridAndPalette(result.base64, {
          cols: fieldCols, rows: fieldRows,
          allowedIds: colorIds.length > 0 ? colorIds : undefined,
          transparentBg: no_background === true,
          targetColorCount: targetColorCount > 0 ? targetColorCount : undefined,
        });
        fieldMap = matrixToFieldMap(snapped.matrix);
        finalColorIds = snapped.stats.dominantColors;
      } catch (e) { console.error("[Generate] snap error:", e); }

      // DB 저장
      if (level_number) {
        const saveData: Record<string, unknown> = {
          level_number, image_base64: displayBase64, field_map: fieldMap,
          status: "generated", updated_at: new Date().toISOString(),
        };
        if (level_data) {
          const fields = [
            "level_id","pkg","pos","chapter","purpose_type","target_cr","target_attempts",
            "field_rows","field_columns","total_cells",
            "rail_capacity","rail_capacity_tier","queue_columns","queue_rows",
            "gimmick_hidden","gimmick_chain","gimmick_pinata","gimmick_spawner_t",
            "gimmick_pin","gimmick_lock_key","gimmick_surprise","gimmick_wall",
            "gimmick_spawner_o","gimmick_pinata_box","gimmick_ice","gimmick_frozen_dart",
            "gimmick_curtain","total_darts","dart_capacity_range","emotion_curve",
            "designer_note","pixel_art_source",
          ];
          for (const f of fields) {
            if (level_data[f] !== undefined && level_data[f] !== null) saveData[f] = level_data[f];
          }
        }
        if (finalColorIds.length > 0) {
          saveData.generated_colors = finalColorIds.map((id) => `c${id}:1`).join(",");
          saveData.generated_num_colors = finalColorIds.length;
        }
        await db.collection("pixelforge_levels").updateOne(
          { level_number }, { $set: saveData }, { upsert: true }
        );
      }

      return NextResponse.json({
        ok: true, base64: displayBase64, usage: result.usage,
        translated_prompt: translatedPrompt,
        field_map: fieldMap ? "generated" : "failed",
        _v: BUILD_VERSION, _fallback: "pixflux", _v2_error: v2Msg.substring(0, 100),
      });
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    const stack = e instanceof Error && e.stack ? e.stack.split("\n").slice(0, 4).join(" | ") : "";
    console.error("[generate]", msg, stack);
    return NextResponse.json({ ok: false, error: msg, stack }, { status: 500 });
  }
}

function detectMode(prompt: string): "pattern" | "motif" {
  const lower = prompt.toLowerCase();
  const kw = ["pattern","tile","grid","checker","lattice","mandala","honeycomb","stripe","weave","geometric","tessellation","symmetry","spiral","concentric","패턴","타일","격자","만화경","벌집","대칭","반복","기하학"];
  return kw.some((k) => lower.includes(k)) ? "pattern" : "motif";
}

export async function GET(req: NextRequest) {
  try {
    const apiKey = req.headers.get("x-pixellab-key") || undefined;
    const balance = await getBalance(apiKey);
    return NextResponse.json(balance);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
