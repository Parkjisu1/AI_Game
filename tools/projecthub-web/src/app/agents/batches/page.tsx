"use client";

import { useEffect, useState } from "react";

interface BatchRequest {
  _id: string;
  created_at: string;
  created_by_email: string;
  mood: string;
  style: string;
  size: string;
  width?: number;
  height?: number;
  count: number;
  n_colors: number;
  start_idx: number;
  status: "pending" | "running" | "done" | "failed";
  started_at?: string;
  finished_at?: string;
  totals?: { ok: number; fail: number; dedup_skip: number; duration_sec: number };
  result_summary?: { label: string; ok: number; fail: number; dedup_skip: number; duration_sec: number }[];
  error?: string;
}

interface Stats {
  total_levels: number;
  by_size: { width: number; height: number; count: number }[];
  by_style: { style: string; count: number }[];
  by_mood: { mood: string; count: number }[];
  request_totals: { ok: number; dedup_skip: number; fail: number };
}

interface Resp {
  requests: BatchRequest[];
  stats: Stats;
}

const MOOD_OPTIONS = ["random", "warm", "cool", "pastel", "vivid", "all"];
const STYLE_OPTIONS = ["", "kaleidoscope", "tile", "organic", "motif", "all"];
const SIZE_OPTIONS = ["medium", "small", "large", "tall", "wide", "mixed", "custom"];

// CSV 헤더 alias (PixelForge 포맷 호환)
const HEADER_ALIASES: Record<string, string[]> = {
  level_number:       ["level_number", "level", "lv", "stage", "레벨", "스테이지"],
  field_rows:         ["field_rows", "rows", "y", "행"],
  field_columns:      ["field_columns", "cols", "x", "열"],
  num_colors:         ["num_colors", "colors", "color count", "색상수"],
  color_distribution: ["color_distribution", "color_dist", "color dist", "색상분포"],
  purpose_type:       ["purpose_type", "purpose", "목적"],
  designer_note:      ["designer_note", "note", "노트"],
  bl_metaphor:        ["bl_metaphor", "metaphor", "메타포"],
  total_cells:        ["total_cells", "cells", "총셀수"],
  queue_columns:      ["queue_columns", "queue_cols", "큐가로"],
  rail_capacity:      ["rail_capacity", "rail_cap", "레일허용량"],
  pkg:                ["pkg", "package", "패키지"],
  pos:                ["pos", "position", "포지션"],
  // 13 gimmick_* 컬럼 (PixelForge LevelDesign.csv v12 정합)
  gimmick_hidden:     ["gimmick_hidden", "hidden"],
  gimmick_chain:      ["gimmick_chain", "chain", "linked"],
  gimmick_pinata:     ["gimmick_pinata", "pinata", "wooden_board"],
  gimmick_glass_pipe: ["gimmick_glass_pipe", "glass_pipe", "spawner_t"],
  gimmick_pin:        ["gimmick_pin", "pin", "barricade"],
  gimmick_lock_key:   ["gimmick_lock_key", "lock_key", "lock", "key"],
  gimmick_surprise:   ["gimmick_surprise", "surprise", "hidden_balloon"],
  gimmick_wall:       ["gimmick_wall", "wall", "iron_wall"],
  gimmick_spawner_o:  ["gimmick_spawner_o", "spawner_o", "pipe"],
  gimmick_pinata_box: ["gimmick_pinata_box", "pinata_box", "target_box"],
  gimmick_ice:        ["gimmick_ice", "ice", "frozen_layer"],
  gimmick_frozen_dart:["gimmick_frozen_dart", "frozen_dart"],
  gimmick_curtain:    ["gimmick_curtain", "curtain", "color_curtain"],
};

interface ParsedCsvRow {
  level_number?: number;
  width?: number;
  height?: number;
  n_colors?: number;
  color_dist?: string;
  purpose?: string;
  designer_note?: string;
  pattern?: string;
  bl_metaphor?: string;
  total_cells?: number;
  queue_columns?: number;
  rail_capacity?: number;
  pkg?: number;
  pos?: number;
  // gimmick counts
  gimmick_hidden?: number; gimmick_chain?: number; gimmick_pinata?: number;
  gimmick_glass_pipe?: number; gimmick_pin?: number; gimmick_lock_key?: number;
  gimmick_surprise?: number; gimmick_wall?: number; gimmick_spawner_o?: number;
  gimmick_pinata_box?: number; gimmick_ice?: number; gimmick_frozen_dart?: number;
  gimmick_curtain?: number;
  // 이미지 업로드: backend로도 전송됨 (importance map용) + modal viewer 비교용
  image_base64?: string;
  _from_image?: boolean;
}

function parseCsvText(text: string, sourceName: string): { rows: ParsedCsvRow[]; warnings: string[] } {
  const warnings: string[] = [];
  // BOM 제거 (UTF-8 BOM EF BB BF — JS에서는 ﻿ 단일 문자로 디코드됨)
  const clean = text.replace(/^﻿/, "");
  // 라인 split — \r\n / \n / \r (구 macOS) 모두 지원
  const lines = clean.split(/\r\n|\r|\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) return { rows: [], warnings: [`${sourceName}: 행 부족 (${lines.length}행)`] };

  const splitCsv = (line: string): string[] => {
    const out: string[] = [];
    let cur = "";
    let inQuote = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuote && line[i + 1] === '"') { cur += '"'; i++; }
        else inQuote = !inQuote;
      } else if (ch === "," && !inQuote) {
        out.push(cur); cur = "";
      } else {
        cur += ch;
      }
    }
    out.push(cur);
    return out.map((s) => s.trim());
  };

  // BalloonFlow Excel은 Row 1=그룹 헤더, Row 2=컬럼명 구조.
  // 첫 5줄을 모두 시도해서 가장 많이 매칭되는 줄을 헤더로 선택.
  let bestHeaderRow = -1;
  let bestColMap: Record<string, number> = {};
  let bestMatches = 0;
  let firstRowSample: string[] = [];
  const scanMax = Math.min(5, lines.length);
  for (let r = 0; r < scanMax; r++) {
    const headerCandidate = splitCsv(lines[r]).map((h) => h.toLowerCase().trim());
    if (r === 0) firstRowSample = headerCandidate;
    const trial: Record<string, number> = {};
    for (const [canonical, aliases] of Object.entries(HEADER_ALIASES)) {
      for (let i = 0; i < headerCandidate.length; i++) {
        if (aliases.includes(headerCandidate[i])) {
          trial[canonical] = i;
          break;
        }
      }
    }
    const matches = Object.keys(trial).length;
    if (matches > bestMatches) {
      bestMatches = matches;
      bestColMap = trial;
      bestHeaderRow = r;
    }
  }

  const colMap = bestColMap;
  if (bestHeaderRow < 0 || (colMap.level_number === undefined && colMap.field_rows === undefined)) {
    warnings.push(
      `${sourceName}: 헤더 인식 실패 — level_number / field_rows 둘 다 없음. ` +
      `첫 줄 샘플: [${firstRowSample.slice(0, 8).join(", ")}${firstRowSample.length > 8 ? ", ..." : ""}] ` +
      `· 기대 별칭: level_number ∈ {${HEADER_ALIASES.level_number.join("|")}}, ` +
      `field_rows ∈ {${HEADER_ALIASES.field_rows.join("|")}}`
    );
    return { rows: [], warnings };
  }

  // 헤더 다음 줄이 데이터인지 한글 sub-header인지 검사
  let dataStart = bestHeaderRow + 1;
  if (lines.length > dataStart) {
    const nextRow = splitCsv(lines[dataStart]);
    const lvIdx = colMap.level_number;
    if (lvIdx !== undefined && nextRow[lvIdx] !== undefined) {
      const v = nextRow[lvIdx];
      if (v && isNaN(Number(v))) {
        // 숫자 아닌 값 → 추가 sub-header로 판단, 한 줄 더 skip
        dataStart += 1;
      }
    }
  }
  if (bestHeaderRow > 0) {
    warnings.push(
      `${sourceName}: 헤더가 ${bestHeaderRow + 1}번째 줄에서 인식됨 ` +
      `(${bestMatches}개 컬럼 매칭, 데이터는 ${dataStart + 1}번째 줄부터)`
    );
  }

  const rows: ParsedCsvRow[] = [];
  for (let li = dataStart; li < lines.length; li++) {
    const cells = splitCsv(lines[li]);
    if (cells.length === 0 || (cells.length === 1 && !cells[0])) continue;
    const get = (key: string): string => {
      const idx = colMap[key];
      return idx !== undefined && cells[idx] !== undefined ? cells[idx].trim() : "";
    };
    const lvRaw = get("level_number");
    const lv = parseInt(lvRaw, 10);
    if (!lv) continue;  // 빈 줄 / 숫자 아님 skip
    const r: ParsedCsvRow = { level_number: lv };
    const rows_v = parseInt(get("field_rows"), 10);
    const cols_v = parseInt(get("field_columns"), 10);
    if (rows_v) r.height = rows_v;
    if (cols_v) r.width = cols_v;
    const nc = parseInt(get("num_colors"), 10);
    if (nc) r.n_colors = nc;
    const cd = get("color_distribution");
    if (cd) r.color_dist = cd;
    const purpose = get("purpose_type");
    if (purpose) r.purpose = purpose;
    const note = get("designer_note");
    if (note) r.designer_note = note;
    const meta = get("bl_metaphor");
    if (meta) r.bl_metaphor = meta;
    const tc = parseInt(get("total_cells"), 10);
    if (tc) r.total_cells = tc;
    const qc = parseInt(get("queue_columns"), 10);
    if (qc) r.queue_columns = qc;
    const rc = parseInt(get("rail_capacity"), 10);
    if (rc) r.rail_capacity = rc;
    const pkg_v = parseInt(get("pkg"), 10);
    if (pkg_v) r.pkg = pkg_v;
    const pos_v = parseInt(get("pos"), 10);
    if (pos_v) r.pos = pos_v;
    // 13 gimmick_* 카운트 추출
    for (const gk of [
      "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
      "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
      "gimmick_spawner_o", "gimmick_pinata_box", "gimmick_ice", "gimmick_frozen_dart",
      "gimmick_curtain",
    ] as const) {
      const v = parseInt(get(gk), 10);
      if (!isNaN(v) && v > 0) (r as Record<string, number>)[gk] = v;
    }
    rows.push(r);
  }
  if (rows.length === 0) warnings.push(`${sourceName}: 데이터 행 0개`);
  return { rows, warnings };
}

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-blue-100 text-blue-700 animate-pulse",
  done:    "bg-emerald-100 text-emerald-700",
  failed:  "bg-red-100 text-red-700",
};

// 자동 기믹 주입용 GIM_KEYS + PRESETS (Complete Field submit 시 사용)
const GIM_KEYS = [
  "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
  "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
  "gimmick_spawner_o", "gimmick_spawner_t", "gimmick_pinata_box",
  "gimmick_ice", "gimmick_frozen_dart", "gimmick_curtain",
];
function presetGimmicks(preset: string, lv: number): Record<string, number> {
  const out: Record<string, number> = {};
  if (preset === "none") return out;
  if (preset === "light") {
    if (lv >= 121) out.gimmick_wall = 1;
    else if (lv >= 101) out.gimmick_surprise = 8;
    else if (lv >= 61) out.gimmick_pin = 2;
    else if (lv >= 31) out.gimmick_pinata = 1;
  } else if (preset === "medium") {
    if (lv >= 201) { out.gimmick_ice = 80; out.gimmick_pin = 3; }
    else if (lv >= 161) { out.gimmick_pinata_box = 1; out.gimmick_pin = 2; }
    else if (lv >= 121) { out.gimmick_wall = 1; out.gimmick_pinata = 2; }
    else if (lv >= 101) { out.gimmick_surprise = 16; out.gimmick_pin = 2; }
    else if (lv >= 61) { out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 31) out.gimmick_pinata = 2;
  } else if (preset === "heavy") {
    if (lv >= 241) { out.gimmick_ice = 120; out.gimmick_pinata_box = 2; out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 161) { out.gimmick_pinata_box = 2; out.gimmick_pin = 4; out.gimmick_pinata = 2; }
    else if (lv >= 121) { out.gimmick_wall = 1; out.gimmick_pinata = 3; out.gimmick_pin = 3; }
    else if (lv >= 101) { out.gimmick_surprise = 24; out.gimmick_pin = 4; out.gimmick_pinata = 1; }
    else if (lv >= 61) { out.gimmick_pin = 5; out.gimmick_pinata = 3; }
    else if (lv >= 31) out.gimmick_pinata = 3;
  }
  return out;
}
// auto 모드: lv에 따라 적정 preset 자동 선택
function autoPresetForLv(lv: number): "none" | "light" | "medium" | "heavy" {
  if (lv < 31) return "none";   // debut 룰: 기믹 부적합
  if (lv < 61) return "light";
  if (lv < 161) return "medium";
  return "heavy";
}
// Complete Field 강제 lv bump (preset이 명시되었지만 csv lv가 낮을 때)
const PRESET_LV_FLOOR: Record<string, number> = {
  none: 0, auto: 0, light: 41, medium: 121, heavy: 161,
};

// BalloonFlow 24색 팔레트 (이미지 → 가장 가까운 색 매핑용)
const BL_PALETTE_RGB_24: [number, number, number][] = [
  [252, 106, 175], [80, 232, 246], [137, 80, 248], [254, 213, 85],
  [115, 254, 102], [253, 161, 76], [255, 255, 255], [65, 65, 65],
  [110, 168, 250], [57, 174, 46], [252, 94, 94], [50, 107, 248],
  [58, 165, 139], [231, 167, 250], [183, 199, 251], [106, 74, 48],
  [254, 227, 169], [253, 183, 193], [158, 61, 94], [167, 221, 148],
  [89, 46, 126], [220, 120, 129], [217, 217, 231], [111, 114, 127],
];

function nearestBLColor(r: number, g: number, b: number): number {
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < BL_PALETTE_RGB_24.length; i++) {
    const [pr, pg, pb] = BL_PALETTE_RGB_24[i];
    const d = (r - pr) * (r - pr) + (g - pg) * (g - pg) + (b - pb) * (b - pb);
    if (d < bestDist) { bestDist = d; bestIdx = i; }
  }
  return bestIdx; // 0-based
}

// File → base64 data URL (이미지 원본 보존)
async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error("file read failed"));
    reader.readAsDataURL(file);
  });
}

// 이미지 한 장 → ParsedCsvRow (field_map 포함)
async function imageToCsvRow(file: File, levelNumber: number): Promise<ParsedCsvRow> {
  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const i = new Image();
    i.onload = () => resolve(i);
    i.onerror = () => reject(new Error("image load failed"));
    i.src = URL.createObjectURL(file);
  });
  // BL Hard Rule: 보드 최대 40×50
  const MAX_W = 40, MAX_H = 50;
  let tw = img.naturalWidth;
  let th = img.naturalHeight;
  if (tw > MAX_W || th > MAX_H) {
    const sx = MAX_W / tw, sy = MAX_H / th;
    const s = Math.min(sx, sy);
    tw = Math.max(2, Math.floor(tw * s));
    th = Math.max(2, Math.floor(th * s));
  }
  const canvas = document.createElement("canvas");
  canvas.width = tw;
  canvas.height = th;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas ctx unavailable");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0, tw, th);
  const imageData = ctx.getImageData(0, 0, tw, th);

  const cells: number[][] = [];
  const colorCounts: Record<number, number> = {};
  for (let y = 0; y < th; y++) {
    const row: number[] = [];
    for (let x = 0; x < tw; x++) {
      const idx = (y * tw + x) * 4;
      const r = imageData.data[idx];
      const g = imageData.data[idx + 1];
      const b = imageData.data[idx + 2];
      const a = imageData.data[idx + 3];
      if (a < 128) {
        row.push(-1);
      } else {
        const blIdx = nearestBLColor(r, g, b);
        const colorId = blIdx + 1;  // 1-based
        row.push(colorId);
        colorCounts[colorId] = (colorCounts[colorId] || 0) + 1;
      }
    }
    cells.push(row);
  }
  const fieldMapStr = cells.map((row) =>
    row.map((c) => c < 0 ? ".." : String(c).padStart(2, "0")).join(" ")
  ).join("\n");
  const totalCells = Object.values(colorCounts).reduce((s, n) => s + n, 0);
  const sortedColors = Object.entries(colorCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([id, n]) => `c${id}:${n}`);
  // 원본 이미지 base64 (modal input preview + backend importance map)
  const imageBase64 = await fileToBase64(file);
  return {
    level_number: levelNumber,
    width: tw,
    height: th,
    total_cells: totalCells,
    n_colors: Object.keys(colorCounts).length,
    color_dist: sortedColors.join(" "),
    designer_note: `[Source]\nImage upload: ${file.name}\nOriginal size: ${img.naturalWidth}×${img.naturalHeight}\n\n[FieldMap]\n${fieldMapStr}`,
    image_base64: imageBase64,  // 백엔드 importance map + 모달 viewer
    _from_image: true,
  };
}

// "1-10, 27, 30-35" → [1,2,...,10,27,30,...,35] (중복/역순 자동 정리, 잘못된 토큰은 skip)
function parseLevelRange(input: string): { nums: Set<number>; bad: string[] } {
  const nums = new Set<number>();
  const bad: string[] = [];
  const parts = input.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean);
  for (const p of parts) {
    const m = p.match(/^(\d+)\s*(?:-|~|–)\s*(\d+)$/);
    if (m) {
      let a = parseInt(m[1], 10);
      let b = parseInt(m[2], 10);
      if (a > b) [a, b] = [b, a];
      for (let i = a; i <= b; i++) nums.add(i);
    } else if (/^\d+$/.test(p)) {
      nums.add(parseInt(p, 10));
    } else {
      bad.push(p);
    }
  }
  return { nums, bad };
}

const SHAPE_PATTERN_RE = /\[(shape|pattern|모양|패턴)\]/i;
const LINEAR_RE = /^(linear|normal|노말|선형)$/i;
const HARD_RE = /^(super.?hard|hard|하드|슈하|슈퍼하드)$/i;

interface FieldCompleteJob {
  _id: string;
  created_at: string;
  created_by_email: string;
  csv_source: string;
  status: "pending" | "running" | "done" | "failed";
  started_at?: string;
  finished_at?: string;
  totals?: { ok: number; fail: number; escalated: number; avg_score: number };
  error?: string;
}

interface FieldCompleteResp {
  jobs: FieldCompleteJob[];
  stats: { jobs: number; ok: number; fail: number; escalated: number; avg_score: number };
}

type RunMode = "batch" | "field-complete";

