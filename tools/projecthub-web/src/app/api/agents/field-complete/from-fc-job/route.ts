import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { spawn } from "child_process";
import { openSync, mkdirSync, readFileSync, existsSync } from "fs";
import { dirname, join } from "path";
import { ObjectId } from "mongodb";

// PF gimmick index (level_number → BL gimmick_* counts). 1200 PF level 변형 union.
// 사용자 룰 (2026-05-21): PF 가 해당 lv 에 기믹 썼으면 BL 도 권장 count 사용,
// 안 썼으면 0. designer 의 [PF presence → BL field 2개 배치] 패턴 반영.
type PfIndexEntry = {
  level_number: number;
  variants: number;
  gimmick_types_pf: string[];
  [gimmickKey: string]: unknown;
};

let _pfIndex: Record<string, PfIndexEntry> | null = null;
function loadPfIndex(): Record<string, PfIndexEntry> {
  if (_pfIndex) return _pfIndex;
  // ProjectHub 루트의 data/ 디렉토리 우선
  const candidates = [
    join(process.cwd(), "data", "pf_gimmick_index.json"),
    "/home/aimed/projecthub-web/data/pf_gimmick_index.json",
  ];
  for (const p of candidates) {
    try {
      if (existsSync(p)) {
        _pfIndex = JSON.parse(readFileSync(p, "utf-8")) as Record<string, PfIndexEntry>;
        return _pfIndex;
      }
    } catch { /* try next */ }
  }
  _pfIndex = {};
  return _pfIndex;
}

export const runtime = "nodejs";

/**
 * 기존 field-complete job(특히 이미지 업로드)의 결과에 기믹 추가.
 *
 * Image upload로 만든 job은 level_number 기본 1 → debut 룰 때문에 기믹 0개.
 * 이 endpoint는 원본 csv_rows를 가져와서:
 *   1. level_number를 preset에 맞게 force-bump (light=41, medium=121, heavy=161)
 *   2. gimmick_* 필드 주입 (PRESETS 기반)
 *   3. 새 fc job 생성 + watcher spawn
 *
 * POST body:
 *   { fc_job_id: string, preset: "light" | "medium" | "heavy" | "none",
 *     iron_wall_mode?, keep_all_candidates?, custom? }
 */

const JOBS_COLLECTION = "pixelforge_field_complete_jobs";

const PRESET_LV_BUMP: Record<string, number> = {
  none: 0,        // 그대로
  light: 41,      // pin 가능
  medium: 121,    // wall+pinata
  heavy: 161,     // pinata_box+pin+pinata
  pf_grounded: 0, // PF 데이터 기반 — lv bump 안 함, CSV lv 그대로
};

/**
 * pf_grounded preset: PF index 룩업 → BL 기믹 카운트.
 * PF 가 해당 lv 에 기믹 썼으면 권장 count, 안 썼으면 0. CSV manual 값이 있으면 그대로 보존(상위에서 처리).
 */
function pfGroundedGimmicks(lv: number): Record<string, number> {
  const idx = loadPfIndex();
  const entry = idx[String(lv)];
  if (!entry) return {};
  const out: Record<string, number> = {};
  for (const k of GIM_KEYS) {
    const v = Number(entry[k] ?? 0);
    if (Number.isFinite(v) && v > 0) out[k] = v;
  }
  return out;
}

const PRESETS: Record<string, (lv: number) => Record<string, number>> = {
  none: () => ({}),
  light: (lv) => {
    const out: Record<string, number> = {};
    if (lv >= 121) out.gimmick_wall = 1;
    else if (lv >= 101) out.gimmick_surprise = 8;
    else if (lv >= 61) out.gimmick_pin = 2;
    else if (lv >= 31) out.gimmick_pinata = 1;
    return out;
  },
  medium: (lv) => {
    const out: Record<string, number> = {};
    if (lv >= 201) { out.gimmick_ice = 80; out.gimmick_pin = 3; }
    else if (lv >= 161) { out.gimmick_pinata_box = 1; out.gimmick_pin = 2; }
    else if (lv >= 121) { out.gimmick_wall = 1; out.gimmick_pinata = 2; }
    else if (lv >= 101) { out.gimmick_surprise = 16; out.gimmick_pin = 2; }
    else if (lv >= 61) { out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 31) out.gimmick_pinata = 2;
    return out;
  },
  heavy: (lv) => {
    const out: Record<string, number> = {};
    if (lv >= 241) { out.gimmick_ice = 120; out.gimmick_pinata_box = 2; out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 161) { out.gimmick_pinata_box = 2; out.gimmick_pin = 4; out.gimmick_pinata = 2; }
    else if (lv >= 121) { out.gimmick_wall = 1; out.gimmick_pinata = 3; out.gimmick_pin = 3; }
    else if (lv >= 101) { out.gimmick_surprise = 24; out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 61) { out.gimmick_pin = 5; out.gimmick_pinata = 3; }
    else if (lv >= 31) out.gimmick_pinata = 3;
    return out;
  },
  // PF 데이터 기반: 해당 lv 의 PF 가 실제로 쓴 기믹만 권장 count 로 주입.
  // PF 가 안 쓴 lv 은 기믹 0 (없으면 없게).
  pf_grounded: (lv) => pfGroundedGimmicks(lv),
};

