// BalloonFlow Queue Generator — TypeScript 1:1 port from MapMakerController.cs
//
// Source of truth: E:/BalloonFlow/BallonFlow_Git/BalloonFlow/Assets/1.Scripts/MapMakerController.cs
//   GenerateQueue (line 3793)
//   DecomposeMagazinesV2 (line 4142)
//   BuildAllowedCaps / BuildCapWeights (line 4047 / 4081)
//   LayoutByDepth / EnforceGridConsecutiveLimit / EnforceFirst3RowsDepthGuard (line 4429 / 4480 / 4302)
//   CalcColorDepth / CalcColorDependency / CalcDifficultyScore (line 4626 / 4556 / 4700)
//
// Spec ref: BalloonFlow_큐생성기_명세.md v3 (2026-05-14) — but weights use v2 values
// to match shipped MapEditor (authoritative). v5.1 swap is data-only.
//
// Used by:
//   - tools/projecthub-web/src/app/api/levels/[id]/export/route.ts
//   - tools/pixelforge-web/src/app/api/queue/generate/route.ts (planned)

export type Difficulty = "tutorial" | "rest" | "normal" | "hard" | "super_hard" | "intro";

export type Cells = number[][];                   // [row][col] = palette_id (>0) or 0/-1 (empty)

export type FieldAnalysis = {
  color_counts: Record<number, number>;
  color_darts: Record<number, number>;            // 10배수 올림
  color_depth: Record<number, number>;            // 0 / 1 / 2
  color_dependency: Record<number, number[]>;
  total_darts: number;
  outermost_colors: number[];
  rail_capacity: number;
  dart_capacity_max: number;
};

export type Holder = { color: number; mag: number };

export type DifficultyScore = {
  absolute: number;
  max_possible: number;
  relative_pct: number;
  grade: "easy" | "normal" | "hard" | "super_hard" | "trivial";
};

export type ValidationReport = {
  decomposed_total: number;
  color_dart_match: boolean;
  holder_count: number;
  all_mags_in_set: boolean;
  all_under_max: boolean;
  cap20_backbone_pass: boolean;
  first_rows_depth_guard: boolean;
  cap_kinds_count: number;
  cap20_ratio: number;
  avg_ammo_per_holder: number;
  retries: number;
  hard_fail_reasons?: string[];
};

// §5 STEP C 큐 기믹 입력 (LD pixelforge_levels.gimmick_*)
export type GimmickCounts = {
  // 큐 기믹 (큐 보관함 단위 적용)
  hidden?: number;        // gimmick_hidden — Hidden Dart Box (Lv11+)
  chain?: number;         // gimmick_chain — Linked Dart Box 총 보관함 수 (Lv21+)
  spawner_t?: number;     // gimmick_spawner_t — Glass Pipe (Lv41+, BL 1.0 SKIP)
  spawner_o?: number;     // gimmick_spawner_o — Pipe (Lv141+, BL 1.0 SKIP)
  frozen_dart?: number;   // gimmick_frozen_dart — Frozen Dart Box (Lv241+)
  lock_key?: number;      // gimmick_lock_key — 1.0 SKIP
  // 필드 기믹 (풍선 단위 적용 — PF 회귀 기반 자동 배치)
  pinata?: number;        // gimmick_pinata — Wooden Board (Lv31+)
  wall?: number;          // gimmick_wall — Iron Wall (Lv121+)
  pin?: number;           // gimmick_pin — Barricade (Lv61+)
  surprise?: number;      // gimmick_surprise — Hidden Balloon (Lv101+)
  pinata_box?: number;    // gimmick_pinata_box — Target Box (Lv161+)
  ice?: number;           // gimmick_ice — Frozen Layer (Lv201+)
  curtain?: number;       // gimmick_curtain — Color Curtain (Lv301+, 1.1+ SKIP)
};

// 필드 기믹 오버레이 — balloon index 기반
export type FieldGimmickOverlay = {
  pinata_balloons: { balloonId: number; life: number }[];        // 풍선 → Pinata 변환
  wall_cells: { row: number; col: number; areaW: number; areaH: number }[];  // 빈 영역 점유
  hidden_balloons: number[];                                      // balloonId 색 숨김
  pinata_box_areas: { row: number; col: number; areaW: number; areaH: number; eggs: { color: number; count: number }[] }[];
  frozen_layer_areas: { row: number; col: number; areaW: number; areaH: number; life: number }[];
  barricade_lines: { positions: { row: number; col: number }[]; color: number; life: number }[];
};

// §5 STEP C 출력 — holder index 기반 오버레이
export type QueueOverlay = {
  hidden_ids: number[];                                    // ?로 숨길 holder index
  linked_groups: { ids: number[]; same_color: boolean }[];  // 연결 묶음
  frozen: { id: number; health: number }[];                // 카운터 기반 동결
  // pipe (Glass Pipe / Pipe) — 1.0 SKIP (필드 모듈 협업 필요)
};

export type StepCValidation = {
  applied: boolean;
  multi_gimmick_pass: boolean;
  hidden_line0_pass: boolean;
  link_n_hidden_pass: boolean;
  chain_adjacency_pass: boolean;     // v3.12 Hard Rule: 묶음 col diff ≤ 1
  chain_cycle_pass: boolean;          // v3.15 Hard Rule: 그룹 의존성 cycle 없음
  hard_fail_reason?: string;
  intro_lv_filter?: keyof GimmickCounts;
  chain_cycle_retries?: number;
};

export type FieldGimmickValidation = {
  applied: boolean;
  pinata_placed: number;
  wall_placed: number;
  hidden_balloons_placed: number;
  pinata_box_placed: number;
  frozen_layer_placed: number;
  barricade_placed: number;
  warnings: string[];
};

export type QueueResult = {
  holders: Holder[];                              // row-major laid out
  queue_columns: number;
  recommended_queue_columns: number;
  field_analysis: FieldAnalysis;
  difficulty_score: DifficultyScore;
  validation: ValidationReport;
  seed: number;
  difficulty: Difficulty;
  overlay?: QueueOverlay;          // §5 STEP C 결과 (gimmickCounts 입력 시)
  step_c_validation?: StepCValidation;
  field_overlay?: FieldGimmickOverlay;  // 필드 기믹 자동 배치 결과
  field_gimmick_validation?: FieldGimmickValidation;
};

// ─── §2-1 — 난이도별 cap 가중치 (C# CAP_WEIGHTS_BASE / CAP_WEIGHTS_REST 그대로) ──
//   diffIdx: 0=Tutorial, 1=Normal/Intro, 2=Hard, 3=SuperHard
//   ※ Rest는 §2-7 cap30 금지 흡수가 base에 적용된 별도 표 사용
const CAP_KEYS: number[] = [10, 20, 30, 40, 50];

const CAP_WEIGHTS_BASE: number[][] = [
  // 10    20    30    40    50
  [0.15, 0.75, 0.02, 0.08, 0.00], // Tutorial (diffIdx 0)
  [0.16, 0.68, 0.02, 0.13, 0.01], // Normal/Intro (diffIdx 1)
  [0.14, 0.71, 0.02, 0.13, 0.00], // Hard (diffIdx 2)
  [0.17, 0.68, 0.03, 0.11, 0.01], // SuperHard (diffIdx 3)
];
const CAP_WEIGHTS_REST: number[] = [0.15, 0.69, 0.00, 0.13, 0.01];

// §2-4 — 앞 50%에 depth 0 비율 (min~max), C# DEPTH0_FRONT_RATIO
const DEPTH0_FRONT_RATIO: number[][] = [
  [0.80, 0.95], // Tutorial/Rest
  [0.40, 0.65], // Normal
  [0.25, 0.45], // Hard
  [0.10, 0.30], // SuperHard
];

// §4-3 — 행/열 연속 max (C# SAME_COLOR_MAX_ROW / COL)
const SAME_COLOR_MAX_ROW: number[] = [1, 2, 3, 4];
const SAME_COLOR_MAX_COL: number[] = [1, 2, 2, 3];

const AVG_CAP = 21;                               // §2-0 PF 평균
const GENERATE_RETRY_MAX = 20;                    // C# 그대로

// ─── PRNG (seeded mulberry32) ───
function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6D2B79F5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

// ─── 유틸 ───
function getDifficultyIndex(d: Difficulty): number {
  switch (d) {
    case "tutorial":
    case "rest":
      return 0;
    case "normal":
    case "intro":
      return 1;
    case "hard":
      return 2;
    case "super_hard":
      return 3;
  }
}

export function getDartCapacityMax(railCapacity: number): number {
  if (railCapacity <= 40) return 30;
  if (railCapacity <= 80) return 40;
  return 50;
}

export function inferRailCapacity(totalDarts: number): number {
  if (totalDarts <= 300) return 40;
  if (totalDarts <= 500) return 80;
  if (totalDarts <= 700) return 120;
  return 160;
}

