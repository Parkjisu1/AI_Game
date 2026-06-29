// Load all 300 pixelforge_levels → 7:3 source assignment → ensure queue_data →
// build BalloonFlow Importer JSON with cells+gimmicks+holders → write to OUT_DIR.
//
// Run on Mother (queue endpoints localhost:3002). scp OUT_DIR back to Windows.

const { MongoClient } = require("/home/aimed/projecthub-web/node_modules/mongodb");
const fs = require("fs");
const path = require("path");
const http = require("http");

const URI = process.env.MONGODB_URI;
const DB = process.env.MONGODB_DB || "aigame";
const OUT_DIR = process.env.OUT_DIR || "/tmp/Generated_300";
const PF_PORT = 3002;
const PF_BASEPATH = "/pixelforge";
const PH_TARGET = 90;   // 7:3 = 210 PF + 90 PH
const LV_RANGE = [1, 300];

if (!URI) { console.error("MONGODB_URI missing"); process.exit(1); }

fs.mkdirSync(OUT_DIR, { recursive: true });

// ── HTTP helpers (localhost only) ────────────────────────────────
function postJson(pathSuffix, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = http.request({
      host: "127.0.0.1", port: PF_PORT, method: "POST",
      path: `${PF_BASEPATH}${pathSuffix}`,
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) },
    }, (res) => {
      let chunks = "";
      res.on("data", (c) => { chunks += c; });
      res.on("end", () => {
        try { resolve(JSON.parse(chunks)); }
        catch { reject(new Error(`bad json: ${chunks.slice(0, 200)}`)); }
      });
    });
    req.on("error", reject);
    req.write(data); req.end();
  });
}

// ── BalloonFlow Importer JSON 빌더 ─────────────────────────────────
function buildFieldMapFromBalloonsAndGimmicks(balloons, gimmicks, rows, cols) {
  // 우선순위: gimmick cells > balloons. 빈 셀 = ".."
  if (rows <= 0 || cols <= 0) return "";
  const grid = Array.from({ length: rows }, () => Array(cols).fill(".."));
  // 풍선 먼저
  for (const b of balloons || []) {
    if (b.row >= 0 && b.row < rows && b.col >= 0 && b.col < cols) {
      grid[b.row][b.col] = String(b.color).padStart(2, "0");
    }
  }
  // 기믹은 cells 단위 (gimmick.cells: [[r,c], ...]) 또는 단일 (row,col)
  for (const g of gimmicks || []) {
    const cells = [];
    if (Array.isArray(g.cells)) {
      for (const c of g.cells) {
        if (Array.isArray(c) && c.length >= 2 && typeof c[0] === "number") {
          cells.push([c[0], c[1]]);
        }
      }
    } else if (typeof g.row === "number" && typeof g.col === "number") {
      cells.push([g.row, g.col]);
    }
    for (const [r, c] of cells) {
      if (r >= 0 && r < rows && c >= 0 && c < cols && grid[r][c] === "..") {
        if (g.type === "Hidden_Balloon" && typeof g.hidden_color === "number") {
          grid[r][c] = String(g.hidden_color).padStart(2, "0");
        } else if (typeof g.color === "number") {
          grid[r][c] = String(g.color).padStart(2, "0");
        }
      }
    }
  }
  return grid.map((row) => row.join(" ")).join("\n");
}

function colorDistStr(colorDarts) {
  if (!colorDarts) return "";
  return Object.entries(colorDarts)
    .map(([k, v]) => `${k}:${v}`)
    .join(" ");
}

function asInt(v, d = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.round(n) : d;
}
function asNum(v, d = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}
function asStr(v, d = "") {
  return v === null || v === undefined ? d : String(v);
}

