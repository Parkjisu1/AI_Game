import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { spawn } from "child_process";
import { openSync, mkdirSync } from "fs";
import { dirname } from "path";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";

/**
 * Art batch 결과에 기믹 후보정 (post-processing).
 *
 * POST body:
 *   { art_batch_id: string, preset: "none" | "light" | "medium" | "heavy",
 *     iron_wall_mode?: "bl_outline" | "pf_wall",
 *     keep_all_candidates?: boolean,
 *     custom?: { gimmick_*: number } }
 *
 * 동작:
 *  1. pixelforge_grid_levels에서 batch_id의 levels 조회 (cells/palette/per_color_count 보유)
 *  2. 각 level을 BL CSV row 형태로 augment:
 *      - level_number = grid name 또는 idx
 *      - pkg = idx/20+1, pos = (idx-1)%20+1
 *      - purpose_type = pkg/pos 기반 (튜토리얼/노말/하드/슈하/휴식)
 *      - field_rows/cols, num_colors, color_distribution = grid에서 직접
 *      - gimmick_* = 프리셋 기반 (debut lv + idx 고려)
 *      - field_map = grid의 cells를 string 형태로 변환
 *  3. field-complete job 생성 + watcher spawn
 */

const JOBS_COLLECTION = "pixelforge_field_complete_jobs";
const ART_BATCH_COLLECTION = "pixelforge_batch_requests";
const GRID_LEVELS_COLLECTION = "pixelforge_grid_levels";

// 프리셋: 활성 기믹 + 카운트
const PRESETS: Record<string, (idx: number, level_num: number) => Record<string, number>> = {
  none: () => ({}),
  light: (idx, lv) => {
    // 1-2개 활성. lv 따라 종류 결정
    const out: Record<string, number> = {};
    if (lv >= 121) out.gimmick_wall = 1;
    else if (lv >= 101) out.gimmick_surprise = 8;
    else if (lv >= 61) out.gimmick_pin = 2;
    else if (lv >= 31) out.gimmick_pinata = 1;
    return out;
  },
  medium: (idx, lv) => {
    const out: Record<string, number> = {};
    if (lv >= 201) { out.gimmick_ice = 80; out.gimmick_pin = 3; }
    else if (lv >= 161) { out.gimmick_pinata_box = 1; out.gimmick_pin = 2; }
    else if (lv >= 121) { out.gimmick_wall = 1; out.gimmick_pinata = 2; }
    else if (lv >= 101) { out.gimmick_surprise = 16; out.gimmick_pin = 2; }
    else if (lv >= 61) { out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 31) out.gimmick_pinata = 2;
    return out;
  },
  heavy: (idx, lv) => {
    const out: Record<string, number> = {};
    if (lv >= 241) { out.gimmick_ice = 120; out.gimmick_pinata_box = 2; out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 161) { out.gimmick_pinata_box = 2; out.gimmick_pin = 4; out.gimmick_pinata = 2; }
    else if (lv >= 121) { out.gimmick_wall = 1; out.gimmick_pinata = 3; out.gimmick_pin = 3; }
    else if (lv >= 101) { out.gimmick_surprise = 24; out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 61) { out.gimmick_pin = 5; out.gimmick_pinata = 3; }
    else if (lv >= 31) out.gimmick_pinata = 3;
    return out;
  },
};

function derivePurpose(idx: number, pos: number): string {
  // BeatChart §6 PKG 3+ 포지션 룰
  if (pos === 9 || pos === 19) return "super_hard";
  if (pos === 5 || pos === 12 || pos === 15) return "hard";
  if (pos === 6 || pos === 10 || pos === 13 || pos === 16 || pos === 20) return "rest";
  if (pos === 1 || pos === 11) return "tutorial";
  return "normal";
}

function buildFieldMapString(cells: number[][]): string {
  return cells.map((row) => row.map((c) => (c < 0 ? ".." : String(c).padStart(2, "0"))).join(" ")).join("\n");
}

function buildColorDist(perColorCount: Record<string, number> | Map<string, number> | undefined): string {
  if (!perColorCount) return "";
  const obj = perColorCount instanceof Map
    ? Object.fromEntries(perColorCount)
    : (perColorCount as Record<string, number>);
  return Object.entries(obj).map(([c, n]) => `c${c}:${n}`).join(" ");
}

interface GridLevelDoc {
  _id: ObjectId;
  width?: number;
  height?: number;
  palette?: number[];
  per_color_count?: Record<string, number>;
  cells?: number[][];
  name?: string;
  extra_meta?: { batch_idx?: number };
}

