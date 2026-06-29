import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { ObjectId } from "mongodb";
import {
  generateQueue,
  purposeToDifficulty,
  type Cells,
  type Difficulty,
  type GimmickCounts,
} from "@/lib/queue-generator";

export const runtime = "nodejs";

// BalloonFlow Level Exporter — uses queue-generator.ts (1:1 port from MapMakerController.cs)
//
// 입력:
//   pixelforge_grid_levels[id]            — Linear batch가 만든 cells + 메타
//   pixelforge_levels[level_number]       — BalloonFlow 300 draft 메타 (옵션, ?targetLevel=N)
//   URL query                             — 위 둘을 모두 오버라이드
//
// 출력:
//   format=balloonflow                    — BalloonFlow Level JSON (필드 + 큐 자동생성 + 분석 + 난이도 점수)
//   ?download=1                           — 첨부 다운로드
//   ?seed=N                               — PRNG 결정성 (재시도용 — 다른 seed 전달하면 다른 결과)
//
// converter_version: 3 (MapEditor 1:1 port)

const round1 = (n: number) => Math.round(n * 10) / 10;

function extractGimmickTypes(meta: Record<string, unknown>): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(meta)) {
    if (!k.startsWith("gimmick_")) continue;
    if (!v || v === 0 || v === "0" || v === "false") continue;
    const name = k.slice("gimmick_".length)
      .split("_")
      .filter(s => s.length > 0)
      .map(s => s[0].toUpperCase() + s.slice(1))
      .join("");
    if (name) out.push(name);
  }
  return out;
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!id || !/^[a-f0-9]{24}$/i.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  const url = new URL(req.url);
  const format = url.searchParams.get("format") || "balloonflow";
  if (format !== "balloonflow" && format !== "pixelforge") {
    return NextResponse.json({ error: `unsupported format: ${format}` }, { status: 400 });
  }

  const qInt = (k: string, def?: number): number | undefined => {
    const v = url.searchParams.get(k);
    if (v == null) return def;
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : def;
  };
  const qFloat = (k: string, def?: number): number | undefined => {
    const v = url.searchParams.get(k);
    if (v == null) return def;
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : def;
  };

  const db = await getDb();

  // 1) Linear grid level 로드
  const grid = await db.collection("pixelforge_grid_levels").findOne({ _id: new ObjectId(id) });
  if (!grid) return NextResponse.json({ error: "not found" }, { status: 404 });

  const cellsRaw = grid.cells as number[][] | undefined;
  if (!Array.isArray(cellsRaw) || cellsRaw.length === 0 || !Array.isArray(cellsRaw[0])) {
    return NextResponse.json(
      { error: "cells missing or malformed", id },
      { status: 422 },
    );
  }

  // 2) BalloonFlow draft 메타 매칭 (옵션)
  // 우선순위:
  //   ?targetLevel query
  //   > grid.name "lvNNNN" 자동 추출 (CSV batch: "csv-lv0274-...")
  //   > grid.name 끝의 "-NNNN" 추출 + 1 (mood/style batch: "kaleidoscope-pastel-plus_motif-0008")
  //   > extra_meta.batch_idx + 1
  //   > 없음
  let metaBase: Record<string, unknown> = {};
  let derivedLv = qInt("targetLevel");
  if (!derivedLv || derivedLv <= 0) {
    const nameStr = String(grid.name ?? "");
    // 1순위: "lvNNNN" (CSV batches: "csv-lv0274-...")
    const m1 = nameStr.match(/lv(\d+)/i);
    if (m1) {
      const n = parseInt(m1[1], 10);
      if (Number.isFinite(n) && n > 0) derivedLv = n;
    }
    // 2순위: 끝에 "-NNNN" (mood/style batches: "...-0008")
    if (!derivedLv) {
      const m2 = nameStr.match(/-(\d+)$/);
      if (m2) {
        const n = parseInt(m2[1], 10);
        if (Number.isFinite(n) && n >= 0) derivedLv = n + 1;  // 0-based idx → 1-based lv
      }
    }
    // 3순위: extra_meta.batch_idx + 1
    if (!derivedLv && grid.extra_meta && typeof (grid.extra_meta as Record<string, unknown>).batch_idx === "number") {
      derivedLv = ((grid.extra_meta as Record<string, number>).batch_idx) + 1;
    }
  }
  const targetLevel = derivedLv;
  if (targetLevel && targetLevel > 0) {
    const m = await db.collection("pixelforge_levels").findOne({ level_number: targetLevel });
    if (m) metaBase = m as Record<string, unknown>;
  }

  // 3) cells → balloons (Unity 좌표 변환)
  const gridRows = cellsRaw.length;
  const gridCols = cellsRaw[0].length;
  const balloonScale = qFloat("balloonScale", (metaBase.balloonScale as number) ?? 0.2)!;
  const flipY = url.searchParams.get("flipY") === "1";
  const hpDefault = qInt("hp", 2)!;

  type Balloon = {
    balloonId: number; color: number;
    gridPosition: { x: number; y: number };
    gimmickType: string; sizeW: number; sizeH: number;
    hp: number; lockPairId: number;
  };
  const balloons: Balloon[] = [];
  const colorCounts: Record<number, number> = {};

  for (let row = 0; row < gridRows; row++) {
    const r = cellsRaw[row];
    for (let col = 0; col < gridCols; col++) {
      const c = r[col];
      if (c == null || c < 0) continue;
      const xNorm = col - (gridCols - 1) / 2;
      const yNorm = flipY
        ? row - (gridRows - 1) / 2
        : (gridRows - 1) / 2 - row;
      balloons.push({
        balloonId: balloons.length,
        color: c,
        gridPosition: { x: round1(xNorm * balloonScale), y: round1(yNorm * balloonScale) },
        gimmickType: "",
        sizeW: 1, sizeH: 1,
        hp: hpDefault,
        lockPairId: -1,
      });
      colorCounts[c] = (colorCounts[c] || 0) + 1;
    }
  }
  if (balloons.length === 0) {
    return NextResponse.json(
      { error: "no balloons (cells all empty)", id },
      { status: 422 },
    );
  }

  const palette: number[] = Array.isArray(grid.palette) && grid.palette.length > 0
    ? (grid.palette as number[])
    : Object.keys(colorCounts).map(Number).sort((a, b) => a - b);

  // 4) 메타 우선순위: query > metaBase > 추정
  const railCapacityOverride = qInt("railCapacity", metaBase.rail_capacity as number | undefined);
  const queueColumnsOverride = qInt("queueColumns", metaBase.queue_columns as number | undefined);
  const difficultyPurpose = qInt("difficultyPurpose", (metaBase.purpose_type as number) ?? 1)!;
  const difficultyStr = url.searchParams.get("difficulty");
  const difficulty: Difficulty = difficultyStr
    ? purposeToDifficulty(difficultyStr)
    : purposeToDifficulty(metaBase.purpose_type ?? difficultyPurpose);

  // metaBase 필드들이 string으로 저장된 경우 (e.g. level_id="BF_274", pkg="14") 강제 숫자 추출
  const toInt = (v: unknown): number | undefined => {
    if (v == null) return undefined;
    if (typeof v === "number") return Number.isFinite(v) ? v : undefined;
    const s = String(v).trim();
    // "BF_274" 또는 "14" → 274 / 14
    const m = s.match(/(\d+)/);
    if (!m) return undefined;
    const n = parseInt(m[1], 10);
    return Number.isFinite(n) ? n : undefined;
  };
  const effectiveLevelId = qInt("levelId")
    ?? toInt(metaBase.level_number)
    ?? toInt(metaBase.level_id)
    ?? targetLevel
    ?? 1;
  const seed = qInt("seed", (grid.seed as number) ?? Math.floor(Date.now() / 1000))!;

  // ─────────────────────────────────────────────────────
  // format=pixelforge — Unity LevelJsonImporterWindow.JsonLevelData 호환
  // ─────────────────────────────────────────────────────
  if (format === "pixelforge") {
    const rowsCnt = cellsRaw.length;
    const colsCnt = cellsRaw[0].length;
    // [FieldMap] string — cellsRaw 값(0-based BL palette index)을 1-based color ID로 변환
    const fieldMapStr = cellsRaw.map((row) =>
      row.map((c) => (c == null || c < 0) ? ".." : String(c + 1).padStart(2, "0")).join(" ")
    ).join("\n");
    // color_distribution: per_color_count {6: 200, 9: 220, ...} (BL idx 0-based) → "c7:200 c10:220"
    const pcc = (grid.per_color_count as Record<string, number>) || {};
    const colorDistEntries = Object.entries(pcc)
      .map(([k, v]) => ({ id: Number(k) + 1, count: Number(v) }))
      .filter((e) => Number.isFinite(e.id) && Number.isFinite(e.count))
      .sort((a, b) => b.count - a.count);
    const colorDistStr = colorDistEntries.map((e) => `c${e.id}:${e.count}`).join(" ");
    const totalCells = colorDistEntries.reduce((s, e) => s + e.count, 0);
    // 자동 도출
    const autoPkg = effectiveLevelId > 0 ? Math.floor((effectiveLevelId - 1) / 20) + 1 : 0;
    const autoPos = effectiveLevelId > 0 ? ((effectiveLevelId - 1) % 20) + 1 : 0;
    const pkgV = qInt("packageId") ?? toInt(metaBase.pkg) ?? autoPkg;
    const posV = qInt("pos") ?? toInt(metaBase.pos) ?? autoPos;
    const chapterV = toInt(metaBase.chapter) ?? pkgV;
    const gimGet = (k: string): number => toInt(metaBase[k]) ?? 0;
    const pfJson = {
      level_number: effectiveLevelId,
      level_id: `Lv${String(effectiveLevelId).padStart(3, "0")}`,
      pkg: pkgV,
      pos: posV,
      chapter: chapterV,
      purpose_type: String(metaBase.purpose_type ?? "Normal"),
      target_cr: toInt(metaBase.target_cr) ?? 85,
      target_attempts: Number(metaBase.target_attempts ?? 1.5),
      num_colors: (grid.palette as number[] | undefined)?.length ?? colorDistEntries.length,
      color_distribution: colorDistStr,
      field_rows: rowsCnt,
      field_columns: colsCnt,
      total_cells: totalCells,
      rail_capacity: toInt(metaBase.rail_capacity) ?? 0,
      rail_capacity_tier: String(metaBase.rail_capacity_tier ?? ""),
      queue_columns: toInt(metaBase.queue_columns) ?? 3,
      queue_rows: toInt(metaBase.queue_rows) ?? 0,
      gimmick_hidden:     gimGet("gimmick_hidden"),
      gimmick_chain:      gimGet("gimmick_chain"),
      gimmick_pinata:     gimGet("gimmick_pinata"),
      gimmick_spawner_t:  gimGet("gimmick_spawner_t"),
      gimmick_pin:        gimGet("gimmick_pin"),
      gimmick_lock_key:   gimGet("gimmick_lock_key"),
      gimmick_surprise:   gimGet("gimmick_surprise"),
      gimmick_wall:       gimGet("gimmick_wall"),
      gimmick_spawner_o:  gimGet("gimmick_spawner_o"),
      gimmick_pinata_box: gimGet("gimmick_pinata_box"),
      gimmick_ice:        gimGet("gimmick_ice"),
      gimmick_frozen_dart:gimGet("gimmick_frozen_dart"),
      gimmick_curtain:    gimGet("gimmick_curtain"),
      total_darts: toInt(metaBase.total_darts) ?? 0,
      dart_capacity_range: String(metaBase.dart_capacity_range ?? "10,20,40"),
      emotion_curve: String(metaBase.emotion_curve ?? ""),
      designer_note: `[Source]\nProjectHub /levels (id=${id}, name=${String(grid.name ?? "unnamed")})\nlevel_number derived: ${effectiveLevelId} (lv${effectiveLevelId})\n\n[FieldMap]\n${fieldMapStr}`,
      pixel_art_source: "",
    };
    if (url.searchParams.get("download") === "1") {
      const fname = effectiveLevelId > 0
        ? `Lv${String(effectiveLevelId).padStart(3, "0")}_PixelForge`
        : String(grid.name ?? "level").replace(/[^a-zA-Z0-9_-]/g, "_");
      return new NextResponse(JSON.stringify(pfJson, null, 2), {
        headers: {
          "Content-Type": "application/json",
          "Content-Disposition": `attachment; filename="${fname}.json"`,
        },
      });
    }
    return NextResponse.json(pfJson);
  }

  // LD 입력 (pixelforge_levels.gimmick_*) — 큐 기믹 + 필드 기믹 모두
  const gimmickCounts: GimmickCounts = {};
  const asN = (v: unknown): number | undefined => {
    const n = typeof v === "number" ? v : parseInt(String(v ?? ""), 10);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  };
  // 큐 기믹
  if (metaBase.gimmick_hidden != null)     gimmickCounts.hidden     = asN(metaBase.gimmick_hidden);
  if (metaBase.gimmick_chain != null)      gimmickCounts.chain      = asN(metaBase.gimmick_chain);
  if (metaBase.gimmick_spawner_t != null)  gimmickCounts.spawner_t  = asN(metaBase.gimmick_spawner_t);
  if (metaBase.gimmick_spawner_o != null)  gimmickCounts.spawner_o  = asN(metaBase.gimmick_spawner_o);
  if (metaBase.gimmick_frozen_dart != null) gimmickCounts.frozen_dart = asN(metaBase.gimmick_frozen_dart);
  if (metaBase.gimmick_lock_key != null)   gimmickCounts.lock_key   = asN(metaBase.gimmick_lock_key);
  // 필드 기믹
  if (metaBase.gimmick_pinata != null)     gimmickCounts.pinata     = asN(metaBase.gimmick_pinata);
  if (metaBase.gimmick_wall != null)       gimmickCounts.wall       = asN(metaBase.gimmick_wall);
  if (metaBase.gimmick_pin != null)        gimmickCounts.pin        = asN(metaBase.gimmick_pin);
  if (metaBase.gimmick_surprise != null)   gimmickCounts.surprise   = asN(metaBase.gimmick_surprise);
  if (metaBase.gimmick_pinata_box != null) gimmickCounts.pinata_box = asN(metaBase.gimmick_pinata_box);
  if (metaBase.gimmick_ice != null)        gimmickCounts.ice        = asN(metaBase.gimmick_ice);
  if (metaBase.gimmick_curtain != null)    gimmickCounts.curtain    = asN(metaBase.gimmick_curtain);
  const hasAnyGimmick = Object.values(gimmickCounts).some(v => v != null && v > 0);

  // 5) 큐 생성 (queue-generator 모듈 호출)
  const queueResult = generateQueue({
    cells: cellsRaw as Cells,
    palette,
    difficulty,
    levelId: effectiveLevelId,
    queueColumns: queueColumnsOverride,
    railCapacity: railCapacityOverride,
    seed,
    gimmickCounts: hasAnyGimmick ? gimmickCounts : undefined,
  });

  // 6) holders → BalloonFlow Holder 형식 변환 + §5 STEP C 오버레이 적용
  const queueColumns = queueResult.queue_columns;
  const overlay = queueResult.overlay;
  const hiddenSet = new Set(overlay?.hidden_ids ?? []);
  const linkedById = new Map<number, { groupId: number }>();
  overlay?.linked_groups.forEach((g, gi) => {
    g.ids.forEach(id => linkedById.set(id, { groupId: gi }));
  });
  const frozenById = new Map<number, number>();
  overlay?.frozen.forEach(f => frozenById.set(f.id, f.health));
  const holders = queueResult.holders.map((h, i) => {
    let queueGimmick = "";
    if (hiddenSet.has(i)) queueGimmick = "Hidden";
    else if (linkedById.has(i)) queueGimmick = "Linked";
    else if (frozenById.has(i)) queueGimmick = "Frozen";
    return {
      holderId: i,
      color: h.color,
      magazineCount: h.mag,
      position: { x: i % queueColumns, y: Math.floor(i / queueColumns) },
      queueGimmick,
      chainGroupId: linkedById.get(i)?.groupId ?? -1,
      frozenHP: frozenById.get(i) ?? 0,
      spawnerHP: 0,
      spawnerColors: [] as number[],
      spawnerMag: 0,
      lockPairId: -1,
    };
  });

  // 필드 기믹 → balloons[] 적용
  const fieldOverlay = queueResult.field_overlay;
  if (fieldOverlay) {
    const pinataMap = new Map<number, number>();
    fieldOverlay.pinata_balloons.forEach(p => pinataMap.set(p.balloonId, p.life));
    const hiddenBalloonSet = new Set(fieldOverlay.hidden_balloons);
    // Pinata box / Frozen layer / Barricade는 별도 영역 — balloons 대신 raw_field_overlay에 포함
    for (let i = 0; i < balloons.length; i++) {
      if (pinataMap.has(i)) {
        balloons[i].gimmickType = "Pinata";
        balloons[i].hp = pinataMap.get(i)!;
      } else if (hiddenBalloonSet.has(i)) {
        balloons[i].gimmickType = "Hidden";
      }
    }
  }
  const conveyorPositions = holders.map(h => ({ x: h.position.x, y: h.position.y }));

  const railCapacity = railCapacityOverride ?? queueResult.field_analysis.rail_capacity;

  // 표준 rail 좌표 (Level_0010 참조)
  const rail = {
    waypoints: [
      { x: -3.0, y: 0.5, z: -3.0 },
      { x:  3.0, y: 0.5, z: -3.0 },
      { x:  3.0, y: 0.5, z:  3.0 },
      { x: -3.0, y: 0.5, z:  3.0 },
      { x: -3.0, y: 0.5, z: -3.0 },
    ],
  };

  const gimmickTypes = extractGimmickTypes(metaBase);

  // 7) 최종 BalloonFlow Level JSON
  // levelId가 1+이면 packageId/positionInPackage 자동 도출 (CSV/메타 우선, 없으면 lv 기반)
  const autoPkg = effectiveLevelId > 0 ? Math.floor((effectiveLevelId - 1) / 20) + 1 : 0;
  const autoPos = effectiveLevelId > 0 ? ((effectiveLevelId - 1) % 20) + 1 : 0;
  // 모두 강제 number — Unity int 호환
  const finalPackageId = qInt("packageId") ?? toInt(metaBase.pkg) ?? autoPkg;
  const finalPositionInPackage = qInt("pos") ?? toInt(metaBase.pos) ?? autoPos;
  const result = {
    levelId: effectiveLevelId,
    packageId: finalPackageId,
    positionInPackage: finalPositionInPackage,
    railCapacity,
    numColors: palette.length,
    balloonCount: balloons.length,
    balloonScale,
    queueColumns,
    targetClearRate: qFloat("targetClearRate", (metaBase.target_cr as number) ?? 0.0)!,
    difficultyPurpose,
    gimmickTypes,
    holders,
    balloons,
    rail,
    conveyorPositions,
    gridCols,
    gridRows,
    star1Threshold: qInt("star1", 0)!,
    star2Threshold: qInt("star2", 0)!,
    star3Threshold: qInt("star3", 0)!,
    tutorialSteps: [] as unknown[],
    cellColors: palette,
    gimmickColors: [] as number[],
    allColors: palette,
    _pixelflow_meta: {
      source_name: (grid.name as string) || `grid-${id}`,
      source_grid_id: id,
      source_difficulty: difficulty,
      converter: "projecthub-web/api/levels/[id]/export",
      converter_version: 6, // v3.15 + 필드 기믹 자동 배치
      spec_source: "BalloonFlow_큐생성기_명세.md v3.15 (Chain col adjacency + cycle 검사) + 픽셀아트워크플로우 §STEP 5 + PF 회귀",
      seed,
      recommended_queue_columns: queueResult.recommended_queue_columns,
      field_analysis: queueResult.field_analysis,
      difficulty_score: queueResult.difficulty_score,
      validation: queueResult.validation,
      overlay: queueResult.overlay ?? null,
      step_c_validation: queueResult.step_c_validation ?? null,
      field_overlay: queueResult.field_overlay ?? null,
      field_gimmick_validation: queueResult.field_gimmick_validation ?? null,
    },
  };

  if (url.searchParams.get("download") === "1") {
    // 파일명: lv 번호 있으면 "Lv274.balloonflow.json", 없으면 source_name
    const fname = effectiveLevelId > 0
      ? `Lv${String(effectiveLevelId).padStart(3, "0")}`
      : String(result._pixelflow_meta.source_name).replace(/[^a-zA-Z0-9_-]/g, "_");
    return new NextResponse(JSON.stringify(result, null, 2), {
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": `attachment; filename="${fname}.balloonflow.json"`,
      },
    });
  }
  return NextResponse.json(result);
}