// §2-3 — queue_columns 자동 추천
export function recommendQueueColumns(holderCount: number, purpose: Difficulty): number {
  let base: number;
  if (holderCount <= 35) base = 3;
  else base = 4;
  if (purpose === "tutorial") return Math.max(2, Math.min(4, base - 1));
  if (purpose === "super_hard") return Math.max(3, Math.min(5, base + 1));
  return base;
}

// §2-8 — BuildAllowedCaps (C# 그대로)
function buildAllowedCaps(
  levelId: number, purpose: Difficulty,
  railCapacity: number, dartCapMax: number,
): Set<number> {
  const caps = new Set<number>([10, 20, 30, 40, 50]);
  if (railCapacity < 80) { caps.delete(40); caps.delete(50); }
  if (railCapacity < 120) caps.delete(50);
  for (const c of [...caps]) if (c > dartCapMax) caps.delete(c);

  // §2-7 cap30 가드
  if (purpose === "tutorial" || purpose === "rest") caps.delete(30);

  // §2-6 cap50 가드
  const pkg = Math.floor((levelId - 1) / 20) + 1;
  let cap50Allowed = true;
  if (pkg < 2) cap50Allowed = false;
  else if (purpose === "tutorial" || purpose === "rest" || purpose === "normal" || purpose === "intro") {
    cap50Allowed = false;
  } else if (pkg >= 11) {
    cap50Allowed = (levelId === 219 || levelId === 249 || levelId === 299);
  }
  if (!cap50Allowed) caps.delete(50);

  // cap20 백본 보장
  caps.add(20);
  return caps;
}

// §2-1 — BuildCapWeights (C# 그대로 — cap20 흡수 + 정규화)
function buildCapWeights(
  diffIdx: number, purpose: Difficulty, allowed: Set<number>,
): Map<number, number> {
  const baseWeights = purpose === "rest"
    ? CAP_WEIGHTS_REST
    : CAP_WEIGHTS_BASE[Math.max(0, Math.min(diffIdx, CAP_WEIGHTS_BASE.length - 1))];

  const w = new Map<number, number>();
  let removed = 0;
  for (let i = 0; i < CAP_KEYS.length; i++) {
    const cap = CAP_KEYS[i];
    const wi = baseWeights[i];
    if (allowed.has(cap)) w.set(cap, wi);
    else removed += wi;
  }
  if (removed > 0) {
    w.set(20, (w.get(20) ?? 0) + removed);
  }
  // 재정규화 (안전장치 — 부동소수 오차 대비)
  let sum = 0;
  for (const v of w.values()) sum += v;
  if (sum > 0) {
    for (const k of [...w.keys()]) w.set(k, w.get(k)! / sum);
  }
  return w;
}

// 가중치 추첨
function weightedRandomPick(values: number[], weights: number[], rng: () => number): number {
  let total = 0;
  for (const w of weights) total += w;
  if (total <= 0) return values[Math.floor(rng() * values.length)];
  const roll = rng() * total;
  let acc = 0;
  for (let i = 0; i < values.length; i++) {
    acc += weights[i];
    if (roll <= acc) return values[i];
  }
  return values[values.length - 1];
}

// §3 STEP A v2 — DecomposeMagazinesV2 (C# 그대로)
function decomposeMagazinesV2(
  colorDarts: number,
  weights: Map<number, number>,
  allowed: Set<number>,
  dartCapMax: number,
  rng: () => number,
): number[] {
  const estimated = Math.max(1, Math.round(colorDarts / AVG_CAP));

  const candidates: number[] = [];
  const candWeights: number[] = [];
  for (const [cap, w] of weights) {
    if (cap > dartCapMax) continue;
    if (!allowed.has(cap)) continue;
    if (w <= 0) continue;
    candidates.push(cap);
    candWeights.push(w);
  }
  if (candidates.length === 0) { candidates.push(20); candWeights.push(1); }

  const result: number[] = [];
  for (let i = 0; i < estimated; i++) {
    result.push(weightedRandomPick(candidates, candWeights, rng));
  }
  balanceToTarget(result, colorDarts, candidates, dartCapMax);
  return result;
}

function findMinIndex(list: number[]): number {
  if (list.length === 0) return -1;
  let idx = 0;
  for (let i = 1; i < list.length; i++) if (list[i] < list[idx]) idx = i;
  return idx;
}
function findMaxIndex(list: number[]): number {
  if (list.length === 0) return -1;
  let idx = 0;
  for (let i = 1; i < list.length; i++) if (list[i] > list[idx]) idx = i;
  return idx;
}

function nextCapUp(current: number, candidates: number[], capMax: number, maxDelta: number): number {
  let best = current;
  for (const c of candidates) {
    if (c <= current) continue;
    if (c > capMax) continue;
    const delta = c - current;
    if (delta > maxDelta) continue;
    if (c > best) best = c;
  }
  return best;
}
function nextCapDown(current: number, candidates: number[], maxDelta: number): number {
  let best = current;
  for (const c of candidates) {
    if (c >= current) continue;
    if (c < 10) continue;
    const delta = current - c;
    if (delta > maxDelta) continue;
    if (c < best || best === current) best = c;
  }
  return best;
}

function balanceToTarget(holders: number[], target: number, candidates: number[], capMax: number): void {
  let safety = 0;
  while (safety++ < 200) {
    let sum = 0;
    for (const h of holders) sum += h;
    const diff = target - sum;
    if (diff === 0) return;

    if (diff > 0) {
      const smallIdx = findMinIndex(holders);
      if (smallIdx >= 0) {
        const cur = holders[smallIdx];
        const next = nextCapUp(cur, candidates, capMax, diff);
        if (next > cur) { holders[smallIdx] = next; continue; }
      }
      let addCap = Math.min(capMax, 20);
      if (!candidates.includes(addCap)) {
        addCap = 20;
        if (!candidates.includes(addCap)) addCap = candidates.length > 0 ? candidates[0] : 10;
      }
      holders.push(addCap);
    } else {
      const bigIdx = findMaxIndex(holders);
      if (bigIdx >= 0) {
        const cur = holders[bigIdx];
        const next = nextCapDown(cur, candidates, -diff);
        if (next >= 10 && next < cur) { holders[bigIdx] = next; continue; }
        if (holders.length > 1) { holders.splice(bigIdx, 1); continue; }
      }
      break;
    }
  }
}

// ─── 4면 스캔: color_depth + color_dependency ───
// C# CalcColorDepth + CalcColorDependency 1:1 포팅
// cells[row][col] — 양수 = palette_id, 0 또는 음수 = 빈 셀
function calcColorDepth(cells: Cells, colorDarts: Record<number, number>): Record<number, number> {
  const rows = cells.length;
  const cols = cells[0]?.length ?? 0;
  const exposureCount: Record<number, number> = {};
  let totalEdges = 0;

  // 상단 (각 col, row 0→max)
  for (let c = 0; c < cols; c++) {
    for (let r = 0; r < rows; r++) {
      const v = cells[r][c];
      if (v != null && v > 0) {
        exposureCount[v] = (exposureCount[v] ?? 0) + 1;
        totalEdges++;
        break;
      }
    }
  }
  // 하단 (각 col, row max→0)
  for (let c = 0; c < cols; c++) {
    for (let r = rows - 1; r >= 0; r--) {
      const v = cells[r][c];
      if (v != null && v > 0) {
        exposureCount[v] = (exposureCount[v] ?? 0) + 1;
        totalEdges++;
        break;
      }
    }
  }
  // 좌측 (각 row, col 0→max)
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const v = cells[r][c];
      if (v != null && v > 0) {
        exposureCount[v] = (exposureCount[v] ?? 0) + 1;
        totalEdges++;
        break;
      }
    }
  }
  // 우측 (각 row, col max→0)
  for (let r = 0; r < rows; r++) {
    for (let c = cols - 1; c >= 0; c--) {
      const v = cells[r][c];
      if (v != null && v > 0) {
        exposureCount[v] = (exposureCount[v] ?? 0) + 1;
        totalEdges++;
        break;
      }
    }
  }

  const depth: Record<number, number> = {};
  for (const ci of Object.keys(colorDarts).map(Number)) {
    const ratio = totalEdges > 0 ? (exposureCount[ci] ?? 0) / totalEdges : 0;
    if (ratio > 0.5) depth[ci] = 0;
    else if (ratio > 0.2) depth[ci] = 1;
    else depth[ci] = 2;
  }
  return depth;
}

