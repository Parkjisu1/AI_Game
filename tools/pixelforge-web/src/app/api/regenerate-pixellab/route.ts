import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { generateImage } from "@/lib/pixellab";
import { koToEn } from "@/lib/translate";
import { snapImageToGridAndPalette } from "@/lib/snapToGrid";
import { matrixToFieldMap } from "@/lib/matrixRenderer";

export const maxDuration = 60;

interface LevelDoc {
  level_number: number;
  field_columns?: number;
  field_rows?: number;
  designer_note?: string;
  color_distribution?: string;
  image_base64?: string;
}

export async function POST(req: NextRequest) {
  try {
    const apiKey = req.headers.get("x-pixellab-key") || undefined;
    const body = await req.json();
    const levelNumber = Number(body.level_number);
    if (!levelNumber || levelNumber <= 0) {
      return NextResponse.json({ ok: false, error: "level_number 필수" }, { status: 400 });
    }

    // palette_ids 또는 colorDist 둘 중 하나 필요
    const paletteIds: number[] = Array.isArray(body.palette_ids)
      ? body.palette_ids.filter((n: unknown) => typeof n === "number" && n >= 1 && n <= 28)
      : [];
    if (paletteIds.length === 0) {
      return NextResponse.json({ ok: false, error: "palette_ids 필수 (변경할 색상)" }, { status: 400 });
    }

    const db = await getDb();
    const lv = (await db.collection("pixelforge_levels").findOne({ level_number: levelNumber })) as LevelDoc | null;
    if (!lv) {
      return NextResponse.json({ ok: false, error: `Level ${levelNumber} 못 찾음` }, { status: 404 });
    }

    const cols = Number(lv.field_columns) || 20;
    const rows = Number(lv.field_rows) || 20;
    const note = String(lv.designer_note || "").trim() || "pixel art pattern";
    const transparentBg = body.no_background === true;

    const translatedPrompt = await koToEn(note);

    // PixelLab 호출 — forced_palette만 (완전 새 생성)
    // PixelLab은 더 큰 해상도로 생성할수록 디테일이 좋아지므로 최대 400까지 키움
    const maxDim = Math.max(cols, rows);
    const genPpc = Math.max(4, Math.min(10, Math.floor(400 / maxDim)));
    const genW = cols * genPpc;
    const genH = rows * genPpc;

    // 모드 분류 (패턴 키워드 검출) + 스타일 defaults 적용
    const lower = note.toLowerCase();
    const isPattern = /pattern|tile|grid|checker|lattice|mandala|kaleidoscope|honeycomb|stripe|weave|geometric|tessellation|symmetry|spiral|패턴|타일|격자|만화경|벌집|만다라|대칭|반복|기하학|스트라이프|체커|소용돌이/.test(lower);

    const result = await generateImage(translatedPrompt, genW, genH, {
      apiKey,
      noBackground: transparentBg,
      view: isPattern ? "high top-down" : "side",
      direction: isPattern ? undefined : "south",
      outline: isPattern ? "single color outline" : "selective outline",
      shading: isPattern ? "flat shading" : "basic shading",
      detail: isPattern ? "medium detail" : "highly detailed",
      isometric: false,
      textGuidanceScale: isPattern ? 12 : 10,
    });

    // ★ 핵심 후처리: 그리드 + 팔레트로 강제 snap
    // PixelLab 원본은 블러/팔레트 이탈 있음 → 각 셀의 mode color를 28색 중 선택
    const snapped = await snapImageToGridAndPalette(result.base64, {
      cols,
      rows,
      allowedIds: paletteIds,
      transparentBg,
    });

    // FieldMap은 snapped matrix에서 직접 생성 (imageToFieldMap 대신)
    const fieldMap = matrixToFieldMap(snapped.matrix);
    console.log(`[regenerate-pixellab] snap stats: ${snapped.stats.uniqueColorsBefore} colors → ${snapped.stats.uniqueColorsAfter} palette colors`);

    // alt 필드로 저장 — snap된 결과 사용 (원본 PixelLab base64가 아님)
    await db.collection("pixelforge_levels").updateOne(
      { level_number: levelNumber },
      {
        $set: {
          image_base64_alt: snapped.base64,
          field_map_alt: fieldMap,
          alt_meta: {
            source: "pixellab+snap",
            width: snapped.width,
            height: snapped.height,
            pixels_per_cell: snapped.pixelsPerCell,
            palette_ids: paletteIds,
            snap_stats: snapped.stats,
            generated_at: new Date().toISOString(),
          },
          updated_at: new Date().toISOString(),
        },
      }
    );

    return NextResponse.json({
      ok: true,
      level_number: levelNumber,
      width: snapped.width,
      height: snapped.height,
      pixelsPerCell: snapped.pixelsPerCell,
      snap_stats: snapped.stats,
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[regenerate-pixellab]", msg);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
