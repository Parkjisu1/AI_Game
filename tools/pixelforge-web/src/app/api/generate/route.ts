import { NextRequest, NextResponse } from "next/server";
import {
  generateImage,
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
const BUILD_VERSION = "v4-highres-raw"; // 배포 확인용

// 패턴/모티프 자동 분류
function detectMode(prompt: string): "pattern" | "motif" {
  const lower = prompt.toLowerCase();
  const patternKeywords = [
    "pattern", "tile", "grid", "checker", "checkerboard", "lattice", "mandala",
    "kaleidoscope", "honeycomb", "stripe", "weave", "geometric", "tessellation",
    "symmetry", "mirror", "spiral", "concentric", "radial", "diamond pattern",
    "패턴", "타일", "격자", "만화경", "벌집", "만다라", "대칭", "반복", "기하학",
    "스트라이프", "체커", "소용돌이", "동심원", "마름모 패턴", "다이아몬드 패턴",
  ];
  return patternKeywords.some((k) => lower.includes(k)) ? "pattern" : "motif";
}

// 모티프(캐릭터/오브젝트) 기본 스타일 — 선명한 외곽 + 입체 쉐이딩
const MOTIF_DEFAULTS: {
  view: PixelLabView;
  direction: PixelLabDirection;
  outline: PixelLabOutline;
  shading: PixelLabShading;
  detail: PixelLabDetail;
  textGuidanceScale: number;
} = {
  view: "side",
  direction: "south",
  outline: "selective outline",
  shading: "basic shading",
  detail: "highly detailed",
  textGuidanceScale: 12,
};

// 패턴(격자/타일/기하학) 기본 스타일 — 탑다운 + 플랫 쉐이딩
const PATTERN_DEFAULTS: {
  view: PixelLabView;
  outline: PixelLabOutline;
  shading: PixelLabShading;
  detail: PixelLabDetail;
  isometric: boolean;
  textGuidanceScale: number;
} = {
  view: "high top-down",
  outline: "single color outline",
  shading: "flat shading",
  detail: "medium detail",
  isometric: false,
  textGuidanceScale: 12,
};

export async function POST(req: NextRequest) {
  try {
    const {
      level_number, prompt, width, height, color_distribution, level_data, no_background,
      use_color_limit,
      // 클라이언트가 style override를 보낼 수도 있음
      mode: clientMode,
      view, direction, outline, shading, detail, isometric,
      text_guidance_scale: clientGuidance,
    } = await req.json();
    const rawKeyHeader = req.headers.get("x-pixellab-key");
    const apiKey = rawKeyHeader || undefined;
    const proApiKey = req.headers.get("x-pixellab-pro-key") || undefined;

    // 헤더 진단 정보 — 400일 때 응답에 포함시킴
    const headerInfo = {
      hasHeader: rawKeyHeader !== null,
      headerLength: rawKeyHeader ? rawKeyHeader.length : 0,
      headerPrefix: rawKeyHeader ? rawKeyHeader.substring(0, 6) : "",
    };
    console.log("[Generate] header:", headerInfo);

    if (!apiKey) {
      return NextResponse.json({
        ok: false,
        error: "x-pixellab-key 헤더가 비어있거나 없음 — 우상단 ⚙️에서 키 재입력 필요",
        headerInfo,
      }, { status: 400 });
    }

    const translatedPrompt = await koToEn(prompt || "pixel art");
    const colorIds = parseColorDist(color_distribution || "");
    // num_colors — 목표 색상 수 (post-processing으로 축소)
    // ★ use_color_limit가 false면 색상 수 제한 안 함 (사용자가 "색상 제한" 체크 해제 시)
    const applyColorLimit = use_color_limit !== false;
    const targetColorCount = applyColorLimit ? (Number(level_data?.num_colors) || 0) : 0;
    const db = await getDb();

    // Track 자동 분류 (원본 한국어 prompt 기준 — 번역 전 키워드 매칭이 정확)
    const mode: "pattern" | "motif" = clientMode === "pattern" || clientMode === "motif"
      ? clientMode
      : detectMode(prompt || "");

    // 모드별 기본값 + 클라이언트 override 병합
    const style = mode === "pattern"
      ? {
          view: (view as PixelLabView) ?? PATTERN_DEFAULTS.view,
          direction: direction as PixelLabDirection | undefined,  // pattern은 direction 안 보냄
          outline: (outline as PixelLabOutline) ?? PATTERN_DEFAULTS.outline,
          shading: (shading as PixelLabShading) ?? PATTERN_DEFAULTS.shading,
          detail: (detail as PixelLabDetail) ?? PATTERN_DEFAULTS.detail,
          isometric: typeof isometric === "boolean" ? isometric : PATTERN_DEFAULTS.isometric,
          textGuidanceScale: typeof clientGuidance === "number" ? clientGuidance : PATTERN_DEFAULTS.textGuidanceScale,
        }
      : {
          view: (view as PixelLabView) ?? MOTIF_DEFAULTS.view,
          direction: (direction as PixelLabDirection) ?? MOTIF_DEFAULTS.direction,
          outline: (outline as PixelLabOutline) ?? MOTIF_DEFAULTS.outline,
          shading: (shading as PixelLabShading) ?? MOTIF_DEFAULTS.shading,
          detail: (detail as PixelLabDetail) ?? MOTIF_DEFAULTS.detail,
          isometric: typeof isometric === "boolean" ? isometric : false,
          textGuidanceScale: typeof clientGuidance === "number" ? clientGuidance : MOTIF_DEFAULTS.textGuidanceScale,
        };

    console.log("[Generate]", { level_number, translated: translatedPrompt, colorIds, no_background, mode, style });

    // 1. PixelLab API — 최대 해상도로 고퀄리티 생성 후 snap-to-grid에서 목표 셀 수로 축소
    const fieldCols = level_data?.field_columns || 20;
    const fieldRows = level_data?.field_rows || 20;
    // PixelLab 허용 범위: 32~400px — 최대한 크게 생성하여 퀄리티 확보
    // snap-to-grid가 fieldCols×fieldRows 셀로 정확히 매핑함
    const maxAllowed = 384; // PixelLab max 400, 여유분 16px
    const ppc = Math.max(2, Math.floor(maxAllowed / Math.max(fieldCols, fieldRows)));
    const genW = Math.min(400, Math.max(64, fieldCols * ppc));
    const genH = Math.min(400, Math.max(64, fieldRows * ppc));

    // pixflux 단독 — Pro key가 있으면 pixflux에도 사용 (동일 계정 크레딧)
    const effectiveKey = proApiKey || apiKey;
    console.log("[Generate] pixflux", { mode, genW, genH, colorCount: colorIds.length, targetColorCount });

    const result = await generateImage(
      translatedPrompt,
      genW || width || 128,
      genH || height || 128,
      colorIds.length > 0 ? colorIds : undefined,
      {
        apiKey: effectiveKey,
        noBackground: no_background === true,
        ...style,
      }
    );

    // 2. snap-to-grid — fieldMap(게임 데이터)만 추출, 표시용 이미지는 PixelLab 원본 사용
    const displayBase64 = result.base64; // PixelLab 원본 (고퀄리티)
    let fieldMap = "";
    let finalColorIds: number[] = colorIds;
    try {
      const snapped = await snapImageToGridAndPalette(result.base64, {
        cols: fieldCols,
        rows: fieldRows,
        allowedIds: colorIds.length > 0 ? colorIds : undefined,
        transparentBg: no_background === true,
        targetColorCount: targetColorCount > 0 ? targetColorCount : undefined,
      });
      fieldMap = matrixToFieldMap(snapped.matrix);
      finalColorIds = snapped.stats.dominantColors;
      console.log(`[Generate] snap: ${snapped.stats.uniqueColorsBefore}→${snapped.stats.uniqueColorsAfter} colors`);
    } catch (e) {
      console.error("[Generate] snap error:", e);
    }

    // 3. DB 저장 — 표시 이미지는 PixelLab 원본, fieldMap은 snap 결과
    if (level_number) {
      const saveData: Record<string, unknown> = {
        level_number,
        image_base64: displayBase64,
        field_map: fieldMap,
        status: "generated",
        updated_at: new Date().toISOString(),
      };

      if (level_data) {
        // ★ num_colors, color_distribution은 의도적으로 제외
        // 이 두 필드는 기획 데이터 (난이도 레버)이므로 이미지 생성이 건드려선 안 됨
        // CSV 가져오기 또는 사용자 수동 편집에서만 변경됨
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
          if (level_data[f] !== undefined && level_data[f] !== null) {
            saveData[f] = level_data[f];
          }
        }
        // designer_note에서 기존 [FieldMap] 제거 (오염 방지)
        if (typeof saveData.designer_note === "string") {
          const idx = (saveData.designer_note as string).indexOf("[FieldMap]");
          if (idx >= 0) saveData.designer_note = (saveData.designer_note as string).substring(0, idx).trim();
        }
      }

      // ★ 레벨 설계 데이터 보호 — num_colors, color_distribution은 기획자의 의도 값
      // 생성 결과로 덮어쓰지 않음. 대신 generated_colors를 별도 필드에 저장하여 비교 가능하게.
      if (finalColorIds.length > 0) {
        saveData.generated_colors = finalColorIds.map((id) => `c${id}:1`).join(",");
        saveData.generated_num_colors = finalColorIds.length;
      }

      await db.collection("pixelforge_levels").updateOne(
        { level_number },
        { $set: saveData },
        { upsert: true }
      );
    }

    return NextResponse.json({
      ok: true,
      base64: displayBase64,
      usage: result.usage,
      translated_prompt: translatedPrompt,
      field_map: fieldMap ? "generated" : "failed",
      _v: BUILD_VERSION,
      _gen_size: `${genW}x${genH}`,
      _display_len: displayBase64.length,
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    const stack = e instanceof Error && e.stack ? e.stack.split("\n").slice(0, 4).join(" | ") : "";
    console.error("[generate]", msg, stack);
    return NextResponse.json({ ok: false, error: msg, stack }, { status: 500 });
  }
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