function calcColorDependency(cells: Cells, colorDarts: Record<number, number>): Record<number, number[]> {
  const rows = cells.length;
  const cols = cells[0]?.length ?? 0;
  const dep: Record<number, Set<number>> = {};
  for (const c of Object.keys(colorDarts).map(Number)) dep[c] = new Set();

  function processLine(seq: number[]): void {
    for (let i = 0; i < seq.length; i++) {
      const b = seq[i];
      if (!(b in dep)) continue;
      for (let j = 0; j < i; j++) {
        const a = seq[j];
        if (a !== b) dep[b].add(a);
      }
    }
  }
  function collectLine(coords: Array<[number, number]>): number[] {
    const seq: number[] = [];
    for (const [r, c] of coords) {
      const v = cells[r][c];
      if (v != null && v > 0 && !seq.includes(v)) seq.push(v);
    }
    return seq;
  }
  // 상단: col 고정, row 0→max
  for (let c = 0; c < cols; c++) {
    const coords: Array<[number, number]> = [];
    for (let r = 0; r < rows; r++) coords.push([r, c]);
    processLine(collectLine(coords));
  }
  // 하단
  for (let c = 0; c < cols; c++) {
    const coords: Array<[number, number]> = [];
    for (let r = rows - 1; r >= 0; r--) coords.push([r, c]);
    processLine(collectLine(coords));
  }
  // 좌측: row 고정, col 0→max
  for (let r = 0; r < rows; r++) {
    const coords: Array<[number, number]> = [];
    for (let c = 0; c < cols; c++) coords.push([r, c]);
    processLine(collectLine(coords));
  }
  // 우측
  for (let r = 0; r < rows; r++) {
    const coords: Array<[number, number]> = [];
    for (let c = cols - 1; c >= 0; c--) coords.push([r, c]);
    processLine(collectLine(coords));
  }

  const out: Record<number, number[]> = {};
  for (const c of Object.keys(dep).map(Number)) out[c] = [...dep[c]];
  return out;
}

// 필드 분석 (color_darts + depth + dependency + rail_capacity 추정)
export function computeFieldAnalysis(cells: Cells, palette: number[]): FieldAnalysis {
  const rows = cells.length;
  const cols = cells[0]?.length ?? 0;
  const counts: Record<number, number> = {};
  for (const c of palette) counts[c] = 0;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const v = cells[r][c];
      if (v != null && v > 0) counts[v] = (counts[v] ?? 0) + 1;
    }
  }
  const darts: Record<number, number> = {};
  for (const c of palette) {
    const raw = counts[c] ?? 0;
    darts[c] = raw > 0 ? Math.ceil(raw / 10) * 10 : 0;
  }
  const totalDarts = Object.values(darts).reduce((s, v) => s + v, 0);
  const railCapacity = inferRailCapacity(totalDarts);
  const dartCapacityMax = getDartCapacityMax(railCapacity);

  const depth = calcColorDepth(cells, darts);
  const dependency = calcColorDependency(cells, darts);
  const outermost = palette.filter(c => depth[c] === 0);

  return {
    color_counts: counts,
    color_darts: darts,
    color_depth: depth,
    color_dependency: dependency,
    total_darts: totalDarts,
    outermost_colors: outermost,
    rail_capacity: railCapacity,
    dart_capacity_max: dartCapacityMax,
  };
}

// ─── §4-2 LayoutByDepth (C# 1:1) ───
function shuffle<T>(arr: T[], rng: () => number): void {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
}

function layoutByDepth(
  magazines: Holder[], depth: Record<number, number>, diffIdx: number, rng: () => number,
): Holder[] {
  const depth0: Holder[] = [];
  const depth12: Holder[] = [];
  for (const m of magazines) {
    const d = depth[m.color] ?? 0;
    if (d === 0) depth0.push(m);
    else depth12.push(m);
  }
  shuffle(depth0, rng);
  shuffle(depth12, rng);

  const ratioRange = DEPTH0_FRONT_RATIO[Math.max(0, Math.min(diffIdx, DEPTH0_FRONT_RATIO.length - 1))];
  const targetRatio = ratioRange[0] + rng() * (ratioRange[1] - ratioRange[0]);
  const halfCount = Math.floor(magazines.length / 2);
  let frontDepth0Count = Math.round(halfCount * targetRatio);
  frontDepth0Count = Math.min(frontDepth0Count, depth0.length);

  const sorted: Holder[] = [];
  sorted.push(...depth0.slice(0, frontDepth0Count));
  const frontDepth12 = Math.min(halfCount - frontDepth0Count, depth12.length);
  if (frontDepth12 > 0) sorted.push(...depth12.slice(0, frontDepth12));
  if (frontDepth0Count < depth0.length) sorted.push(...depth0.slice(frontDepth0Count));
  if (frontDepth12 < depth12.length) sorted.push(...depth12.slice(frontDepth12));
  return sorted;
}

// ─── §4-2 ViolatesConsecutive (C# 1:1) ───
function violatesConsecutive(
  list: Holder[], cols: number, _rows: number,
  r: number, c: number, maxRow: number, maxCol: number,
): boolean {
  const idx = r * cols + c;
  if (idx >= list.length) return false;
  const color = list[idx].color;

  let rowRun = 1;
  for (let cc = c - 1; cc >= 0; cc--) {
    const id = r * cols + cc;
    if (id >= list.length) break;
    if (list[id].color !== color) break;
    rowRun++;
  }
  if (rowRun > maxRow) return true;

  let colRun = 1;
  for (let rr = r - 1; rr >= 0; rr--) {
    const id = rr * cols + c;
    if (id >= list.length) break;
    if (list[id].color !== color) break;
    colRun++;
  }
  if (colRun > maxCol) return true;
  return false;
}

function enforceGridConsecutiveLimit(list: Holder[], cols: number, maxRow: number, maxCol: number): void {
  if (list.length === 0 || cols <= 0) return;
  const rows = Math.ceil(list.length / cols);
  for (let pass = 0; pass < 2; pass++) {
    for (let i = 0; i < list.length; i++) {
      const c = i % cols;
      const r = Math.floor(i / cols);
      if (violatesConsecutive(list, cols, rows, r, c, maxRow, maxCol)) {
        for (let k = i + 1; k < list.length; k++) {
          if (list[k].color === list[i].color) continue;
          const a = list[i], b = list[k];
          list[i] = b; list[k] = a;
          const kc = k % cols, kr = Math.floor(k / cols);
          const okI = !violatesConsecutive(list, cols, rows, r, c, maxRow, maxCol);
          const okK = !violatesConsecutive(list, cols, rows, kr, kc, maxRow, maxCol);
          if (okI && okK) break;
          list[i] = a; list[k] = b;
        }
      }
    }
  }
}

// §4-2 step 5 — first 3 rows depth guard (C# Phase 1 strict + Phase 2 fallback)
function enforceFirst3RowsDepthGuard(
  list: Holder[], cols: number, depth: Record<number, number>,
  maxRow: number, maxCol: number,
): boolean {
  const firstZone = Math.min(cols * 3, list.length);
  const rows = Math.ceil(list.length / cols);

  let totalDepth0 = 0;
  for (const h of list) if ((depth[h.color] ?? 0) === 0) totalDepth0++;
  if (totalDepth0 === 0) return true; // 외곽 색 없는 필드 → guard 건너뜀

  const hasDepth0InFirst = (): boolean => {
    for (let i = 0; i < firstZone; i++) {
      if ((depth[list[i].color] ?? 0) === 0) return true;
    }
    return false;
  };
  if (hasDepth0InFirst()) return true;

  // Phase 1 strict
  for (let k = firstZone; k < list.length; k++) {
    if ((depth[list[k].color] ?? 0) !== 0) continue;
    for (let i = 0; i < firstZone; i++) {
      const a = list[i], b = list[k];
      list[i] = b; list[k] = a;
      const ic = i % cols, ir = Math.floor(i / cols);
      const kc = k % cols, kr = Math.floor(k / cols);
      const okI = !violatesConsecutive(list, cols, rows, ir, ic, maxRow, maxCol);
      const okK = !violatesConsecutive(list, cols, rows, kr, kc, maxRow, maxCol);
      if (okI && okK) return true;
      list[i] = a; list[k] = b;
    }
  }
  // Phase 2 fallback (consec 위반 허용)
  for (let k = firstZone; k < list.length; k++) {
    if ((depth[list[k].color] ?? 0) !== 0) continue;
    const a = list[0], b = list[k];
    list[0] = b; list[k] = a;
    return true;
  }
  return false;
}

// §6 Hard Rule
function validateHardRules(
  list: Holder[], totalDarts: number, dartCapMax: number, queueCols: number,
): string | null {
  if (!list || list.length === 0) return "보관함이 없음";
  let sum = 0;
  for (const h of list) {
    const m = h.mag;
    if (![10, 20, 30, 40, 50].includes(m)) return `cap not in {10,20,30,40,50}: ${m}`;
    if (m > dartCapMax) return `cap ${m} > dart_capacity_max ${dartCapMax}`;
    sum += m;
  }
  if (sum !== totalDarts) return `sum ${sum} != total ${totalDarts}`;
  if (queueCols < 2 || queueCols > 5) return `queueColumns ${queueCols} not in [2,5]`;
  return null;
}

