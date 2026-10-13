import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

// 어떤 목록 페이지도 안 쓰는 무거운 필드들 — 항상 제외.
// balloons(27MB), field_analysis, *_pre_correction/*_pre_last_correction 백업, v1 백업
// 필요 시 단건 GET 으로 개별 조회.
const ALWAYS_EXCLUDE = {
  balloons: 0,
  field_analysis: 0,
  field_map_pre_correction: 0,
  field_map_pre_last_correction: 0,
  field_map_v1_backup: 0,
  image_base64_pre_correction: 0,
  image_base64_pre_last_correction: 0,
} as const;

// /levels 목록 페이지 전용 추가 슬림 (image_base64/field_map 도 제외).
// /gallery, /json-vault 는 image_base64/field_map 필요하므로 slim=0.
const SLIM_EXTRA = {
  image_base64: 0,
  image_base64_alt: 0,
  field_map: 0,
} as const;

// 디자이너 행만 (worker output 행은 status 없음).
// field_complete_levels.py 워커가 같은 컬렉션에 부수 문서를 만들었던 잔재 — 영구 분리됨.
const DESIGNER_FILTER = { status: { $exists: true } } as const;

export async function GET(req: NextRequest) {
  try {
    const slim = req.nextUrl.searchParams.get("slim") === "1";
    const projection = slim ? { ...ALWAYS_EXCLUDE, ...SLIM_EXTRA } : ALWAYS_EXCLUDE;
    const db = await getDb();
    const levels = await db
      .collection("pixelforge_levels")
      .find(DESIGNER_FILTER, { projection })
      .sort({ level_number: 1 })
      .toArray();
    return NextResponse.json(levels);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[GET /api/levels]", msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// upsert에 안전하지 않은 필드 제거 + level_number 검증
function sanitize(level: Record<string, unknown>): Record<string, unknown> | null {
  const clean: Record<string, unknown> = { ...level };
  // _id는 MongoDB가 ObjectId로 기대하므로 제거 (string 들어오면 cast 에러)
  delete clean._id;
  // 빈 문자열/undefined 필드 정리
  for (const k of Object.keys(clean)) {
    if (clean[k] === undefined || clean[k] === null) delete clean[k];
  }
  // level_number는 양의 정수여야 함
  const lvNum = Number(clean.level_number);
  if (!Number.isFinite(lvNum) || lvNum <= 0) return null;
  clean.level_number = lvNum;
  return clean;
}

export async function POST(req: NextRequest) {
  try {
    const db = await getDb();
    const body = await req.json();

    if (Array.isArray(body)) {
      // 배치 — 각 항목 sanitize, 무효 항목은 스킵
      const valid: Record<string, unknown>[] = [];
      const skipped: Array<{ index: number; reason: string }> = [];
      body.forEach((row, i) => {
        const cleaned = sanitize(row);
        if (cleaned) valid.push(cleaned);
        else skipped.push({ index: i, reason: "invalid level_number" });
      });

      if (valid.length === 0) {
        return NextResponse.json(
          { ok: false, error: "유효한 행 없음 (level_number가 양수여야 함)", skipped },
          { status: 400 }
        );
      }

      const ops = valid.map((level) => ({
        updateOne: {
          filter: { level_number: level.level_number },
          update: { $set: { ...level, updated_at: new Date().toISOString() } },
          upsert: true,
        },
      }));
      const result = await db.collection("pixelforge_levels").bulkWrite(ops);
      return NextResponse.json({
        ok: true,
        count: result.upsertedCount + result.modifiedCount,
        skipped: skipped.length,
      });
    }

    // 단일 항목
    const cleaned = sanitize(body);
    if (!cleaned) {
      return NextResponse.json(
        { ok: false, error: "level_number가 양수여야 함" },
        { status: 400 }
      );
    }
    cleaned.updated_at = new Date().toISOString();
    cleaned.created_at = cleaned.created_at || new Date().toISOString();
    await db.collection("pixelforge_levels").updateOne(
      { level_number: cleaned.level_number },
      { $set: cleaned },
      { upsert: true }
    );
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    const stack = e instanceof Error ? e.stack?.split("\n").slice(0, 3).join(" | ") : "";
    console.error("[POST /api/levels]", msg, stack);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
