// 기존 이미지(image_base64)를 재생성 없이 snap-to-grid 후처리만 적용
// AI 호출 없음, 빠름, 무료
import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { snapImageToGridAndPalette } from "@/lib/snapToGrid";
import { matrixToFieldMap } from "@/lib/matrixRenderer";
import { parseColorDist } from "@/lib/palette";

interface LevelDoc {
  level_number: number;
  field_columns?: number;
  field_rows?: number;
  image_base64?: string;
  color_distribution?: string;
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const levelNumber = Number(body.level_number);
    if (!levelNumber || levelNumber <= 0) {
      return NextResponse.json({ ok: false, error: "level_number 필수" }, { status: 400 });
    }

    const db = await getDb();
    const lv = (await db.collection("pixelforge_levels").findOne({ level_number: levelNumber })) as LevelDoc | null;
    if (!lv) {
      return NextResponse.json({ ok: false, error: "Level not found" }, { status: 404 });
    }
    if (!lv.image_base64) {
      return NextResponse.json({ ok: false, error: "원본 image_base64가 없음" }, { status: 400 });
    }

    const cols = Number(lv.field_columns) || 20;
    const rows = Number(lv.field_rows) || 20;
    const transparentBg = body.no_background === true;

    // 클라이언트가 palette_ids를 지정하면 그것만 사용, 아니면 시트의 color_distribution
    let paletteIds: number[] = Array.isArray(body.palette_ids)
      ? body.palette_ids.filter((n: unknown) => typeof n === "number" && n >= 1 && n <= 28)
      : [];
    if (paletteIds.length === 0) {
      paletteIds = parseColorDist(String(lv.color_distribution || ""));
    }

    const snapped = await snapImageToGridAndPalette(lv.image_base64, {
      cols,
      rows,
      allowedIds: paletteIds.length > 0 ? paletteIds : undefined,
      transparentBg,
    });

    // save_to_original: true면 image_base64를 직접 덮어쓰기 (Pro 후처리용)
    const saveToOriginal = body.save_to_original === true;
    const setFields: Record<string, unknown> = {
      updated_at: new Date().toISOString(),
    };

    if (saveToOriginal) {
      setFields.image_base64 = snapped.base64;
      setFields.field_map = matrixToFieldMap(snapped.matrix);
    } else {
      setFields.image_base64_alt = snapped.base64;
      setFields.field_map_alt = matrixToFieldMap(snapped.matrix);
      setFields.alt_meta = {
        source: "snap-existing",
        width: snapped.width,
        height: snapped.height,
        pixels_per_cell: snapped.pixelsPerCell,
        palette_ids: paletteIds.length > 0 ? paletteIds : undefined,
        snap_stats: snapped.stats,
        generated_at: new Date().toISOString(),
      };
    }

    await db.collection("pixelforge_levels").updateOne(
      { level_number: levelNumber },
      { $set: setFields }
    );

    return NextResponse.json({
      ok: true,
      level_number: levelNumber,
      snap_stats: snapped.stats,
      saved_to: saveToOriginal ? "image_base64" : "image_base64_alt",
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[snap-existing]", msg);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