const GIM_KEYS = [
  "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
  "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
  "gimmick_spawner_o", "gimmick_spawner_t", "gimmick_pinata_box",
  "gimmick_ice", "gimmick_frozen_dart", "gimmick_curtain",
];

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

  const fcJobId = String(body.fc_job_id ?? "");
  if (!fcJobId) return NextResponse.json({ error: "fc_job_id required" }, { status: 400 });

  const preset = String(body.preset ?? "medium");
  const presetFn = PRESETS[preset];
  if (!presetFn) return NextResponse.json({ error: `invalid preset: ${preset}` }, { status: 400 });
  const lvBump = PRESET_LV_BUMP[preset] ?? 0;

  const ironWallMode = String(body.iron_wall_mode ?? "bl_outline");
  const keepAllCandidates = body.keep_all_candidates === true;
  const customGimmicks = (body.custom as Record<string, number>) ?? {};

  const db = await getDb();
  const jobs = db.collection(JOBS_COLLECTION);

  // 원본 fc job 조회
  let origJob;
  try {
    origJob = await jobs.findOne({ _id: new ObjectId(fcJobId) });
  } catch {
    return NextResponse.json({ error: "invalid fc_job_id" }, { status: 400 });
  }
  if (!origJob) return NextResponse.json({ error: "fc job not found" }, { status: 404 });

  const origRows = (origJob.csv_rows as Record<string, unknown>[]) || [];
  if (origRows.length === 0) {
    return NextResponse.json({ error: "원본 job에 csv_rows 없음" }, { status: 400 });
  }

  // csv_rows 변환: level_number 보존 우선 + CSV 디자이너 기믹 의도 보존 + preset 보완
  const csvRows: Record<string, unknown>[] = origRows.map((r, i) => {
    const origLv = Number(r.level_number ?? (i + 1));
    // 사용자 룰 (2026-05-21): CSV 에 실제 lv (>1) 명시되어 있으면 절대 override 안 함.
    // lvBump 는 image-upload 케이스 (origLv=1 default) 에서만 적용.
    const hasExplicitLv = Number.isFinite(origLv) && origLv > 1;
    const lv = (lvBump > 0 && !hasExplicitLv) ? lvBump + i : origLv;

    const presetGim = presetFn(lv);

    // CSV 에 디자이너가 명시한 기믹 보존 — preset 이 덮어쓰지 않도록.
    const csvManualGim: Record<string, number> = {};
    for (const k of GIM_KEYS) {
      const v = Number(r[k] ?? 0);
      if (Number.isFinite(v) && v > 0) csvManualGim[k] = v;
    }
    const hasManualGim = Object.keys(csvManualGim).length > 0;

    // 우선순위: csv manual > custom (UI override) > preset
    const gimOverride: Record<string, number> = {};
    for (const k of GIM_KEYS) gimOverride[k] = 0;
    Object.assign(gimOverride, presetGim);
    if (hasManualGim) Object.assign(gimOverride, csvManualGim);  // CSV 디자이너 의도 보존
    Object.assign(gimOverride, customGimmicks);                  // UI 명시 override 최우선
    gimOverride.gimmick_lock_key = 0;  // 1.0 SKIP (강제)

    // pkg/pos 재계산 (lv 변경됐으면 새 값, 아니면 원본 보존)
    const pkg = hasExplicitLv && r.pkg ? Number(r.pkg) : Math.floor((lv - 1) / 20) + 1;
    const pos = hasExplicitLv && r.pos ? Number(r.pos) : ((lv - 1) % 20) + 1;

    return {
      ...r,
      level_number: lv,
      pkg,
      pos,
      chapter: hasExplicitLv && r.chapter ? Number(r.chapter) : pkg,
      ...gimOverride,
      _source_fc_job_id: fcJobId,
      _orig_level_number: origLv,
      _preset_applied: preset,
      _gimmick_source: hasManualGim ? "csv_manual" : (preset === "pf_grounded" ? "pf_grounded" : `preset_${preset}`),
    };
  });

  const now = new Date().toISOString();
  const jobDoc = {
    created_at: now,
    created_by_email: email.toLowerCase(),
    csv_rows: csvRows,
    csv_source: `from_fc_job ${fcJobId.slice(-8)} (n=${csvRows.length}, preset=${preset})`,
    source_fc_job_id: fcJobId,
    preset,
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
      child.on("error", (e) => { console.error(`[fc-from-fc ${id}] spawn error:`, e); });
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
    source_fc_job_id: fcJobId,
    preset,
    lv_bumped: lvBump > 0,
    log_path: autoRun ? `${logDir}/field_complete_${id}.log` : undefined,
  });
}
