import { NextRequest, NextResponse } from "next/server";
import { generatePixelMatrix } from "@/lib/llm";
import { renderMatrixToPng, matrixToFieldMap } from "@/lib/matrixRenderer";
import { parseColorDist } from "@/lib/palette";
import { getDb } from "@/lib/mongodb";

// Vercel function timeout 확장 (Hobby 최대 60s, Pro는 더 가능)
export const maxDuration = 60;

interface LevelDoc {
  level_number: number;
  field_columns?: number;
  field_rows?: number;
  designer_note?: string;
  color_distribution?: string;
}

export async function POST(req: NextRequest) {
  try {
    const apiKey = req.headers.get("x-google-key") || process.env.GOOGLE_API_KEY;
    if (!apiKey) {
      return NextResponse.json(
        { ok: false, error: "Google AI Studio API Key가 설정되지 않았습니다 (우상단 ⚙️)" },
        { status: 400 }
      );
    }
    const model = req.headers.get("x-llm-model") || undefined;

    const body = await req.json();
    const levelNumber = Number(body.level_number);
    if (!levelNumber || levelNumber <= 0) {
      return NextResponse.json({ ok: false, error: "level_number 필수" }, { status: 400 });
    }

    const db = await getDb();
    const lv = (await db.collection("pixelforge_levels").findOne({ level_number: levelNumber })) as LevelDoc | null;
    if (!lv) {
      return NextResponse.json({ ok: false, error: `Level ${levelNumber} 못 찾음` }, { status: 404 });
    }

    const cols = Math.max(4, Math.min(80, Number(lv.field_columns) || 20));
    const rows = Math.max(4, Math.min(80, Number(lv.field_rows) || 20));
    const note = String(lv.designer_note || "").trim() || "abstract pixel pattern";
    const transparentBg = body.no_background === true;

    // 색상 결정: 클라이언트에서 보낸 paletteIds 우선, 없으면 시트 분포
    let paletteIds: number[] = [];
    if (Array.isArray(body.palette_ids) && body.palette_ids.length > 0) {
      paletteIds = body.palette_ids.filter((n: unknown) => typeof n === "number");
    } else {
      paletteIds = parseColorDist(String(lv.color_distribution || ""));
    }

    // 1) LLM으로 매트릭스 생성
    const { matrix, rawText, parseStats } = await generatePixelMatrix({
      apiKey,
      model,
      prompt: note,
      cols,
      rows,
      paletteIds: paletteIds.length > 0 ? paletteIds : undefined,
      emptyAllowed: transparentBg,
    });

    // 2) 매트릭스 → PNG
    const { base64, width, height, pixelsPerCell } = await renderMatrixToPng(matrix, { transparentBg });

    // 3) FieldMap 텍스트 생성
    const fieldMap = matrixToFieldMap(matrix);

    // 4) DB에 alt 필드로 저장 — 원본 image_base64, field_map, status, 모든 게임 데이터 보존
    await db.collection("pixelforge_levels").updateOne(
      { level_number: levelNumber },
      {
        $set: {
          image_base64_alt: base64,
          field_map_alt: fieldMap,
          alt_meta: {
            source: parseStats?.usedModel || model || "gemini-2.5-flash",
            width,
            height,
            pixels_per_cell: pixelsPerCell,
            generated_at: new Date().toISOString(),
            track: parseStats?.track,
            raw_response: rawText?.substring(0, 5000) || "",
            parsed_row_count: parseStats?.parsedRowCount,
            expected_rows: parseStats?.expectedRows,
            row_lengths: parseStats?.rowLengths?.slice(0, 50),
          },
          updated_at: new Date().toISOString(),
        },
      }
    );

    return NextResponse.json({ ok: true, level_number: levelNumber, width, height, pixelsPerCell });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    const stack = e instanceof Error && e.stack ? e.stack.split("\n").slice(0, 4).join(" | ") : "";
    console.error("[regenerate-llm]", msg, stack);
    return NextResponse.json({ ok: false, error: msg, stack }, { status: 500 });
  }
}