export default function BatchesPage() {
  const [data, setData] = useState<Resp | null>(null);
  const [fcData, setFcData] = useState<FieldCompleteResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // 모드 토글
  const [mode, setMode] = useState<RunMode>("batch");

  // 폼 상태
  const [mood, setMood] = useState("random");
  const [style, setStyle] = useState("");
  const [size, setSize] = useState("medium");
  const [count, setCount] = useState(100);
  const [nColors, setNColors] = useState(4);
  const [startIdx, setStartIdx] = useState(0);
  const [width, setWidth] = useState(25);
  const [height, setHeight] = useState(25);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState("");
  // CSV 상태
  const [csvRows, setCsvRows] = useState<ParsedCsvRow[]>([]);
  const [csvSource, setCsvSource] = useState("");
  const [csvWarnings, setCsvWarnings] = useState<string[]>([]);
  // 선택 상태 — selected = level_number Set. CSV 로드 시 전체 선택이 기본.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [rangeInput, setRangeInput] = useState("");
  const [rangeWarn, setRangeWarn] = useState("");
  const [showAllRows, setShowAllRows] = useState(false);

  // Job 상세 modal
  const [openJobId, setOpenJobId] = useState<string | null>(null);
  const [jobDetail, setJobDetail] = useState<unknown>(null);
  const [jobDetailLoading, setJobDetailLoading] = useState(false);

  // v1.2.3 토글들
  const [ironWallMode, setIronWallMode] = useState<"bl_outline" | "pf_wall">("bl_outline");
  const [keepAllCandidates, setKeepAllCandidates] = useState(false);  // n=10 picker
  const [allowDuplicate, setAllowDuplicate] = useState(true);  // Art 생성 dedup 우회 (default true — 1~300 lv 작업에 적합)

  // UI 가이드 (popup modal) + 고급 옵션 토글
  const [showGuide, setShowGuide] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // 🧩 Art batch에 기믹 추가 modal
  const [gimmickModalBatchId, setGimmickModalBatchId] = useState<string | null>(null);
  const [gimmickPreset, setGimmickPreset] = useState<"none" | "light" | "medium" | "heavy">("medium");
  const [gimmickSubmitting, setGimmickSubmitting] = useState(false);

  // 🧩 field-complete job에 기믹 추가 modal (이미지 업로드 결과 등)
  const [fcGimmickModalId, setFcGimmickModalId] = useState<string | null>(null);
  const [fcGimmickPreset, setFcGimmickPreset] = useState<"none" | "light" | "medium" | "heavy" | "pf_grounded">("pf_grounded");
  const [fcGimmickSubmitting, setFcGimmickSubmitting] = useState(false);

  // 🧩 Complete Field 실행 시 자동 기믹 주입 preset (CSV에 명시 없을 때만 적용)
  const [autoGimmickPreset, setAutoGimmickPreset] = useState<"auto" | "none" | "light" | "medium" | "heavy">("auto");

  // 🎨 v43 batch modal — 디자이너 원본 gen_43_pipeline.py 직접 spawn
  const [v43ModalOpen, setV43ModalOpen] = useState(false);
  const [v43Levels, setV43Levels] = useState("1,3,4,5,7,14,18,20,21,23,25,27,37,50");
  const [v43NSeeds, setV43NSeeds] = useState(10);
  const [v43NFinal, setV43NFinal] = useState(2);
  const [v43Label, setV43Label] = useState("v47 batch");
  const [v43Submitting, setV43Submitting] = useState(false);
  const [v43LastJobId, setV43LastJobId] = useState<string | null>(null);

  // 📂 최신 CSV — 중앙 관리
  type CsvVersion = { _id: string; version: string; label: string; uploaded_at: string;
                      uploaded_by: string; row_count: number; target_levels: number[];
                      is_latest: boolean; csv_text?: string };
  const [csvLatest, setCsvLatest] = useState<CsvVersion | null>(null);
  const [csvHistory, setCsvHistory] = useState<CsvVersion[]>([]);
  const [csvModalOpen, setCsvModalOpen] = useState(false);
  const [csvUploadText, setCsvUploadText] = useState("");
  const [csvUploadLabel, setCsvUploadLabel] = useState("");
  const [csvSubmitting, setCsvSubmitting] = useState(false);
  const [csvUploadError, setCsvUploadError] = useState<{
    msg: string; detail?: { delimiter?: string; first_5_lines?: string[]; hint?: string };
  } | null>(null);
  const [csvDragOver, setCsvDragOver] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch("/api/agents/csv-latest");
        const j = await r.json();
        if (!cancelled) {
          setCsvLatest(j.latest || null);
          setCsvHistory(j.history || []);
        }
      } catch { /* ignore */ }
    }
    load();
    const t = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  // CSV 모달 열려있는 동안 window 전역에 떨어지는 drag/drop 의 기본 동작 차단
  // (이걸 안 하면 drop zone 밖으로 파일이 떨어졌을 때 브라우저가 그 파일을 열거나 다운로드함)
  useEffect(() => {
    if (!csvModalOpen) return;
    const prevent = (e: DragEvent) => { e.preventDefault(); };
    window.addEventListener("dragover", prevent);
    window.addEventListener("drop", prevent);
    return () => {
      window.removeEventListener("dragover", prevent);
      window.removeEventListener("drop", prevent);
    };
  }, [csvModalOpen]);

  async function submitCsvUpload() {
    if (!csvUploadText.trim()) return;
    setCsvSubmitting(true);
    setCsvUploadError(null);
    try {
      const r = await fetch("/api/agents/csv-latest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ csv_text: csvUploadText, label: csvUploadLabel, csv_source: "manual upload" }),
      });
      const j = await r.json();
      if (!r.ok) {
        setCsvUploadError({ msg: j.error || `HTTP ${r.status}`, detail: j.detail });
        setToast(`CSV 파싱 실패 — 모달 내 진단 확인`);
        return;
      }
      setToast(`✓ CSV ${j.version} 업로드 (${j.row_count}건, delim=${j.delimiter}, header ${j.header_rows}행)`);
      setCsvModalOpen(false);
      setCsvUploadText("");
      setCsvUploadLabel("");
      setCsvUploadError(null);
      // refresh
      const rr = await fetch("/api/agents/csv-latest");
      const jj = await rr.json();
      setCsvLatest(jj.latest || null);
      setCsvHistory(jj.history || []);
    } catch (e) {
      setCsvUploadError({ msg: e instanceof Error ? e.message : String(e) });
      setToast(`CSV 업로드 실패`);
    } finally {
      setCsvSubmitting(false);
    }
  }

  // CSV 파일 → 텍스트 (UTF-8 우선, BOM 제거; 실패 시 EUC-KR fallback 안내)
  function readCsvFile(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("파일 읽기 실패"));
      reader.onload = (ev) => {
        let text = String(ev.target?.result || "");
        // UTF-8 BOM 제거
        if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
        // � replacement character 다수 발견 → 인코딩 미스매치 가능성
        const replCount = (text.match(/�/g) || []).length;
        if (replCount > 3) {
          // EUC-KR 재시도
          const r2 = new FileReader();
          r2.onload = (ev2) => {
            let t2 = String(ev2.target?.result || "");
            if (t2.charCodeAt(0) === 0xFEFF) t2 = t2.slice(1);
            resolve(t2);
          };
          r2.onerror = () => resolve(text); // fallback to UTF-8 text
          r2.readAsText(file, "EUC-KR");
        } else {
          resolve(text);
        }
      };
      reader.readAsText(file, "utf-8");
    });
  }

  // 🎬 Pipeline Sessions — 통합 4-stage 워크플로
  type PipelineSession = {
    _id: string; label: string; created_at: string; updated_at?: string;
    created_by_email: string; target_levels: number[];
    art_mode: "v47" | "cowork"; auto_advance?: boolean;
    gimmick_preset: string; n_seeds?: number; n_final?: number;
    csv_version_label?: string;
    stage: "csv" | "art_running" | "art_done" | "curated_pending" | "curated_done"
          | "queue_running" | "queue_done"
          | "field_running" | "field_done" | "download" | "done" | "failed";
    queue_summary?: { generated: number; failed: number; skipped?: number;
                      results?: Array<{ level: number; grade: string; target: string; matched: boolean; seed: number; relative: number }> };
    art_job?: { type: string; job_id: string; status: string; finished_at?: string; total_levels?: number };
    field_complete_job?: { job_id: string; status: string; finished_at?: string;
                            totals?: { ok: number; fail: number; escalated: number; avg_score: number } };
    curations?: Record<string, "A" | "B" | null>;
    error?: string;
  };
  const [pipelines, setPipelines] = useState<PipelineSession[]>([]);
  const [pipelineNewOpen, setPipelineNewOpen] = useState(false);
  const [plDetailId, setPlDetailId] = useState<string | null>(null);
  type PipelineDetail = PipelineSession & {
    evaluation?: V43EvalEntry[];
    pngs?: V43Pngs[]; png_count?: number;
    log_tail?: string;
    fc_totals?: { ok: number; fail: number; escalated: number; avg_score: number };
    fc_results_summary?: Array<{ level_number: number; ok: boolean; score: number;
                                  balloons: number; gimmicks: number; gimmick_types: string[] }>;
  };
  const [plDetail, setPlDetail] = useState<PipelineDetail | null>(null);
  const [plDetailLoading, setPlDetailLoading] = useState(false);
  const [plCurations, setPlCurations] = useState<Record<number, "A" | "B" | null>>({});
  const [plActionSubmitting, setPlActionSubmitting] = useState(false);

  // 신규 pipeline form state
  const [newPlLabel, setNewPlLabel] = useState("");
  const [newPlLevels, setNewPlLevels] = useState("1,3,4,5,7,14,18,20,21,23,25,27,37,50");
  const [newPlAutoAdvance, setNewPlAutoAdvance] = useState(true);
  // newPlPreset 제거 — Pipeline 모달에서 preset 선택 폐지. CSV 컬럼이 single-source-of-truth, 미명시 lv 는 server default(pf_grounded)로 자동 채움.

  // pipeline polling
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch("/api/agents/pipeline");
        const j = await r.json();
        if (!cancelled && Array.isArray(j.sessions)) setPipelines(j.sessions);
      } catch { /* ignore */ }
    }
    load();
    const t = setInterval(load, 6000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  async function submitNewPipeline() {
    if (!newPlLevels.trim()) { setToast("대상 lv 필요"); return; }
    setPlActionSubmitting(true);
    try {
      const r = await fetch("/api/agents/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: newPlLabel || `Pipeline ${new Date().toISOString().slice(0, 19)}`,
          target_levels: newPlLevels,
          art_mode: "v47",
          auto_advance: newPlAutoAdvance,
          // gimmick_preset 미지정 → pipeline/route.ts 가 'pf_grounded' default 적용.
          // CSV row 의 gimmick_* 컬럼이 최우선, 미명시는 PF lookup 으로 보충.
          n_seeds: 10, n_final: 2,
        }),
      });
      const j = await r.json();
      if (!r.ok || !j.ok) { setToast(`Pipeline 시작 실패: ${j.error || r.status}`); return; }
      setToast(`✓ Pipeline 시작 (${j.target_levels?.length}lv, id ${String(j.id).slice(-6)})`);
      setPipelineNewOpen(false);
      // 즉시 한 번 refresh
      const rr = await fetch("/api/agents/pipeline");
      const jj = await rr.json();
      if (Array.isArray(jj.sessions)) setPipelines(jj.sessions);
    } catch (e) {
      setToast(`Pipeline 시작 실패: ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setPlActionSubmitting(false);
    }
  }

  async function openPipelineDetail(id: string) {
    setPlDetailId(id);
    setPlDetailLoading(true);
    setPlDetail(null);
    setPlCurations({});
    try {
      const r = await fetch(`/api/agents/pipeline/${id}`);
      const j = await r.json();
      if (r.ok) setPlDetail(j);
      else setToast(`상세 로드 실패: ${j.error || r.status}`);
    } catch (e) {
      setToast(`상세 로드 실패: ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setPlDetailLoading(false);
    }
  }

  // pl detail polling 동안
  useEffect(() => {
    if (!plDetailId) return;
    const t = setInterval(async () => {
      try {
        const r = await fetch(`/api/agents/pipeline/${plDetailId}`);
        const j = await r.json();
        if (r.ok) setPlDetail(j);
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(t);
  }, [plDetailId]);

  async function advancePipeline(action: "curate" | "queue" | "field" | "download" | "retry_field",
                                  selections?: Record<number, "A" | "B" | null>) {
    if (!plDetailId) return;
    setPlActionSubmitting(true);
    try {
      const body: Record<string, unknown> = { action };
      if (selections) body.selections = selections;
      const r = await fetch(`/api/agents/pipeline/${plDetailId}/advance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok) { setToast(`${action} 실패: ${j.error || r.status}`); return; }
      setToast(`✓ ${action} 완료 (stage=${j.stage})`);
      // refresh
      const rr = await fetch(`/api/agents/pipeline/${plDetailId}`);
      const jj = await rr.json();
      if (rr.ok) setPlDetail(jj);
    } catch (e) {
      setToast(`${action} 실패: ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setPlActionSubmitting(false);
    }
  }

  // stage label/색
  const STAGE_META: Record<string, { label: string; bg: string; text: string }> = {
    "csv":              { label: "CSV",       bg: "bg-gray-100",     text: "text-gray-600" },
    "art_running":      { label: "Art 진행중", bg: "bg-blue-100",     text: "text-blue-700" },
    "art_done":         { label: "Art 완료",   bg: "bg-cyan-100",     text: "text-cyan-700" },
    "curated_pending":  { label: "큐레이션 대기", bg: "bg-amber-100", text: "text-amber-700" },
    "curated_done":     { label: "큐레이션 완료", bg: "bg-teal-100",  text: "text-teal-700" },
    "queue_running":    { label: "Queue 진행중", bg: "bg-indigo-100", text: "text-indigo-700" },
    "queue_done":       { label: "Queue 완료",   bg: "bg-violet-100", text: "text-violet-700" },
    "field_running":    { label: "Field 진행중", bg: "bg-purple-100", text: "text-purple-700" },
    "field_done":       { label: "Field 완료",   bg: "bg-fuchsia-100", text: "text-fuchsia-700" },
    "download":         { label: "다운로드",     bg: "bg-emerald-100", text: "text-emerald-700" },
    "done":             { label: "완료",         bg: "bg-emerald-200", text: "text-emerald-800" },
    "failed":           { label: "실패",         bg: "bg-red-100",     text: "text-red-700" },
  };

  // 5-stage progress 표시용 — 어느 stage 가 active 인지
  const STAGE_ORDER = ["csv", "art_running|art_done",
                       "curated_pending|curated_done",
                       "queue_running|queue_done",
                       "field_running|field_done", "download|done"];
  function stageIndex(stage: string): number {
    for (let i = 0; i < STAGE_ORDER.length; i++) {
      if (STAGE_ORDER[i].split("|").includes(stage)) return i;
    }
    if (stage === "failed") return -1;
    return 0;
  }

  // 🎨 v43 jobs 목록 + 상세 모달
  type V43Job = { _id: string; status: string; label: string; created_at?: string;
                  finished_at?: string; target_levels?: number[]; total_levels?: number;
                  error?: string; source_job?: string };
  const [v43JobsList, setV43JobsList] = useState<V43Job[]>([]);
  const [v43DetailId, setV43DetailId] = useState<string | null>(null);
  type V43Detail = { _id: string; status: string; label: string; source_job?: string;
                     target_levels?: number[]; total_levels?: number;
                     evaluation?: V43EvalEntry[]; pngs?: V43Pngs[]; png_count?: number;
                     error?: string };
  const [v43Detail, setV43Detail] = useState<V43Detail | null>(null);
  const [v43DetailLoading, setV43DetailLoading] = useState(false);

  // v43 jobs polling (8s)
  useEffect(() => {
    let cancelled = false;
    async function fetchV43() {
      try {
        const r = await fetch("/api/agents/v43-batch");
        const j = await r.json();
        if (!cancelled && Array.isArray(j.jobs)) setV43JobsList(j.jobs);
      } catch { /* ignore */ }
    }
    fetchV43();
    const t = setInterval(fetchV43, 8000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  async function openV43Detail(id: string) {
    setV43DetailId(id);
    setV43DetailLoading(true);
    setV43Detail(null);
    setV43Curations({});
    try {
      const r = await fetch(`/api/agents/v43-batch/${id}/preview`);
      const j = await r.json();
      if (r.ok) setV43Detail(j);
      else setToast(`v43 상세 로드 실패: ${j.error || r.status}`);
    } catch (e) {
      setToast(`v43 상세 실패: ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setV43DetailLoading(false);
    }
  }

  // 큐레이션 — A/B 선택 state
  const [v43Curations, setV43Curations] = useState<Record<number, "A" | "B" | null>>({});
  const [v43CurateSubmitting, setV43CurateSubmitting] = useState(false);
  async function submitV43Curation() {
    if (!v43DetailId) return;
    const selected = Object.entries(v43Curations).filter(([, v]) => v !== null);
    if (selected.length === 0) { setToast("선택된 후보 없음"); return; }
    setV43CurateSubmitting(true);
    try {
      const r = await fetch(`/api/agents/v43-batch/${v43DetailId}/curate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selections: v43Curations }),
      });
      const j = await r.json();
      if (!r.ok) { setToast(`큐레이션 실패: ${j.error || r.status}`); return; }
      setToast(`✓ 큐레이션 완료: ${j.success}/${j.total} 성공`);
    } catch (e) {
      setToast(`큐레이션 실패: ${e instanceof Error ? e.message : "?"}`);
    } finally {
      setV43CurateSubmitting(false);
    }
  }

  const [v43UseLatestCsv, setV43UseLatestCsv] = useState(true);  // 기본 latest CSV 사용

  async function submitV43Batch() {
    setV43Submitting(true);
    try {
      const lvList = v43Levels.split(/[,\s]+/).filter(Boolean).join(",");
      // latest CSV 가 있으면 우선 사용. 없으면 DB 합성 fallback.
      const useLatest = v43UseLatestCsv && csvLatest;
      const r = await fetch("/api/agents/v43-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_levels: lvList,
          n_seeds: v43NSeeds,
          n_final: v43NFinal,
          label: v43Label,
          use_latest_csv: !!useLatest,
          generate_csv_from_db: !useLatest,  // latest 없으면 DB 합성
        }),
      });
      const j = await r.json();
      if (!r.ok || !j.ok) {
        setToast(`✗ v43 batch 실행 실패: ${j.error || r.status}`);
        return;
      }
      setV43LastJobId(j.id);
      setToast(`✓ v43 batch 시작 (${j.target_levels?.length}개 lv, id ${j.id.slice(-6)})`);
      setV43ModalOpen(false);
    } catch (e) {
      setToast(`✗ ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setV43Submitting(false);
    }
  }

  async function submitFcGimmickAdd() {
    if (!fcGimmickModalId) return;
    setFcGimmickSubmitting(true);
    try {
      const r = await fetch("/api/agents/field-complete/from-fc-job", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fc_job_id: fcGimmickModalId,
          preset: fcGimmickPreset,
          iron_wall_mode: ironWallMode,
          keep_all_candidates: keepAllCandidates,
        }),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t);
      }
      const j = (await r.json()) as { id: string; row_count: number; lv_bumped: boolean };
      setToast(`✓ ${j.row_count}건에 기믹 추가 시작 (preset=${fcGimmickPreset}${j.lv_bumped ? ", lv force-bump" : ""}, job ${j.id.slice(-6)})`);
      setTimeout(() => setToast(""), 5000);
      setFcGimmickModalId(null);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setFcGimmickSubmitting(false);
    }
  }

  async function submitGimmickAdd() {
    if (!gimmickModalBatchId) return;
    setGimmickSubmitting(true);
    try {
      const r = await fetch("/api/agents/field-complete/from-art-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          art_batch_id: gimmickModalBatchId,
          preset: gimmickPreset,
          iron_wall_mode: ironWallMode,
          keep_all_candidates: keepAllCandidates,
        }),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t);
      }
      const j = (await r.json()) as { id: string; row_count: number };
      setToast(`✓ ${j.row_count}건에 기믹 추가 시작 (preset=${gimmickPreset}, job ${j.id.slice(-6)})`);
      setTimeout(() => setToast(""), 5000);
      setGimmickModalBatchId(null);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setGimmickSubmitting(false);
    }
  }

  // 첫 방문 시 가이드 자동 열기 + localStorage 기억
  useEffect(() => {
    try {
      const seen = window.localStorage.getItem("fc_guide_seen_v1");
      if (!seen) setShowGuide(true);
    } catch { /* localStorage 차단 환경 */ }
  }, []);
  // ESC로 닫기
  useEffect(() => {
    if (!showGuide) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setShowGuide(false); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [showGuide]);
  function dismissGuide() {
    setShowGuide(false);
    try { window.localStorage.setItem("fc_guide_seen_v1", "1"); } catch { /* */ }
  }

  async function refresh() {
    try {
      const [r, fr] = await Promise.all([
        fetch("/api/agents/batches"),
        fetch("/api/agents/field-complete"),
      ]);
      if (r.ok) setData((await r.json()) as Resp);
      if (fr.ok) setFcData((await fr.json()) as FieldCompleteResp);
      if (!r.ok && !fr.ok) throw new Error(`batches HTTP ${r.status} / field-complete HTTP ${fr.status}`);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 8000);
    return () => clearInterval(t);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErr("");
    setToast("");
    try {
      // CSV 모드: selected에 포함된 level_number만 전송
      const filteredCsvRows = csvRows.length > 0
        ? csvRows.filter((r) => r.level_number !== undefined && selected.has(r.level_number))
        : [];
      if (csvRows.length > 0 && filteredCsvRows.length === 0) {
        throw new Error("선택된 레벨이 없음 — 최소 1개 이상 선택하세요");
      }

      let endpoint: string;
      let payload: Record<string, unknown>;
      if (mode === "field-complete") {
        if (filteredCsvRows.length === 0) {
          throw new Error("Complete Field 모드는 CSV/이미지 업로드 + 선택이 필요합니다");
        }
        // ParsedCsvRow (frontend shorthand) → BL schema (backend expects)
        // 이미지 업로드도 ParsedCsvRow 사용하므로 동일한 매핑 적용
        // + 자동 기믹 주입: CSV에 gimmick_* 명시 없으면 preset 기반 자동 적용
        const remapped: Record<string, unknown>[] = filteredCsvRows.map((r, i) => {
          const out: Record<string, unknown> = { ...r };
          if (r.width !== undefined) out.field_columns = r.width;
          if (r.height !== undefined) out.field_rows = r.height;
          if (r.color_dist !== undefined) out.color_distribution = r.color_dist;
          if (r.n_colors !== undefined) out.num_colors = r.n_colors;
          if (r.purpose !== undefined) out.purpose_type = r.purpose;

          // CSV에 기믹이 명시되어 있는가?
          const hasManualGim = GIM_KEYS.some((k) => Number((r as unknown as Record<string, unknown>)[k] ?? 0) > 0);

          // lv 결정: CSV에 실제 값(>1) 있으면 절대 override 안 함 (사용자 룰 2026-05-21).
          // image-upload (lv=1 default) 케이스에서만 preset floor 적용.
          const csvLv = r.level_number ?? 1;
          const hasExplicitLv = csvLv > 1;
          let lv = csvLv;
          if (!hasManualGim && !hasExplicitLv && autoGimmickPreset !== "auto" && autoGimmickPreset !== "none") {
            const floor = PRESET_LV_FLOOR[autoGimmickPreset] ?? 0;
            if (floor > 0 && lv < floor) lv = floor + i;
          }
          out.level_number = lv;
          if (out.pkg === undefined) out.pkg = Math.floor((lv - 1) / 20) + 1;
          if (out.pos === undefined) out.pos = ((lv - 1) % 20) + 1;
          if (out.purpose_type === undefined) out.purpose_type = "normal";
          if (out.queue_columns === undefined) out.queue_columns = 3;
          if (out.total_cells === undefined) out.total_cells = (r.width ?? 0) * (r.height ?? 0);
          const tc = Number(out.total_cells) || 0;
          if (out.rail_capacity === undefined) {
            out.rail_capacity = tc > 700 ? 160 : tc > 500 ? 120 : 80;
          }
          // iron_wall_mode pf_wall inject
          if (ironWallMode === "pf_wall") {
            out.designer_note = ((out.designer_note as string) || "") + "\n[mode=pf_wall]";
          }

          // 🧩 자동 기믹 주입 (CSV에 gimmick_* 명시 없을 때만)
          if (!hasManualGim) {
            const effectivePreset = autoGimmickPreset === "auto" ? autoPresetForLv(lv) : autoGimmickPreset;
            const gim = presetGimmicks(effectivePreset, lv);
            for (const k of GIM_KEYS) if (out[k] === undefined) out[k] = 0;
            for (const [k, v] of Object.entries(gim)) out[k] = v;
            out._auto_gimmick_preset = effectivePreset;
          }
          return out;
        });
        endpoint = "/api/agents/field-complete";
        payload = {
          csv_rows: remapped,
          csv_source: csvSource || "csv",
          allow_escalation: true,
          keep_all_candidates: keepAllCandidates,
        };
      } else {
        endpoint = "/api/agents/batches";
        payload = filteredCsvRows.length > 0
          ? { csv_rows: filteredCsvRows, csv_source: csvSource || "csv", allow_duplicate: allowDuplicate }
          : {
              mood, style, size, count, n_colors: nColors, start_idx: startIdx,
              allow_duplicate: allowDuplicate,
              ...(size === "custom" || size === "" ? { width, height } : {}),
            };
      }

      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t);
      }
      const j = (await r.json()) as { id: string };
      const label = mode === "field-complete" ? "필드완성 job" : "Art 생성 batch";
      setToast(`✓ ${label} 시작됨 (${j.id.slice(-6)}) — 아래 표에서 진행 추적`);
      setTimeout(() => setToast(""), 4000);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function openJob(id: string) {
    setOpenJobId(id);
    setJobDetailLoading(true);
    setJobDetail(null);
    try {
      const r = await fetch(`/api/agents/field-complete?id=${id}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setJobDetail(j);
    } catch (e) {
      setErr(String(e));
    } finally {
      setJobDetailLoading(false);
    }
  }
  function closeJob() { setOpenJobId(null); setJobDetail(null); }

  async function importFromCollection(payload: Record<string, unknown>) {
    setSubmitting(true);
    setErr(""); setToast("");
    try {
      const r = await fetch("/api/agents/field-complete/from-collection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "pixelforge_levels",
          allow_escalation: true,
          iron_wall_mode: ironWallMode,
          keep_all_candidates: keepAllCandidates,
          ...payload,
        }),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t);
      }
      const j = (await r.json()) as { id: string; row_count: number; source: string };
      setToast(`✓ ${j.row_count}건 import → field-complete job 시작 (${j.id.slice(-6)})`);
      setTimeout(() => setToast(""), 5000);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleImageFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const allRows: ParsedCsvRow[] = [];
    const allWarnings: string[] = [];
    const fileNames: string[] = [];
    let lvCounter = 1;
    for (const file of Array.from(files)) {
      if (!file.type.startsWith("image/") && !/\.(png|jpe?g|gif|webp|bmp)$/i.test(file.name)) {
        allWarnings.push(`${file.name}: 이미지 파일 아님 (skip)`);
        continue;
      }
      try {
        const row = await imageToCsvRow(file, lvCounter++);
        allRows.push(row);
        fileNames.push(file.name);
      } catch (e) {
        allWarnings.push(`${file.name}: ${String(e)}`);
      }
    }
    if (allRows.length === 0) {
      allWarnings.push("처리된 이미지 0개");
    }
    setCsvRows(allRows);
    setCsvWarnings(allWarnings);
    setCsvSource(fileNames.length === 1 ? `[image] ${fileNames[0]}` : `[image] ${fileNames.length} files`);
    setSelected(new Set(allRows.map((r) => r.level_number ?? 0).filter((n) => n > 0)));
    setRangeInput("");
    setRangeWarn("");
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const allRows: ParsedCsvRow[] = [];
    const allWarnings: string[] = [];
    const fileNames: string[] = [];
    for (const file of Array.from(files)) {
      if (!file.name.toLowerCase().endsWith(".csv")) continue;
      try {
        const text = await file.text();
        const { rows, warnings } = parseCsvText(text, file.name);
        allRows.push(...rows);
        allWarnings.push(...warnings);
        fileNames.push(file.name);
      } catch (e) {
        allWarnings.push(`${file.name}: ${String(e)}`);
      }
    }
    setCsvRows(allRows);
    setCsvWarnings(allWarnings);
    setCsvSource(fileNames.length === 1 ? fileNames[0] : `${fileNames.length} files`);
    // 새 CSV 로드 시 전체 선택
    setSelected(new Set(allRows.map((r) => r.level_number ?? 0).filter((n) => n > 0)));
    setRangeInput("");
    setRangeWarn("");
  }

  function clearCsv() {
    setCsvRows([]);
    setCsvWarnings([]);
    setCsvSource("");
    setSelected(new Set());
    setRangeInput("");
    setRangeWarn("");
  }

  // 선택 헬퍼
  const toggleRow = (lv: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(lv)) next.delete(lv);
      else next.add(lv);
      return next;
    });
  };
  const selectAll = () => {
    setSelected(new Set(csvRows.map((r) => r.level_number ?? 0).filter((n) => n > 0)));
  };
  const selectNone = () => setSelected(new Set());

  // Range 입력 적용 — input의 level_number들을 selected에 SET (덮어쓰기)
  const applyRange = () => {
    const { nums, bad } = parseLevelRange(rangeInput);
    const csvLevels = new Set(csvRows.map((r) => r.level_number ?? 0));
    // CSV에 실제로 존재하는 번호만 선택
    const valid = new Set<number>();
    const missing: number[] = [];
    nums.forEach((n) => {
      if (csvLevels.has(n)) valid.add(n);
      else missing.push(n);
    });
    setSelected(valid);
    const parts: string[] = [];
    if (bad.length > 0) parts.push(`잘못된 토큰: ${bad.slice(0, 5).join(", ")}${bad.length > 5 ? "..." : ""}`);
    if (missing.length > 0) parts.push(`CSV에 없는 lv: ${missing.slice(0, 5).join(", ")}${missing.length > 5 ? `...(+${missing.length - 5})` : ""}`);
    setRangeWarn(parts.join(" · "));
  };

  // Quick filter — 조건 만족 row만 selected에 SET (덮어쓰기)
  const filterLinear = () => {
    const next = new Set<number>();
    csvRows.forEach((r) => {
      if (r.level_number && r.purpose && LINEAR_RE.test(r.purpose.trim())) next.add(r.level_number);
    });
    setSelected(next);
    setRangeWarn("");
  };
  const filterShapePattern = () => {
    const next = new Set<number>();
    csvRows.forEach((r) => {
      if (r.level_number && r.designer_note && SHAPE_PATTERN_RE.test(r.designer_note)) next.add(r.level_number);
    });
    setSelected(next);
    setRangeWarn("");
  };
  // Hard/SuperHard 제외 = 현재 selected에서 Hard/SuperHard만 제거
  const excludeHard = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      csvRows.forEach((r) => {
        if (r.level_number && r.purpose && HARD_RE.test(r.purpose.trim())) next.delete(r.level_number);
      });
      return next;
    });
    setRangeWarn("");
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">📦 Level Batches</h1>
          <p className="mt-1 text-sm text-gray-500">
            {mode === "field-complete"
              ? "필드완성: CSV row → v3.15 JSON (balloons + gimmicks + field_analysis). 점수 < 0.85일 때 Claude LLM auto-escalation."
              : "Batch 트리거 → SSH로 실행. 색상만 다른 변형은 structure_hash로 자동 차단."}
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setV43ModalOpen(true)}
            className="text-xs px-3 py-1.5 bg-fuchsia-100 hover:bg-fuchsia-200 rounded-lg font-semibold text-fuchsia-900 border border-fuchsia-300"
            title="디자이너 원본 (v47 zone 함수 9종 포함) 그대로 실행 — 10 seed → top 5 → A/B 후보">
            🎨 v47 Pattern Batch
          </button>
          <button type="button" onClick={() => setShowGuide(true)}
            className="text-xs px-3 py-1.5 bg-blue-100 hover:bg-blue-200 rounded-lg font-semibold text-blue-900 border border-blue-300">
            💡 사용법
          </button>
          <a href="/agents" className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg">← /agents</a>
          <a href="/levels" className="text-xs px-3 py-1.5 bg-purple-50 text-purple-700 hover:bg-purple-100 rounded-lg border border-purple-200">🖼 갤러리</a>
          <a href="/agents/eval" className="text-xs px-3 py-1.5 bg-amber-50 text-amber-700 hover:bg-amber-100 rounded-lg border border-amber-200">🧪 Eval</a>
        </div>
      </div>

      {/* 💡 사용 가이드 Popup Modal */}
      {showGuide && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={dismissGuide}>
          <div className="max-h-[90vh] w-full max-w-5xl overflow-hidden rounded-xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            {/* Modal header */}
            <div className="flex items-center justify-between border-b bg-gradient-to-r from-blue-50 to-blue-100 px-5 py-3">
              <div>
                <h2 className="text-base font-bold text-blue-900">💡 Field Completer — 사용 가이드</h2>
                <p className="mt-0.5 text-[11px] text-blue-700">시나리오별 어떤 옵션을 쓸지 + 점수 해석 + 자주 묻는 케이스</p>
              </div>
              <button type="button" onClick={dismissGuide}
                className="rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-gray-700 ring-1 ring-gray-300 hover:bg-gray-100">
                ✕ 닫기 (ESC)
              </button>
            </div>
            {/* Modal body */}
            <div className="max-h-[78vh] overflow-y-auto px-5 py-4 text-xs text-gray-700">
              {/* TL;DR */}
              <div className="mb-4 rounded-lg border-l-4 border-emerald-500 bg-emerald-50 p-3">
                <div className="text-sm font-bold text-emerald-900">⭐ TL;DR — 90% 케이스</div>
                <ol className="ml-4 mt-1 list-decimal text-sm text-emerald-900">
                  <li><strong>🧩 Complete Field</strong> 모드 토글</li>
                  <li>초록 박스 → <strong><code className="bg-white px-1 rounded">Generated 레벨에 기믹 추가 (≤50)</code></strong> 클릭</li>
                  <li>job 표 row 클릭 → modal에서 결과 확인</li>
                  <li><strong>⬇ BalloonFlow Importer 포맷 zip 다운로드</strong> → Unity import</li>
                </ol>
              </div>

              {/* 시나리오 표 */}
              <div className="mb-4">
                <h3 className="mb-2 text-sm font-bold text-gray-800">📋 시나리오 매트릭스</h3>
                <table className="w-full text-[11px]">
                  <thead className="bg-blue-100 text-left text-blue-900">
                    <tr>
                      <th className="px-2 py-1.5 font-semibold">시나리오</th>
                      <th className="px-2 py-1.5 font-semibold">모드</th>
                      <th className="px-2 py-1.5 font-semibold">버튼/옵션</th>
                      <th className="px-2 py-1.5 font-semibold">예상 결과</th>
                    </tr>
                  </thead>
                  <tbody className="align-top">
                    <tr className="border-t border-blue-100 bg-amber-50/30">
                      <td className="px-2 py-1.5 font-semibold">기존 디자인 레벨에 기믹 추가 ⭐</td>
                      <td className="px-2 py-1.5">🧩 Complete Field</td>
                      <td className="px-2 py-1.5"><code className="bg-white px-1 rounded">Generated 레벨에 기믹 추가 (≤50)</code></td>
                      <td className="px-2 py-1.5">기존 풍선 배치 그대로 + 기믹 자동 overlay. 평균 점수 0.95+</td>
                    </tr>
                    <tr className="border-t border-blue-100">
                      <td className="px-2 py-1.5 font-semibold">draft 레벨 채우기</td>
                      <td className="px-2 py-1.5">🧩 Complete Field</td>
                      <td className="px-2 py-1.5"><code className="bg-white px-1 rounded">draft 레벨</code></td>
                      <td className="px-2 py-1.5">color_distribution / total_cells 자동 보강. 평균 0.93-0.97</td>
                    </tr>
                    <tr className="border-t border-blue-100">
                      <td className="px-2 py-1.5 font-semibold">디자이너가 여러 변형 비교</td>
                      <td className="px-2 py-1.5">🧩 Complete Field</td>
                      <td className="px-2 py-1.5">🔧 고급 옵션 ▶ <strong>n=10 후보 모두 표시</strong> ✓</td>
                      <td className="px-2 py-1.5">modal에서 10개 후보 grid 비교. seed별 점수+썸네일.</td>
                    </tr>
                    <tr className="border-t border-blue-100">
                      <td className="px-2 py-1.5 font-semibold">PF 스타일 wall 패턴</td>
                      <td className="px-2 py-1.5">🧩 Complete Field</td>
                      <td className="px-2 py-1.5">🔧 고급 옵션 ▶ <strong>Iron Wall mode: pf_wall</strong></td>
                      <td className="px-2 py-1.5">cluster 외부 상단 2×2/4×2 wall (PF 1-300 패턴)</td>
                    </tr>
                    <tr className="border-t border-blue-100">
                      <td className="px-2 py-1.5 font-semibold">특정 lv만 처리</td>
                      <td className="px-2 py-1.5">🧩 Complete Field</td>
                      <td className="px-2 py-1.5"><code className="bg-white px-1 rounded">특정 level_number 지정</code> → 47, 86, 121</td>
                      <td className="px-2 py-1.5">지정 lv만 실행</td>
                    </tr>
                    <tr className="border-t border-blue-100">
                      <td className="px-2 py-1.5 font-semibold">자체 CSV 업로드</td>
                      <td className="px-2 py-1.5">🧩 Complete Field</td>
                      <td className="px-2 py-1.5">📑 CSV 파일 선택 + 범위 입력</td>
                      <td className="px-2 py-1.5">디자이너 row → field-complete</td>
                    </tr>
                    <tr className="border-t border-blue-100">
                      <td className="px-2 py-1.5 font-semibold">⭐ 이미지에서 레벨 만들기</td>
                      <td className="px-2 py-1.5">🧩 Complete Field</td>
                      <td className="px-2 py-1.5">🖼 이미지 파일 / 📁 이미지 폴더</td>
                      <td className="px-2 py-1.5">PNG/JPG → BL 24색 nearest 매핑 → [FieldMap] 자동 → 기믹 추가</td>
                    </tr>
                    <tr className="border-t border-blue-100">
                      <td className="px-2 py-1.5 font-semibold">새 픽셀아트 (BL 무관)</td>
                      <td className="px-2 py-1.5">🎨 Art 생성</td>
                      <td className="px-2 py-1.5">mood/style/size/count 폼</td>
                      <td className="px-2 py-1.5">cowork pattern, pixelforge_grid_levels 저장</td>
                    </tr>
                    <tr className="border-t border-blue-100">
                      <td className="px-2 py-1.5 font-semibold">결과 Unity import</td>
                      <td className="px-2 py-1.5">(공통)</td>
                      <td className="px-2 py-1.5">job 클릭 → modal → <strong>⬇ zip</strong></td>
                      <td className="px-2 py-1.5">Lv###_FieldComplete.json × N + manifest + README</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* 점수 해석 */}
              <div className="mb-4 grid grid-cols-3 gap-3">
                <div className="rounded-lg border-2 border-emerald-300 bg-emerald-50 p-3">
                  <div className="text-lg font-bold text-emerald-700">🟢 ≥ 0.85</div>
                  <div className="mt-1 text-[11px] text-emerald-900">PASS — Unity import 권장</div>
                </div>
                <div className="rounded-lg border-2 border-amber-300 bg-amber-50 p-3">
                  <div className="text-lg font-bold text-amber-700">🟡 0.70~0.85</div>
                  <div className="mt-1 text-[11px] text-amber-900">검토 필요 — LLM auto-escalation 발생 가능</div>
                </div>
                <div className="rounded-lg border-2 border-red-300 bg-red-50 p-3">
                  <div className="text-lg font-bold text-red-700">🔴 &lt; 0.70</div>
                  <div className="mt-1 text-[11px] text-red-900">REJECT 권장 — 입력 데이터 확인</div>
                </div>
              </div>

              {/* 7-dim 점수 */}
              <div className="mb-4 rounded-lg border bg-gray-50 p-3">
                <div className="mb-2 text-sm font-bold text-gray-800">📊 7-차원 점수 (modal에서 확인)</div>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div><strong>metaphor_score</strong> (0.45) — 픽셀아트 메타포 보존 ⭐핵심</div>
                  <div><strong>mod10_compliance</strong> (0.18) — 색상별 다트 10배수 정합</div>
                  <div><strong>hard_rule_pass</strong> (0.12) — HR 1-19 + placement_violations</div>
                  <div><strong>debut_compliance</strong> (0.08) — 도입 lv 격리</div>
                  <div><strong>queue_alignment</strong> (0.05) — 다트 총합 큐 범위</div>
                  <div><strong>hp_visual_gap</strong> (0.07) — 셀% vs HP% gap (v1.2.3)</div>
                  <div><strong>soft_rule_pass</strong> (0.05) — 60-lv reappearance (v1.2.3)</div>
                </div>
              </div>

              {/* FAQ */}
              <div className="mb-2">
                <h3 className="mb-2 text-sm font-bold text-gray-800">❓ 자주 묻는 케이스</h3>
                <ul className="ml-3 list-disc space-y-1 text-[11px]">
                  <li><strong>Q. 점수가 항상 0.97인데 시각 품질은 별로</strong> → 활성 기믹 없는 generated 레벨은 trivial하게 1.0. 진짜 quality test는 active gimmick 있는 hard/super_hard에서</li>
                  <li><strong>Q. 같은 레벨 재실행하면 결과 같음?</strong> → 결정성 보장 (seed=level×13+7+seed_offset×1009)</li>
                  <li><strong>Q. LLM 항상 채택?</strong> → 휴리스틱 대비 (a) score 우위 OR (b) score 동률+meta 우위 OR (c) meta 0.02+ 우위 시 채택</li>
                  <li><strong>Q. PixelForge UI에서도 보임?</strong> → 같은 MongoDB `pixelforge_levels.field_completed=true` 필드, PixelForge UI 변경은 별도 작업</li>
                  <li><strong>Q. CSV 업로드 vs 컬렉션 import 어느 게 좋나?</strong> → 컬렉션 import (Generated/draft 버튼) 권장. CSV는 신규 레벨 만들 때</li>
                </ul>
              </div>
            </div>
            {/* Modal footer */}
            <div className="flex items-center justify-between border-t bg-gray-50 px-5 py-3">
              <span className="text-[11px] text-gray-500">처음 방문 시 자동 표시됨. 다시 보려면 우상단 <strong>💡 사용법</strong> 버튼.</span>
              <button type="button" onClick={dismissGuide}
                className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-700">
                다시 보지 않기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Art 모드 Dedup 옵션 */}
      {mode === "batch" && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border-2 border-dashed border-indigo-200 bg-indigo-50 p-3">
          <span className="text-xs font-semibold text-indigo-900">🎨 Art 생성 옵션:</span>
          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input type="checkbox" checked={allowDuplicate}
              onChange={(e) => setAllowDuplicate(e.target.checked)} />
            <span className="font-semibold text-gray-700">Dedup 허용 (structure_hash 중복 차단 우회)</span>
            <span className="text-gray-500">— 같은 구조 art도 모두 저장 → CSV 41건 = 41 결과</span>
          </label>
        </div>
      )}

      {/* Mode 토글 */}
      <div className="mb-4 flex items-center gap-2 rounded-xl border bg-white p-3 shadow-sm">
        <span className="text-xs font-semibold text-gray-600">모드:</span>
        <button type="button" onClick={() => setMode("batch")}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
            mode === "batch"
              ? "bg-indigo-600 text-white"
              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
          }`}>
          🎨 Art 생성 (cowork patterns)
        </button>
        <button type="button" onClick={() => setMode("field-complete")}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
            mode === "field-complete"
              ? "bg-emerald-600 text-white"
              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
          }`}>
          🧩 Complete Field (v3.15 JSON)
        </button>
        <span className="ml-2 text-[11px] text-gray-500">
          {mode === "field-complete"
            ? "Python 결정론 + Claude escalation. 필드완성 명세 v1.1 알고리즘 적용."
            : "PixelForge 카드 생성 (cowork v5.1). CSV 기반 결정성 random."}
        </span>
        {mode === "field-complete" && (
          <div className="ml-auto flex items-center gap-1">
            <label className="text-[10px] font-semibold text-emerald-700">🧩 자동 기믹:</label>
            <select value={autoGimmickPreset}
              onChange={(e) => setAutoGimmickPreset(e.target.value as typeof autoGimmickPreset)}
              className="rounded border border-emerald-300 bg-white px-2 py-1 text-[11px] font-medium text-emerald-700">
              <option value="auto">auto (lv 따라 자동)</option>
              <option value="none">none (기믹 없음)</option>
              <option value="light">light (가벼움)</option>
              <option value="medium">medium (균형)</option>
              <option value="heavy">heavy (어려움)</option>
            </select>
            <span className="text-[10px] text-gray-500" title="CSV에 gimmick_* > 0이 있으면 무시되고 CSV 값이 우선됨">
              (CSV 명시 우선)
            </span>
          </div>
        )}
      </div>

      {/* 🔧 고급 옵션 — Iron Wall mode + n=10 picker (collapsible, field-complete 한정) */}
      {mode === "field-complete" && (
        <div className="mb-4 rounded-xl border bg-white shadow-sm">
          <button type="button" onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex w-full items-center justify-between px-4 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50">
            <span>🔧 고급 옵션
              {(ironWallMode === "pf_wall" || keepAllCandidates) && (
                <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-700">
                  {[ironWallMode === "pf_wall" && "pf_wall", keepAllCandidates && "n=10"].filter(Boolean).join(", ")}
                </span>
              )}
            </span>
            <span className="text-[10px] text-gray-500">{showAdvanced ? "▼" : "▶"} (기본값 그대로면 OK)</span>
          </button>
          {showAdvanced && (
            <div className="border-t border-gray-200 px-4 py-3">
              <div className="mb-3">
                <div className="mb-1 text-xs font-semibold text-gray-700">Iron Wall mode</div>
                <div className="flex gap-3 text-xs">
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input type="radio" checked={ironWallMode === "bl_outline"}
                      onChange={() => setIronWallMode("bl_outline")} />
                    <span>bl_outline <span className="text-gray-500">— 기본, 디자이너 의도 보존 (전체 outline)</span></span>
                  </label>
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input type="radio" checked={ironWallMode === "pf_wall"}
                      onChange={() => setIronWallMode("pf_wall")} />
                    <span>pf_wall <span className="text-gray-500">— PF 1-300 패턴 (cluster 외부 2×2/4×2)</span></span>
                  </label>
                </div>
              </div>
              <div>
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input type="checkbox" checked={keepAllCandidates}
                    onChange={(e) => setKeepAllCandidates(e.target.checked)} />
                  <span className="font-semibold text-gray-700">n=10 후보 모두 표시</span>
                  <span className="text-gray-500">— modal에서 디자이너가 직접 비교/pick (스토리지 ↑, 처리 시간 동일)</span>
                </label>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Import from pixelforge_levels (field-complete 모드 한정) */}
      {mode === "field-complete" && (
        <div className="mb-4 rounded-xl border-2 border-dashed border-emerald-300 bg-emerald-50 p-3">
          <div className="mb-2 text-xs font-semibold text-emerald-900">📂 컬렉션에서 직접 import:</div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-emerald-700 font-medium">⭐ 권장 (기존 풍선 보존):</span>
            <button type="button" disabled={submitting}
              onClick={() => importFromCollection({ filter: { status: "generated", field_map: { $exists: true, $nin: [null, ""] } }, max_rows: 50 })}
              className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
              Generated 레벨에 기믹 추가 (≤50)
            </button>
            <span className="text-[10px] text-gray-600">기존 field_map 그대로 사용 → 기믹만 overlay</span>
          </div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-gray-600">기타:</span>
            <button type="button" disabled={submitting}
              onClick={() => importFromCollection({ filter: { status: "draft" }, max_rows: 100 })}
              className="rounded-md bg-white px-3 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-300 hover:bg-emerald-100 disabled:opacity-50">
              draft 레벨 (field_map 없으면 default)
            </button>
            <button type="button" disabled={submitting}
              onClick={() => {
                const lvs = prompt("level_number 쉼표/공백 입력 (e.g. 47, 86, 121):");
                if (!lvs) return;
                const nums = lvs.split(/[,\s]+/).map(s => parseInt(s, 10)).filter(n => !isNaN(n));
                if (nums.length === 0) { alert("유효한 번호 없음"); return; }
                importFromCollection({ level_numbers: nums });
              }}
              className="rounded-md bg-white px-3 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-300 hover:bg-emerald-100 disabled:opacity-50">
              특정 level_number 지정
            </button>
          </div>
        </div>
      )}

      {err && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">에러: {err}</div>}

      {/* Advanced toggle — 기존 분리 섹션 (Art batch form / 통계 / 개별 jobs 표) */}
      <div className="mb-3 flex justify-end">
        <button type="button" onClick={() => setShowAdvanced((v) => !v)}
          className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded text-gray-700 border border-gray-300">
          {showAdvanced ? "▲ Advanced 숨김 (기존 Art form / Standalone Jobs 숨김)" : "▼ Advanced 보기 (기존 Art form / Standalone Jobs / Art requests)"}
        </button>
      </div>

      {showAdvanced && (
      <>
      {/* 트리거 폼 */}
      <section className="mb-8 rounded-xl border bg-white p-5 shadow-sm">
        <h2 className="mb-4 text-base font-semibold">▶ 새 batch 트리거</h2>

        {/* CSV 업로드 영역 — 활성화되면 mood/style/size 무시됨 */}
        <div className="mb-5 rounded-lg border-2 border-dashed border-violet-200 bg-violet-50 p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-violet-900">📑 CSV / 폴더 업로드 <span className="font-normal text-violet-600">(PixelForge 포맷 호환)</span></h3>
            {csvRows.length > 0 && (
              <button type="button" onClick={clearCsv}
                className="rounded bg-white px-2 py-0.5 text-xs text-violet-700 ring-1 ring-violet-300 hover:bg-violet-100">
                ✕ CSV 해제
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="cursor-pointer rounded-md bg-white px-3 py-1.5 text-xs font-medium text-violet-700 ring-1 ring-violet-300 hover:bg-violet-100">
              📄 CSV 파일 선택 (단일/다수)
              <input type="file" accept=".csv,text/csv" multiple
                onChange={(e) => handleFiles(e.target.files)} className="hidden" />
            </label>
            <label className="cursor-pointer rounded-md bg-white px-3 py-1.5 text-xs font-medium text-violet-700 ring-1 ring-violet-300 hover:bg-violet-100">
              📁 CSV 폴더 선택
              <input type="file"
                /* @ts-expect-error webkitdirectory is non-standard */
                webkitdirectory=""
                directory=""
                multiple
                onChange={(e) => handleFiles(e.target.files)} className="hidden" />
            </label>
            <span className="text-xs text-gray-400">또는</span>
            <label className="cursor-pointer rounded-md bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 ring-1 ring-amber-300 hover:bg-amber-100">
              🖼 이미지 파일 선택
              <input type="file" accept="image/*,.png,.jpg,.jpeg,.gif,.webp,.bmp" multiple
                onChange={(e) => handleImageFiles(e.target.files)} className="hidden" />
            </label>
            <label className="cursor-pointer rounded-md bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 ring-1 ring-amber-300 hover:bg-amber-100">
              📁 이미지 폴더 선택
              <input type="file"
                /* @ts-expect-error webkitdirectory is non-standard */
                webkitdirectory=""
                directory=""
                multiple
                onChange={(e) => handleImageFiles(e.target.files)} className="hidden" />
            </label>
            <span className="text-xs text-violet-700">
              {csvRows.length === 0
                ? "CSV: level_number/field_rows/color_distribution/gimmick_* | 이미지: PNG/JPG → BL 24색 nearest → [FieldMap] 자동"
                : `✓ ${csvSource} → ${csvRows.length} rows 파싱됨`}
            </span>
          </div>
          {csvWarnings.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-amber-700">
              {csvWarnings.slice(0, 5).map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
          {csvRows.length > 0 && (
            <>
              {/* 선택 카운터 + range 입력 + quick filters */}
              <div className="mt-3 rounded-lg border bg-white p-3">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-xs">
                    <span className="font-semibold text-violet-900">선택 {selected.size}</span>
                    <span className="text-gray-500"> / 전체 {csvRows.length}</span>
                  </div>
                  <div className="flex gap-1">
                    <button type="button" onClick={selectAll}
                      className="rounded bg-white px-2 py-0.5 text-[11px] text-violet-700 ring-1 ring-violet-300 hover:bg-violet-50">전체 선택</button>
                    <button type="button" onClick={selectNone}
                      className="rounded bg-white px-2 py-0.5 text-[11px] text-gray-600 ring-1 ring-gray-300 hover:bg-gray-50">전체 해제</button>
                  </div>
                </div>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <input type="text" value={rangeInput} onChange={(e) => setRangeInput(e.target.value)}
                    placeholder="범위 입력: 1-10, 27, 30-35"
                    className="flex-1 min-w-[200px] rounded-md border px-2 py-1 text-xs"
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); applyRange(); } }} />
                  <button type="button" onClick={applyRange}
                    className="rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700">범위 적용</button>
                </div>
                {rangeWarn && (
                  <div className="mb-2 rounded bg-amber-50 px-2 py-1 text-[11px] text-amber-700">{rangeWarn}</div>
                )}
                <div className="flex flex-wrap gap-1.5">
                  <button type="button" onClick={filterLinear}
                    className="rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700 ring-1 ring-emerald-200 hover:bg-emerald-100">
                    purpose_type = linear/normal만
                  </button>
                  <button type="button" onClick={filterShapePattern}
                    className="rounded-md bg-sky-50 px-2 py-1 text-[11px] text-sky-700 ring-1 ring-sky-200 hover:bg-sky-100">
                    [Shape] / [Pattern] 태그만
                  </button>
                  <button type="button" onClick={excludeHard}
                    className="rounded-md bg-rose-50 px-2 py-1 text-[11px] text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100">
                    Hard / SuperHard 제외
                  </button>
                </div>
              </div>

              {/* 프리뷰 테이블 — 체크박스 + 전체/페이지 토글 */}
              <div className="mt-3 overflow-x-auto rounded border bg-white">
                <table className="w-full text-[11px]">
                  <thead className="sticky top-0 bg-gray-50 text-gray-600">
                    <tr>
                      <th className="w-8 px-2 py-1 text-center">
                        <input type="checkbox"
                          checked={selected.size === csvRows.length && csvRows.length > 0}
                          ref={(el) => {
                            if (el) el.indeterminate = selected.size > 0 && selected.size < csvRows.length;
                          }}
                          onChange={(e) => (e.target.checked ? selectAll() : selectNone())} />
                      </th>
                      <th className="px-2 py-1 text-left">lv</th>
                      <th className="px-2 py-1 text-left">W×H</th>
                      <th className="px-2 py-1 text-left">colors</th>
                      <th className="px-2 py-1 text-left">purpose</th>
                      <th className="px-2 py-1 text-left">color_dist</th>
                      <th className="px-2 py-1 text-left">designer_note</th>
                    </tr>
                  </thead>
                  <tbody className={showAllRows ? "" : "max-h-[400px]"}>
                    {(showAllRows ? csvRows : csvRows.slice(0, 50)).map((r, i) => {
                      const lv = r.level_number ?? 0;
                      const isSel = selected.has(lv);
                      return (
                        <tr key={i} className={`border-t ${isSel ? "bg-violet-50/40" : "bg-white"}`}>
                          <td className="px-2 py-1 text-center">
                            <input type="checkbox" checked={isSel}
                              onChange={() => toggleRow(lv)} disabled={!lv} />
                          </td>
                          <td className="px-2 py-1 font-medium">{r.level_number}</td>
                          <td className="px-2 py-1">{r.width ?? "-"}×{r.height ?? "-"}</td>
                          <td className="px-2 py-1">{r.n_colors ?? "-"}</td>
                          <td className="px-2 py-1 text-gray-700">{r.purpose || "-"}</td>
                          <td className="px-2 py-1 font-mono">{r.color_dist || "-"}</td>
                          <td className="max-w-md truncate px-2 py-1 text-gray-600" title={r.designer_note || ""}>
                            {r.designer_note || "-"}
                          </td>
                        </tr>
                      );
                    })}
                    {!showAllRows && csvRows.length > 50 && (
                      <tr className="border-t bg-gray-50">
                        <td colSpan={7} className="px-2 py-2 text-center">
                          <button type="button" onClick={() => setShowAllRows(true)}
                            className="text-[11px] text-indigo-700 hover:underline">
                            … 외 {csvRows.length - 50} 행 모두 보기
                          </button>
                        </td>
                      </tr>
                    )}
                    {showAllRows && csvRows.length > 50 && (
                      <tr className="border-t bg-gray-50">
                        <td colSpan={7} className="px-2 py-1 text-center">
                          <button type="button" onClick={() => setShowAllRows(false)}
                            className="text-[11px] text-gray-600 hover:underline">접기</button>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>

        <form onSubmit={submit} className="grid grid-cols-2 gap-4 lg:grid-cols-6">
          <Field label="Mood">
            <select value={mood} onChange={(e) => setMood(e.target.value)}
              disabled={csvRows.length > 0}
              className="w-full rounded-md border px-2 py-1.5 text-sm disabled:bg-gray-100 disabled:text-gray-400">
              {MOOD_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </Field>
          <Field label="Style">
            <select value={style} onChange={(e) => setStyle(e.target.value)}
              disabled={csvRows.length > 0}
              className="w-full rounded-md border px-2 py-1.5 text-sm disabled:bg-gray-100 disabled:text-gray-400">
              {STYLE_OPTIONS.map((o) => <option key={o} value={o}>{o || "(none)"}</option>)}
            </select>
          </Field>
          <Field label="Size">
            <select value={size} onChange={(e) => setSize(e.target.value)}
              disabled={csvRows.length > 0}
              className="w-full rounded-md border px-2 py-1.5 text-sm disabled:bg-gray-100 disabled:text-gray-400">
              {SIZE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </Field>
          <Field label="Count">
            <input type="number" value={count} onChange={(e) => setCount(parseInt(e.target.value) || 0)}
              min={1} max={2000}
              disabled={csvRows.length > 0}
              className="w-full rounded-md border px-2 py-1.5 text-sm disabled:bg-gray-100 disabled:text-gray-400" />
          </Field>
          <Field label="N colors">
            <input type="number" value={nColors} onChange={(e) => setNColors(parseInt(e.target.value) || 0)}
              min={2} max={8}
              disabled={csvRows.length > 0}
              className="w-full rounded-md border px-2 py-1.5 text-sm disabled:bg-gray-100 disabled:text-gray-400" />
          </Field>
          <Field label="Start idx">
            <input type="number" value={startIdx} onChange={(e) => setStartIdx(parseInt(e.target.value) || 0)}
              min={0}
              disabled={csvRows.length > 0}
              className="w-full rounded-md border px-2 py-1.5 text-sm disabled:bg-gray-100 disabled:text-gray-400" />
          </Field>

          {/* Custom W×H — size=custom 또는 빈값일 때만 활성 */}
          {(size === "custom" || size === "") && csvRows.length === 0 && (
            <>
              <Field label="Width (가로)">
                <input type="number" value={width} onChange={(e) => setWidth(parseInt(e.target.value) || 0)}
                  min={5} max={60}
                  className="w-full rounded-md border px-2 py-1.5 text-sm" />
              </Field>
              <Field label="Height (세로)">
                <input type="number" value={height} onChange={(e) => setHeight(parseInt(e.target.value) || 0)}
                  min={5} max={60}
                  className="w-full rounded-md border px-2 py-1.5 text-sm" />
              </Field>
            </>
          )}

          <div className="col-span-full flex items-center gap-3">
            <button type="submit" disabled={submitting || (csvRows.length > 0 && selected.size === 0) || (mode === "field-complete" && csvRows.length === 0)}
              className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:bg-gray-300 ${
                mode === "field-complete"
                  ? "bg-emerald-600 hover:bg-emerald-700"
                  : "bg-indigo-600 hover:bg-indigo-700"
              }`}>
              {submitting ? "시작 중..." :
                mode === "field-complete"
                  ? `Complete Field 실행 (선택 ${selected.size} / ${csvRows.length}행)`
                  : csvRows.length > 0 ? `생성하기 (선택 ${selected.size} / ${csvRows.length}행)` : "생성하기"}
            </button>
            <span className="text-xs text-gray-500">
              {mode === "field-complete"
                ? "필드완성: CSV row → 8 STEP 알고리즘 → v3.15 JSON. pixelforge_levels 컬렉션에 upsert."
                : csvRows.length > 0
                  ? "CSV 모드: mood/style/size/count/n_colors 무시 — 선택된 row의 spec만 사용"
                  : "SIZE_PRESETS: small=20×20, medium=25×25, large=30×30, tall=20×30, wide=30×20, mixed=item별 random, custom=W×H 직접"}
            </span>
          </div>
        </form>

        {toast && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800">
            {toast}
          </div>
        )}
      </section>

      {/* 종합 통계 */}
      {data && (
        <section className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-4">
          <Card title="총 레벨 수" value={data.stats?.total_levels?.toLocaleString() ?? "—"} hint="pixelforge_grid_levels" />
          <Card title="누적 OK" value={data.stats?.request_totals?.ok?.toLocaleString() ?? "—"} hint="batch 트리거 기준" />
          <Card title="Dedup 차단" value={data.stats?.request_totals?.dedup_skip?.toLocaleString() ?? "—"}
            hint="색상만 다른 중복" tone="amber" />
          <Card title="실패" value={data.stats?.request_totals?.fail?.toLocaleString() ?? "—"} tone="red" />
        </section>
      )}

      {/* 분포 */}
      {data && (
        <section className="mb-8 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <DistroBox title="📐 Size 분포" rows={(data.stats?.by_size ?? []).map((s) => ({
            label: `${s.width}×${s.height}`, count: s.count,
          }))} />
          <DistroBox title="🎨 Style 분포" rows={(data.stats?.by_style ?? []).map((s) => ({
            label: s.style || "(none)", count: s.count,
          }))} />
          <DistroBox title="🌈 Mood 분포" rows={(data.stats?.by_mood ?? []).map((s) => ({
            label: s.mood || "(none)", count: s.count,
          }))} />
        </section>
      )}

      {/* 필드완성 통계 (mode=field-complete일 때) */}
      {fcData && mode === "field-complete" && (
        <section className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-4">
          <Card title="필드완성 job 수" value={fcData.stats?.jobs?.toLocaleString() ?? "—"} hint="pixelforge_field_complete_jobs" tone="emerald" />
          <Card title="누적 OK 레벨" value={fcData.stats?.ok?.toLocaleString() ?? "—"} tone="emerald" />
          <Card title="Escalated" value={fcData.stats?.escalated?.toLocaleString() ?? "—"} hint="Claude LLM 보강" tone="amber" />
          <Card title="평균 점수" value={(fcData.stats?.avg_score || 0).toFixed(3)}
            hint={(fcData.stats?.avg_score ?? 0) >= 0.85 ? "PASS" : "below 0.85"}
            tone={(fcData.stats?.avg_score ?? 0) >= 0.85 ? "emerald" : "amber"} />
        </section>
      )}
      </>
      )}

      {/* 🎬 Pipeline Sessions — 통합 4-stage 표 (메인) */}
      <section className="mb-6 rounded-xl border-2 border-emerald-300 bg-emerald-50/40 p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-emerald-900">
            🎬 Pipeline Sessions — Art → Curate → Field → Download
            <span className="ml-2 text-[10px] font-normal text-emerald-700">
              한 작업 = 한 행. 클릭하여 stage 별 진행
            </span>
          </h2>
          <button type="button" onClick={() => setPipelineNewOpen(true)}
            className="text-xs px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded font-semibold text-white">
            + 새 Pipeline 시작
          </button>
        </div>
        {pipelines.length === 0 && (
          <p className="py-4 text-center text-sm text-emerald-700">
            진행 중인 Pipeline 없음 — [+ 새 Pipeline 시작] 클릭
          </p>
        )}
        {pipelines.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-emerald-100 text-emerald-900">
                <tr>
                  <th className="px-3 py-2 text-left">Stage</th>
                  <th className="px-3 py-2 text-left">Created</th>
                  <th className="px-3 py-2 text-left">Label</th>
                  <th className="px-3 py-2 text-left">Progress</th>
                  <th className="px-3 py-2 text-right">Lvs</th>
                  <th className="px-3 py-2 text-left">CSV</th>
                  <th className="px-3 py-2 text-center">Action</th>
                </tr>
              </thead>
              <tbody>
                {pipelines.map((p) => {
                  const meta = STAGE_META[p.stage] || STAGE_META["csv"];
                  const sIdx = stageIndex(p.stage);
                  return (
                    <tr key={p._id} className="border-t border-emerald-100 hover:bg-emerald-100/40 cursor-pointer"
                        onClick={() => openPipelineDetail(p._id)}>
                      <td className="px-3 py-2">
                        <span className={`rounded px-2 py-0.5 text-[10px] font-medium ${meta.bg} ${meta.text}`}>
                          {meta.label}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-gray-600">{p.created_at?.slice(5, 19)}</td>
                      <td className="px-3 py-2 font-medium">{p.label}</td>
                      <td className="px-3 py-2">
                        <div className="flex gap-1">
                          {[0, 1, 2, 3, 4].map((i) => (
                            <span key={i} className={`inline-block w-3 h-3 rounded-full ${
                              p.stage === "failed" ? "bg-red-300"
                                : i < sIdx ? "bg-emerald-500"
                                : i === sIdx ? "bg-emerald-400 ring-2 ring-emerald-200 animate-pulse"
                                : "bg-gray-200"
                            }`} title={["CSV","Art","Curate","Field","Down"][i]} />
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{p.target_levels?.length ?? "—"}</td>
                      <td className="px-3 py-2 text-[10px] text-gray-500 truncate max-w-[160px]" title={p.csv_version_label}>
                        {p.csv_version_label || "—"}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <button type="button" onClick={(e) => { e.stopPropagation(); openPipelineDetail(p._id); }}
                          className="rounded bg-emerald-100 hover:bg-emerald-200 px-2 py-1 text-[10px] font-medium text-emerald-700">
                          🔍 열기
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 📂 중앙 CSV — 최신 버전 1개만 모든 배치가 참조 */}
      <section className="mb-6 rounded-xl border-2 border-amber-200 bg-amber-50/40 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-base font-semibold text-amber-900">
            📂 최신 Level Design CSV
            <span className="ml-2 text-[10px] font-normal text-amber-700">
              모든 배치 (Art/v47/필드완성) 가 참조하는 중앙 CSV. 매 잡마다 업로드 불필요.
            </span>
          </h2>
          <button type="button" onClick={() => setCsvModalOpen(true)}
            className="text-xs px-3 py-1.5 bg-amber-200 hover:bg-amber-300 rounded font-semibold text-amber-900">
            📤 CSV 업로드 / 교체
          </button>
        </div>
        {!csvLatest && (
          <p className="py-2 text-center text-sm text-amber-700">
            아직 등록된 CSV 없음 — 위 [📤 CSV 업로드] 클릭하여 시작.
          </p>
        )}
        {csvLatest && (
          <div className="flex items-center justify-between text-xs">
            <div>
              <span className="font-semibold text-amber-900">현재 latest:</span>{" "}
              <code className="bg-white px-1.5 py-0.5 rounded">{csvLatest.version}</code>{" "}
              <span className="text-amber-700">"{csvLatest.label}"</span>
              <span className="ml-2 text-amber-600">
                · {csvLatest.row_count} rows · {csvLatest.uploaded_at?.slice(0, 19)} · {csvLatest.uploaded_by}
              </span>
            </div>
            <div className="text-[10px] text-amber-700">
              과거 버전 {csvHistory.length - 1}건 보관
            </div>
          </div>
        )}
      </section>

      {showAdvanced && (
      <>
      {/* 🛠 Standalone Jobs — Art(🎨 v47) + Field Complete(🧩) 통합 history */}
      <section className="mb-8 rounded-xl border bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base font-semibold text-gray-900">
            🛠 Standalone Jobs (자동 갱신) — Art + Field 통합 history
          </h2>
          <span className="text-[10px] text-gray-500">
            🎨 Art {v43JobsList.length} · 🧩 Field {fcData?.jobs?.length ?? 0}
          </span>
        </div>
        <p className="mb-3 text-[10px] text-gray-500">
          Pipeline 세션에서 자동 생성되거나(<code>source_pipeline</code> 라벨 표시) 직접 트리거된 모든 job.
          행 클릭 → 상세 모달.
        </p>
        {(() => {
          type UnifiedRow = {
            kind: "art" | "fc";
            _id: string;
            status: string;
            created_at?: string;
            label?: string;
            email?: string;
            source?: string;
            levels?: number;
            png_pairs?: number;
            totals?: { ok?: number; fail?: number; escalated?: number; avg_score?: number };
            from_pipeline?: boolean;
          };
          const artRows: UnifiedRow[] = v43JobsList.map((j) => ({
            kind: "art" as const,
            _id: j._id,
            status: j.status,
            created_at: j.created_at,
            label: j.label,
            source: j.source_job,
            levels: j.target_levels?.length,
            png_pairs: j.total_levels,
            from_pipeline: typeof j.label === "string" && j.label.startsWith("[Pipeline "),
          }));
          const fcRows: UnifiedRow[] = (fcData?.jobs || []).map((j) => ({
            kind: "fc" as const,
            _id: j._id,
            status: j.status,
            created_at: j.created_at,
            email: j.created_by_email,
            source: j.csv_source,
            totals: j.totals,
            from_pipeline: typeof j.csv_source === "string" && j.csv_source.startsWith("[Pipeline "),
          }));
          const all = [...artRows, ...fcRows].sort((a, b) =>
            (b.created_at || "").localeCompare(a.created_at || ""));
          if (!fcData && v43JobsList.length === 0) {
            return <p className="py-6 text-center text-sm text-gray-400">데이터 로딩 중...</p>;
          }
          if (all.length === 0) {
            return <p className="py-6 text-center text-sm text-gray-400">
              job 없음 — [+ 새 Pipeline] 으로 시작하거나, 우상단 [🎨 v47 Pattern Batch] 직접 트리거
            </p>;
          }
          return (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-3 py-2 text-left">Kind</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-left">Created</th>
                    <th className="px-3 py-2 text-left">Label / Source</th>
                    <th className="px-3 py-2 text-right">Levels</th>
                    <th className="px-3 py-2 text-right">Result</th>
                    <th className="px-3 py-2 text-center">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {all.map((j) => {
                    const isArt = j.kind === "art";
                    const onRowClick = () => isArt ? openV43Detail(j._id) : openJob(j._id);
                    return (
                      <tr key={`${j.kind}-${j._id}`}
                          className={`border-t cursor-pointer ${isArt ? "hover:bg-fuchsia-50/60" : "hover:bg-emerald-50"}`}
                          onClick={onRowClick}>
                        <td className="px-3 py-2">
                          <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            isArt ? "bg-fuchsia-100 text-fuchsia-700" : "bg-emerald-100 text-emerald-700"}`}>
                            {isArt ? "🎨 Art" : "🧩 Field"}
                          </span>
                          {j.from_pipeline && (
                            <span className="ml-1 rounded bg-blue-50 px-1.5 py-0.5 text-[9px] text-blue-700"
                                  title="Pipeline 세션에서 생성됨">↳ pl</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <span className={`rounded px-2 py-0.5 text-[10px] font-medium ${
                            j.status === "done" ? "bg-emerald-100 text-emerald-700"
                            : j.status === "running" ? "bg-blue-100 text-blue-700"
                            : j.status === "failed" ? "bg-red-100 text-red-700"
                            : "bg-gray-100 text-gray-600"}`}>
                            {j.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-gray-600">{j.created_at?.slice(0, 19)}</td>
                        <td className="px-3 py-2 truncate max-w-[220px]"
                            title={(j.label || j.source || "") + (j.email ? ` · ${j.email}` : "")}>
                          <span className="font-medium">{j.label || j.source || "—"}</span>
                          {j.email && <span className="ml-2 text-[10px] text-gray-500">{j.email}</span>}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {isArt ? (j.levels ?? "—") : "—"}
                          {isArt && j.png_pairs ? (
                            <span className="ml-1 text-[10px] text-fuchsia-700">×{2}</span>
                          ) : null}
                        </td>
                        <td className="px-3 py-2 text-right text-[11px]">
                          {isArt ? (
                            j.png_pairs ? <span className="text-fuchsia-700">{j.png_pairs} pairs</span> : "—"
                          ) : j.totals ? (
                            <span>
                              <span className="text-emerald-700">{j.totals.ok ?? 0}</span>
                              <span className="text-gray-400">/</span>
                              <span className="text-red-600">{j.totals.fail ?? 0}</span>
                              {(j.totals.escalated ?? 0) > 0 && (
                                <span className="ml-1 text-amber-700">↑{j.totals.escalated}</span>
                              )}
                              {j.totals.avg_score !== undefined && (
                                <span className={`ml-2 tabular-nums ${
                                  j.totals.avg_score >= 0.85 ? "text-emerald-700"
                                  : j.totals.avg_score >= 0.70 ? "text-amber-700" : "text-gray-500"}`}>
                                  {j.totals.avg_score.toFixed(3)}
                                </span>
                              )}
                            </span>
                          ) : "—"}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <button type="button"
                            onClick={(e) => { e.stopPropagation(); onRowClick(); }}
                            className={`rounded px-2 py-1 text-[10px] font-medium ${
                              isArt ? "bg-fuchsia-100 hover:bg-fuchsia-200 text-fuchsia-700"
                                    : "bg-emerald-100 hover:bg-emerald-200 text-emerald-700"}`}>
                            🔍 상세
                          </button>
                          {!isArt && j.status === "done" && (j.totals?.ok ?? 0) > 0 && (
                            <button type="button"
                              onClick={(e) => { e.stopPropagation(); setFcGimmickModalId(j._id); }}
                              className="ml-1 rounded bg-indigo-100 px-2 py-1 text-[10px] font-medium text-indigo-700 hover:bg-indigo-200"
                              title="이 job의 csv_rows에 lv force-bump + gimmick 주입 → 새 fc job 실행">
                              🧩 기믹 추가
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
        })()}
      </section>

      {/* 최근 요청 */}
      <section className="rounded-xl border bg-white p-5 shadow-sm">
        <h2 className="mb-4 text-base font-semibold">📋 최근 요청 (자동 갱신 8s)</h2>
        {loading && <p className="text-gray-400">로딩 중...</p>}
        {data && (data.requests ?? []).length === 0 && (
          <p className="py-6 text-center text-sm text-gray-400">아직 요청 없음 — 위 폼에서 트리거</p>
        )}
        {data && (data.requests ?? []).length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Created</th>
                  <th className="px-3 py-2 text-left">Email</th>
                  <th className="px-3 py-2 text-left">Mood</th>
                  <th className="px-3 py-2 text-left">Style</th>
                  <th className="px-3 py-2 text-left">Size</th>
                  <th className="px-3 py-2 text-right">Count</th>
                  <th className="px-3 py-2 text-right">OK</th>
                  <th className="px-3 py-2 text-right">Dedup</th>
                  <th className="px-3 py-2 text-right">Fail</th>
                  <th className="px-3 py-2 text-right">Time</th>
                  <th className="px-3 py-2 text-center">기믹 후보정</th>
                </tr>
              </thead>
              <tbody>
                {(data.requests ?? []).map((r) => (
                  <tr key={r._id} className="border-t hover:bg-gray-50">
                    <td className="px-3 py-2">
                      <span className={`rounded px-2 py-0.5 text-[10px] font-medium ${STATUS_STYLE[r.status] || "bg-gray-100"}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-600">{r.created_at?.slice(0, 19)}</td>
                    <td className="px-3 py-2 text-gray-500">{r.created_by_email}</td>
                    <td className="px-3 py-2">{r.mood}</td>
                    <td className="px-3 py-2">{r.style || <span className="text-gray-400">—</span>}</td>
                    <td className="px-3 py-2">
                      {r.size || (r.width && r.height ? `${r.width}×${r.height}` : "—")}
                    </td>
                    <td className="px-3 py-2 text-right">{r.count}</td>
                    <td className="px-3 py-2 text-right text-emerald-700">{r.totals?.ok ?? "—"}</td>
                    <td className="px-3 py-2 text-right text-amber-700">{r.totals?.dedup_skip ?? "—"}</td>
                    <td className="px-3 py-2 text-right text-red-600">{r.totals?.fail ?? "—"}</td>
                    <td className="px-3 py-2 text-right text-gray-500">
                      {r.totals?.duration_sec ? `${Math.round(r.totals.duration_sec)}s` : "—"}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {r.status === "done" && ((r.totals?.ok ?? 0) > 0 || (r.totals?.dedup_skip ?? 0) > 0) ? (
                        <button type="button"
                          onClick={() => setGimmickModalBatchId(r._id)}
                          className={`rounded-md px-2 py-1 text-[10px] font-medium ring-1 ${
                            (r.totals?.ok ?? 0) > 0
                              ? "bg-emerald-50 text-emerald-700 ring-emerald-300 hover:bg-emerald-100"
                              : "bg-amber-50 text-amber-700 ring-amber-300 hover:bg-amber-100"
                          }`}
                          title={
                            (r.totals?.ok ?? 0) > 0
                              ? "이 batch 의 새 결과로 field-complete 실행"
                              : `dedup ${r.totals?.dedup_skip ?? 0}건 — 같은 email 의 기존 갤러리 레벨로 fallback`
                          }
                        >
                          🧩 기믹 추가{(r.totals?.ok ?? 0) === 0 ? " (dedup)" : ""}
                        </button>
                      ) : <span className="text-gray-300 text-[10px]">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      </>
      )}

      {/* 🧩 Art batch → 기믹 후보정 small modal */}
      {gimmickModalBatchId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => !gimmickSubmitting && setGimmickModalBatchId(null)}>
          <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-1 text-base font-bold text-emerald-900">🧩 Art batch에 기믹 후보정</h3>
            <p className="mb-2 text-[11px] text-gray-500">
              batch <code className="bg-gray-100 px-1 rounded">{gimmickModalBatchId.slice(-8)}</code>의 결과를 BL 메타 augment 후 field-complete 실행
            </p>
            <div className="mb-3 rounded bg-yellow-50 border border-yellow-200 px-3 py-2 text-[10px] text-yellow-900">
              ⚠️ <strong>CSV 모드 batch이면 원본 CSV의 <code>purpose_type</code>/<code>gimmick_*</code>가 자동 적용됩니다</strong> (preset은 CSV에 정보 없는 row에만 fallback).<br />
              순수 mood/style batch (CSV 없이 생성)인 경우만 preset이 모든 row에 적용됨.
            </div>
            <div className="mb-3">
              <div className="mb-1 text-xs font-semibold text-gray-700">기믹 프리셋</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {(["none", "light", "medium", "heavy"] as const).map((p) => (
                  <label key={p}
                    className={`flex flex-col rounded-lg border-2 p-2 cursor-pointer transition ${
                      gimmickPreset === p ? "border-emerald-500 bg-emerald-50" : "border-gray-200 bg-white hover:bg-gray-50"
                    }`}>
                    <div className="flex items-center gap-1">
                      <input type="radio" checked={gimmickPreset === p}
                        onChange={() => setGimmickPreset(p)} />
                      <span className="font-semibold capitalize">{p}</span>
                    </div>
                    <span className="ml-5 text-[10px] text-gray-500">
                      {p === "none" && "기믹 없음 (필드만 정합)"}
                      {p === "light" && "1-2개 활성 (lv 따라 자동 선정)"}
                      {p === "medium" && "3-4개 활성 (균형)"}
                      {p === "heavy" && "5개 최대 (Hard/SuperHard 적합)"}
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <div className="mb-3 rounded bg-blue-50 p-2 text-[10px] text-blue-800">
              📋 자동 적용: pkg=idx/20+1, pos=(idx-1)%20+1, purpose=pos 기반 (1·11=tutorial / 9·19=super_hard / 5·12·15=hard / 6·10·13·16·20=rest / 외=normal)
              <br />🔧 고급 옵션의 Iron Wall mode (<strong>{ironWallMode}</strong>) + n=10 후보 ({keepAllCandidates ? "✓" : "✗"})도 함께 적용
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setGimmickModalBatchId(null)} disabled={gimmickSubmitting}
                className="rounded-md bg-gray-100 px-3 py-1.5 text-xs hover:bg-gray-200 disabled:opacity-50">취소</button>
              <button type="button" onClick={submitGimmickAdd} disabled={gimmickSubmitting}
                className="rounded-md bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:bg-gray-300">
                {gimmickSubmitting ? "실행 중..." : `기믹 후보정 실행 (preset=${gimmickPreset})`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🧩 fc job → 기믹 추가 small modal */}
      {/* 🎨 v43 batch modal */}
      {/* 📂 CSV 업로드 모달 */}
      {/* 🎬 새 Pipeline Session 시작 모달 */}
      {pipelineNewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => !plActionSubmitting && setPipelineNewOpen(false)}>
          <div className="w-full max-w-xl rounded-xl bg-white p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-1 text-base font-bold text-emerald-900">🎬 새 Pipeline Session 시작</h3>
            <p className="mb-3 text-[11px] text-gray-500">
              CSV → Art (v47) → Curate (A/B) → Field Complete → Download. 한 행으로 통합 관리.
            </p>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block mb-1 font-semibold text-gray-700">Label</label>
                <input type="text" value={newPlLabel}
                  onChange={(e) => setNewPlLabel(e.target.value)}
                  placeholder="예: pkg 3-5 v47"
                  className="w-full px-2 py-1.5 border border-gray-300 rounded"
                  disabled={plActionSubmitting} />
              </div>
              <div>
                <label className="block mb-1 font-semibold text-gray-700">대상 레벨</label>
                <input type="text" value={newPlLevels}
                  onChange={(e) => setNewPlLevels(e.target.value)}
                  className="w-full px-2 py-1.5 border border-gray-300 rounded font-mono text-[11px]"
                  placeholder="1,3,5-10,50"
                  disabled={plActionSubmitting} />
                <p className="mt-1 text-[10px] text-gray-500">쉼표 + 범위 (-) 지원</p>
              </div>
              <label className="flex items-center gap-2 cursor-pointer p-2 rounded border border-gray-200">
                <input type="checkbox" checked={newPlAutoAdvance}
                  onChange={(e) => setNewPlAutoAdvance(e.target.checked)} disabled={plActionSubmitting} />
                <span className="text-xs">
                  <span className="font-semibold">자동 진행</span>
                  <span className="block text-[10px] text-gray-500">큐레이션 → Field 자동 시작</span>
                </span>
              </label>
              {csvLatest ? (
                <div className="rounded bg-amber-50 border border-amber-200 px-3 py-2 text-[10px] text-amber-900 space-y-1">
                  <div>
                    📂 사용 CSV: <code className="bg-white px-1 rounded">{csvLatest.version}</code>{" "}
                    "{csvLatest.label}" ({csvLatest.row_count} rows)
                  </div>
                  <div className="text-amber-700">
                    💡 기믹 종류·개수는 <strong>CSV 컬럼</strong>(<code>gimmick_chain</code>, <code>gimmick_hidden</code>, <code>gimmick_wall</code> 등)에서 직접 지정됩니다.
                    CSV에 명시되지 않은 lv는 PF lookup(pf_grounded)로 자동 보충.
                  </div>
                </div>
              ) : (
                <div className="rounded bg-amber-50 border border-amber-200 px-3 py-2 text-[10px] text-amber-900 space-y-1">
                  <div>⚠️ 등록된 latest CSV 없음 — pixelforge_levels DB 에서 자동 합성됨</div>
                  <div className="text-amber-700">
                    💡 CSV 미지정 시 기믹은 PF lookup(pf_grounded)로 자동 적용. CSV 업로드 후 컬럼별 지정 권장.
                  </div>
                </div>
              )}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setPipelineNewOpen(false)} disabled={plActionSubmitting}
                className="px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 rounded disabled:opacity-50">취소</button>
              <button type="button" onClick={submitNewPipeline} disabled={plActionSubmitting}
                className="px-4 py-1.5 text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 rounded disabled:bg-gray-300">
                {plActionSubmitting ? "시작 중..." : "🚀 시작"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🎬 Pipeline Session 상세 모달 — 5-stage 진행 + stage 별 액션 */}
      {plDetailId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => { setPlDetailId(null); setPlDetail(null); }}>
          <div className="max-h-[92vh] w-full max-w-7xl overflow-hidden rounded-xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="border-b bg-emerald-50 px-5 py-3">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <h2 className="text-sm font-bold text-emerald-900">🎬 Pipeline: {plDetail?.label}</h2>
                  <p className="text-[11px] text-gray-500">
                    id: {plDetailId}{plDetail?.target_levels ? ` · ${plDetail.target_levels.length} lv` : ""}
                    {plDetail?.gimmick_preset ? ` · preset=${plDetail.gimmick_preset}` : ""}
                  </p>
                </div>
                <button onClick={() => { setPlDetailId(null); setPlDetail(null); }}
                  className="rounded bg-gray-200 px-3 py-1.5 text-xs hover:bg-gray-300">✕ 닫기</button>
              </div>
              {/* 5-stage progress bar */}
              <div className="flex items-center gap-1">
                {["📂 CSV", "🎨 Art", "🔍 Curate", "🎲 Queue", "🧩 Field", "⬇ Down"].map((lbl, i) => {
                  const sIdx = plDetail ? stageIndex(plDetail.stage) : 0;
                  const active = i === sIdx;
                  const done = i < sIdx;
                  return (
                    <div key={i} className="flex items-center">
                      <span className={`px-3 py-1 rounded-full text-[10px] font-semibold ${
                        plDetail?.stage === "failed" ? "bg-red-100 text-red-700"
                          : done ? "bg-emerald-500 text-white"
                          : active ? "bg-emerald-200 text-emerald-900 ring-2 ring-emerald-400 animate-pulse"
                          : "bg-gray-200 text-gray-500"
                      }`}>
                        {done ? "✓ " : ""}{lbl}
                      </span>
                      {i < 4 && <span className="mx-1 text-gray-400">→</span>}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="max-h-[78vh] overflow-y-auto px-5 py-4">
              {plDetailLoading && <p className="text-sm text-gray-400">불러오는 중...</p>}
              {!plDetailLoading && plDetail && (
                <PipelineStagePanel
                  detail={plDetail}
                  curations={plCurations}
                  setCurations={setPlCurations}
                  onAdvance={advancePipeline}
                  submitting={plActionSubmitting}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {csvModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => !csvSubmitting && setCsvModalOpen(false)}>
          <div className="w-full max-w-2xl rounded-xl bg-white p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-2 text-base font-bold text-amber-900">📤 CSV 업로드 / 교체</h3>
            <p className="mb-3 text-[11px] text-gray-500">
              중앙 CSV 갱신 — 이후 모든 배치가 이 CSV 참조. 이전 버전은 history 에 archive.
              <br/>형식: 1행 카테고리 / 2행 영문 헤더 / 3행 한글 헤더 / 4행~ 데이터.
            </p>
            <div className="mb-3">
              <label className="block text-xs font-semibold text-gray-700 mb-1">Label (선택)</label>
              <input type="text" value={csvUploadLabel}
                onChange={(e) => setCsvUploadLabel(e.target.value)}
                placeholder="예: BalloonFlow_LevelDesign_v3"
                className="w-full px-2 py-1.5 border border-gray-300 rounded text-xs"
                disabled={csvSubmitting} />
            </div>
            <div className="mb-3">
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                CSV 텍스트 또는 파일 선택
              </label>
              <div
                onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); setCsvDragOver(true); }}
                onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setCsvDragOver(true); }}
                onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); setCsvDragOver(false); }}
                onDrop={async (e) => {
                  e.preventDefault(); e.stopPropagation();
                  setCsvDragOver(false);
                  const f = e.dataTransfer.files?.[0];
                  if (!f) return;
                  if (csvSubmitting) return;
                  try {
                    const text = await readCsvFile(f);
                    setCsvUploadText(text);
                    if (!csvUploadLabel) setCsvUploadLabel(f.name.replace(/\.(csv|tsv|txt)$/i, ""));
                    setCsvUploadError(null);
                  } catch (err) {
                    setCsvUploadError({ msg: err instanceof Error ? err.message : "파일 읽기 실패" });
                  }
                }}
                className={`mb-2 rounded-lg border-2 border-dashed p-3 text-center transition ${
                  csvDragOver ? "border-amber-500 bg-amber-50 ring-2 ring-amber-200"
                              : "border-gray-300 bg-gray-50"}`}>
                <p className="mb-2 text-[11px] text-gray-600">
                  📂 파일을 <strong>여기에 끌어다 놓거나</strong> 아래 버튼 클릭
                </p>
                <input type="file" accept=".csv,text/csv,text/plain,.txt,.tsv"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    try {
                      const text = await readCsvFile(f);
                      setCsvUploadText(text);
                      if (!csvUploadLabel) setCsvUploadLabel(f.name.replace(/\.(csv|tsv|txt)$/i, ""));
                      setCsvUploadError(null);
                    } catch (err) {
                      setCsvUploadError({ msg: err instanceof Error ? err.message : "파일 읽기 실패" });
                    }
                  }}
                  className="text-xs mx-auto block" disabled={csvSubmitting} />
                {csvDragOver && (
                  <p className="mt-1 text-[10px] font-semibold text-amber-700">⬇ 여기에 드롭</p>
                )}
              </div>
              <textarea value={csvUploadText}
                onChange={(e) => setCsvUploadText(e.target.value)}
                placeholder="여기에 CSV 텍스트 붙여넣기 또는 위 파일 선택 (UTF-8 권장, EUC-KR 자동 fallback, BOM 자동 제거, , ; \t delimiter 자동 감지)"
                className="w-full h-32 px-2 py-1.5 border border-gray-300 rounded font-mono text-[10px]"
                disabled={csvSubmitting} />
              <p className="mt-1 text-[10px] text-gray-500">
                미리보기: {csvUploadText.length > 0 ? `${csvUploadText.split("\n").length} 라인 / ${csvUploadText.length} 바이트` : "(비어있음)"}
              </p>
            </div>
            {csvUploadError && (
              <div className="mb-3 rounded border border-red-300 bg-red-50 p-3 text-[10px] text-red-900">
                <div className="font-bold mb-1">⚠️ 파싱 실패</div>
                <div className="mb-2">{csvUploadError.msg}</div>
                {csvUploadError.detail?.delimiter && (
                  <div>· 감지된 delimiter: <code className="bg-white px-1 rounded">{csvUploadError.detail.delimiter}</code></div>
                )}
                {csvUploadError.detail?.first_5_lines && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-red-700 font-semibold">첫 5줄 미리보기</summary>
                    <pre className="mt-1 bg-white p-2 rounded font-mono text-[9px] overflow-x-auto whitespace-pre-wrap">
                      {csvUploadError.detail.first_5_lines.map((l, i) => `[${i+1}] ${l}`).join("\n")}
                    </pre>
                  </details>
                )}
                {csvUploadError.detail?.hint && (
                  <div className="mt-2 text-red-700">💡 {csvUploadError.detail.hint}</div>
                )}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setCsvModalOpen(false); setCsvUploadError(null); }} disabled={csvSubmitting}
                className="px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 rounded disabled:opacity-50">취소</button>
              <button type="button" onClick={submitCsvUpload}
                disabled={csvSubmitting || !csvUploadText.trim()}
                className="px-4 py-1.5 text-xs font-medium bg-amber-600 text-white hover:bg-amber-700 rounded disabled:bg-gray-300">
                {csvSubmitting ? "업로드 중..." : "📤 latest 로 등록"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 🎨 v43 상세 모달 (PNG grid + evaluation 요약) */}
      {v43DetailId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => { setV43DetailId(null); setV43Detail(null); }}>
          <div className="max-h-[92vh] w-full max-w-7xl overflow-hidden rounded-xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b bg-fuchsia-50 px-5 py-3">
              <div>
                <h2 className="text-sm font-semibold text-fuchsia-900">
                  🎨 v43 결과 — {v43Detail?.label || v43DetailId.slice(-8)}
                </h2>
                <p className="text-[11px] text-gray-500">
                  id: {v43DetailId}{v43Detail?.source_job ? ` · src: ${v43Detail.source_job}` : ""}
                  {v43Detail?.target_levels ? ` · ${v43Detail.target_levels.length} lv` : ""}
                  {v43Detail?.png_count !== undefined ? ` · ${v43Detail.png_count} PNG` : ""}
                </p>
              </div>
              <div className="flex gap-2">
                {v43Detail?.evaluation && (() => {
                  const evals = (v43Detail.evaluation || []) as V43EvalEntry[];
                  const okFinal = evals.filter((r) => (r.final_candidates || []).length > 0);
                  const bothX10 = okFinal.filter((r) => r.final_candidates.every((c: V43Cand) => c.x10_pass));
                  const avgScore = okFinal.length > 0
                    ? okFinal.reduce((s, r) => s + (r.final_candidates[0]?.total_score || 0), 0) / okFinal.length
                    : 0;
                  return (
                    <div className="rounded bg-white px-3 py-1.5 text-[10px] text-fuchsia-900 border border-fuchsia-200">
                      <span className="font-bold">{okFinal.length}/{evals.length}</span> gen
                      <span className="mx-2">·</span>
                      <span className="font-bold text-emerald-700">{bothX10.length}</span> both-×10
                      <span className="mx-2">·</span>
                      avg score <span className="font-bold">{avgScore.toFixed(3)}</span>
                    </div>
                  );
                })()}
                {v43Detail?.status === "done" && (() => {
                  const selectedCount = Object.values(v43Curations).filter((v) => v).length;
                  return (
                    <button onClick={submitV43Curation}
                      disabled={v43CurateSubmitting || selectedCount === 0}
                      className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:bg-gray-300">
                      {v43CurateSubmitting ? "적용 중..." : `✓ 큐레이션 적용 (${selectedCount})`}
                    </button>
                  );
                })()}
                <button onClick={() => { setV43DetailId(null); setV43Detail(null); }}
                  className="rounded bg-gray-200 px-3 py-1.5 text-xs hover:bg-gray-300">✕ 닫기</button>
              </div>
            </div>

            <div className="max-h-[80vh] overflow-y-auto px-5 py-4">
              {v43DetailLoading && <p className="text-sm text-gray-400">불러오는 중...</p>}
              {!v43DetailLoading && v43Detail && (
                <div className="space-y-3">
                  {(v43Detail.evaluation || []).map((entry: V43EvalEntry) => {
                    const candA = entry.final_candidates?.[0];
                    const candB = entry.final_candidates?.[1];
                    const pngA = v43Detail.pngs?.find((p: V43Pngs) => p.level === entry.level && p.label === "A");
                    const pngB = v43Detail.pngs?.find((p: V43Pngs) => p.level === entry.level && p.label === "B");
                    return (
                      <div key={entry.level} className="rounded-lg border border-fuchsia-200 bg-white p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <div className="text-sm font-semibold text-fuchsia-900">
                            Lv {entry.level} — {entry.metaphor || "(no metaphor)"}
                          </div>
                          <div className="text-[10px] text-gray-500">
                            {entry.board_size?.[0]}×{entry.board_size?.[1]} · nc={entry.num_colors}
                          </div>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {[{ cand: candA, png: pngA, label: "A" as const }, { cand: candB, png: pngB, label: "B" as const }].map(({ cand, png, label }) => {
                            const selected = v43Curations[entry.level] === label;
                            return (
                            <div key={label}
                              onClick={() => setV43Curations((prev) => ({ ...prev, [entry.level]: selected ? null : label }))}
                              className={`rounded border-2 p-2 cursor-pointer transition ${
                                selected ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-200"
                                         : "border-gray-200 bg-gray-50 hover:bg-gray-100"}`}
                            >
                              <div className="mb-1 flex items-center justify-between text-[10px]">
                                <span className="font-bold text-fuchsia-700">
                                  {selected ? "✓ " : ""}{label}
                                </span>
                                {cand && (
                                  <span className={cand.x10_pass ? "text-emerald-700" : "text-red-600"}>
                                    {cand.x10_pass ? "✓ ×10" : "✗ ×10"}
                                  </span>
                                )}
                              </div>
                              {png ? (
                                /* eslint-disable-next-line @next/next/no-img-element */
                                <img src={`data:image/png;base64,${png.base64}`}
                                  alt={`Lv${entry.level}-${label}`}
                                  className="w-full bg-white rounded"
                                  style={{ imageRendering: "pixelated", aspectRatio: `${entry.board_size?.[0]}/${entry.board_size?.[1]}` }} />
                              ) : (
                                <div className="aspect-square bg-gray-200 rounded flex items-center justify-center text-[10px] text-gray-400">
                                  no png
                                </div>
                              )}
                              {cand && (
                                <div className="mt-1 grid grid-cols-2 gap-x-2 text-[10px] text-gray-600">
                                  <div>score: <span className="font-mono">{cand.total_score?.toFixed(3)}</span></div>
                                  <div>T cells: <span className="font-mono">{cand.t_cells}</span></div>
                                  <div>visual: <span className="font-mono">{cand.visual_quality?.toFixed(3)}</span></div>
                                  <div>noise: <span className="font-mono">{cand.noise_score?.toFixed(3)}</span></div>
                                  {cand.cluster_dist && (
                                    <div className="col-span-2 text-[10px] text-gray-500">
                                      gt30: {cand.cluster_dist.gt30_pct}% · le3: {cand.cluster_dist.le3_pct}%
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                  {!v43Detail.evaluation && (
                    <p className="text-center text-sm text-gray-400 py-12">evaluation.json 없음 (job 미완료 또는 오류)</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {v43ModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => !v43Submitting && setV43ModalOpen(false)}>
          <div className="w-full max-w-xl rounded-xl bg-white p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-1 text-base font-bold text-fuchsia-900">🎨 v47 Pattern Batch — 디자이너 원본 직접 실행</h3>
            <p className="mb-3 text-[11px] text-gray-500">
              <code className="bg-gray-100 px-1 rounded">gen_43_pipeline.py</code> 를 0 줄 변경 없이 spawn.
              10 시드 생성 → top 5 선별 → A/B 최종 후보 → PNG + evaluation.json.
            </p>
            <div className="mb-3 rounded bg-fuchsia-50 border border-fuchsia-200 px-3 py-2 text-[10px] text-fuchsia-900">
              ℹ️ 결과는 <code className="bg-white px-1 rounded">~/.hermes/v43_out/&lt;job_id&gt;/</code> 에 저장.
            </div>

            <div className="mb-3 rounded bg-amber-50 border border-amber-200 px-3 py-2 text-[10px]">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={v43UseLatestCsv} disabled={!csvLatest}
                  onChange={(e) => setV43UseLatestCsv(e.target.checked)} />
                <span className="font-semibold text-amber-900">📂 최신 중앙 CSV 사용</span>
                {csvLatest ? (
                  <span className="text-amber-700">
                    — <code className="bg-white px-1 rounded">{csvLatest.version}</code> "{csvLatest.label}" ({csvLatest.row_count} rows)
                  </span>
                ) : (
                  <span className="text-gray-400">— 등록된 CSV 없음. 위 [📤 CSV 업로드] 먼저</span>
                )}
              </label>
              <p className="ml-6 mt-1 text-[10px] text-gray-600">
                해제 시: pixelforge_levels DB 에서 자동 합성 (메타포/사이즈/색상수만)
              </p>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block mb-1 font-semibold text-gray-700">대상 레벨 (쉼표 또는 범위)</label>
                <input type="text" value={v43Levels}
                  onChange={(e) => setV43Levels(e.target.value)}
                  className="w-full px-2 py-1.5 border border-gray-300 rounded font-mono text-[11px]"
                  placeholder="1,3,5-10,50,121-130"
                  disabled={v43Submitting} />
                <p className="mt-1 text-[10px] text-gray-500">
                  예: <code>1,3,4,5,7,14,18,20,21,23,25,27,37,50,51,59,64,65,70,72,76,78,81,88,115,123,137,139,144,156,163,167,203,209,231,248,262,263,271,274,292</code> (디자이너 41-lv 셋)
                </p>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block mb-1 font-semibold text-gray-700">n_seeds</label>
                  <input type="number" min={2} max={20} value={v43NSeeds}
                    onChange={(e) => setV43NSeeds(Number(e.target.value) || 10)}
                    className="w-full px-2 py-1.5 border border-gray-300 rounded text-center"
                    disabled={v43Submitting} />
                </div>
                <div>
                  <label className="block mb-1 font-semibold text-gray-700">n_final (A/B...)</label>
                  <input type="number" min={1} max={5} value={v43NFinal}
                    onChange={(e) => setV43NFinal(Number(e.target.value) || 2)}
                    className="w-full px-2 py-1.5 border border-gray-300 rounded text-center"
                    disabled={v43Submitting} />
                </div>
                <div>
                  <label className="block mb-1 font-semibold text-gray-700">label</label>
                  <input type="text" value={v43Label}
                    onChange={(e) => setV43Label(e.target.value)}
                    className="w-full px-2 py-1.5 border border-gray-300 rounded"
                    disabled={v43Submitting} />
                </div>
              </div>
              {v43LastJobId && (
                <div className="rounded bg-emerald-50 border border-emerald-200 px-3 py-2 text-[10px] text-emerald-900">
                  ✓ 직전 job: <code>{v43LastJobId}</code> — 진행 상황은 <code>tail -f ~/.hermes/logs/v43/v43_{v43LastJobId}.log</code> 로 모니터링
                </div>
              )}
            </div>

            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setV43ModalOpen(false)} disabled={v43Submitting}
                className="px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 rounded disabled:opacity-50">취소</button>
              <button type="button" onClick={submitV43Batch} disabled={v43Submitting}
                className="px-4 py-1.5 text-xs font-medium bg-fuchsia-600 text-white hover:bg-fuchsia-700 rounded disabled:bg-gray-300">
                {v43Submitting ? "실행 중..." : "🎨 실행"}
              </button>
            </div>
          </div>
        </div>
      )}

      {fcGimmickModalId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => !fcGimmickSubmitting && setFcGimmickModalId(null)}>
          <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-1 text-base font-bold text-indigo-900">🧩 기존 fc job에 기믹 후보정</h3>
            <p className="mb-2 text-[11px] text-gray-500">
              job <code className="bg-gray-100 px-1 rounded">{fcGimmickModalId.slice(-8)}</code>의 csv_rows를 가져와 lv force-bump + gimmick 주입 → 새 fc job 실행
            </p>
            <div className="mb-3 rounded bg-emerald-50 border border-emerald-200 px-3 py-2 text-[10px] text-emerald-900">
              ✅ <strong>CSV 에 실제 level_number (&gt;1) 명시되어 있으면 그대로 보존</strong> (2026-05-21 fix). lv force-bump 는 image-upload (lv=1 default) 케이스에만 적용.<br/>
              ✅ <strong>CSV 에 디자이너가 명시한 gimmick_* 값 보존</strong> — preset 은 0인 셀에만 채워넣음.
            </div>
            <div className="mb-3 rounded bg-amber-50 border border-amber-200 px-3 py-2 text-[10px] text-amber-900">
              <strong>preset 별 동작</strong>:
              <ul className="ml-4 mt-1 list-disc">
                <li><strong>pf_grounded ⭐</strong>: PF 1200 lv 데이터 lookup — 해당 lv 가 PF 에서 실제로 쓴 기믹만 권장 count. PF 가 안 쓴 lv 은 기믹 0 ("있게있게, 없으면 없게")</li>
                <li><strong>none</strong>: lv 유지, 기믹 없음 재실행</li>
                <li><strong>light</strong>: image-upload 용 lv 41+ force-bump + pinata 1개</li>
                <li><strong>medium</strong>: image-upload 용 lv 121+ force-bump + wall+pinata</li>
                <li><strong>heavy</strong>: image-upload 용 lv 161+ force-bump + 다수 기믹</li>
              </ul>
            </div>
            <div className="mb-3">
              <div className="mb-1 text-xs font-semibold text-gray-700">기믹 프리셋</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {(["pf_grounded", "none", "light", "medium", "heavy"] as const).map((p) => (
                  <label key={p}
                    className={`flex flex-col rounded-lg border-2 p-2 cursor-pointer transition ${
                      fcGimmickPreset === p ? "border-indigo-500 bg-indigo-50" : "border-gray-200 bg-white hover:bg-gray-50"
                    }`}>
                    <div className="flex items-center gap-1">
                      <input type="radio" checked={fcGimmickPreset === p}
                        onChange={() => setFcGimmickPreset(p)} />
                      <span className="font-semibold">{p === "pf_grounded" ? "PF 기반 ⭐" : p}</span>
                    </div>
                    <span className="ml-5 text-[10px] text-gray-500">
                      {p === "pf_grounded" && "PF 1200 lv 룩업 — 있게/없게 그대로 (lv 보존)"}
                      {p === "none" && "lv 유지, 기믹 없음 재실행"}
                      {p === "light" && "image-upload용 lv 41+ pinata 1개"}
                      {p === "medium" && "image-upload용 lv 121+ wall + pinata"}
                      {p === "heavy" && "image-upload용 lv 161+ 다수 기믹"}
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setFcGimmickModalId(null)} disabled={fcGimmickSubmitting}
                className="rounded-md bg-gray-100 px-3 py-1.5 text-xs hover:bg-gray-200 disabled:opacity-50">취소</button>
              <button type="button" onClick={submitFcGimmickAdd} disabled={fcGimmickSubmitting}
                className="rounded-md bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:bg-gray-300">
                {fcGimmickSubmitting ? "실행 중..." : `기믹 추가 실행 (preset=${fcGimmickPreset})`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Job 상세 modal */}
      {openJobId && (
        <JobDetailModal
          jobId={openJobId}
          detail={jobDetail}
          loading={jobDetailLoading}
          onClose={closeJob}
        />
      )}
    </div>
  );
}

// BalloonFlow 24색 팔레트 (c1..c24 → 1-based index)
const BL_PALETTE_HEX: string[] = [
  "#FC6AAF", "#50E8F6", "#8950F8", "#FED555",
  "#73FE66", "#FDA14C", "#FFFFFF", "#414141",
  "#6EA8FA", "#39AE2E", "#FC5E5E", "#326BF8",
  "#3AA58B", "#E7A7FA", "#B7C7FB", "#6A4A30",
  "#FEE3A9", "#FDB7C1", "#9E3D5E", "#A7DD94",
  "#592E7E", "#DC7881", "#D9D9E7", "#6F727F",
];
function colorHex(c: number): string {
  if (c >= 1 && c <= BL_PALETTE_HEX.length) return BL_PALETTE_HEX[c - 1];
  // c25+ (extended) fallback
  return "#888888";
}

// 🎬 Pipeline 세션 상세 모달 — stage 별 액션 패널
type V43Pngs = { filename: string; level: number; label: string; metaphor: string; base64: string };
type V43Cand = { seed_idx?: number; x10_pass?: boolean; t_cells?: number;
                 t_sym_score?: number; noise_score?: number; visual_quality?: number;
                 total_score?: number; cluster_dist?: { le3_pct?: number; gt30_pct?: number };
                 colors?: string[] };
type V43EvalEntry = { level: number; metaphor: string; board_size: number[];
                      num_colors: number; final_candidates: V43Cand[] };

interface PipelineStageProps {
  detail: {
    _id: string; label: string; stage: string;
    target_levels?: number[]; gimmick_preset?: string;
    art_job?: { type: string; job_id: string; status: string };
    field_complete_job?: { job_id: string; status: string };
    log_tail?: string;
    evaluation?: V43EvalEntry[];
    pngs?: V43Pngs[]; png_count?: number;
    fc_totals?: { ok: number; fail: number; escalated: number; avg_score: number };
    fc_results_summary?: Array<{ level_number: number; ok: boolean; score: number;
                                   balloons: number; gimmicks: number; gimmick_types: string[] }>;
    queue_summary?: { generated: number; failed: number; skipped?: number;
                      results?: Array<{ level: number; grade: string; target: string; matched: boolean; seed: number; relative: number }> };
    error?: string;
  };
  curations: Record<number, "A" | "B" | null>;
  setCurations: React.Dispatch<React.SetStateAction<Record<number, "A" | "B" | null>>>;
  onAdvance: (action: "curate" | "queue" | "field" | "download" | "retry_field",
              selections?: Record<number, "A" | "B" | null>) => Promise<void>;
  submitting: boolean;
}

function PipelineStagePanel({ detail, curations, setCurations, onAdvance, submitting }: PipelineStageProps) {
  const stage = detail.stage;
  // ── Stage: art_running ──
  if (stage === "art_running") {
    return (
      <div>
        <h3 className="mb-2 text-sm font-semibold text-blue-900">🎨 Art 진행 중</h3>
        <p className="text-xs text-gray-600 mb-3">
          gen_43_pipeline.py spawn — 10 시드 × top 5 × A/B 후보. 보통 2~10분.
        </p>
        {detail.log_tail && (
          <pre className="bg-gray-900 text-green-300 p-3 rounded text-[10px] font-mono overflow-x-auto whitespace-pre-wrap max-h-80">
            {detail.log_tail}
          </pre>
        )}
        {!detail.log_tail && <p className="text-xs text-gray-400 py-12 text-center">로그 대기 중...</p>}
      </div>
    );
  }

  // ── Stage: art_done / curated_pending — 큐레이션 ──
  if (stage === "art_done" || stage === "curated_pending") {
    const evals = detail.evaluation || [];
    const okEvals = evals.filter((r) => (r.final_candidates || []).length > 0);
    const bothX10 = okEvals.filter((r) => r.final_candidates.every((c: V43Cand) => c.x10_pass));
    const selectedCount = Object.values(curations).filter((v) => v).length;

    function autoSelectByScore() {
      const next: Record<number, "A" | "B"> = {};
      for (const e of evals) {
        if (!e.final_candidates || e.final_candidates.length === 0) continue;
        const a = e.final_candidates[0];
        const b = e.final_candidates[1];
        if (!b) { next[e.level] = "A"; continue; }
        next[e.level] = ((a.total_score || 0) >= (b.total_score || 0)) ? "A" : "B";
      }
      setCurations(next);
    }
    function selectAll(label: "A" | "B") {
      const next: Record<number, "A" | "B"> = {};
      for (const e of evals) next[e.level] = label;
      setCurations(next);
    }

    return (
      <div>
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-amber-900">🔍 큐레이션 — A/B 후보 선택</h3>
            <p className="text-[10px] text-gray-500">
              {okEvals.length}/{evals.length} 생성 · both-×10 {bothX10.length} · 선택 {selectedCount}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => selectAll("A")}
              className="text-xs px-2 py-1 bg-fuchsia-100 hover:bg-fuchsia-200 rounded">전체 A</button>
            <button onClick={() => selectAll("B")}
              className="text-xs px-2 py-1 bg-fuchsia-100 hover:bg-fuchsia-200 rounded">전체 B</button>
            <button onClick={autoSelectByScore}
              className="text-xs px-2 py-1 bg-emerald-100 hover:bg-emerald-200 rounded">score 자동</button>
            <button onClick={() => setCurations({})}
              className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded">해제</button>
            <button onClick={() => onAdvance("curate", curations)}
              disabled={submitting || selectedCount === 0}
              className="text-xs px-3 py-1 bg-emerald-600 text-white hover:bg-emerald-700 rounded disabled:bg-gray-300 font-semibold">
              {submitting ? "적용 중..." : `✓ 큐레이션 적용 (${selectedCount})`}
            </button>
          </div>
        </div>
        <div className="space-y-3">
          {evals.map((entry: V43EvalEntry) => {
            const candA = entry.final_candidates?.[0];
            const candB = entry.final_candidates?.[1];
            const pngA = detail.pngs?.find((p) => p.level === entry.level && p.label === "A");
            const pngB = detail.pngs?.find((p) => p.level === entry.level && p.label === "B");
            return (
              <div key={entry.level} className="rounded-lg border border-amber-200 bg-white p-3">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-sm font-semibold text-amber-900">
                    Lv {entry.level} — {entry.metaphor || "(no metaphor)"}
                  </div>
                  <div className="text-[10px] text-gray-500">
                    {entry.board_size?.[0]}×{entry.board_size?.[1]} · nc={entry.num_colors}
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {[{ cand: candA, png: pngA, label: "A" as const }, { cand: candB, png: pngB, label: "B" as const }].map(({ cand, png, label }) => {
                    const selected = curations[entry.level] === label;
                    return (
                      <div key={label}
                        onClick={() => setCurations((prev) => ({ ...prev, [entry.level]: selected ? null : label }))}
                        className={`rounded border-2 p-2 cursor-pointer transition ${
                          selected ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-200"
                                   : "border-gray-200 bg-gray-50 hover:bg-gray-100"}`}>
                        <div className="mb-1 flex items-center justify-between text-[10px]">
                          <span className="font-bold text-fuchsia-700">{selected ? "✓ " : ""}{label}</span>
                          {cand && (
                            <span className={cand.x10_pass ? "text-emerald-700" : "text-red-600"}>
                              {cand.x10_pass ? "✓ ×10" : "✗ ×10"}
                            </span>
                          )}
                        </div>
                        {png ? (
                          /* eslint-disable-next-line @next/next/no-img-element */
                          <img src={`data:image/png;base64,${png.base64}`} alt={`${entry.level}-${label}`}
                            className="w-full bg-white rounded"
                            style={{ imageRendering: "pixelated", aspectRatio: `${entry.board_size?.[0]}/${entry.board_size?.[1]}` }} />
                        ) : <div className="aspect-square bg-gray-200 rounded text-[10px] text-gray-400 flex items-center justify-center">no png</div>}
                        {cand && (
                          <div className="mt-1 text-[10px] text-gray-600">
                            score <span className="font-mono">{cand.total_score?.toFixed(3)}</span>
                            {" · T"}<span className="font-mono">{cand.t_cells}</span>
                            {" · noise"}<span className="font-mono">{cand.noise_score?.toFixed(2)}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // ── Stage: curated_done — 다음은 Queue (Curate → Queue → Field) ──
  if (stage === "curated_done") {
    return (
      <div className="text-center py-12">
        <h3 className="text-base font-semibold text-teal-900 mb-2">🔍 큐레이션 완료</h3>
        <p className="text-xs text-gray-600 mb-4">다음 단계: 🎲 Queue 생성 (난이도 매칭 + 큐기믹)</p>
        <div className="flex items-center justify-center gap-2">
          <button onClick={() => onAdvance("queue")} disabled={submitting}
            className="px-5 py-2 text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 rounded disabled:bg-gray-300">
            {submitting ? "시작 중..." : "🎲 Queue 생성 시작 →"}
          </button>
          <a href={`/api/agents/pipeline/${detail._id}/export?stage=curate`}
            className="px-4 py-2 text-sm font-semibold bg-teal-100 text-teal-800 hover:bg-teal-200 rounded">
            ⬇ Art JSON
          </a>
        </div>
      </div>
    );
  }

  // ── Stage: queue_running ──
  if (stage === "queue_running") {
    return (
      <div>
        <h3 className="mb-2 text-sm font-semibold text-indigo-900">🎲 Queue 생성 진행 중</h3>
        <p className="text-xs text-gray-600 mb-3">
          레벨별 큐 생성 + 난이도 매칭(시드스윕 — purpose_type 등급에 맞을 때까지). 보통 수십초~수분.
        </p>
        <p className="text-xs text-gray-400 py-12 text-center">처리 중... (자동 갱신 5s)</p>
      </div>
    );
  }

  // ── Stage: queue_done — 난이도 매칭 결과 + 다음 Field ──
  if (stage === "queue_done") {
    const qs = detail.queue_summary;
    const matched = qs?.results?.filter((r) => r.matched).length ?? 0;
    return (
      <div>
        <h3 className="text-sm font-semibold text-violet-900 mb-3">🎲 Queue 완료 — 다음: 🧩 Field</h3>
        {qs && (
          <div className="grid grid-cols-3 gap-3 mb-4 text-xs">
            <div className="rounded bg-violet-50 p-2 text-center"><div className="text-[10px] text-gray-600">생성</div><div className="text-lg font-bold text-violet-700">{qs.generated}</div></div>
            <div className="rounded bg-emerald-50 p-2 text-center"><div className="text-[10px] text-gray-600">난이도 매칭</div><div className="text-lg font-bold text-emerald-700">{matched}/{qs.generated}</div></div>
            <div className="rounded bg-red-50 p-2 text-center"><div className="text-[10px] text-gray-600">실패</div><div className="text-lg font-bold text-red-700">{qs.failed}</div></div>
          </div>
        )}
        {qs?.results && qs.results.length > 0 && (
          <div className="mb-4 max-h-48 overflow-auto rounded border border-gray-100">
            <table className="w-full text-[11px]">
              <thead className="bg-gray-100 sticky top-0"><tr>
                <th className="px-2 py-1 text-left">Lv</th><th className="px-2 py-1 text-left">목표</th>
                <th className="px-2 py-1 text-left">결과</th><th className="px-2 py-1 text-right">점수</th>
                <th className="px-2 py-1 text-center">매칭</th></tr></thead>
              <tbody>
                {qs.results.map((r) => (
                  <tr key={r.level} className={`border-t ${r.matched ? "" : "bg-amber-50"}`}>
                    <td className="px-2 py-1 font-medium">{r.level}</td>
                    <td className="px-2 py-1">{r.target}</td>
                    <td className="px-2 py-1">{r.grade}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{r.relative?.toFixed(0)}</td>
                    <td className="px-2 py-1 text-center">{r.matched ? "✓" : "≈"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="flex items-center justify-center gap-2 py-2">
          <button onClick={() => onAdvance("field")} disabled={submitting}
            className="px-5 py-2 text-sm font-semibold bg-purple-600 text-white hover:bg-purple-700 rounded disabled:bg-gray-300">
            {submitting ? "시작 중..." : "🧩 Field Complete 시작 →"}
          </button>
          <a href={`/api/agents/pipeline/${detail._id}/export?stage=queue`}
            className="px-4 py-2 text-sm font-semibold bg-violet-100 text-violet-800 hover:bg-violet-200 rounded">
            ⬇ Queue JSON
          </a>
        </div>
      </div>
    );
  }

  // ── Stage: field_running ──
  if (stage === "field_running") {
    return (
      <div>
        <h3 className="mb-2 text-sm font-semibold text-purple-900">🧩 Field Complete 진행 중</h3>
        <p className="text-xs text-gray-600 mb-3">
          field_complete_levels.py watcher 실행. 기믹 배치 + ×10 정합 + score 계산.
          preset=<code>{detail.gimmick_preset}</code>. 보통 1~5분.
        </p>
        <p className="text-xs text-gray-400 py-12 text-center">처리 중... (자동 갱신 5s)</p>
      </div>
    );
  }

  // ── Stage: field_done / download / done ──
  if (stage === "field_done" || stage === "download" || stage === "done") {
    const totals = detail.fc_totals;
    const sum = detail.fc_results_summary || [];
    return (
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-emerald-900">
            🧩 Field Complete 완료 — 다음: ⬇ 다운로드
          </h3>
          {stage === "field_done" && (
            <button onClick={() => onAdvance("retry_field")} disabled={submitting}
              className="text-xs px-3 py-1.5 bg-amber-100 hover:bg-amber-200 rounded">
              🔄 재실행
            </button>
          )}
        </div>
        {totals && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-xs">
            <div className="rounded bg-emerald-50 p-2 text-center">
              <div className="text-[10px] text-gray-600">OK / Fail</div>
              <div className="text-lg font-bold text-emerald-700">{totals.ok}<span className="text-red-600">/{totals.fail}</span></div>
            </div>
            <div className="rounded bg-amber-50 p-2 text-center">
              <div className="text-[10px] text-gray-600">Escalated</div>
              <div className="text-lg font-bold text-amber-700">{totals.escalated}</div>
            </div>
            <div className="rounded bg-blue-50 p-2 text-center">
              <div className="text-[10px] text-gray-600">avg score</div>
              <div className="text-lg font-bold text-blue-700">{totals.avg_score?.toFixed(3)}</div>
            </div>
            <div className="rounded bg-fuchsia-50 p-2 text-center">
              <div className="text-[10px] text-gray-600">FC job id</div>
              <div className="text-[10px] font-mono text-fuchsia-700">{detail.field_complete_job?.job_id?.slice(-8)}</div>
            </div>
          </div>
        )}
        {sum.length > 0 && (
          <div className="mb-4">
            <h4 className="text-xs font-semibold text-gray-700 mb-2">샘플 (상위 5)</h4>
            <table className="w-full text-[11px]">
              <thead className="bg-gray-100">
                <tr><th className="px-2 py-1 text-left">Lv</th><th className="px-2 py-1 text-right">score</th>
                  <th className="px-2 py-1 text-right">balloons</th><th className="px-2 py-1 text-right">gimmicks</th>
                  <th className="px-2 py-1 text-left">types</th></tr>
              </thead>
              <tbody>
                {sum.map((r) => (
                  <tr key={r.level_number} className="border-t">
                    <td className="px-2 py-1 font-medium">{r.level_number}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{r.score?.toFixed(3)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{r.balloons}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{r.gimmicks}</td>
                    <td className="px-2 py-1 text-gray-600 truncate max-w-[200px]" title={r.gimmick_types?.join(", ")}>
                      {r.gimmick_types?.join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="text-center py-4">
          {detail.field_complete_job?.job_id && (
            <a href={`/api/agents/field-complete/${detail.field_complete_job.job_id}/export?force=1`}
               className="inline-block px-5 py-2 text-sm font-semibold bg-emerald-600 text-white hover:bg-emerald-700 rounded">
              ⬇ BalloonFlow Importer ZIP 다운로드
            </a>
          )}
        </div>
      </div>
    );
  }

  // ── Stage: failed ──
  if (stage === "failed") {
    return (
      <div className="text-center py-12">
        <h3 className="text-base font-semibold text-red-900 mb-2">✗ 실패</h3>
        <p className="text-xs text-red-700 mb-4">{detail.error || "(원인 미상)"}</p>
        <button onClick={() => onAdvance("retry_field")} disabled={submitting}
          className="px-5 py-2 text-sm bg-amber-100 hover:bg-amber-200 rounded">
          🔄 Field 재시도
        </button>
      </div>
    );
  }

  return <p className="text-center text-gray-400 py-12">stage: {stage}</p>;
}

interface BalloonInfo { row: number; col: number; color: number; life?: number; }
interface GimmickInfo {
  type: string;
  row?: number;
  col?: number;
  cells?: unknown[];
  size?: [number, number];
  hidden_color?: number;
  color?: number;
  // v1.2.3 신규 메타
  mode?: string;            // Iron_Wall: bl_outline / pf_wall
  block_size?: [number, number]; // Frozen_Layer
  counter?: number;         // Frozen_Layer
  box_size?: [number, number];   // Target_Box
  target_count?: number;    // Target_Box
  per_target_life?: number; // Target_Box
  length?: number;          // Barricade
  life?: number;
  sparse?: boolean;         // Target_Box
}

interface CandidateInfo {
  seed_offset: number;
  score: number;
  score_dims?: Record<string, number>;
  gimmicks?: GimmickInfo[];
  field_analysis?: { total_darts?: number; color_darts?: Record<string, number>; metaphor_preservation_score?: number; field_rows?: number; field_columns?: number; };
}

interface JobDetailRow {
  level_number: number;
  ok: boolean;
  score?: number;
  score_dims?: Record<string, number>;
  balloons?: BalloonInfo[];
  gimmicks?: GimmickInfo[];
  field_analysis?: {
    total_darts?: number;
    color_darts?: Record<string, number>;
    gimmick_life?: Record<string, number>;
    metaphor_preservation_score?: number;
    field_rows?: number;
    field_columns?: number;
    placement_violations?: string[];
    hp_visual_gap_warnings?: string[];
  };
  warnings?: string[];
  error?: string;
  errors?: string[];
  escalated?: boolean;
  color_distribution_auto?: boolean;
  normalized_purpose?: string;
  placement_violations?: string[];
  all_candidates?: CandidateInfo[];
  candidates_meta?: { n_tried?: number; n_ok?: number; score_range?: [number, number]; };
}

interface JobDetail {
  _id: string;
  status: string;
  csv_source: string;
  totals?: { ok: number; fail: number; escalated: number; avg_score: number };
  results?: JobDetailRow[];
  input_images?: { level_number?: number; image_base64?: string }[];
  csv_row_gimmicks?: Record<string, {
    bl_metaphor?: string;
    field: Record<string, number>;
    queue: Record<string, number>;
  }>;
}

// CSV gimmick 키 → 짧은 표시명 (queue 컬럼 안 + tooltip 용)
const GIMMICK_SHORT_LABEL: Record<string, string> = {
  // field
  gimmick_pinata: "Wood", gimmick_pin: "Bar", gimmick_surprise: "HBal",
  gimmick_wall: "Wall", gimmick_pinata_box: "Box", gimmick_ice: "Frozen",
  gimmick_curtain: "Curt", gimmick_snake: "Snake",
  // queue
  gimmick_hidden: "Hdn", gimmick_chain: "Link", gimmick_glass_pipe: "GPipe",
  gimmick_spawner_o: "Pipe", gimmick_spawner_t: "STube",
  gimmick_frozen_dart: "FDart", gimmick_lock_key: "Lock",
};

function formatCsvGimmicks(g: Record<string, number>): string {
  return Object.entries(g)
    .map(([k, v]) => `${GIMMICK_SHORT_LABEL[k] ?? k}×${v}`)
    .join(" ");
}

function LevelGridSvg({ row, size = "sm", pixelMode = false }: { row: JobDetailRow; size?: "sm" | "lg"; pixelMode?: boolean }) {
  const balloons = row.balloons || [];
  const gimmicks = row.gimmicks || [];
  const fa = row.field_analysis || {};
  // field dimensions
  let rows = fa.field_rows ?? 0;
  let cols = fa.field_columns ?? 0;
  if (!rows || !cols) {
    // balloons에서 추정
    for (const b of balloons) {
      if (b.row + 1 > rows) rows = b.row + 1;
      if (b.col + 1 > cols) cols = b.col + 1;
    }
  }
  if (!rows || !cols) return <span className="text-gray-300 text-[10px]">no grid</span>;
  const pxSize = size === "lg" ? 360 : 80;
  const cellPx = Math.min(pxSize / cols, pxSize / rows);
  const w = cellPx * cols;
  const h = cellPx * rows;
  const r = 0.42;  // balloon radius (cell unit)

  // Gimmick 셀 lookup
  const gimmickAt: Record<string, { type: string; meta?: string }> = {};
  for (const g of gimmicks) {
    const cells: [number, number][] = [];
    if (g.cells) {
      for (const c of g.cells) {
        if (Array.isArray(c) && c.length >= 2 && typeof c[0] === "number" && typeof c[1] === "number") {
          cells.push([c[0] as number, c[1] as number]);
        }
      }
    } else if (typeof g.row === "number" && typeof g.col === "number") {
      cells.push([g.row, g.col]);
    }
    for (const [rr, cc] of cells) {
      gimmickAt[`${rr},${cc}`] = { type: g.type, meta: g.type === "Hidden_Balloon" ? String(g.hidden_color ?? "") : undefined };
    }
  }

  return (
    <svg width={w} height={h} viewBox={`0 0 ${cols} ${rows}`}
      style={{ background: "#fafafa", border: "1px solid #ddd" }}>
      {/* 풍선 — pixelMode면 사각 셀, 아니면 원 (BalloonFlow 게임 스타일) */}
      {balloons.map((b, i) => (
        pixelMode ? (
          <rect key={`b${i}`} x={b.col} y={b.row} width={1} height={1}
            fill={colorHex(b.color)} stroke="none" />
        ) : (
          <circle key={`b${i}`} cx={b.col + 0.5} cy={b.row + 0.5} r={r}
            fill={colorHex(b.color)} stroke="#333" strokeWidth="0.04" />
        )
      ))}
      {/* 기믹 오버레이 */}
      {gimmicks.map((g, gi) => {
        const cells: [number, number][] = [];
        if (g.cells) {
          for (const c of g.cells) {
            if (Array.isArray(c) && c.length >= 2 && typeof c[0] === "number" && typeof c[1] === "number") {
              cells.push([c[0] as number, c[1] as number]);
            }
          }
        } else if (typeof g.row === "number" && typeof g.col === "number") {
          cells.push([g.row, g.col]);
        }
        return cells.map(([rr, cc], i) => {
          const key = `g${gi}_${i}`;
          if (g.type === "Iron_Wall") {
            return <rect key={key} x={cc} y={rr} width={1} height={1} fill="rgba(80,80,80,0.85)" stroke="#222" strokeWidth="0.05" />;
          }
          if (g.type === "Frozen_Layer") {
            return <rect key={key} x={cc + 0.05} y={rr + 0.05} width={0.9} height={0.9} fill="rgba(120,200,250,0.45)" stroke="#3AA5DD" strokeWidth="0.05" />;
          }
          if (g.type === "Hidden_Balloon") {
            return (
              <g key={key}>
                <circle cx={cc + 0.5} cy={rr + 0.5} r={r} fill="#aaa" stroke="#333" strokeWidth="0.04" />
                <text x={cc + 0.5} y={rr + 0.7} fontSize="0.65" textAnchor="middle" fill="white" fontWeight="bold">?</text>
              </g>
            );
          }
          if (g.type === "Wooden_Board") {
            return <rect key={key} x={cc + 0.05} y={rr + 0.05} width={0.9} height={0.9} fill="#8B5A2B" stroke="#5D3A1A" strokeWidth="0.06" />;
          }
          if (g.type === "Target_Box") {
            return (
              <g key={key}>
                <rect x={cc + 0.1} y={rr + 0.1} width={0.8} height={0.8} fill="#FFE4B5" stroke="#FF6B6B" strokeWidth="0.1" />
                <circle cx={cc + 0.5} cy={rr + 0.5} r={0.2} fill="#FF6B6B" />
              </g>
            );
          }
          if (g.type === "Barricade") {
            return <polygon key={key} points={`${cc+0.5},${rr+0.1} ${cc+0.9},${rr+0.9} ${cc+0.1},${rr+0.9}`} fill="#444" stroke="#000" strokeWidth="0.05" />;
          }
          // 기타
          return <rect key={key} x={cc + 0.1} y={rr + 0.1} width={0.8} height={0.8} fill="rgba(255,0,255,0.4)" stroke="#900" strokeWidth="0.05" />;
        });
      })}
    </svg>
  );
}

type QueueStatus = {
  total: number;
  withQueue: number;
  withoutQueue: number;
  levels: Array<{ level_number: number; hasQueue: boolean; hasFieldMap: boolean; hasDesignerRow: boolean }>;
};

function JobDetailModal({ jobId, detail, loading, onClose }:
  { jobId: string; detail: unknown; loading: boolean; onClose: () => void }) {
  const d = detail as JobDetail | null;
  const [expandedLv, setExpandedLv] = useState<number | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [queueStatusError, setQueueStatusError] = useState<string>("");
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState<{ generated: number; failed: number; duration_sec: number } | null>(null);

  // 모달 진입 시 queue-status fetch
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await fetch(`/api/agents/field-complete/${jobId}/queue-status`);
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
        if (!cancelled) { setQueueStatus(j); setQueueStatusError(""); }
      } catch (e) {
        if (!cancelled) setQueueStatusError((e as Error).message);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [jobId]);

  async function reloadQueueStatus() {
    try {
      const r = await fetch(`/api/agents/field-complete/${jobId}/queue-status`);
      const j = await r.json();
      if (r.ok) setQueueStatus(j);
    } catch {/* swallow */}
  }

  async function handleGenerateQueues(force = false) {
    if (generating) return;
    setGenerating(true);
    setGenResult(null);
    try {
      const r = await fetch(`/api/agents/field-complete/${jobId}/generate-queues`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force }),
      });
      const j = await r.json();
      if (!r.ok || !j.ok) throw new Error(j.error || `HTTP ${r.status}`);
      setGenResult({ generated: j.generated, failed: (j.failed || []).length, duration_sec: j.duration_sec });
      await reloadQueueStatus();
    } catch (e) {
      setGenResult(null);
      alert(`Queue 생성 실패: ${(e as Error).message}`);
    } finally {
      setGenerating(false);
    }
  }

  const allQueuesReady = !!queueStatus && queueStatus.withoutQueue === 0 && queueStatus.total > 0;
  const someEligible = !!queueStatus && queueStatus.withoutQueue > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-6xl overflow-hidden rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b bg-emerald-50 px-5 py-3">
          <div>
            <h2 className="text-sm font-semibold text-emerald-900">🧩 필드완성 job 상세</h2>
            <p className="text-[11px] text-gray-500">
              id: {jobId} · {d?.csv_source || "—"}
            </p>
            {queueStatus && (
              <p className="mt-0.5 text-[11px]">
                <span className="text-gray-600">Queue: </span>
                <span className={allQueuesReady ? "font-semibold text-emerald-700" : "font-semibold text-amber-700"}>
                  {queueStatus.withQueue}/{queueStatus.total} 생성됨
                </span>
                {!allQueuesReady && <span className="ml-1 text-gray-500">({queueStatus.withoutQueue}개 미생성)</span>}
              </p>
            )}
            {queueStatusError && <p className="text-[11px] text-red-600">queue-status: {queueStatusError}</p>}
            {genResult && (
              <p className="mt-0.5 text-[11px] text-blue-700">
                ✓ Queue 생성 완료 — 성공 {genResult.generated} / 실패 {genResult.failed} ({genResult.duration_sec?.toFixed(1) ?? "—"}s)
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {/* Queue 생성 버튼 — 미생성 있을 때 활성 */}
            {someEligible && (
              <button
                disabled={generating}
                onClick={() => handleGenerateQueues(false)}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {generating ? "🎲 Queue 생성 중..." : `🎲 Queue 생성 (${queueStatus!.withoutQueue}개)`}
              </button>
            )}
            {/* 다운로드 — Queue 모두 준비됐을 때만 활성 */}
            {allQueuesReady ? (
              <a href={`/api/agents/field-complete/${jobId}/export`}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700">
                ⬇ BalloonFlow Importer 다운로드 (zip)
              </a>
            ) : (
              <button
                disabled
                title={queueStatus
                  ? `${queueStatus.withoutQueue}개 레벨 Queue 미생성. 먼저 [🎲 Queue 생성] 클릭`
                  : "queue 상태 확인 중..."}
                className="cursor-not-allowed rounded-md bg-gray-300 px-3 py-1.5 text-xs font-medium text-gray-500"
              >
                ⬇ 다운로드 (Queue 생성 후 활성)
              </button>
            )}
            {/* 강제 다운로드 — 단순 BuildHolders fallback */}
            {!allQueuesReady && queueStatus && (
              <a href={`/api/agents/field-complete/${jobId}/export?force=1`}
                title="Queue 미생성 무시. Unity가 단순 BuildHolders 알고리즘으로 큐 자동 생성."
                className="rounded-md border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50">
                강제 다운로드
              </a>
            )}
            <button onClick={onClose}
              className="rounded-md bg-gray-200 px-3 py-1.5 text-xs hover:bg-gray-300">✕ 닫기</button>
          </div>
        </div>
        <div className="max-h-[78vh] overflow-y-auto px-5 py-4">
          {loading && <p className="text-sm text-gray-400">불러오는 중...</p>}
          {!loading && d && (
            <>
              <div className="mb-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="rounded bg-emerald-50 p-2"><span className="text-gray-600">OK / Fail</span><br /><span className="text-lg font-bold text-emerald-700">{d.totals?.ok}</span> / <span className="text-red-600">{d.totals?.fail}</span></div>
                <div className="rounded bg-amber-50 p-2"><span className="text-gray-600">Escalated</span><br /><span className="text-lg font-bold text-amber-700">{d.totals?.escalated}</span></div>
                <div className="rounded bg-blue-50 p-2"><span className="text-gray-600">평균 점수</span><br /><span className="text-lg font-bold text-blue-700">{d.totals?.avg_score?.toFixed(3)}</span></div>
                <div className="rounded bg-gray-50 p-2"><span className="text-gray-600">총 row</span><br /><span className="text-lg font-bold">{d.results?.length ?? 0}</span></div>
              </div>
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-2 py-1 text-center w-[90px]">preview</th>
                    <th className="px-2 py-1 text-left">lv</th>
                    <th className="px-2 py-1 text-left">OK</th>
                    <th className="px-2 py-1 text-right">score</th>
                    <th className="px-2 py-1 text-right">mod10</th>
                    <th className="px-2 py-1 text-right">meta</th>
                    <th className="px-2 py-1 text-right">hard</th>
                    <th className="px-2 py-1 text-right">debut</th>
                    <th className="px-2 py-1 text-right">queue</th>
                    <th className="px-2 py-1 text-right">balloons</th>
                    <th className="px-2 py-1 text-right">gimmicks</th>
                    <th className="px-2 py-1 text-right">darts</th>
                    <th className="px-2 py-1 text-left">field gimmick</th>
                    <th className="px-2 py-1 text-left">queue gimmick (CSV)</th>
                    <th className="px-2 py-1 text-left">warn</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.results || []).map((r, i) => {
                    const dims = r.score_dims || {};
                    const fa = r.field_analysis || {};
                    const gtypes = (r.gimmicks || []).map((g) => g.type).filter((v, i, a) => a.indexOf(v) === i);
                    // CSV 명시 큐 기믹 (gimmick_hidden, gimmick_chain 등)
                    const csvG = d.csv_row_gimmicks?.[String(r.level_number)];
                    const csvQueueGim = csvG?.queue || {};
                    const csvFieldGim = csvG?.field || {};
                    const queueGimText = formatCsvGimmicks(csvQueueGim);
                    const csvFieldText = formatCsvGimmicks(csvFieldGim);
                    const csvMetaphor = csvG?.bl_metaphor || "";
                    const isExpanded = expandedLv === r.level_number;
                    return (
                      <>
                        <tr key={`r${i}`} className={`border-t cursor-pointer ${r.ok ? "" : "bg-red-50"} ${isExpanded ? "bg-emerald-50" : ""}`}
                          onClick={() => r.ok && setExpandedLv(isExpanded ? null : r.level_number)}>
                          <td className="px-1 py-1 text-center">
                            {r.ok && (r.balloons?.length ?? 0) > 0 ? (
                              <div className="inline-block" title="클릭해서 확대">
                                <LevelGridSvg row={r} size="sm" />
                              </div>
                            ) : <span className="text-gray-300">—</span>}
                          </td>
                          <td className="px-2 py-1 font-medium">{r.level_number}</td>
                          <td className="px-2 py-1">{r.ok ? "✓" : "✗"}</td>
                          <td className={`px-2 py-1 text-right tabular-nums ${(r.score ?? 0) >= 0.85 ? "text-emerald-700 font-medium" : "text-amber-700"}`}>{(r.score ?? 0).toFixed(3)}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{(dims.mod10_compliance ?? 0).toFixed(2)}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{(dims.metaphor_score ?? 0).toFixed(2)}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{(dims.hard_rule_pass ?? 0).toFixed(2)}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{(dims.debut_compliance ?? 0).toFixed(2)}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{(dims.queue_alignment ?? 0).toFixed(2)}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{r.balloons?.length ?? 0}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{r.gimmicks?.length ?? 0}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{fa.total_darts ?? "—"}</td>
                          <td className="max-w-[180px] truncate px-2 py-1 text-gray-600"
                              title={`actual: ${gtypes.join(", ") || "—"}\nCSV req: ${csvFieldText || "—"}${csvMetaphor ? `\nmetaphor: ${csvMetaphor}` : ""}`}>
                            {gtypes.length === 0 ? "—" : gtypes.join(", ")}
                          </td>
                          <td className="max-w-[180px] truncate px-2 py-1 text-blue-700"
                              title={`CSV 명시 큐 기믹: ${queueGimText || "(none)"}${csvMetaphor ? `\nbl_metaphor: ${csvMetaphor}` : ""}`}>
                            {queueGimText || <span className="text-gray-300">—</span>}
                          </td>
                          <td className="max-w-[160px] truncate px-2 py-1 text-amber-700" title={(r.warnings || []).join(" | ") || r.error || ""}>
                            {r.ok ? (r.warnings?.length ? `⚠ ${r.warnings.length}` : "") : `✗ ${r.error || ""}`}
                          </td>
                        </tr>
                        {isExpanded && r.ok && (
                          <tr key={`e${i}`} className="border-t bg-emerald-50/50">
                            <td colSpan={15} className="p-4">
                              {(() => {
                                const inputImg = d.input_images?.find(im => im.level_number === r.level_number)?.image_base64;
                                const fromImage = !!inputImg;
                                return (
                              <div className="flex gap-4">
                                {/* 입력 이미지 (이미지 업로드 케이스만) */}
                                {fromImage && (
                                  <div className="flex flex-col items-center">
                                    <div className="mb-1 text-[10px] font-semibold text-amber-700">원본 입력 이미지</div>
                                    <img src={inputImg} alt="input"
                                      style={{
                                        width: 360, height: "auto", maxHeight: 360,
                                        imageRendering: "pixelated",
                                        border: "1px solid #ddd",
                                      }} />
                                  </div>
                                )}
                                <div className="flex flex-col items-center">
                                  <div className="mb-1 text-[10px] font-semibold text-emerald-700">
                                    {fromImage ? "결과 (픽셀 모드, 풍선+기믹)" : "결과 (BalloonFlow 풍선 스타일)"}
                                  </div>
                                  <LevelGridSvg row={r} size="lg" pixelMode={fromImage} />
                                </div>
                                <div className="flex-1 text-[11px] text-gray-700">
                                  <div className="mb-2 font-semibold text-emerald-800">Lv {r.level_number} 상세</div>
                                  <div className="grid grid-cols-2 gap-1">
                                    <div><span className="text-gray-500">field:</span> {fa.field_rows}×{fa.field_columns}</div>
                                    <div><span className="text-gray-500">balloons:</span> {r.balloons?.length}</div>
                                    <div><span className="text-gray-500">gimmicks:</span> {r.gimmicks?.length} ({gtypes.join(", ") || "none"})</div>
                                    <div><span className="text-gray-500">total_darts:</span> {fa.total_darts}</div>
                                    <div className="col-span-2"><span className="text-gray-500">color_darts:</span> {Object.entries(fa.color_darts || {}).map(([k, v]) => `${k}:${v}`).join("  ")}</div>
                                    <div className="col-span-2"><span className="text-gray-500">gimmick_life:</span> {Object.entries(fa.gimmick_life || {}).map(([k, v]) => `${k}:${v}`).join(", ") || "—"}</div>
                                    <div className="col-span-2"><span className="text-gray-500">metaphor_score:</span> {fa.metaphor_preservation_score?.toFixed(3) ?? "—"}</div>
                                  </div>
                                  {r.warnings?.length ? (
                                    <div className="mt-2 rounded bg-amber-50 p-2 text-amber-700">
                                      <div className="font-semibold">⚠ warnings:</div>
                                      <ul className="ml-3 list-disc">{r.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                                    </div>
                                  ) : null}
                                  {(r.placement_violations?.length || r.field_analysis?.placement_violations?.length) ? (
                                    <div className="mt-2 rounded bg-red-50 p-2 text-red-700">
                                      <div className="font-semibold">🚫 placement_violations (HR 7/8/12-16):</div>
                                      <ul className="ml-3 list-disc">
                                        {(r.placement_violations || r.field_analysis?.placement_violations || []).map((v, i) => <li key={i}>{v}</li>)}
                                      </ul>
                                    </div>
                                  ) : null}
                                  {r.field_analysis?.hp_visual_gap_warnings?.length ? (
                                    <div className="mt-2 rounded bg-orange-50 p-2 text-orange-700">
                                      <div className="font-semibold">📐 HP/visual gap (§12):</div>
                                      <ul className="ml-3 list-disc">{r.field_analysis.hp_visual_gap_warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                                    </div>
                                  ) : null}
                                  {/* n=10 candidate picker */}
                                  {r.all_candidates && r.all_candidates.length > 1 ? (
                                    <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 p-2">
                                      <div className="mb-2 flex items-center justify-between">
                                        <div className="text-xs font-semibold text-indigo-900">
                                          🎲 n={r.all_candidates.length} 후보 (score {r.candidates_meta?.score_range?.[0]?.toFixed(3)}~{r.candidates_meta?.score_range?.[1]?.toFixed(3)})
                                        </div>
                                        <span className="text-[10px] text-indigo-600">★ = best pick (현재 채택)</span>
                                      </div>
                                      <div className="grid grid-cols-5 gap-2">
                                        {r.all_candidates
                                          .slice()
                                          .sort((a, b) => (b.score || 0) - (a.score || 0))
                                          .map((c, ci) => {
                                            const candRow: JobDetailRow = {
                                              level_number: r.level_number,
                                              ok: true,
                                              balloons: r.balloons,
                                              gimmicks: c.gimmicks,
                                              field_analysis: c.field_analysis as JobDetailRow['field_analysis'],
                                            };
                                            return (
                                              <div key={ci} className={`flex flex-col items-center rounded border-2 bg-white p-1 ${ci === 0 ? "border-amber-400 ring-2 ring-amber-200" : "border-gray-200"}`}>
                                                <LevelGridSvg row={candRow} size="sm" />
                                                <div className="mt-1 text-[10px] font-semibold text-gray-700">
                                                  {ci === 0 ? "★ " : ""}seed{c.seed_offset}
                                                </div>
                                                <div className={`text-[10px] tabular-nums ${(c.score || 0) >= 0.85 ? "text-emerald-700 font-semibold" : "text-amber-700"}`}>
                                                  {(c.score || 0).toFixed(3)}
                                                </div>
                                                <div className="text-[9px] text-gray-500">
                                                  meta={(c.score_dims?.metaphor_score || 0).toFixed(2)}
                                                </div>
                                              </div>
                                            );
                                          })}
                                      </div>
                                    </div>
                                  ) : null}

                                  {/* v1.2.3 신규 기믹 메타 */}
                                  {r.gimmicks?.some(g => g.mode || g.block_size || g.target_count || g.length) ? (
                                    <div className="mt-2 rounded bg-blue-50 p-2 text-blue-800">
                                      <div className="font-semibold">📋 v1.2.3 메타:</div>
                                      <ul className="ml-3 list-disc text-[10px]">
                                        {r.gimmicks.map((g, i) => {
                                          const parts: string[] = [];
                                          if (g.mode) parts.push(`mode=${g.mode}`);
                                          if (g.block_size) parts.push(`block_size=${g.block_size.join("×")}`);
                                          if (g.counter !== undefined) parts.push(`counter=${g.counter}`);
                                          if (g.box_size) parts.push(`box=${g.box_size.join("×")}`);
                                          if (g.target_count) parts.push(`targets=${g.target_count}`);
                                          if (g.per_target_life) parts.push(`per_target_life=${g.per_target_life}`);
                                          if (g.length) parts.push(`length=${g.length}`);
                                          if (g.sparse !== undefined) parts.push(`sparse=${g.sparse}`);
                                          if (!parts.length) return null;
                                          return <li key={i}>{g.type}: {parts.join(", ")}</li>;
                                        }).filter(Boolean)}
                                      </ul>
                                    </div>
                                  ) : null}
                                  <div className="mt-2 flex gap-2 text-[10px]">
                                    <LegendDot color="#FC6AAF" label="c1 HotPink" />
                                    <LegendDot color="#50E8F6" label="c2 Cyan" />
                                    <LegendDot color="#FED555" label="c4 Yellow" />
                                    <LegendDot color="#73FE66" label="c5 Green" />
                                    <LegendDot color="rgba(80,80,80,0.85)" label="Iron Wall" shape="rect" />
                                    <LegendDot color="rgba(120,200,250,0.6)" label="Frozen" shape="rect" />
                                    <LegendDot color="#aaa" label="Hidden ?" />
                                    <LegendDot color="#8B5A2B" label="Wooden" shape="rect" />
                                    <LegendDot color="#FF6B6B" label="Target" />
                                    <LegendDot color="#444" label="Barricade" shape="tri" />
                                  </div>
                                </div>
                              </div>
                                );
                              })()}
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function LegendDot({ color, label, shape = "circle" }: { color: string; label: string; shape?: "circle" | "rect" | "tri" }) {
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      <svg width="12" height="12" viewBox="0 0 1 1">
        {shape === "circle" && <circle cx="0.5" cy="0.5" r="0.42" fill={color} stroke="#333" strokeWidth="0.05" />}
        {shape === "rect" && <rect x="0.05" y="0.05" width="0.9" height="0.9" fill={color} stroke="#333" strokeWidth="0.05" />}
        {shape === "tri" && <polygon points="0.5,0.1 0.9,0.9 0.1,0.9" fill={color} stroke="#333" strokeWidth="0.05" />}
      </svg>
      <span className="text-gray-600">{label}</span>
    </span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-600">{label}</span>
      {children}
    </label>
  );
}

function Card({ title, value, hint, tone = "gray" }:
  { title: string; value: string; hint?: string; tone?: "gray" | "amber" | "red" | "emerald" }) {
  const toneClass = {
    gray: "text-gray-900",
    amber: "text-amber-700",
    red: "text-red-600",
    emerald: "text-emerald-700",
  }[tone];
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <div className="text-xs text-gray-500">{title}</div>
      <div className={`mt-1 text-2xl font-bold ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-gray-400">{hint}</div>}
    </div>
  );
}

function DistroBox({ title, rows }: { title: string; rows: { label: string; count: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-xs text-gray-400">데이터 없음</p>
      ) : (
        <div className="space-y-1.5">
          {rows.slice(0, 10).map((r) => (
            <div key={r.label} className="flex items-center gap-2 text-xs">
              <span className="w-20 shrink-0 truncate text-gray-600">{r.label}</span>
              <div className="relative h-4 flex-1 rounded bg-gray-100">
                <div className="h-full rounded bg-indigo-400"
                  style={{ width: `${(r.count / max) * 100}%` }} />
              </div>
              <span className="w-12 text-right tabular-nums text-gray-700">{r.count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
