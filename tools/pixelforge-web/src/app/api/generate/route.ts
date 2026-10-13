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
import { resolveStyleType, getStyleRef } from "@/lib/styleRef";
import { koToEn } from "@/lib/translate";
import { getDb } from "@/lib/mongodb";
import { snapImageToGridAndPaletteV2 } from "@/lib/snapToGridV2";
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
      gen_target_long,   // 지정 시 큰 해상도로 생성("크게 생성" 버튼). 미지정=1:1
      force_palette,     // "팔레트 강제": snap K→28을 color_ids로만 매핑
      single_subject,    // "단일 중앙 피사체": 프롬프트 컨벤션 + no_background (씬화/구석잘림 근본 방지)
      reference_image_base64, // (선택) v2 reference_images로 피사체/구도 유도
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

    // "단일 중앙 피사체" 컨벤션 — 캐릭터형에서 PixelLab이 씬/풍경으로 그리는 것(②③)을 프롬프트로 차단.
    //   v2엔 negative_description가 없어 description에 의도+억제를 함께 래핑. + no_background 권장.
    const subjStyleType = resolveStyleType(level_data); // character/background/structure
    const wantSingle = single_subject === true && subjStyleType === "character";
    const finalPrompt = wantSingle
      ? `a single ${translatedPrompt}, centered, full body, fills the frame, isolated subject on a plain solid background, no scenery, no landscape, no background details, not cropped`
      : translatedPrompt;
    const effectiveNoBg = (no_background === true) || wantSingle;

    const colorIds = parseColorDist(color_distribution || "");
    const applyColorLimit = use_color_limit !== false;
    const targetColorCount = applyColorLimit ? (Number(level_data?.num_colors) || 0) : 0;
    const db = await getDb();

    const fieldCols = level_data?.field_columns || 20;
    const fieldRows = level_data?.field_rows || 20;

    // 기본은 1:1 (필드 셀 수 = 픽셀 수). 단 "크게 생성" 요청(gen_target_long) 시에만
    //   필드 정수배로 키워 생성 → 작은 캔버스에 우겨넣어 잘리던 피사체에 여유. snap이 다운샘플.
    //   PixelLab 최대 792×688.
    const PL_MAX_W = 792, PL_MAX_H = 688;
    const reqTargetLong = Number(gen_target_long) || 0;
    const longSide = Math.max(fieldCols, fieldRows);
    let genScale = 1;
    if (reqTargetLong > 0) {
      genScale = Math.max(1, Math.round(reqTargetLong / Math.max(1, longSide)));
      while (genScale > 1 && (fieldCols * genScale > PL_MAX_W || fieldRows * genScale > PL_MAX_H)) genScale--;
    }
    const genW = Math.max(16, fieldCols * genScale);
    const genH = Math.max(16, fieldRows * genScale);

    // style_image 조회 — 레벨 유형(character/background/structure)에 맞는 레퍼런스 선택.
    // style_type 수동 override > bl_category 자동 매핑 > 공통 style_image fallback.
    const styleType = subjStyleType;
    const styleRef = await getStyleRef(db, styleType);
    const hasStyleImage = Boolean(styleRef?.base64);

    // ★ generate-image-v2 사용 (Pro key 우선, 없으면 Free key)
    const effectiveKey = proApiKey || apiKey;

    console.log("[Generate] v2", {
      level_number, genW, genH, genScale, fieldCols, fieldRows,
      hasStyleImage, styleType, styleKey: styleRef?.usedKey,
      wantSingle, forcePalette: force_palette === true, hasRef: Boolean(reference_image_base64),
      keyType: proApiKey ? "pro" : "free",
      prompt: finalPrompt,
    });

    try {
      // generate-image-v2 (async) — style_options.color_palette: false
      const { jobId, usage } = await generateImageV2Start(
        finalPrompt, genW, genH,
        {
          apiKey: effectiveKey,
          noBackground: effectiveNoBg,
          referenceImageBase64: typeof reference_image_base64 === "string" ? reference_image_base64 : undefined,
          styleImageBase64: hasStyleImage ? styleRef!.base64 : undefined,
          styleImageWidth: hasStyleImage ? styleRef!.width : undefined,
          styleImageHeight: hasStyleImage ? styleRef!.height : undefined,
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
          force_palette: force_palette === true,
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

      // pixflux fallback: 1:1 (max 400)
      const pxW = Math.min(400, Math.max(16, fieldCols));
      const pxH = Math.min(400, Math.max(16, fieldRows));

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

      // snap-to-grid (V2)
      const displayBase64 = result.base64;
      let fieldMap = "";
      let finalColorIds: number[] = colorIds;
      let paletteMapping: Record<number, number> = {};
      let pipelineTag = "";
      try {
        const snapped = await snapImageToGridAndPaletteV2(result.base64, {
          cols: fieldCols, rows: fieldRows,
          allowedIds: colorIds.length > 0 ? colorIds : undefined,
          transparentBg: no_background === true,
          targetColorCount: targetColorCount > 0 ? targetColorCount : undefined,
        });
        fieldMap = matrixToFieldMap(snapped.matrix);
        finalColorIds = snapped.stats.dominantColors;
        paletteMapping = snapped.paletteMapping;
        pipelineTag = snapped.stats.pipeline;
      } catch (e) { console.error("[Generate] snap error:", e); }

      // DB 저장
      if (level_number) {
        const saveData: Record<string, unknown> = {
          level_number, image_base64: displayBase64, field_map: fieldMap,
          field_map_pipeline: pipelineTag, palette_mapping: paletteMapping,
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
