import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { getCompletedBoard, runGimmickCli } from "@/lib/gimmick-board";

// POST { level_number, variant_index, gimmick_type? }
//  → 완성보드 로드 → 택1 안 auto-fix(10배수) → 병합 → pixelforge_gimmick_placements 저장
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const levelNumber = Number(body.level_number);
    const gimmickType = String(body.gimmick_type || "Wooden");
    // 선택안을 직접 받음(권장, vision 비결정성 안전). 없으면 variant_index 하위호환.
    const chosenVariant = body.variant;
    const variantIndex = Number(body.variant_index);
    if (!Number.isFinite(levelNumber) || (!chosenVariant && !Number.isFinite(variantIndex))) {
      return NextResponse.json({ ok: false, error: "level_number + (variant 또는 variant_index) 필요" }, { status: 400 });
    }
    const db = await getDb();
    const board = await getCompletedBoard(db, levelNumber);
    if (!board) {
      return NextResponse.json(
        { ok: false, error: `완성보드 없음 (Lv ${levelNumber} — 필드완성 선행 필요)` },
        { status: 404 },
      );
    }
    const res = await runGimmickCli<{
      ok: boolean;
      error?: string;
      chosen?: string;
      merged?: unknown;
      adjustments?: unknown[];
      designer_needed?: unknown[];
      clean?: boolean;
      validation?: unknown;
      preview_b64?: string;
    }>({ cmd: "commit", board, gimmick_type: gimmickType,
        ...(chosenVariant ? { variant: chosenVariant } : { variant_index: variantIndex }) });

    if (!res.ok) {
      return NextResponse.json(res, { status: 400 });
    }

    // 최종 board(병합본)를 placements 컬렉션에 upsert (preview_b64 는 저장 제외 — 용량)
    await db.collection("pixelforge_gimmick_placements").updateOne(
      { level_number: levelNumber, gimmick_type: gimmickType },
      {
        $set: {
          level_number: levelNumber,
          gimmick_type: gimmickType,
          ...(Number.isFinite(variantIndex) ? { variant_index: variantIndex } : {}),
          chosen: res.chosen,
          merged: res.merged,
          adjustments: res.adjustments,
          designer_needed: res.designer_needed,
          clean: res.clean,
          validation: res.validation,
          updated_at: new Date().toISOString(),
        },
      },
      { upsert: true },
    );

    return NextResponse.json({ level_number: levelNumber, saved: true, ...res });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String((e as Error)?.message || e) }, { status: 500 });
  }
}
