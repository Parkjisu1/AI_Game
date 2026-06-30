import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { spawn } from "child_process";
import { openSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";

/**
 * Pipeline stage 진행 — 사용자 액션.
 *
 * POST /api/agents/pipeline/[id]/advance
 * body: { action: "curate" | "field" | "download" | "retry_art" | "retry_field",
 *         selections?: {[lv]: "A"|"B"} }   // action=curate 시 필수
 *
 * stage 전이:
 *   curated_pending → curate(selections) → curated_done → field_running (auto if auto_advance)
 *   curated_done → field → field_running → field_done (watcher 가 자동)
 *   field_done → download → done
 *
 * 부수 동작:
 *   action=curate: 큐레이션 결과 → pixelforge_levels.field_map 갱신 (재사용: 기존 /v43-batch/[id]/curate 의 로직)
 *   action=field : field_complete spawn — csv_rows 합성 후 watcher 호출
 *   action=download: zip 생성 (existing /field-complete/[id]/export)
 */

const COLL = "pixelforge_pipeline_sessions";
const WATCHER_DIR = process.env.WATCHER_DIR || "/home/aimed/.hermes/watcher";
const PYTHON_BIN = process.env.WATCHER_PYTHON || "/home/aimed/.hermes/watcher/venv/bin/python";
const FC_LOG_DIR = process.env.FIELD_COMPLETE_LOG_DIR || "/home/aimed/.hermes/logs";

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  const email = session?.user?.email || "";
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  let objId: ObjectId;
  try { objId = new ObjectId(id); }
  catch { return NextResponse.json({ error: "invalid id" }, { status: 400 }); }

  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; }
  catch { return NextResponse.json({ error: "invalid json" }, { status: 400 }); }

  const action = String(body.action || "");
  const db = await getDb();
  const sess = await db.collection(COLL).findOne({ _id: objId });
  if (!sess) return NextResponse.json({ error: "session not found" }, { status: 404 });

  const now = new Date().toISOString();

  if (action === "curate") {
    // Selections POST → /v43-batch/[id]/curate 의 코어 로직 인라인.
    // 그냥 internal HTTP fetch 대신 직접 처리 — pngjs 사용.
    const selections = (body.selections || {}) as Record<string, "A" | "B" | null>;
    const artJobId = (sess.art_job as { job_id?: string } | undefined)?.job_id;
    if (!artJobId) return NextResponse.json({ error: "art_job_id 없음" }, { status: 400 });

    // internal fetch — req.nextUrl.origin(HTTPS) 로 가면 SSL handshake 실패 (2026-05-27 발견).
    // 같은 Next.js 프로세스에 자기 자신을 localhost HTTP 로 호출.
    const baseUrl = `http://127.0.0.1:${process.env.PORT || 3000}`;
    interface CurateResp { results?: Array<{ level: number; ok?: boolean }>; [k: string]: unknown }
    let r: Response;
    let j: CurateResp;
    try {
      r = await fetch(`${baseUrl}/api/agents/v43-batch/${artJobId}/curate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "cookie": req.headers.get("cookie") || "" },
        body: JSON.stringify({ selections }),
      });
      j = (await r.json()) as CurateResp;
    } catch (e) {
      return NextResponse.json({ error: "curate fetch 실패", detail: e instanceof Error ? e.message : String(e) }, { status: 502 });
    }
    if (!r.ok) {
      return NextResponse.json({ error: "curate 실패", detail: j }, { status: r.status });
    }

    // stage → curated_done (또는 auto_advance 면 곧장 field_running 시작)
    const updates: Record<string, unknown> = {
      updated_at: now,
      curations: selections,
      curation_results: j.results,
      stage: sess.auto_advance ? "field_running" : "curated_done",
    };
    await db.collection(COLL).updateOne({ _id: objId }, {
      $set: updates,
      $push: { stage_history: { stage: updates.stage as string, at: now, by: email.toLowerCase() } } as never,
    });

    // auto_advance 시 FC 자동 spawn
    if (sess.auto_advance) {
      await spawnFieldComplete(db, sess, objId, email, j.results || []);
    }

    return NextResponse.json({ ok: true, curate: j, stage: updates.stage });
  }

  // ── [2026-06-18] Queue 스테이지 (Curate → Queue → Field) ──────────────────────
  // 큐레이션된 field_map 위에서 레벨별 큐 생성 + 난이도 매칭(시드스윕).
  // purpose_type→목표 등급, /api/queue/generate(seed) 의 difficulty_score.grade 가
  // 목표와 맞는 시드를 골라 confirm. 못 맞추면 최근접 등급 채택(+flag).
  if (action === "queue") {
    const okStages = ["curated_done", "art_done", "curated_pending", "queue_done"];
    if (!okStages.includes(String(sess.stage))) {
      return NextResponse.json({ error: `stage=${sess.stage} 에서 queue 실행 불가 (curated_done 필요)` }, { status: 400 });
    }
    const targetLevels = (sess.target_levels as number[]) || [];
    const curated = ((sess.curation_results as unknown[]) || []) as Array<{ level: number; ok?: boolean }>;
    const lvs = curated.length > 0 ? curated.filter((c) => c.ok).map((c) => c.level) : targetLevels;
    const force = body.force === true;
    const N_SEEDS = Number(body.nSeeds) > 0 ? Math.min(40, Number(body.nSeeds)) : 16;

    await db.collection(COLL).updateOne({ _id: objId }, {
      $set: { stage: "queue_running", updated_at: now },
      $push: { stage_history: { stage: "queue_running", at: now, by: email.toLowerCase() } } as never,
    });

    const PF_BASE = "http://127.0.0.1:3002/pixelforge";
    const rows = await db.collection("pixelforge_levels")
      .find({ level_number: { $in: lvs }, status: { $exists: true } },
            { projection: { level_number: 1, purpose_type: 1, field_map: 1, queue_data: 1 } })
      .toArray();
    const metaByLv = new Map(rows.map((r) => [Number(r.level_number), r]));
    const GRADE_ORDER: Record<string, number> = { easy: 0, normal: 1, hard: 2, super_hard: 3, trivial: -1 };
    const targetGradeOf = (p: unknown): string => {
      const s = String(p ?? "").toLowerCase();
      if (s.includes("super") || s.includes("슈퍼")) return "super_hard";
      if (s.includes("hard") || s.includes("하드")) return "hard";
      if (s.includes("rest") || s.includes("휴식") || s.includes("tutorial") || s.includes("튜토") || s.includes("easy")) return "easy";
      return "normal";
    };

    const results: Array<{ level: number; grade: string; target: string; matched: boolean; seed: number; relative: number }> = [];
    const failed: Array<{ level: number; error: string }> = [];
    const skipped: number[] = [];

    for (const lv of lvs) {
      const meta = metaByLv.get(lv);
      if (!meta || !meta.field_map || !String(meta.field_map).trim()) { failed.push({ level: lv, error: "no field_map" }); continue; }
      if (meta.queue_data && !force) { skipped.push(lv); continue; }
      const target = targetGradeOf(meta.purpose_type);
      let chosen: { queue: unknown; seed: number; grade: string; rel: number } | null = null;
      let closest: { queue: unknown; seed: number; grade: string; rel: number } | null = null;
      let closestDelta = Infinity;
      for (let s = 0; s < N_SEEDS; s++) {
        try {
          const gr = await fetch(`${PF_BASE}/api/queue/generate`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ level_number: lv, seed: s }),
          });
          const gj = await gr.json();
          if (!gr.ok || !gj.queue) continue;
          const ds = (gj.queue.difficulty_score || {}) as { grade?: string; relative_pct?: number };
          const grade = ds.grade || "normal";
          const rel = ds.relative_pct ?? 0;
          if (grade === target) { chosen = { queue: gj.queue, seed: s, grade, rel }; break; }
          const delta = Math.abs((GRADE_ORDER[grade] ?? 1) - (GRADE_ORDER[target] ?? 1));
          if (delta < closestDelta) { closestDelta = delta; closest = { queue: gj.queue, seed: s, grade, rel }; }
        } catch { /* next seed */ }
      }
      const pick = chosen || closest;
      if (!pick) { failed.push({ level: lv, error: "queue gen failed (all seeds)" }); continue; }
      try {
        await fetch(`${PF_BASE}/api/queue/confirm`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ level_number: lv, queue: pick.queue }),
        });
        results.push({ level: lv, grade: pick.grade, target, matched: !!chosen, seed: pick.seed, relative: pick.rel });
      } catch (e) { failed.push({ level: lv, error: `confirm: ${e}` }); }
    }

    const doneAt = new Date().toISOString();
    await db.collection(COLL).updateOne({ _id: objId }, {
      $set: { stage: "queue_done", updated_at: doneAt,
              queue_summary: { generated: results.length, failed: failed.length, skipped: skipped.length, results, failed_levels: failed } },
      $push: { stage_history: { stage: "queue_done", at: doneAt, by: email.toLowerCase() } } as never,
    });
    return NextResponse.json({ ok: true, stage: "queue_done",
      generated: results.length, failed: failed.length, skipped: skipped.length, results, failed_levels: failed });
  }

  if (action === "field") {
    // [2026-06-18] Queue 후 Field. queue_done 도 허용(권장 순서). 기존 curated_done 도 하위호환.
    const okFieldStages = ["curated_done", "art_done", "curated_pending", "queue_done"];
    if (!okFieldStages.includes(String(sess.stage))) {
      return NextResponse.json({ error: `stage=${sess.stage} 에서 field 실행 불가 (queue_done/curated_done 필요)` }, { status: 400 });
    }
    // 큐레이션이 비어있어도 OK — pixelforge_levels.field_map 그대로 사용
    await db.collection(COLL).updateOne({ _id: objId }, {
      $set: { stage: "field_running", updated_at: now },
      $push: { stage_history: { stage: "field_running", at: now, by: email.toLowerCase() } } as never,
    });
    const sel = ((sess.curation_results as unknown[]) || []) as Array<{ level: number; ok?: boolean }>;
    await spawnFieldComplete(db, sess, objId, email, sel);
    return NextResponse.json({ ok: true, stage: "field_running" });
  }

  if (action === "download") {
    if (sess.stage !== "field_done") {
      return NextResponse.json({ error: `stage=${sess.stage} 에서 download 불가 (field_done 필요)` }, { status: 400 });
    }
    const fcJobId = (sess.field_complete_job as { job_id?: string } | undefined)?.job_id;
    if (!fcJobId) return NextResponse.json({ error: "fc_job_id 없음" }, { status: 400 });
    // export endpoint 의 zip URL 반환 (실제 zip 생성은 UI 에서 a href)
    await db.collection(COLL).updateOne({ _id: objId }, {
      $set: { stage: "done", updated_at: now, "download.ready_at": now,
              "download.fc_job_id": fcJobId },
      $push: { stage_history: { stage: "done", at: now, by: email.toLowerCase() } } as never,
    });
    return NextResponse.json({ ok: true, stage: "done",
      download_url: `/api/agents/field-complete/${fcJobId}/export?force=1` });
  }

  if (action === "retry_art") {
    return NextResponse.json({ error: "retry_art 는 새 pipeline 생성으로 대체" }, { status: 400 });
  }
  if (action === "retry_field") {
    if (sess.stage === "field_done" || sess.stage === "failed") {
      const sel = ((sess.curation_results as unknown[]) || []) as Array<{ level: number; ok?: boolean }>;
      await db.collection(COLL).updateOne({ _id: objId }, {
        $set: { stage: "field_running", updated_at: now },
        $push: { stage_history: { stage: "field_running", at: now, by: email.toLowerCase(), note: "retry" } } as never,
      });
      await spawnFieldComplete(db, sess, objId, email, sel);
      return NextResponse.json({ ok: true, stage: "field_running" });
    }
    return NextResponse.json({ error: `stage=${sess.stage} 에서 retry_field 불가` }, { status: 400 });
  }

  return NextResponse.json({ error: `unknown action: ${action}` }, { status: 400 });
}

async function spawnFieldComplete(
  db: import("mongodb").Db,
  sess: Record<string, unknown>,
  sessObjId: ObjectId,
  email: string,
  curatedResults: Array<{ level: number; ok?: boolean }>,
): Promise<void> {
  const targetLevels = (sess.target_levels as number[]) || [];
  const preset = (sess.gimmick_preset as string) || "pf_grounded";

  // pixelforge_levels 에서 큐레이션된 (또는 모든 target) lv 의 field_map + 메타 → csv_rows 합성
  const rows = await db.collection("pixelforge_levels")
    .find({ level_number: { $in: targetLevels }, status: { $exists: true } })
    .toArray();
  const byLv = new Map(rows.map((r) => [Number(r.level_number), r]));

  // 큐레이션 successful 만 우선 (지정 안 됐으면 전체)
  const lvsToProcess = curatedResults.length > 0
    ? curatedResults.filter((c) => c.ok).map((c) => c.level)
    : targetLevels;

  // PF lookup index 로 pf_grounded preset 적용 (기존 from-fc-job preset 로직 재사용)
  let pfIndex: Record<string, Record<string, number>> = {};
  try {
    const fs = await import("fs/promises");
    const pIdx = await fs.readFile("/home/aimed/projecthub-web/data/pf_gimmick_index.json", "utf-8");
    pfIndex = JSON.parse(pIdx);
  } catch { /* ignore */ }
  const GIM_KEYS = [
    "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
    "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
    "gimmick_spawner_o", "gimmick_spawner_t", "gimmick_pinata_box",
    "gimmick_ice", "gimmick_frozen_dart", "gimmick_curtain",
  ];
  // BL debut lv (field_complete_levels.py BL_DEBUT_LV 와 정합).
  // lv < debut 인 gimmick 은 validation reject — PF lookup 자동주입 결과를 사전 필터링.
  const BL_DEBUT_LV: Record<string, number> = {
    gimmick_hidden: 11, gimmick_chain: 21, gimmick_pinata: 31,
    gimmick_glass_pipe: 41, gimmick_pin: 61, gimmick_lock_key: 81,
    gimmick_snake: 81, gimmick_surprise: 101, gimmick_wall: 121,
    gimmick_spawner_o: 141, gimmick_pinata_box: 161, gimmick_ice: 201,
    gimmick_frozen_dart: 241, gimmick_curtain: 301,
    gimmick_spawner_t: 41, // glass_pipe alias
  };

  const csvRows: Record<string, unknown>[] = [];
  for (const lv of lvsToProcess) {
    const r = byLv.get(lv);
    if (!r) continue;
    const row: Record<string, unknown> = {
      level_number: lv,
      pkg: r.pkg, pos: r.pos, chapter: r.chapter,
      purpose_type: r.purpose_type ?? "normal",
      field_rows: r.field_rows, field_columns: r.field_columns,
      total_cells: r.total_cells, num_colors: r.num_colors,
      color_distribution: r.color_distribution,
      queue_columns: r.queue_columns ?? 3,
      rail_capacity: r.rail_capacity ?? 80,
      designer_note: r.designer_note ?? "",
      field_map: r.field_map ?? "",
      bl_metaphor: r.bl_metaphor ?? "",
      _pipeline_session: String(sessObjId),
    };
    // gimmick injection — BL debut gate 적용 (lv < debut 인 gimmick 은 skip).
    // PF lookup 은 PF (PixelFlow) lv 기준 회귀이므로 BL debut 와 다름 — 사전 필터링 필수.
    const gim: Record<string, number> = {};
    if (preset === "pf_grounded" && pfIndex[String(lv)]) {
      const entry = pfIndex[String(lv)];
      for (const k of GIM_KEYS) {
        if (typeof entry[k] === "number" && entry[k] > 0) {
          const debut = BL_DEBUT_LV[k] ?? 0;
          if (lv >= debut) gim[k] = entry[k] as number;
        }
      }
    }
    // CSV 자체에 명시된 gimmick 우선 (덮어쓰기) — 동일하게 debut gate 적용 (방어적).
    for (const k of GIM_KEYS) {
      const v = Number(r[k] ?? 0);
      if (Number.isFinite(v) && v > 0) {
        const debut = BL_DEBUT_LV[k] ?? 0;
        if (lv >= debut) gim[k] = v;
      }
    }
    for (const k of GIM_KEYS) row[k] = gim[k] ?? 0;
    row.gimmick_lock_key = 0; // 1.0 SKIP
    csvRows.push(row);
  }

  if (csvRows.length === 0) {
    await db.collection(COLL).updateOne({ _id: sessObjId }, {
      $set: { stage: "failed", error: "FC csv_rows 합성 0건" },
    });
    return;
  }

  // pixelforge_field_complete_jobs insert
  const fcInsert = await db.collection("pixelforge_field_complete_jobs").insertOne({
    created_at: new Date().toISOString(),
    created_by_email: email.toLowerCase(),
    csv_rows: csvRows,
    csv_source: `[Pipeline ${String(sessObjId).slice(-6)}] preset=${preset}, n=${csvRows.length}`,
    source_pipeline: String(sessObjId),
    preset,
    row_count: csvRows.length,
    allow_escalation: true,
    keep_all_candidates: false,
    status: "pending",
  });
  const fcJobId = String(fcInsert.insertedId);

  // session link
  await db.collection(COLL).updateOne({ _id: sessObjId }, {
    $set: {
      field_complete_job: { job_id: fcJobId, status: "running", started_at: new Date().toISOString() },
      updated_at: new Date().toISOString(),
    },
  });

  // spawn watcher
  try {
    const logPath = join(FC_LOG_DIR, `field_complete_${fcJobId}.log`);
    try { mkdirSync(dirname(logPath), { recursive: true }); } catch { /* exists */ }
    const out = openSync(logPath, "a");
    const child = spawn(
      PYTHON_BIN,
      ["field_complete_levels.py", "--request", fcJobId],
      {
        cwd: WATCHER_DIR, detached: true, stdio: ["ignore", out, out],
        env: { ...process.env, MONGODB_URI: process.env.MONGODB_URI, MONGODB_DB: process.env.MONGODB_DB || "aigame" },
      },
    );
    child.on("error", (e) => console.error(`[pipeline FC spawn] ${e}`));
    child.unref();
  } catch (e) {
    await db.collection(COLL).updateOne({ _id: sessObjId }, {
      $set: { stage: "failed", error: `FC spawn 실패: ${e}` },
    });
  }
}