// §7 난이도 점수 (C# CalcDifficultyScore — colorDependency 활용)
export function calcDifficultyScore(
  magazines: Holder[],
  colorDepth: Record<number, number>,
  colorDependency: Record<number, number[]>,
  colorDartsTotal: Record<number, number>,
  railCapacity: number,
): DifficultyScore {
  if (railCapacity <= 0) {
    return { absolute: 0, max_possible: 0, relative_pct: 0, grade: "trivial" };
  }
  let innerDarts = 0;
  for (const m of magazines) {
    if ((colorDepth[m.color] ?? 0) > 0) innerDarts += m.mag;
  }
  const maxPossible = innerDarts / railCapacity;
  if (maxPossible <= 0) {
    return { absolute: 0, max_possible: 0, relative_pct: 0, grade: "trivial" };
  }

  const consumed: Record<number, number> = {};
  let absolute = 0;
  for (const m of magazines) {
    const color = m.color;
    const depth = colorDepth[color] ?? 0;
    let fireable = false;
    if (depth === 0) {
      fireable = true;
    } else {
      const blockers = colorDependency[color] ?? [];
      if (blockers.length === 0) {
        fireable = true;
      } else {
        let allUnblocked = true;
        for (const blocker of blockers) {
          const total = colorDartsTotal[blocker] ?? 0;
          const used = consumed[blocker] ?? 0;
          if (total <= 0 || used / total < 0.5) { allUnblocked = false; break; }
        }
        fireable = allUnblocked;
      }
    }
    if (!fireable) absolute += m.mag / railCapacity;
    consumed[color] = (consumed[color] ?? 0) + m.mag;
  }

  const relative = Math.min(100, Math.max(0, (absolute / maxPossible) * 100));
  let grade: DifficultyScore["grade"];
  if (relative < 35) grade = "easy";
  else if (relative < 70) grade = "normal";
  else if (relative < 90) grade = "hard";
  else grade = "super_hard";

  return {
    absolute: Math.round(absolute * 100) / 100,
    max_possible: Math.round(maxPossible * 100) / 100,
    relative_pct: Math.round(relative * 10) / 10,
    grade,
  };
}

// purpose 변환 — string + number 모두 지원
export function purposeToDifficulty(p: unknown): Difficulty {
  if (typeof p === "string") {
    const s = p.toLowerCase();
    if (s.includes("super")) return "super_hard";
    if (s.includes("hard")) return "hard";
    if (s.includes("intro")) return "intro";
    if (s.includes("rest")) return "rest";
    if (s.includes("tutorial") || s.includes("easy")) return "tutorial";
    return "normal";
  }
  if (typeof p === "number") {
    if (p <= 0) return "tutorial";
    if (p === 1) return "rest";
    if (p === 2) return "normal";
    if (p === 3) return "hard";
    if (p >= 4) return "super_hard";
  }
  return "normal";
}

// ─── 메인 진입점 — generateQueue ───
//
// cells: 2D field grid (row-major). 빈 셀 = 0 또는 음수.
// palette: 색상 ID 목록 (없으면 cells에서 추출).
// difficulty + levelId: 가드 + 가중치 결정.
// queueColumns: 미지정 시 자동 추천.
// seed: PRNG 결정성 (재시도 시 다른 seed 전달).
//
// 반환: QueueResult — holders, score, validation 모두 포함.
export type GenerateOptions = {
  cells: Cells;
  palette?: number[];
  difficulty: Difficulty;
  levelId: number;
  queueColumns?: number;          // override (0/undefined = auto)
  railCapacity?: number;          // override (undefined = inferred)
  seed?: number;                  // PRNG seed (default: Date.now)
  gimmickCounts?: GimmickCounts;  // §5 STEP C + 필드 기믹 자동 배치 입력
  cellsForFieldGimmick?: boolean; // false면 필드 기믹 SKIP (default: 적용)
};

export function generateQueue(opts: GenerateOptions): QueueResult {
  const { cells, difficulty, levelId } = opts;
  const seed = opts.seed ?? Math.floor(Date.now() / 1000);
  const rng = mulberry32(Math.max(1, seed));

  // 팔레트 결정
  let palette = opts.palette;
  if (!palette || palette.length === 0) {
    const seen = new Set<number>();
    for (const row of cells) for (const v of row) if (v != null && v > 0) seen.add(v);
    palette = [...seen].sort((a, b) => a - b);
  }

  // 필드 분석
  const analysis = computeFieldAnalysis(cells, palette);
  const railCapacity = opts.railCapacity ?? analysis.rail_capacity;
  const dartCapMax = getDartCapacityMax(railCapacity);
  const totalDarts = analysis.total_darts;

  const diffIdx = getDifficultyIndex(difficulty);
  const allowed = buildAllowedCaps(levelId, difficulty, railCapacity, dartCapMax);
  const weights = buildCapWeights(diffIdx, difficulty, allowed);

  let allMagazines: Holder[] | null = null;
  let queueCols = opts.queueColumns && opts.queueColumns > 0 ? opts.queueColumns : 3;
  let attempts = 0;
  let lastFailReason: string | null = null;
  const failReasons: string[] = [];

  for (attempts = 0; attempts < GENERATE_RETRY_MAX; attempts++) {
    // §3 STEP A
    const pending: Holder[] = [];
    for (const ci of palette) {
      const cd = analysis.color_darts[ci] ?? 0;
      if (cd <= 0) continue;
      const mags = decomposeMagazinesV2(cd, weights, allowed, dartCapMax, rng);
      for (const m of mags) pending.push({ color: ci, mag: m });
    }

    queueCols = opts.queueColumns && opts.queueColumns > 0
      ? Math.max(2, Math.min(5, opts.queueColumns))
      : Math.max(2, Math.min(5, recommendQueueColumns(pending.length, difficulty)));

    // §4 STEP B
    const laid = layoutByDepth(pending, analysis.color_depth, diffIdx, rng);
    const maxRow = SAME_COLOR_MAX_ROW[Math.min(diffIdx, SAME_COLOR_MAX_ROW.length - 1)];
    const maxCol = SAME_COLOR_MAX_COL[Math.min(diffIdx, SAME_COLOR_MAX_COL.length - 1)];
    enforceGridConsecutiveLimit(laid, queueCols, maxRow, maxCol);
    const guardOk = enforceFirst3RowsDepthGuard(laid, queueCols, analysis.color_depth, maxRow, maxCol);

    const hardFail = validateHardRules(laid, totalDarts, dartCapMax, queueCols);
    if (hardFail == null && guardOk) {
      allMagazines = laid;
      lastFailReason = null;
      break;
    }
    lastFailReason = hardFail ?? "first-3-rows depth guard (§4-2 step 5)";
    failReasons.push(lastFailReason);
  }

  if (allMagazines == null) {
    // Hard fail 후에도 결과 반환 — caller가 validation으로 판단
    allMagazines = [];
  }

  const score = calcDifficultyScore(
    allMagazines, analysis.color_depth, analysis.color_dependency,
    analysis.color_darts, railCapacity,
  );

  // Validation
  const cap20Count = allMagazines.filter(h => h.mag === 20).length;
  const usedCaps = new Set(allMagazines.map(h => h.mag));
  const decomposedTotal = allMagazines.reduce((s, h) => s + h.mag, 0);
  const colorDartMatch = palette.every(c => {
    const expected = analysis.color_darts[c] ?? 0;
    const got = allMagazines!.filter(h => h.color === c).reduce((s, h) => s + h.mag, 0);
    return got === expected;
  });

  const validation: ValidationReport = {
    decomposed_total: decomposedTotal,
    color_dart_match: colorDartMatch,
    holder_count: allMagazines.length,
    all_mags_in_set: allMagazines.every(h => [10, 20, 30, 40, 50].includes(h.mag)),
    all_under_max: allMagazines.every(h => h.mag <= dartCapMax),
    cap20_backbone_pass: cap20Count >= 1,
    first_rows_depth_guard: lastFailReason == null,
    cap_kinds_count: usedCaps.size,
    cap20_ratio: allMagazines.length > 0
      ? Math.round(cap20Count / allMagazines.length * 100) / 100 : 0,
    avg_ammo_per_holder: allMagazines.length > 0
      ? Math.round(decomposedTotal / allMagazines.length * 10) / 10 : 0,
    retries: attempts,
    hard_fail_reasons: failReasons.length > 0 ? failReasons : undefined,
  };

  // ── §5 STEP C 큐 기믹 자동 배치 (v3.11) ──
  let overlay: QueueOverlay | undefined;
  let stepCValidation: StepCValidation | undefined;
  if (opts.gimmickCounts) {
    const result = generateStepC(
      allMagazines,
      queueCols,
      analysis,
      opts.gimmickCounts,
      difficulty,
      levelId,
      rng,
    );
    overlay = result.overlay;
    stepCValidation = result.validation;
  }

  // ── 필드 기믹 자동 배치 (PF 회귀 + 픽셀아트워크플로우 §STEP 5) ──
  let fieldOverlay: FieldGimmickOverlay | undefined;
  let fieldValidation: FieldGimmickValidation | undefined;
  if (opts.gimmickCounts && opts.cellsForFieldGimmick !== false) {
    const result = generateFieldGimmicks(
      cells,
      analysis,
      opts.gimmickCounts,
      difficulty,
      levelId,
      rng,
    );
    fieldOverlay = result.overlay;
    fieldValidation = result.validation;
  }

  return {
    holders: allMagazines,
    queue_columns: queueCols,
    recommended_queue_columns: recommendQueueColumns(allMagazines.length, difficulty),
    field_analysis: analysis,
    difficulty_score: score,
    validation,
    seed,
    difficulty,
    overlay,
    step_c_validation: stepCValidation,
    field_overlay: fieldOverlay,
    field_gimmick_validation: fieldValidation,
  };
}