function buildBalloonFlowJson(row, sourceLabel) {
  const lv = asInt(row.level_number, 1);
  let rows = asInt(row.field_rows, 16);
  let cols = asInt(row.field_columns, 16);
  const balloons = Array.isArray(row.balloons) ? row.balloons : [];
  const gimmicks = Array.isArray(row.gimmicks) ? row.gimmicks : [];

  // field_map — DB 의 field_map 우선, 없으면 balloons + gimmicks 로 재구성
  let fieldMap = typeof row.field_map === "string" ? row.field_map.trim() : "";
  if (!fieldMap && balloons.length > 0) {
    fieldMap = buildFieldMapFromBalloonsAndGimmicks(balloons, gimmicks, rows, cols);
  }

  // field_map 실제 크기로 field_rows/columns 보정 (8개 레벨 dim mismatch 케이스)
  if (fieldMap) {
    const lines = fieldMap.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length > 0) {
      const actualRows = lines.length;
      const actualCols = lines[0].split(/\s+/).length;
      if (actualRows !== rows || actualCols !== cols) {
        // field_map 이 truth — 모든 행이 같은 컬럼 수 가졌는지 확인
        const allUniform = lines.every(l => l.split(/\s+/).length === actualCols);
        if (allUniform) {
          rows = actualRows;
          cols = actualCols;
        }
      }
    }
  }

  // color_darts (field_analysis 우선, 없으면 카운트 계산)
  let colorDarts = row.field_analysis?.color_darts || null;
  if (!colorDarts && balloons.length > 0) {
    colorDarts = {};
    for (const b of balloons) {
      const k = `c${b.color}`;
      colorDarts[k] = (colorDarts[k] || 0) + 1;
    }
  }
  const colorDistFromAnalysis = colorDistStr(colorDarts);
  const colorDistribution = colorDistFromAnalysis || asStr(row.color_distribution, "");

  // pkg / pos / chapter
  const pkg = asInt(row.pkg, Math.floor((lv - 1) / 20) + 1);
  const pos = asInt(row.pos, ((lv - 1) % 20) + 1);
  const chapter = asInt(row.chapter, pkg);

  // gimmick 카운트 (CSV 컬럼 기준)
  const gimCols = [
    "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_spawner_t",
    "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
    "gimmick_spawner_o", "gimmick_pinata_box", "gimmick_ice",
    "gimmick_frozen_dart", "gimmick_curtain",
  ];
  const gimickCounts = {};
  for (const k of gimCols) gimickCounts[k] = asInt(row[k], 0);

  // queue_data 가 있으면 그대로, 없으면 빈 객체 (Unity importer 가 BuildHolders 호출)
  const queueData = row.queue_data || null;

  // designer_note 에 [FieldMap] 섹션 + [Source] 라벨 + 점수 메타 첨부
  const noteBase = asStr(row.designer_note, "").replace(/\[FieldMap\][\s\S]*/, "").trim();
  const sourceTag = `[Source]\n${sourceLabel}` + (row.field_complete_score
    ? `\nfield_complete_score=${asNum(row.field_complete_score, 0).toFixed(4)}` : "");
  const fmTag = fieldMap ? `\n[FieldMap]\n${fieldMap}` : "";
  const designerNote = `${noteBase}\n\n${sourceTag}${fmTag}`.trim();

  // BalloonFlow Importer (snake_case ONLY — LevelJsonImporterWindow.JsonLevelData 스키마)
  // ⚠ camelCase "levelId"/"balloons"/"holders"/"rail" 사용 금지:
  //   importer 의 TryLoadLevelConfig 가 잘못 매칭하여 빈 LevelConfig 로 인식함.
  return {
    level_number: lv,
    level_id: `BF_${String(lv).padStart(3, "0")}`,
    pkg, pos, chapter,
    purpose_type: asStr(row.purpose_type, "normal"),
    target_cr: asInt(row.target_cr, 85),
    target_attempts: asNum(row.target_attempts, 1.5),
    num_colors: asInt(row.num_colors, 0),
    color_distribution: colorDistribution,
    field_rows: rows,
    field_columns: cols,
    total_cells: asInt(row.total_cells, balloons.length || 0),
    rail_capacity: asInt(row.rail_capacity, 0),
    rail_capacity_tier: asStr(row.rail_capacity_tier, ""),
    queue_columns: asInt(row.queue_columns, 3),
    queue_rows: asInt(row.queue_rows, 8),
    ...gimickCounts,
    total_darts: asInt(row.field_analysis?.total_darts ?? row.total_darts, 0),
    dart_capacity_range: asStr(row.dart_capacity_range, "10,20,40"),
    emotion_curve: asStr(row.emotion_curve, ""),
    designer_note: designerNote,
    pixel_art_source: asStr(row.pixel_art_source, ""),

    // 셀+기믹 raw — importer 충돌 방지 위해 이름 변경 (balloons/holders/rail/levelId 키 회피).
    // 확장 importer 가 읽을 경우 _bl_cells / _bl_holders 키로 접근.
    _bl_cells: {
      placements: balloons.map(b => ({ r: b.row, c: b.col, color: b.color, life: b.life ?? 1 })),
      gimmick_objects: gimmicks,
    },
    _bl_holders: queueData ? {
      slots: queueData.holders || [],
      rail_layout: queueData.rail || null,
      queue_pattern: queueData.queue_pattern || null,
      difficulty: queueData.difficulty || null,
    } : null,

    // 메타
    _source: sourceLabel,        // "PF" or "PH"
    _has_queue: !!queueData,
    _has_balloons: balloons.length > 0,
    _has_gimmicks: gimmicks.length > 0,
    _exported_at: new Date().toISOString(),
  };
}

