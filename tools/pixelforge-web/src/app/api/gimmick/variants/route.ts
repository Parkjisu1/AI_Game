import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { getCompletedBoard, runGimmickCli } from "@/lib/gimmick-board";

// POST { level_number, gimmick_type? } → 완성보드 로드 → 4안 생성(검증+미리보기+auto-fix 예고)
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const levelNumber = Number(body.level_number);
    const gimmickType = String(body.gimmick_type || "Wooden");
    const useVision = Boolean(body.use_vision);
    if (!Number.isFinite(levelNumber)) {
      return NextResponse.json({ ok: false, error: "level_number 필요" }, { status: 400 });
    }
    const db = await getDb();
    const board = await getCompletedBoard(db, levelNumber);
    if (!board) {
      return NextResponse.json(
        { ok: false, error: `완성보드 없음 (Lv ${levelNumber} — 필드완성 선행 필요)` },
        { status: 404 },
      );
    }
    const res = await runGimmickCli({ cmd: "variants", board, gimmick_type: gimmickType, use_vision: useVision });
    return NextResponse.json({ level_number: levelNumber, ...(res as object) });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String((e as Error)?.message || e) }, { status: 500 });
  }
}