// ════════════════════════════════════════════════════════════════
//  §5 STEP C — 큐 기믹 자동 배치 (v3.11, 2026-05-15)
// ════════════════════════════════════════════════════════════════
//
// 명세: BalloonFlow_큐생성기_명세.md §5
// 입력: GimmickCounts (LD pixelforge_levels.gimmick_*) + holders + field_analysis
// 출력: QueueOverlay (hidden_ids / linked_groups / frozen)
//
// 적용 순서 (§5.B 알고리즘 통합 흐름):
//   1. INTRO_LVS_QUEUE 격리 가드 (도입 lv면 도입 기믹만 활성)
//   2. Linked 먼저 (큰 묶음 위치 어려움)
//   3. Frozen (Linked·Hidden 모두 제외, alone 보장)
//   4. Hidden (Frozen 제외, Linked 양 끝 OK, line 0 금지, 희소색 가중)
//   5. Pipe (1.0 SKIP)
//
// 다중 기믹 가드 (§5.7):
//   Hidden + Linked: OK (PF 79 lv, Hidden의 34% Linked 겹침)
//   Hidden + Frozen: 금지 (PF 0건, Hard Rule)
//   Linked + Frozen: 금지 (PF 0건, Hard Rule)
//   Hidden line 0 (첫 행): 금지 (Hard Rule, 메카닉상 자동 공개)
//   link_n ≥ 4 묶음에 Hidden: 금지 (Hard Rule, PF 0%)

// §5.2 INTRO_LVS_QUEUE — 도입 lv 격리
const INTRO_LVS_QUEUE: Record<number, keyof GimmickCounts> = {
  11: "hidden",
  21: "chain",
  41: "spawner_t",
  81: "lock_key",
  141: "spawner_o",
  241: "frozen_dart",
};

// §5.5 Frozen Health = total_sh × ratio × ±60% — PF 정규화 비율
const FROZEN_BASE_RATIO: Partial<Record<Difficulty, number>> = {
  tutorial:   0.20,
  rest:       0.20,
  normal:     0.35,
  intro:      0.35,
  hard:       0.45,
  super_hard: 0.60,
};

// §5.5 Frozen front_half 편향 — PF 회귀
const FROZEN_FRONT_HALF_BIAS: Partial<Record<Difficulty, number>> = {
  tutorial:   0.55,
  rest:       0.55,
  normal:     0.60,
  intro:      0.60,
  hard:       0.55,
  super_hard: 0.80,
};

// §5.4 Hidden front_half 약한 편향
const HIDDEN_FRONT_HALF_BIAS = 0.58;

// v3.6 color_w 3단계 (color share 임계)
const COLOR_W_RARE_THRESHOLD = 0.05;       // ≤5% = 강한 가중
const COLOR_W_UNCOMMON_THRESHOLD = 0.10;   // 5-10% = 약한 가중
const COLOR_W_RARE_BOOST = 3.0;
const COLOR_W_UNCOMMON_BOOST = 1.5;
const COLOR_W_COMMON_PENALTY = 0.4;        // >10% = 회피 (×0.4)

// v3.4·v3.8 Linked link_n별 같은 cap 통일 확률
const LINKED_SAME_CAP_PROB: Record<number, number> = {
  2: 0.60, 3: 0.52, 4: 0.75, 5: 1.0,
};
// v3.5 Linked 같은 색 묶음 확률
const LINKED_SAME_COLOR_PROB: Record<number, number> = {
  2: 0.08, 3: 0.40, 4: 0.62, 5: 1.0,
};

// 도입 lv 격리 (§5.2)
function applyIntroLvGuard(lv: number, raw: GimmickCounts): { filtered: GimmickCounts; introKey?: keyof GimmickCounts } {
  const introKey = INTRO_LVS_QUEUE[lv];
  if (!introKey) return { filtered: { ...raw } };
  const filtered: GimmickCounts = {};
  const v = raw[introKey];
  if (v != null && v > 0) (filtered as Record<string, number>)[introKey] = v;
  return { filtered, introKey };
}

// §5.3.1 splitChain — 95% 디폴트 (2-link 반복) + 5% 변형 (단일 큰 묶음)
function splitChain(total: number, difficulty: Difficulty, rng: () => number): number[] {
  if (total < 2) return [];
  const useDefault = rng() < 0.95;
  if (useDefault) {
    if (total === 2) return [2];
    if (total === 3) return [3];
    if (total % 2 === 0) return Array(total / 2).fill(2);
    // 홀수: 2반복 + 끝 3
    return [...Array(Math.floor((total - 3) / 2)).fill(2), 3];
  }
  // 5% 변형
  if (total === 4) return [4];
  if (total === 5 && difficulty === "super_hard") return [5];
  if (total >= 6) {
    const big = total >= 8 ? 4 : 3;
    return [big, ...splitChain(total - big, difficulty, rng)];
  }
  // fallback
  const out: number[] = Array(Math.floor(total / 2)).fill(2);
  if (total % 2 === 1) out.push(1);
  return out.filter(n => n >= 2);
}

// 색상의 "share" 계산 = colorDarts[c] / total_darts
function colorShare(color: number, fa: FieldAnalysis): number {
  return fa.total_darts > 0 ? (fa.color_darts[color] ?? 0) / fa.total_darts : 0;
}

// v3.6 color_w — 희소색 우선 가중치 (3단계)
function colorWeight(color: number, fa: FieldAnalysis): number {
  const share = colorShare(color, fa);
  if (share <= COLOR_W_RARE_THRESHOLD) return COLOR_W_RARE_BOOST;
  if (share <= COLOR_W_UNCOMMON_THRESHOLD) return COLOR_W_UNCOMMON_BOOST;
  return COLOR_W_COMMON_PENALTY;
}

// 가중 샘플링 (k개 추첨, 중복 없음)
function weightedSample(
  items: number[], weights: number[], k: number, rng: () => number,
): number[] {
  const n = items.length;
  const remaining = items.slice();
  const remainingW = weights.slice();
  const out: number[] = [];
  const pickK = Math.min(k, n);
  for (let i = 0; i < pickK; i++) {
    let total = 0;
    for (const w of remainingW) total += w;
    if (total <= 0) break;
    let roll = rng() * total;
    let chosen = -1;
    for (let j = 0; j < remaining.length; j++) {
      roll -= remainingW[j];
      if (roll <= 0) { chosen = j; break; }
    }
    if (chosen < 0) chosen = remaining.length - 1;
    out.push(remaining[chosen]);
    remaining.splice(chosen, 1);
    remainingW.splice(chosen, 1);
  }
  return out;
}

// §5.3.2 pickLinkedPositions (v3.12-v3.15)
//   v3.12: BL 좌표 — line_index = col / position_in_line = row
//   v3.13: 인접 col 제약 col_max=1 강제 (PF 97% col diff 0·1)
//   v3.14: row tier fallback (1, 3, n_rows) — 사용자 "행은 떨어져도 OK"
//   v3.9 LINKED_DIRECTION_WEIGHTS (BL 좌표 정합): down 1.6 / right 1.0 / diag 0.7 / up 0.2
function pickLinkedPositions(
  totalSh: number, queueCols: number, linkN: number,
  exclude: Set<number>, rng: () => number,
): number[] {
  const available: number[] = [];
  for (let i = 0; i < totalSh; i++) if (!exclude.has(i)) available.push(i);
  if (available.length < linkN) return [];

  const nRows = Math.ceil(totalSh / queueCols);

  // seed 위치 선택
  const seedId = available[Math.floor(rng() * available.length)];
  const seedRow = Math.floor(seedId / queueCols);
  const seedCol = seedId % queueCols;

  // v3.14 row tier fallback (col_max=1 고정)
  const tiers: [number, number][] = [[1, 1], [3, 1], [nRows, 1]];
  for (const [rowMax, colMax] of tiers) {
    const candidates: number[] = [];
    const candWeights: number[] = [];
    for (const sid of available) {
      if (sid === seedId) continue;
      const r = Math.floor(sid / queueCols);
      const c = sid % queueCols;
      const rowDist = Math.abs(r - seedRow);
      const colDist = Math.abs(c - seedCol);
      if (rowDist > rowMax || colDist > colMax) continue;
      // 거리 가중 (행 거리 분포)
      let w = rowDist === 1 ? 0.74 : rowDist === 2 ? 0.18 : 0.08;
      // 방향 가중 (v3.9, BL 좌표)
      const dRow = r - seedRow;
      const dCol = c - seedCol;
      let dirW = 1.0;
      if (dRow > 0 && dCol === 0) dirW = 1.6;       // down (가장 흔함)
      else if (dRow === 0 && dCol > 0) dirW = 1.0;   // right
      else if (dRow > 0 && dCol > 0) dirW = 0.7;     // down-right
      else if (dRow > 0 && dCol < 0) dirW = 0.7;     // down-left
      else if (dRow < 0 && dCol === 0) dirW = 0.2;   // up (드물게)
      else if (dRow === 0 && dCol < 0) dirW = 0.2;   // left
      else dirW = 0.2;                                // up-right, up-left
      candidates.push(sid);
      candWeights.push(w * dirW);
    }
    if (candidates.length >= linkN - 1) {
      const picked = weightedSample(candidates, candWeights, linkN - 1, rng);
      return [seedId, ...picked];
    }
  }
  return [];
}