export async function POST(req: NextRequest) {
  const session = await auth();
  const email = session?.user?.email || "";
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const artBatchId = String(body.art_batch_id ?? "");
  if (!artBatchId) return NextResponse.json({ error: "art_batch_id required" }, { status: 400 });

  const preset = String(body.preset ?? "medium");
  const presetFn = PRESETS[preset];
  if (!presetFn) return NextResponse.json({ error: `invalid preset: ${preset}` }, { status: 400 });

  const ironWallMode = String(body.iron_wall_mode ?? "bl_outline");
  const keepAllCandidates = body.keep_all_candidates === true;
  const customGimmicks = (body.custom as Record<string, number>) ?? {};

  const db = await getDb();

  // 1. Art batch 메타 조회 (created_by_email 매핑용)
  let artBatch;
  try {
    artBatch = await db.collection(ART_BATCH_COLLECTION).findOne({ _id: new ObjectId(artBatchId) });
  } catch {
    return NextResponse.json({ error: "invalid art_batch_id" }, { status: 400 });
  }
  if (!artBatch) return NextResponse.json({ error: "art batch not found" }, { status: 404 });

  // 2. 해당 batch의 grid levels 조회 (생성된 결과들)
  const gridLevels = await db.collection<GridLevelDoc>(GRID_LEVELS_COLLECTION)
    .find({ "extra_meta.batch_request_id": artBatchId })
    .toArray();

  // fallback A: batch_request_id 안 들어가 있으면 team_id + email + created_at 윈도우로 추정
  let levels = gridLevels;
  let fallbackUsed: string | null = null;
  if (levels.length === 0) {
    const t0 = artBatch.created_at ? new Date(artBatch.created_at as string).getTime() : 0;
    const t1 = artBatch.finished_at ? new Date(artBatch.finished_at as string).getTime() + 60_000 : Date.now();
    levels = await db.collection<GridLevelDoc>(GRID_LEVELS_COLLECTION)
      .find({
        created_by_email: artBatch.created_by_email,
        created_at: { $gte: new Date(t0).toISOString(), $lte: new Date(t1).toISOString() },
        team_id: { $regex: `^batch_` },
      } as Record<string, unknown>)
      .toArray();
    if (levels.length > 0) fallbackUsed = "time_window";
  }

  // fallback B: dedup 케이스 — 이 배치의 csv_rows level_number 로 기존 grid_levels 매칭.
  // 사용자 룰 (2026-05-21): dedup으로 ok=0이어도 기존 갤러리 레벨에 기믹 추가 가능하도록.
  // pixelforge_grid_levels 의 name 패턴 = "csv-lv{NNNN}-{metaphor}". csv_rows level_number 별 최신 매칭 picks.
  if (levels.length === 0) {
    const csvLvs = ((artBatch.csv_rows as Record<string, unknown>[]) || [])
      .map((r) => Number(r.level_number ?? 0))
      .filter((lv) => Number.isFinite(lv) && lv > 0);
    if (csvLvs.length > 0) {
      // build regex array — `csv-lv0001-...`, `csv-lv0292-...` 등
      const nameRegexes = csvLvs.map((lv) => new RegExp(`^csv-lv0*${lv}-`));
      const all = await db.collection<GridLevelDoc>(GRID_LEVELS_COLLECTION)
        .find({
          created_by_email: artBatch.created_by_email,
          name: { $in: nameRegexes },
        } as Record<string, unknown>)
        .sort({ created_at: -1 })
        .toArray();
      // level_number 별 최신 1건만 추림
      const latestByLv = new Map<number, GridLevelDoc>();
      for (const g of all) {
        const m = (g.name as string | undefined)?.match(/^csv-lv0*(\d+)-/);
        if (!m) continue;
        const lv = Number(m[1]);
        if (!latestByLv.has(lv)) latestByLv.set(lv, g);
      }
      levels = [...latestByLv.values()];
      if (levels.length > 0) fallbackUsed = "dedup_name_match";
    }
  }

  if (levels.length === 0) {
    return NextResponse.json({
      error: "no grid levels found for this batch",
      hint: "이 배치는 새 결과 0건이고 dedup 매칭도 실패. PixelForge /levels 페이지에서 직접 작업 권장.",
    }, { status: 404 });
  }

  // 2-1. batch_request의 원본 csv_rows를 level_number로 인덱스 (CSV에 명시된 purpose/gimmick 우선 사용)
  const origCsvByLv = new Map<number, Record<string, unknown>>();
  for (const cr of ((artBatch.csv_rows as Record<string, unknown>[]) || [])) {
    const lvNum = Number(cr.level_number ?? 0);
    if (lvNum > 0) origCsvByLv.set(lvNum, cr);
  }

  // 한글 → 영문 normalize (Python 측과 동기화)
  const purposeKoToEn: Record<string, string> = {
    "튜토리얼": "tutorial", "휴식": "rest", "노말": "normal",
    "하드": "hard", "슈퍼하드": "super_hard", "슈하": "super_hard",
  };
  function normPurpose(p: unknown): string | null {
    if (!p) return null;
    const s = String(p).trim();
    return purposeKoToEn[s] ?? s.toLowerCase().replace(/[- ]/g, "_");
  }

  // 2-2. grid_level.name 에서 메타포 + level 추출 — "csv-lv0NNN-METAPHOR" 패턴.
  //      v42 zone_pipeline 활성화 + CSV 정확 매칭에 필요.
  function extractMetaphorFromName(name: string | undefined): string {
    if (!name) return "";
    const m = name.match(/^csv-lv0*\d+-(.+)$/);
    if (!m) return "";
    return m[1].replace(/_/g, " ").trim();
  }
  function extractLvFromName(name: string | undefined): number | null {
    if (!name) return null;
    const m = name.match(/^csv-lv0*(\d+)-/);
    return m ? Number(m[1]) : null;
  }

  // 3. 각 level을 BL CSV row로 augment
  // dedup_fallback 모드: 기존 grid cells 무시하고 v42 zone_pipeline 으로 재생성.
  //   - field_map 비움 (watcher STEP 2 priority 1·2 skip)
  //   - bl_metaphor 채움 (watcher STEP 2 priority 2.5 활성)
  // 일반 모드: 기존 field_map 보존 (PixelForge 신규 이미지 그대로 사용).
  const useV42Metaphor = fallbackUsed === "dedup_name_match";
  const csvRows: Record<string, unknown>[] = levels.slice(0, 1000).map((g, i) => {
    const idx = (g.extra_meta?.batch_idx ?? i) + 1;
    // BUG FIX (2026-05-22): grid_level.name 에서 진짜 lv 추출 (예: "csv-lv0050-..." → 50).
    // 이전엔 array idx (1,2,3,...) 사용 → CSV [1,3,50,121,...] 가 1-40 로 잘못 매핑됨.
    const csvLv = extractLvFromName(g.name as string | undefined);
    const lv = csvLv ?? idx;
    // CSV의 원본 row와 매칭 (level_number 기준)
    const origCsv = origCsvByLv.get(lv) ?? origCsvByLv.get(idx);
    const pkg = Number(origCsv?.pkg ?? Math.floor((lv - 1) / 20) + 1);
    const pos = Number(origCsv?.pos ?? ((lv - 1) % 20) + 1);
    // CSV의 purpose 우선 (한글 normalize), 없으면 lv 기반 자동
    const purpose_type = normPurpose(origCsv?.purpose ?? origCsv?.purpose_type) ?? derivePurpose(lv, pos);
    const num_colors = (g.palette ?? []).length;
    const color_distribution = buildColorDist(g.per_color_count);
    const field_rows = g.height ?? 0;
    const field_columns = g.width ?? 0;
    const total_cells = (g.cells ?? []).flat().filter((c) => c >= 0).length;

    // 메타포 — origCsv > grid name 추출 순.
    const bl_metaphor = String(origCsv?.bl_metaphor ?? extractMetaphorFromName(g.name as string | undefined));

    // field_map / designer_note — v42 모드 분기.
    const rawFieldMap = buildFieldMapString(g.cells ?? []);
    const field_map = useV42Metaphor ? "" : rawFieldMap;
    const designer_note = useV42Metaphor
      ? `[Source]\nArt batch ${artBatchId} idx=${idx} (${g.name ?? "unnamed"})\n[Metaphor]\n${bl_metaphor}\n[Mode] v42_zone_pipeline (dedup_fallback)${ironWallMode === "pf_wall" ? "\n[mode=pf_wall]" : ""}`
      : `[Source]\nArt batch ${artBatchId} idx=${idx} (${g.name ?? "unnamed"})\n\n[FieldMap]\n${rawFieldMap}${ironWallMode === "pf_wall" ? "\n[mode=pf_wall]" : ""}`;

    // gimmick 우선순위: CSV 원본 > custom > preset
    const presetGim = presetFn(idx, lv);
    const csvGim: Record<string, number> = {};
    if (origCsv) {
      const GIMS = [
        "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
        "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
        "gimmick_spawner_o", "gimmick_pinata_box", "gimmick_ice",
        "gimmick_frozen_dart", "gimmick_curtain",
      ];
      for (const k of GIMS) {
        const v = Number(origCsv[k] ?? 0);
        if (!isNaN(v) && v > 0) csvGim[k] = v;
      }
    }
    const hasCSVGim = Object.keys(csvGim).length > 0;
    const finalGim: Record<string, number> = {
      gimmick_hidden: 0, gimmick_chain: 0, gimmick_pinata: 0, gimmick_glass_pipe: 0,
      gimmick_pin: 0, gimmick_lock_key: 0, gimmick_surprise: 0, gimmick_wall: 0,
      gimmick_spawner_o: 0, gimmick_spawner_t: 0, gimmick_pinata_box: 0,
      gimmick_ice: 0, gimmick_frozen_dart: 0, gimmick_curtain: 0,
      // CSV에 명시 있으면 그게 우선, 없으면 preset
      ...(hasCSVGim ? csvGim : presetGim),
      ...customGimmicks,
    };
    finalGim.gimmick_lock_key = 0;  // 1.0 SKIP

    return {
      level_number: lv,
      pkg,
      pos,
      chapter: pkg,
      purpose_type,
      field_rows,
      field_columns,
      total_cells,
      num_colors,
      color_distribution,
      queue_columns: 3,
      rail_capacity: total_cells > 700 ? 160 : total_cells > 500 ? 120 : 80,
      designer_note,
      field_map,
      bl_metaphor,
      ...finalGim,
      _source_grid_id: String(g._id),
      _v42_mode: useV42Metaphor,
    };
  });

  // 4. field-complete job 생성 + watcher spawn
  const jobs = db.collection(JOBS_COLLECTION);
  const now = new Date().toISOString();
  const csvSourceSuffix = fallbackUsed === "dedup_name_match" ? ", dedup_fallback" : "";
  const jobDoc = {
    created_at: now,
    created_by_email: email.toLowerCase(),
    csv_rows: csvRows,
    csv_source: `from_art_batch ${artBatchId.slice(-8)} (n=${csvRows.length}, preset=${preset}${csvSourceSuffix})`,
    art_batch_id: artBatchId,
    preset,
    fallback_used: fallbackUsed,
    row_count: csvRows.length,
    allow_escalation: true,
    keep_all_candidates: keepAllCandidates,
    iron_wall_mode: ironWallMode,
    status: "pending",
  };
  const inserted = await jobs.insertOne(jobDoc);
  const id = String(inserted.insertedId);

  // watcher spawn
  const watcherDir = process.env.WATCHER_DIR || "/home/aimed/.hermes/watcher";
  const pythonBin = process.env.WATCHER_PYTHON || "/home/aimed/.hermes/watcher/venv/bin/python";
  const logDir = process.env.FIELD_COMPLETE_LOG_DIR || "/home/aimed/.hermes/logs";
  const autoRun = (process.env.FIELD_COMPLETE_AUTO_RUN ?? "1") !== "0";

  if (autoRun) {
    try {
      const logPath = `${logDir}/field_complete_${id}.log`;
      try { mkdirSync(dirname(logPath), { recursive: true }); } catch { /* exists */ }
      const out = openSync(logPath, "a");
      const child = spawn(pythonBin, ["field_complete_levels.py", "--request", id],
        { cwd: watcherDir, detached: true, stdio: ["ignore", out, out], env: process.env });
      child.on("error", (e) => { console.error(`[fc-from-art ${id}] spawn error:`, e); });
      child.unref();
    } catch (e) {
      await jobs.updateOne(
        { _id: inserted.insertedId },
        { $set: { status: "failed", error: `spawn failed: ${e}`, finished_at: new Date().toISOString() } },
      );
      return NextResponse.json({ error: `실행 실패: ${e}` }, { status: 500 });
    }
  }

  return NextResponse.json({
    ok: true,
    id,
    row_count: csvRows.length,
    art_batch_id: artBatchId,
    preset,
    fallback_used: fallbackUsed,
    log_path: autoRun ? `${logDir}/field_complete_${id}.log` : undefined,
  });
}
