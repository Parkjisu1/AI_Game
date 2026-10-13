import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import {
  generateQueue,
  purposeToDifficulty,
  type Cells,
  type Difficulty,
  type GimmickCounts,
} from "@/lib/queue-generator";

export const runtime = "nodejs";

// PixelForge Queue Generator endpoint
//
// 입력:
//   POST body: { level_number, seed?, queueColumns?, railCapacity?, difficulty?, levelId? }
//   또는 GET ?level_number=42&seed=42
//
// 처리:
//   1. pixelforge_levels[level_number] 로드 (field_map + 메타)
//   2. field_map (텍스트 그리드) → cells[][] 파싱
//   3. queue-generator 호출 (MapEditor 1:1 port)
//   4. 결과 반환 (휘발성 — DB 저장 안 함. 디자이너가 [Confirm]시에만 별도 endpoint로 저장)
//
// 응답: { ok: true, ...QueueResult, level_meta }

// field_map 텍스트 → cells[][] 파싱
//   포맷: "01 02 .. 03\n07 07 07 07\n..." (2자리 palette_id 또는 "..")
//   ".." = 빈 셀 → 0 변환
function parseFieldMap(fm: string): { cells: Cells; rows: number; cols: number; palette: number[] } {
  const lines = fm.split("\n").filter(L => L.trim().length > 0);
  const cells: Cells = [];
  const paletteSet = new Set<number>();
  for (const line of lines) {
    const tokens = line.trim().split(/\s+/);
    const row: number[] = [];
    for (const t of tokens) {
      if (t === ".." || t === "00") {
        row.push(0);
      } else {
        const n = parseInt(t, 10);
        if (Number.isFinite(n) && n > 0) {
          row.push(n);
          paletteSet.add(n);
        } else {
          row.push(0);
        }
      }
    }
    cells.push(row);
  }
  return {
    cells,
    rows: cells.length,
    cols: cells[0]?.length ?? 0,
    palette: [...paletteSet].sort((a, b) => a - b),
  };
}

async function loadAndGenerate(
  levelNumber: number,
  opts: {
    seed?: number;
    queueColumns?: number;
    railCapacity?: number;
    difficulty?: string;
    levelId?: number;
  },
) {
  const db = await getDb();
  const lv = await db.collection("pixelforge_levels").findOne({ level_number: levelNumber });
  if (!lv) {
    return NextResponse.json({ ok: false, error: `level ${levelNumber} not found` }, { status: 404 });
  }
  const fm = (lv.field_map as string | undefined) ?? "";
  if (!fm.trim()) {
    return NextResponse.json({ ok: false, error: "field_map empty (generate field first)" }, { status: 422 });
  }

  const parsed = parseFieldMap(fm);
  if (parsed.rows === 0 || parsed.cols === 0) {
    return NextResponse.json({ ok: false, error: "field_map malformed" }, { status: 422 });
  }

  const difficulty: Difficulty = opts.difficulty
    ? purposeToDifficulty(opts.difficulty)
    : purposeToDifficulty(lv.purpose_type ?? "normal");

  const seed = opts.seed ?? Math.floor(Math.random() * 0x7fffffff);
  const effectiveLevelId = opts.levelId ?? Number(lv.level_id) ?? Number(lv.level_number) ?? 1;

  // 입력 (pixelforge_levels.gimmick_*) — 큐 + 필드 기믹
  const asN = (v: unknown): number | undefined => {
    const n = typeof v === "number" ? v : parseInt(String(v ?? ""), 10);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  };
  const gimmickCounts: GimmickCounts = {};
  if (lv.gimmick_hidden != null)       gimmickCounts.hidden      = asN(lv.gimmick_hidden);
  if (lv.gimmick_chain != null)        gimmickCounts.chain       = asN(lv.gimmick_chain);
  if (lv.gimmick_spawner_t != null)    gimmickCounts.spawner_t   = asN(lv.gimmick_spawner_t);
  if (lv.gimmick_spawner_o != null)    gimmickCounts.spawner_o   = asN(lv.gimmick_spawner_o);
  if (lv.gimmick_frozen_dart != null)  gimmickCounts.frozen_dart = asN(lv.gimmick_frozen_dart);
  if (lv.gimmick_lock_key != null)     gimmickCounts.lock_key    = asN(lv.gimmick_lock_key);
  if (lv.gimmick_pinata != null)       gimmickCounts.pinata      = asN(lv.gimmick_pinata);
  if (lv.gimmick_wall != null)         gimmickCounts.wall        = asN(lv.gimmick_wall);
  if (lv.gimmick_pin != null)          gimmickCounts.pin         = asN(lv.gimmick_pin);
  if (lv.gimmick_surprise != null)     gimmickCounts.surprise    = asN(lv.gimmick_surprise);
  if (lv.gimmick_pinata_box != null)   gimmickCounts.pinata_box  = asN(lv.gimmick_pinata_box);
  if (lv.gimmick_ice != null)          gimmickCounts.ice         = asN(lv.gimmick_ice);
  if (lv.gimmick_curtain != null)      gimmickCounts.curtain     = asN(lv.gimmick_curtain);
  const hasAnyGimmick = Object.values(gimmickCounts).some(v => v != null && v > 0);

  const result = generateQueue({
    cells: parsed.cells,
    palette: parsed.palette,
    difficulty,
    levelId: effectiveLevelId,
    queueColumns: opts.queueColumns,
    railCapacity: opts.railCapacity,
    seed,
    gimmickCounts: hasAnyGimmick ? gimmickCounts : undefined,
  });

  return NextResponse.json({
    ok: true,
    level_meta: {
      level_number: lv.level_number,
      level_id: lv.level_id,
      pkg: lv.pkg,
      pos: lv.pos,
      purpose_type: lv.purpose_type,
      field_rows: parsed.rows,
      field_columns: parsed.cols,
      palette: parsed.palette,
    },
    queue: result,
  });
}

function asInt(v: unknown): number | undefined {
  if (v == null || v === "") return undefined;
  const n = parseInt(String(v), 10);
  return Number.isFinite(n) ? n : undefined;
}

export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const lvNum = asInt(url.searchParams.get("level_number"));
    if (lvNum == null) {
      return NextResponse.json({ ok: false, error: "missing level_number" }, { status: 400 });
    }
    return await loadAndGenerate(lvNum, {
      seed: asInt(url.searchParams.get("seed")),
      queueColumns: asInt(url.searchParams.get("queueColumns")),
      railCapacity: asInt(url.searchParams.get("railCapacity")),
      difficulty: url.searchParams.get("difficulty") ?? undefined,
      levelId: asInt(url.searchParams.get("levelId")),
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[GET /api/queue/generate]", msg);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as Record<string, unknown>;
    const lvNum = asInt(body.level_number);
    if (lvNum == null) {
      return NextResponse.json({ ok: false, error: "missing level_number" }, { status: 400 });
    }
    return await loadAndGenerate(lvNum, {
      seed: asInt(body.seed),
      queueColumns: asInt(body.queueColumns),
      railCapacity: asInt(body.railCapacity),
      difficulty: typeof body.difficulty === "string" ? body.difficulty : undefined,
      levelId: asInt(body.levelId),
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[POST /api/queue/generate]", msg);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