// §5.A.11 buildChainDependencyGraph (v3.15)
//   그룹 G의 row > 0 보관함은 같은 col 위쪽(row 작은) 다른 그룹 G'에 의존.
//   deps[G] = G가 의존하는 다른 그룹 ID 집합
function buildChainDependencyGraph(
  groups: number[][], queueCols: number, totalSh: number,
): Map<number, Set<number>> {
  // sid → group_id 역방향 매핑
  const sidToGid = new Map<number, number>();
  groups.forEach((shooters, gid) => {
    shooters.forEach(sid => sidToGid.set(sid, gid));
  });
  const deps = new Map<number, Set<number>>();
  groups.forEach((_, gid) => deps.set(gid, new Set()));

  groups.forEach((shooters, gid) => {
    for (const sid of shooters) {
      const row = Math.floor(sid / queueCols);
      const col = sid % queueCols;
      if (row === 0) continue;                          // row 0은 즉시 터치 가능
      // 같은 col 위쪽(row 작은) 모든 보관함 → 다른 그룹이면 의존
      for (let r2 = 0; r2 < row; r2++) {
        const sid2 = r2 * queueCols + col;
        if (sid2 >= totalSh) continue;
        const gid2 = sidToGid.get(sid2);
        if (gid2 != null && gid2 !== gid) {
          deps.get(gid)!.add(gid2);
        }
      }
    }
  });
  return deps;
}

// §5.A.11 hasCycle — DFS 위상 정렬로 cycle 검사
function hasCycle(deps: Map<number, Set<number>>): boolean {
  const WHITE = 0, GRAY = 1, BLACK = 2;
  const color = new Map<number, number>();
  for (const k of deps.keys()) color.set(k, WHITE);

  function dfs(node: number): boolean {
    color.set(node, GRAY);
    const nexts = deps.get(node);
    if (nexts) {
      for (const next of nexts) {
        const c = color.get(next) ?? WHITE;
        if (c === GRAY) return true;
        if (c === WHITE && dfs(next)) return true;
      }
    }
    color.set(node, BLACK);
    return false;
  }

  for (const gid of deps.keys()) {
    if ((color.get(gid) ?? WHITE) === WHITE) {
      if (dfs(gid)) return true;
    }
  }
  return false;
}

// v3.12 Chain 사슬 인접 col 제약 — (col, row) 정렬 후 연속 페어 col diff ≤ 1
function validateChainAdjacency(groups: number[][], queueCols: number): boolean {
  for (const grp of groups) {
    if (grp.length < 2) continue;
    const sorted = grp
      .map(sid => ({ sid, col: sid % queueCols, row: Math.floor(sid / queueCols) }))
      .sort((a, b) => a.col - b.col || a.row - b.row);
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].col - sorted[i - 1].col > 1) return false;
    }
  }
  return true;
}

// §5.5 pickFrozenHealth — v1.2.23 PF picked 분포 (N=43, mode 6/16/24)
// 이전 ratio 기반 (×0.4~1.4) 폐기. PF 실측 mode 6(11.6%)/16(9.3%)/24(7%) + 6-30 구간 74.5%.
// 난이도별 weight 변동: easy → 낮은 값 (6-10), hard → 중상 (16-30+).
const FROZEN_HEALTH_DIST_V123: Record<Difficulty, { val: number; w: number }[]> = {
  tutorial: [{val:6,w:0.40},{val:8,w:0.25},{val:10,w:0.20},{val:16,w:0.10},{val:4,w:0.05}],
  rest:     [{val:6,w:0.40},{val:8,w:0.25},{val:10,w:0.20},{val:16,w:0.10},{val:4,w:0.05}],
  normal:   [{val:6,w:0.20},{val:8,w:0.15},{val:10,w:0.10},{val:16,w:0.20},{val:24,w:0.15},{val:18,w:0.10},{val:30,w:0.10}],
  hard:     [{val:6,w:0.08},{val:16,w:0.20},{val:18,w:0.10},{val:24,w:0.25},{val:26,w:0.10},{val:30,w:0.10},{val:32,w:0.10},{val:42,w:0.07}],
  super_hard:[{val:16,w:0.10},{val:24,w:0.15},{val:30,w:0.15},{val:42,w:0.15},{val:52,w:0.20},{val:61,w:0.15},{val:32,w:0.10}],
  intro:    [{val:6,w:0.40},{val:8,w:0.25},{val:10,w:0.20},{val:16,w:0.10},{val:4,w:0.05}],
};

function pickFrozenHealth(totalSh: number, difficulty: Difficulty, rng: () => number): number {
  const dist = FROZEN_HEALTH_DIST_V123[difficulty] ?? FROZEN_HEALTH_DIST_V123.normal;
  const totalW = dist.reduce((s, e) => s + e.w, 0);
  let r = rng() * totalW;
  for (const e of dist) {
    r -= e.w;
    if (r <= 0) {
      // totalSh 가 너무 적으면 (e.g., 4 슈터만) value 가 totalSh-1 초과 안 하도록
      return Math.max(2, Math.min(totalSh - 1, e.val));
    }
  }
  return Math.max(2, Math.min(totalSh - 1, dist[dist.length - 1].val));
}

// §5.5 pickFrozenPosition — front_half 편향
function pickFrozenPosition(
  totalSh: number, queueCols: number, difficulty: Difficulty,
  exclude: Set<number>, rng: () => number,
): number | null {
  const available: number[] = [];
  const weights: number[] = [];
  const halfLineCount = Math.ceil(Math.ceil(totalSh / queueCols) / 2);
  const halfHolderIdx = halfLineCount * queueCols;
  const frontBias = FROZEN_FRONT_HALF_BIAS[difficulty] ?? 0.6;
  for (let i = 0; i < totalSh; i++) {
    if (exclude.has(i)) continue;
    available.push(i);
    weights.push(i < halfHolderIdx ? frontBias : (1 - frontBias));
  }
  if (available.length === 0) return null;
  const picked = weightedSample(available, weights, 1, rng);
  return picked[0] ?? null;
}

// §5.4 pickHiddenPositions — front_half 약한 편향 + 희소색 가중 + line 0 금지 (Hard Rule)
function pickHiddenPositions(
  holders: Holder[], queueCols: number, n: number,
  exclude: Set<number>, fa: FieldAnalysis, rng: () => number,
): number[] {
  const totalSh = holders.length;
  const halfLineCount = Math.ceil(Math.ceil(totalSh / queueCols) / 2);
  const halfHolderIdx = halfLineCount * queueCols;
  const lineFirstSize = queueCols;                         // line 0 = 첫 queue_columns개

  const available: number[] = [];
  const weights: number[] = [];
  for (let i = 0; i < totalSh; i++) {
    if (exclude.has(i)) continue;
    if (i < lineFirstSize) continue;                       // ★ Hidden line 0 금지 (Hard Rule)
    available.push(i);
    const positionW = i < halfHolderIdx ? HIDDEN_FRONT_HALF_BIAS : (1 - HIDDEN_FRONT_HALF_BIAS);
    const colorW = colorWeight(holders[i].color, fa);
    weights.push(positionW * colorW);
  }
  return weightedSample(available, weights, n, rng);
}

// §5.7 다중 기믹 가드 + Hard Rules 검증
function validateMultiGimmickGuards(
  overlay: QueueOverlay, queueCols: number,
): { ok: boolean; reason?: string; line0_pass: boolean; link_n_hidden_pass: boolean } {
  const frozenIds = new Set(overlay.frozen.map(f => f.id));
  const linkedIds = new Set(overlay.linked_groups.flatMap(g => g.ids));
  const hiddenIds = new Set(overlay.hidden_ids);

  // Frozen 단독 보장
  for (const id of frozenIds) {
    if (linkedIds.has(id)) return { ok: false, reason: `Frozen ∩ Linked at id=${id}`, line0_pass: true, link_n_hidden_pass: true };
    if (hiddenIds.has(id)) return { ok: false, reason: `Frozen ∩ Hidden at id=${id}`, line0_pass: true, link_n_hidden_pass: true };
  }

  // v3.2 Hard Rule: Hidden line 0 금지 (검증)
  let line0Pass = true;
  for (const id of hiddenIds) {
    if (id < queueCols) { line0Pass = false; break; }
  }

  // v3.2 Hard Rule: link_n ≥ 4 묶음에 Hidden 금지
  let linkNHiddenPass = true;
  for (const g of overlay.linked_groups) {
    if (g.ids.length >= 4) {
      for (const id of g.ids) {
        if (hiddenIds.has(id)) { linkNHiddenPass = false; break; }
      }
    }
    if (!linkNHiddenPass) break;
  }

  if (!line0Pass) return { ok: false, reason: "Hidden line 0 (Hard Rule §5.2)", line0_pass: false, link_n_hidden_pass: linkNHiddenPass };
  if (!linkNHiddenPass) return { ok: false, reason: "Hidden in link_n>=4 (Hard Rule v3.2)", line0_pass: true, link_n_hidden_pass: false };

  return { ok: true, line0_pass: true, link_n_hidden_pass: true };
}