// ── 메인 ────────────────────────────────────────────────────────
(async () => {
  const c = new MongoClient(URI);
  await c.connect();
  const db = c.db(DB);
  const coll = db.collection("pixelforge_levels");

  // 1) Load 300 designer rows
  const rows = await coll.find({
    level_number: { $gte: LV_RANGE[0], $lte: LV_RANGE[1] },
    status: { $exists: true },
  }).sort({ level_number: 1 }).toArray();
  console.log(`[load] ${rows.length} rows lv ${LV_RANGE[0]}-${LV_RANGE[1]}`);

  // 2) Source assignment — 90 best PH + 210 PF
  const phCandidates = rows
    .filter(r => r.field_completed === true)
    .sort((a, b) => (b.field_complete_score || 0) - (a.field_complete_score || 0));
  const ph90 = new Set(phCandidates.slice(0, PH_TARGET).map(r => r.level_number));
  console.log(`[source] PH (top ${PH_TARGET} by score): ${ph90.size}, PF: ${rows.length - ph90.size}`);

  // 3) Ensure queue_data — 누락 행만 generate
  let queueGen = 0, queueFail = 0;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (r.queue_data) continue;
    if (!r.field_map) { queueFail++; continue; }
    try {
      const gen = await postJson("/api/queue/generate", { level_number: r.level_number });
      if (!gen.ok) { queueFail++; continue; }
      const conf = await postJson("/api/queue/confirm", { level_number: r.level_number, queue: gen.queue });
      if (!conf.ok) { queueFail++; continue; }
      r.queue_data = gen.queue;
      queueGen++;
      if (queueGen % 25 === 0) console.log(`  queue generate progress: ${queueGen}/${rows.filter(x=>!x.queue_data).length + queueGen}`);
    } catch (e) {
      queueFail++;
      console.log(`  lv${r.level_number} queue fail: ${e.message}`);
    }
  }
  console.log(`[queue] generated: ${queueGen}, failed: ${queueFail}`);

  // 4) Build + write 300 JSONs
  const manifest = {
    generated_at: new Date().toISOString(),
    total: rows.length,
    source_breakdown: { PF: 0, PH: 0 },
    queue_breakdown: { with_queue: 0, no_queue: 0 },
    levels: [],
  };
  for (const r of rows) {
    const sourceLabel = ph90.has(r.level_number) ? "PH" : "PF";
    const json = buildBalloonFlowJson(r, sourceLabel);
    const fname = `Lv${String(r.level_number).padStart(3, "0")}.json`;
    fs.writeFileSync(path.join(OUT_DIR, fname), JSON.stringify(json, null, 2), "utf-8");
    manifest.source_breakdown[sourceLabel]++;
    if (json._has_queue) manifest.queue_breakdown.with_queue++;
    else manifest.queue_breakdown.no_queue++;
    manifest.levels.push({
      level_number: r.level_number,
      source: sourceLabel,
      score: r.field_complete_score || null,
      has_queue: !!json._has_queue,
      has_gimmicks: !!json._has_gimmicks,
      pkg: r.pkg, pos: r.pos,
      bl_metaphor: r.bl_metaphor || null,
    });
  }
  fs.writeFileSync(path.join(OUT_DIR, "_manifest.json"), JSON.stringify(manifest, null, 2));

  // 5) README
  const readme = `# BalloonFlow 300 Levels Export

Generated: ${manifest.generated_at}
Total: ${manifest.total} levels (Lv001~Lv300)

## Source breakdown
- PF (PixelForge): ${manifest.source_breakdown.PF} (target 210, 7:3 ratio)
- PH (ProjectHub field-complete): ${manifest.source_breakdown.PH} (target 90)

## Queue breakdown
- With holders data: ${manifest.queue_breakdown.with_queue}
- Without holders (Unity will BuildHolders): ${manifest.queue_breakdown.no_queue}

## Unity Import
1. Unity Editor 열기
2. BalloonFlow > Import Level Data From JSON
3. 폴더 추가 → 이 디렉토리 선택
4. ${manifest.total}개 자동 로드 → 저장 대상 선택 → "<DB>에 추가" 클릭

## Output schema (per file)
- Standard BalloonFlow LevelJsonImporterWindow.JsonLevelData 필드 (Unity 호환)
- 추가: cells_with_gimmicks { balloons[], gimmicks[] }
- 추가: holders_with_gimmicks { holders[], rail, queue_pattern, difficulty }
- _source: "PF" or "PH"
`;
  fs.writeFileSync(path.join(OUT_DIR, "README.md"), readme);

  console.log(`\n[done] wrote ${rows.length} JSONs + _manifest.json + README.md to ${OUT_DIR}`);
  console.log(`       PF: ${manifest.source_breakdown.PF} / PH: ${manifest.source_breakdown.PH}`);
  console.log(`       queue: with=${manifest.queue_breakdown.with_queue} / no=${manifest.queue_breakdown.no_queue}`);

  await c.close();
})().catch(e => { console.error("FATAL", e); process.exit(1); });