// ════════════════════════════════════════════════════════════════
//  필드 기믹 자동 배치 (PF 회귀 + 픽셀아트워크플로우 §STEP 5)
// ════════════════════════════════════════════════════════════════
//
// 입력: cells + GimmickCounts (pinata, wall, surprise, pinata_box, ice, pin)
// 출력: FieldGimmickOverlay (balloons[]에 적용될 변환·점유 정보)
//
// PF 회귀 룰:
//   Pinata: 풍선 → 다중 타격 변환 (life 5/10/20/40 분포). 영역 1×1~3×3
//   Wall: 빈 영역에 점유. 1×1 우선 (PF lv1 wall = 3×3 corner)
//   Surprise (Hidden Balloon): 풍선 색 숨김. 안쪽 풍선 우선 (depth 1+)
//   Target Box (eggBoxes): 2×2+ 영역 박스로 변환, eggs[{material, count}]
//   Frozen Layer (pixelIceBlocks): 영역에 얼음 layer. life 큰 (50~200)
//   Barricade (pin): 1×N 형태로 풍선 앞에 배치 (PF에 직접 매핑 없음 — workflow doc 기반)

// PF 회귀 — Pinata life 분포 (PF Level_0031_Hard 기준 5/10/20/40 다양)
function pickPinataLife(difficulty: Difficulty, rng: () => number): number {
  const POOL = difficulty === "tutorial" || difficulty === "rest"
    ? [5, 5, 10, 10, 20]
    : difficulty === "super_hard"
    ? [10, 20, 20, 40, 40]
    : [5, 10, 20, 20, 40];
  return POOL[Math.floor(rng() * POOL.length)];
}

function pickFrozenLayerLife(difficulty: Difficulty, rng: () => number): number {
  const POOL = difficulty === "super_hard"
    ? [80, 100, 150, 200]
    : difficulty === "hard"
    ? [40, 60, 80, 100]
    : [20, 30, 40, 50];
  return POOL[Math.floor(rng() * POOL.length)];
}

// 빈 칸 좌표 수집 (cells에서 v <= 0인 칸)
function collectEmptyCells(cells: Cells): { row: number; col: number }[] {
  const out: { row: number; col: number }[] = [];
  for (let r = 0; r < cells.length; r++) {
    for (let c = 0; c < cells[r].length; c++) {
      const v = cells[r][c];
      if (v == null || v <= 0) out.push({ row: r, col: c });
    }
  }
  return out;
}

// 풍선 좌표 + balloonId 수집
function collectBalloons(cells: Cells): { balloonId: number; row: number; col: number; color: number }[] {
  const out: { balloonId: number; row: number; col: number; color: number }[] = [];
  let id = 0;
  for (let r = 0; r < cells.length; r++) {
    for (let c = 0; c < cells[r].length; c++) {
      const v = cells[r][c];
      if (v != null && v > 0) {
        out.push({ balloonId: id++, row: r, col: c, color: v });
      }
    }
  }
  return out;
}

// 인접 풍선 클러스터 찾기 (같은 색 BFS)
function findClusters(cells: Cells, minSize = 4): { color: number; cells: { row: number; col: number }[] }[] {
  const rows = cells.length;
  const cols = cells[0]?.length ?? 0;
  const visited: boolean[][] = Array.from({ length: rows }, () => new Array(cols).fill(false));
  const clusters: { color: number; cells: { row: number; col: number }[] }[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (visited[r][c]) continue;
      const v = cells[r][c];
      if (v == null || v <= 0) { visited[r][c] = true; continue; }
      // BFS
      const stack = [{ row: r, col: c }];
      const cluster: { row: number; col: number }[] = [];
      while (stack.length > 0) {
        const cur = stack.pop()!;
        // ★ bounds 체크 먼저
        if (cur.row < 0 || cur.row >= rows || cur.col < 0 || cur.col >= cols) continue;
        if (visited[cur.row][cur.col]) continue;
        if (cells[cur.row][cur.col] !== v) continue;
        visited[cur.row][cur.col] = true;
        cluster.push(cur);
        stack.push({ row: cur.row - 1, col: cur.col });
        stack.push({ row: cur.row + 1, col: cur.col });
        stack.push({ row: cur.row, col: cur.col - 1 });
        stack.push({ row: cur.row, col: cur.col + 1 });
      }
      if (cluster.length >= minSize) clusters.push({ color: v, cells: cluster });
    }
  }
  return clusters;
}

// 필드 분석으로 색상 깊이 가져와 안쪽(>0) 풍선 우선
function pickInnerBalloons(
  balloons: { balloonId: number; color: number }[],
  fa: FieldAnalysis,
  n: number,
  exclude: Set<number>,
  rng: () => number,
): number[] {
  const cands: number[] = [];
  const ws: number[] = [];
  for (const b of balloons) {
    if (exclude.has(b.balloonId)) continue;
    cands.push(b.balloonId);
    const depth = fa.color_depth[b.color] ?? 0;
    // 안쪽일수록 가중 (depth 0 = 0.3, depth 1 = 1.0, depth 2 = 1.5)
    ws.push(depth === 0 ? 0.3 : depth === 1 ? 1.0 : 1.5);
  }
  return weightedSample(cands, ws, n, rng);
}

function generateFieldGimmicks(
  cells: Cells,
  fa: FieldAnalysis,
  rawCounts: GimmickCounts,
  difficulty: Difficulty,
  lv: number,
  rng: () => number,
): { overlay: FieldGimmickOverlay; validation: FieldGimmickValidation } {
  const overlay: FieldGimmickOverlay = {
    pinata_balloons: [],
    wall_cells: [],
    hidden_balloons: [],
    pinata_box_areas: [],
    frozen_layer_areas: [],
    barricade_lines: [],
  };
  const warnings: string[] = [];

  // INTRO_LVS 격리 — 도입 lv면 도입 기믹만
  const introMap: Record<number, keyof GimmickCounts> = {
    31: "pinata", 61: "pin", 101: "surprise",
    121: "wall", 161: "pinata_box", 201: "ice",
  };
  const introKey = introMap[lv];
  const counts: GimmickCounts = introKey
    ? { [introKey]: rawCounts[introKey] } as GimmickCounts
    : { ...rawCounts };

  const allBalloons = collectBalloons(cells);
  const usedBalloons = new Set<number>();

  // 1. Pinata — 풍선 → 다중 타격 변환 (depth 0 외곽 우선 — 직접 타격 가능해야)
  const pinataN = counts.pinata ?? 0;
  if (pinataN > 0 && allBalloons.length > 0) {
    const cands: number[] = [];
    const ws: number[] = [];
    for (const b of allBalloons) {
      cands.push(b.balloonId);
      const depth = fa.color_depth[b.color] ?? 0;
      ws.push(depth === 0 ? 1.5 : depth === 1 ? 1.0 : 0.5);
    }
    const picked = weightedSample(cands, ws, Math.min(pinataN, allBalloons.length), rng);
    for (const id of picked) {
      overlay.pinata_balloons.push({ balloonId: id, life: pickPinataLife(difficulty, rng) });
      usedBalloons.add(id);
    }
  }

  // 2. Iron Wall — 빈 칸에 점유. 풍선 영역 외곽이나 큰 빈 영역
  const wallN = counts.wall ?? 0;
  if (wallN > 0) {
    const empties = collectEmptyCells(cells);
    if (empties.length === 0) {
      warnings.push("Iron Wall 배치 불가 (빈 셀 없음)");
    } else {
      // 무작위 N개 1×1 (단순 모델)
      const picked: { row: number; col: number }[] = [];
      const pool = empties.slice();
      shuffle(pool, rng);
      for (let i = 0; i < Math.min(wallN, pool.length); i++) picked.push(pool[i]);
      for (const p of picked) overlay.wall_cells.push({ row: p.row, col: p.col, areaW: 1, areaH: 1 });
    }
  }

  // 3. Hidden Balloon (surprise) — 안쪽 풍선 우선
  const surpriseN = counts.surprise ?? 0;
  if (surpriseN > 0) {
    overlay.hidden_balloons = pickInnerBalloons(allBalloons, fa, surpriseN, usedBalloons, rng);
    overlay.hidden_balloons.forEach(id => usedBalloons.add(id));
  }

  // 4. Target Box (pinata_box) — 2×2+ 영역 박스 (PF eggBoxes)
  const boxN = counts.pinata_box ?? 0;
  if (boxN > 0) {
    const clusters = findClusters(cells, 4).filter(c => {
      // 사용 안 된 풍선만 포함된 클러스터
      const ids = new Set<number>();
      for (const cell of c.cells) {
        const b = allBalloons.find(bb => bb.row === cell.row && bb.col === cell.col);
        if (b) ids.add(b.balloonId);
      }
      return [...ids].every(id => !usedBalloons.has(id));
    });
    for (let i = 0; i < boxN && i < clusters.length; i++) {
      const cl = clusters[i];
      // bounding box
      const minR = Math.min(...cl.cells.map(c => c.row));
      const maxR = Math.max(...cl.cells.map(c => c.row));
      const minC = Math.min(...cl.cells.map(c => c.col));
      const maxC = Math.max(...cl.cells.map(c => c.col));
      const areaW = Math.min(3, maxC - minC + 1);
      const areaH = Math.min(3, maxR - minR + 1);
      // 색상 분포 → eggs
      const colorCounts: Record<number, number> = {};
      for (const cell of cl.cells) {
        const v = cells[cell.row][cell.col];
        if (v && v > 0) colorCounts[v] = (colorCounts[v] ?? 0) + 1;
      }
      const eggs = Object.entries(colorCounts)
        .map(([c, n]) => ({ color: parseInt(c), count: n }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 3);
      overlay.pinata_box_areas.push({ row: minR, col: minC, areaW, areaH, eggs });
      // 사용 마킹
      for (const cell of cl.cells) {
        const b = allBalloons.find(bb => bb.row === cell.row && bb.col === cell.col);
        if (b) usedBalloons.add(b.balloonId);
      }
    }
  }

  // 5. Frozen Layer (ice) — 영역 + 큰 life
  const iceN = counts.ice ?? 0;
  if (iceN > 0) {
    const clusters = findClusters(cells, 6);
    for (let i = 0; i < iceN && i < clusters.length; i++) {
      const cl = clusters[i];
      const minR = Math.min(...cl.cells.map(c => c.row));
      const maxR = Math.max(...cl.cells.map(c => c.row));
      const minC = Math.min(...cl.cells.map(c => c.col));
      const maxC = Math.max(...cl.cells.map(c => c.col));
      const areaW = Math.min(4, maxC - minC + 1);
      const areaH = Math.min(4, maxR - minR + 1);
      overlay.frozen_layer_areas.push({
        row: minR, col: minC, areaW, areaH,
        life: pickFrozenLayerLife(difficulty, rng),
      });
    }
  }

  // 6. Barricade (pin) — 1×N 형태로 외곽 풍선 앞에 (단순: depth 0 풍선 N개 라인 형성)
  const pinN = counts.pin ?? 0;
  if (pinN > 0) {
    // 색상별로 depth 0 풍선 묶음 찾기 → 가장 긴 라인 N개
    const lines: { positions: { row: number; col: number }[]; color: number; life: number }[] = [];
    const clusters = findClusters(cells, 3);
    const depth0Clusters = clusters.filter(c => (fa.color_depth[c.color] ?? 0) === 0);
    for (let i = 0; i < Math.min(pinN, depth0Clusters.length); i++) {
      const cl = depth0Clusters[i];
      // 한 줄로 정렬된 긴 라인 추출 (간단: 첫 풍선의 row 같은 cells)
      const targetRow = cl.cells[0].row;
      const linePos = cl.cells.filter(c => c.row === targetRow).slice(0, 4);
      if (linePos.length >= 2) {
        lines.push({
          positions: linePos,
          color: cl.color,
          life: 1 + Math.floor(rng() * 3),  // life 1-3
        });
      }
    }
    overlay.barricade_lines = lines;
  }

  // 7. Color Curtain — 1.1+ SKIP

  return {
    overlay,
    validation: {
      applied: true,
      pinata_placed: overlay.pinata_balloons.length,
      wall_placed: overlay.wall_cells.length,
      hidden_balloons_placed: overlay.hidden_balloons.length,
      pinata_box_placed: overlay.pinata_box_areas.length,
      frozen_layer_placed: overlay.frozen_layer_areas.length,
      barricade_placed: overlay.barricade_lines.length,
      warnings,
    },
  };
}

// §5.9 메인 진입점 — 단일 결과 모드 (n=10 candidates는 향후 별도 task)
function generateStepC(
  holders: Holder[], queueCols: number, fa: FieldAnalysis,
  rawCounts: GimmickCounts, difficulty: Difficulty, lv: number, rng: () => number,
): { overlay: QueueOverlay; validation: StepCValidation } {
  const { filtered, introKey } = applyIntroLvGuard(lv, rawCounts);
  const totalSh = holders.length;
  const overlay: QueueOverlay = {
    hidden_ids: [],
    linked_groups: [],
    frozen: [],
  };

  // 1. Linked (§5.3) — 큰 묶음 위치 잡기 어려우니 우선
  // v3.15: 그룹 추가마다 cycle 검사. cycle 발생 시 그 그룹만 재추첨 (5회 retry).
  let chainCycleRetries = 0;
  if (filtered.chain && filtered.chain >= 2 && totalSh >= 2) {
    const partitions = splitChain(filtered.chain, difficulty, rng);
    const MAX_GROUP_RETRY = 5;
    let outerAttempt = 0;
    const MAX_OUTER = 5;
    outer: while (outerAttempt < MAX_OUTER) {
      outerAttempt++;
      overlay.linked_groups = [];
      const used = new Set<number>();
      let allOk = true;
      for (const linkN of partitions) {
        if (linkN < 2) continue;
        let groupOk = false;
        for (let attempt = 0; attempt < MAX_GROUP_RETRY; attempt++) {
          const positions = pickLinkedPositions(totalSh, queueCols, linkN, used, rng);
          if (positions.length !== linkN) break;
          // v3.12 col adjacency 검사
          const tentativeGroups = [...overlay.linked_groups.map(g => g.ids), positions];
          if (!validateChainAdjacency(tentativeGroups, queueCols)) {
            chainCycleRetries++;
            continue;
          }
          // v3.15 cycle 검사
          const deps = buildChainDependencyGraph(tentativeGroups, queueCols, totalSh);
          if (hasCycle(deps)) {
            chainCycleRetries++;
            continue;
          }
          // OK
          const sameColor = rng() < (LINKED_SAME_COLOR_PROB[linkN] ?? 0.1);
          overlay.linked_groups.push({ ids: positions, same_color: sameColor });
          positions.forEach(p => used.add(p));
          groupOk = true;
          break;
        }
        if (!groupOk) { allOk = false; break; }
      }
      if (allOk) break outer;
    }
  }

  // 2. Frozen (§5.5) — Linked 제외 (Hidden은 아직 안 들어감)
  if (filtered.frozen_dart && filtered.frozen_dart >= 1) {
    const linkedIds = new Set(overlay.linked_groups.flatMap(g => g.ids));
    const used = new Set<number>(linkedIds);
    for (let i = 0; i < filtered.frozen_dart; i++) {
      const id = pickFrozenPosition(totalSh, queueCols, difficulty, used, rng);
      if (id == null) break;
      used.add(id);
      overlay.frozen.push({ id, health: pickFrozenHealth(totalSh, difficulty, rng) });
    }
  }

  // 3. Hidden (§5.4) — Frozen 제외, Linked OK, line 0 금지
  if (filtered.hidden && filtered.hidden >= 1) {
    const frozenIds = new Set(overlay.frozen.map(f => f.id));
    overlay.hidden_ids = pickHiddenPositions(
      holders, queueCols, filtered.hidden,
      frozenIds, fa, rng,
    );
  }

  // 4. Pipe (§5.6) — 1.0 SKIP

  // 5. Validation
  const guard = validateMultiGimmickGuards(overlay, queueCols);
  // v3.12 Chain adjacency 최종 검증
  const groupIds = overlay.linked_groups.map(g => g.ids);
  const adjacencyOk = validateChainAdjacency(groupIds, queueCols);
  // v3.15 cycle 최종 검증
  const finalDeps = buildChainDependencyGraph(groupIds, queueCols, totalSh);
  const cycleOk = !hasCycle(finalDeps);

  const allPass = guard.ok && adjacencyOk && cycleOk;
  let reason = guard.reason;
  if (!adjacencyOk) reason = "Chain 사슬 col diff > 1 (v3.12 Hard Rule)";
  else if (!cycleOk) reason = "Chain 그룹 의존성 cycle (v3.15 Hard Rule)";

  return {
    overlay,
    validation: {
      applied: true,
      multi_gimmick_pass: allPass,
      hidden_line0_pass: guard.line0_pass,
      link_n_hidden_pass: guard.link_n_hidden_pass,
      chain_adjacency_pass: adjacencyOk,
      chain_cycle_pass: cycleOk,
      hard_fail_reason: reason,
      intro_lv_filter: introKey,
      chain_cycle_retries: chainCycleRetries,
    },
  };
}
