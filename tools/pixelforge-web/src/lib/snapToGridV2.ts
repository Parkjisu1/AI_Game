// Image → clean field-map pipeline V2 (unfake-style)
//
// Pipeline:
//   1) Collect all opaque pixels
//   2) Median-cut quantize to K colors (unfake core idea — AA/noise collapses into K clusters)
//   3) Per-cell mode on K-index (not on 28-palette — more robust)
//   4) Map K clusters → 28-palette by Lab ΔE minimum (K mapping decisions, not per-cell)
//   5) Apply mapping to produce final 28-palette matrix + stats
//
// Why this beats V1 (snapToGrid.ts):
//   - V1 maps each pixel to 28-palette first, then votes — AA pixels split votes across adjacent 28-colors.
//   - V2 clusters in image-native space first, so each cell votes on a clean K-index.
//   - K→28 mapping is a K-size decision table — trivially inspectable/overridable.
//
// Output format: same SnapResult shape + `paletteMapping` for traceability.
import sharp from "sharp";
import { GAME_PALETTE } from "./palette";
import { renderMatrixToPng } from "./matrixRenderer";

export interface SnapV2Options {
  cols: number;
  rows: number;
  // Hint for expected palette. V2 does NOT enforce it on K→28 mapping
  // (that would collapse to V1 behavior and lose the unfake benefit).
  // Used only as a tie-breaker hint + final top-N reduction when combined with targetColorCount.
  allowedIds?: number[];
  transparentBg?: boolean;
  targetColorCount?: number;   // drives both K (oversample) and final top-N
  // Override K→28 mapping for specific K indices (human correction hook)
  paletteOverride?: Record<number, number>;
  // "팔레트 강제": true + allowedIds 있으면 K→28 매핑을 의도 색(allowedIds)으로만 제한.
  // 기본 false (unfake "정확생성+인간수정" 철학 보존). ④ 색상 의도 불일치 해결용 opt-in.
  forcePalette?: boolean;
}

export interface SnapV2Result {
  matrix: number[][];
  base64: string;
  width: number;
  height: number;
  pixelsPerCell: number;
  paletteMapping: Record<number, number>; // K-index (1-based) → 28-palette ID
  kPalette: Array<[number, number, number]>; // K cluster centroids (RGB)
  stats: {
    cellsAnalyzed: number;
    uniqueColorsBefore: number;
    uniqueColorsAfter: number;
    dominantColors: number[];
    k: number;
    pipeline: "unfake_v1";
  };
}

// ───────────────────────────────────────────────────────────
// Lab color space (for perceptual K→28 mapping)
// ───────────────────────────────────────────────────────────
function rgbToLab(r: number, g: number, b: number): [number, number, number] {
  // sRGB → linear
  const srgb = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  // linear → XYZ (D65)
  const x = srgb[0] * 0.4124564 + srgb[1] * 0.3575761 + srgb[2] * 0.1804375;
  const y = srgb[0] * 0.2126729 + srgb[1] * 0.7151522 + srgb[2] * 0.0721750;
  const z = srgb[0] * 0.0193339 + srgb[1] * 0.1191920 + srgb[2] * 0.9503041;
  // XYZ → Lab (D65 reference white)
  const xn = x / 0.95047, yn = y / 1.00000, zn = z / 1.08883;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const L = 116 * f(yn) - 16;
  const a = 500 * (f(xn) - f(yn));
  const bLab = 200 * (f(yn) - f(zn));
  return [L, a, bLab];
}

function labDistSq(a: [number, number, number], b: [number, number, number]): number {
  const dl = a[0] - b[0], da = a[1] - b[1], db = a[2] - b[2];
  return dl * dl + da * da + db * db;
}

// ───────────────────────────────────────────────────────────
// [2026-06-15 색상매칭 개선] K→28 매핑이 순수 RGB 유클리드라 "탁한 색"(예: 초원 풀색)이
// 회색(24)·검정(8)에 빨려감 → 제작 이미지(초록)와 저장 JSON 레벨(회색) 디자인 불일치.
// 원인: 28색 팔레트에 "중간 톤 녹색"이 없어 honest 최근접이 무채색이 됨(Lab도 동일 — 위 §5 주석 참고).
// 해결: hue(색조) 계열을 1차 게이팅 후, 그 계열 안에서만 RGB 최근접 선택(결정론적, AI 불필요).
//
// ▼▼ 원복(ROLLBACK) ▼▼  HUE_GATE.enabled = false → 즉시 기존 순수-RGB 동작과 100% 동일.
// 튜닝값(검증: 탁한 풀색 4종 → 초록/연초록, 진짜 회색은 회색 유지):
//   pxNeutralFloor=18  hueWindow=50  palNeutralFloor=20
// ───────────────────────────────────────────────────────────
const HUE_GATE = { enabled: true, pxNeutralFloor: 18, hueWindow: 50, palNeutralFloor: 20 };

function rgbHueV2(r: number, g: number, b: number): number {
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), c = mx - mn;
  if (c === 0) return 0;
  let h: number;
  if (mx === r) h = ((g - b) / c) % 6;
  else if (mx === g) h = (b - r) / c + 2;
  else h = (r - g) / c + 4;
  h *= 60;
  return h < 0 ? h + 360 : h;
}
function hueDistV2(a: number, b: number): number {
  const d = Math.abs(a - b) % 360;
  return Math.min(d, 360 - d);
}
// 팔레트 hue/chroma 1회 캐싱
const PAL_HUE: Record<number, number> = {};
const PAL_CHROMA: Record<number, number> = {};
for (const [idStr, rgb] of Object.entries(GAME_PALETTE)) {
  const id = parseInt(idStr), [r, g, b] = rgb;
  PAL_CHROMA[id] = Math.max(r, g, b) - Math.min(r, g, b);
  PAL_HUE[id] = rgbHueV2(r, g, b);
}
// 후보 id 목록 중 RGB 최근접 (게이트 OFF / 폴백용)
function rgbNearestId(r: number, g: number, b: number, ids: number[]): number {
  let bestId = ids[0] || 1, bestDist = Infinity;
  for (const id of ids) {
    const pal = GAME_PALETTE[id];
    if (!pal) continue;
    const dr = r - pal[0], dg = g - pal[1], db = b - pal[2];
    const d = dr * dr + dg * dg + db * db;
    if (d < bestDist) { bestDist = d; bestId = id; }
  }
  return bestId;
}
// hue 계열 게이팅 후 RGB 최근접. 후보군(candidateIds) 안에서만 동작 → allowedIds/topN 모두와 호환.
function nearestPaletteHueGated(r: number, g: number, b: number, candidateIds: number[]): number {
  if (candidateIds.length === 0) return 1;
  if (!HUE_GATE.enabled) return rgbNearestId(r, g, b, candidateIds); // 원복 스위치
  const chroma = Math.max(r, g, b) - Math.min(r, g, b);
  let pool = candidateIds;
  if (chroma >= HUE_GATE.pxNeutralFloor) {
    // 유채색 → 같은 hue 계열(유채색 팔레트)만. 없으면 유채색 전체, 그래도 없으면 후보 전체.
    const h = rgbHueV2(r, g, b);
    const chrom = candidateIds.filter((id) => (PAL_CHROMA[id] ?? 0) >= HUE_GATE.palNeutralFloor);
    const fam = chrom.filter((id) => hueDistV2(h, PAL_HUE[id] ?? 0) < HUE_GATE.hueWindow);
    if (fam.length) pool = fam;
    else if (chrom.length) pool = chrom;
  } else {
    // 무채색 → 무채색 팔레트끼리만 (없으면 후보 전체)
    const neut = candidateIds.filter((id) => (PAL_CHROMA[id] ?? 0) < HUE_GATE.palNeutralFloor);
    if (neut.length) pool = neut;
  }
  return rgbNearestId(r, g, b, pool);
}

// ───────────────────────────────────────────────────────────
// Median-cut color quantization
// ───────────────────────────────────────────────────────────
interface Pixel { r: number; g: number; b: number; count: number }

function medianCut(pixels: Pixel[], k: number): Array<[number, number, number]> {
  if (pixels.length === 0) return [[0, 0, 0]];
  if (k <= 1) return [averageBox(pixels)];

  let boxes: Pixel[][] = [pixels];
  while (boxes.length < k) {
    // pick box with largest (weighted) axis range
    let idx = -1, bestRange = -1;
    for (let i = 0; i < boxes.length; i++) {
      const box = boxes[i];
      if (box.length < 2) continue;
      const range = longestAxisRange(box);
      if (range > bestRange) { bestRange = range; idx = i; }
    }
    if (idx < 0) break; // can't split further

    const box = boxes[idx];
    const axis = longestAxis(box);
    box.sort((a, b) => (axis === 0 ? a.r - b.r : axis === 1 ? a.g - b.g : a.b - b.b));
    const mid = Math.floor(box.length / 2);
    boxes.splice(idx, 1, box.slice(0, mid), box.slice(mid));
  }

  return boxes.map(averageBox);
}

function longestAxis(box: Pixel[]): 0 | 1 | 2 {
  let minR = 255, maxR = 0, minG = 255, maxG = 0, minB = 255, maxB = 0;
  for (const p of box) {
    if (p.r < minR) minR = p.r; if (p.r > maxR) maxR = p.r;
    if (p.g < minG) minG = p.g; if (p.g > maxG) maxG = p.g;
    if (p.b < minB) minB = p.b; if (p.b > maxB) maxB = p.b;
  }
  const rR = maxR - minR, gR = maxG - minG, bR = maxB - minB;
  if (rR >= gR && rR >= bR) return 0;
  if (gR >= bR) return 1;
  return 2;
}

function longestAxisRange(box: Pixel[]): number {
  let minR = 255, maxR = 0, minG = 255, maxG = 0, minB = 255, maxB = 0;
  for (const p of box) {
    if (p.r < minR) minR = p.r; if (p.r > maxR) maxR = p.r;
    if (p.g < minG) minG = p.g; if (p.g > maxG) maxG = p.g;
    if (p.b < minB) minB = p.b; if (p.b > maxB) maxB = p.b;
  }
  return Math.max(maxR - minR, maxG - minG, maxB - minB);
}

function averageBox(box: Pixel[]): [number, number, number] {
  let totalW = 0, sR = 0, sG = 0, sB = 0;
  for (const p of box) {
    sR += p.r * p.count; sG += p.g * p.count; sB += p.b * p.count;
    totalW += p.count;
  }
  if (totalW === 0) return [0, 0, 0];
  return [Math.round(sR / totalW), Math.round(sG / totalW), Math.round(sB / totalW)];
}

// ───────────────────────────────────────────────────────────
// Toroidal recenter — PixelLab 생성 이미지의 wrap/offset 보정.
// 증상: 콘텐츠가 한쪽으로 밀리고 잘린 부분이 반대편 가장자리에서 재출현(토로이드 오프셋).
// 방법: 행/열 콘텐츠 프로파일의 최장 '빈 seam'을 찾아 콘텐츠를 contiguous하게 roll한 뒤
//       toroidal roll로 중앙 정렬(배경 보존 — 풀블리드 배경에 빈 가장자리 안 생김).
// 이미 정렬된 이미지에는 near-no-op.
// ───────────────────────────────────────────────────────────
function recenterMatrixToroidal(matrix: number[][]): number[][] {
  const H = matrix.length;
  if (H === 0) return matrix;
  const W = matrix[0].length;
  if (W === 0) return matrix;

  // 배경 = 0(빈칸) + 지배적 단색(non-zero의 30% 초과 시 — 풀블리드 배경/테두리)
  const cnt = new Map<number, number>();
  let nz = 0;
  for (const row of matrix) for (const v of row) { cnt.set(v, (cnt.get(v) || 0) + 1); if (v !== 0) nz++; }
  const bg = new Set<number>([0]);
  let topV = 0, topC = 0;
  for (const [v, c] of cnt) if (v !== 0 && c > topC) { topC = c; topV = v; }
  if (topV && topC > 0.3 * nz) bg.add(topV);
  const isBg = (v: number) => bg.has(v);

  const colProf = new Array<number>(W).fill(0);
  const rowProf = new Array<number>(H).fill(0);
  for (let r = 0; r < H; r++) for (let c = 0; c < W; c++) if (!isBg(matrix[r][c])) { colProf[c]++; rowProf[r]++; }
  if (!rowProf.some((v) => v > 0)) return matrix; // 콘텐츠 없음 → 그대로

  // 최장 원형 빈 구간 직후 인덱스(=콘텐츠 시작)
  const contentStart = (prof: number[], n: number): number => {
    let bestStart = 0, bestLen = 0, i = 0;
    const d = prof.concat(prof);
    while (i < n) {
      if (d[i] === 0) { let j = i; while (j < i + n && d[j] === 0) j++; if (j - i > bestLen) { bestLen = j - i; bestStart = i % n; } i = j; }
      else i++;
    }
    return (bestStart + bestLen) % n;
  };
  const dx = contentStart(colProf, W);
  const dy = contentStart(rowProf, H);

  // 콘텐츠를 (0,0)으로 roll
  const rolled: number[][] = [];
  for (let r = 0; r < H; r++) {
    const row = new Array<number>(W);
    for (let c = 0; c < W; c++) row[c] = matrix[(r + dy) % H][(c + dx) % W];
    rolled.push(row);
  }

  // 콘텐츠 폭/높이(콘텐츠는 0에서 시작) → toroidal roll로 중앙 정렬
  let maxC = 0, maxR = 0;
  for (let r = 0; r < H; r++) for (let c = 0; c < W; c++) if (!isBg(rolled[r][c])) { if (c > maxC) maxC = c; if (r > maxR) maxR = r; }
  const cw = maxC + 1, rh = maxR + 1;
  const sx = Math.max(0, Math.floor((W - cw) / 2));
  const sy = Math.max(0, Math.floor((H - rh) / 2));
  const out: number[][] = [];
  for (let r = 0; r < H; r++) {
    const row = new Array<number>(W);
    for (let c = 0; c < W; c++) row[c] = rolled[((r - sy) % H + H) % H][((c - sx) % W + W) % W];
    out.push(row);
  }
  return out;
}

// ───────────────────────────────────────────────────────────
// Main pipeline
// ───────────────────────────────────────────────────────────
export async function snapImageToGridAndPaletteV2(
  inputBase64: string,
  opts: SnapV2Options,
): Promise<SnapV2Result> {
  const { cols, rows, transparentBg = false } = opts;
  // Oversample K so anti-aliasing edge pixels get their own clusters
  // instead of polluting interior-color clusters. Final count is compressed
  // back to targetColorCount after cell-mode voting.
  const targetFinalColors = opts.targetColorCount && opts.targetColorCount > 0
    ? Math.min(28, opts.targetColorCount) : 0;
  const k = Math.max(
    8,
    Math.min(16, targetFinalColors > 0 ? targetFinalColors * 2 : 8),
  );
  // K→28 mapping is always open (all 28 palette). allowedIds is NOT enforced here —
  // the reviewer's design is "let unfake produce accurate colors; human edits palette_mapping if wrong".
  const allPaletteIds = Array.from({ length: 28 }, (_, i) => i + 1);

  // 1) decode to raw RGBA
  const inputBuf = Buffer.from(inputBase64, "base64");
  const img = sharp(inputBuf).ensureAlpha();
  const { data, info } = await img.raw().toBuffer({ resolveWithObject: true });
  const srcW = info.width;
  const srcH = info.height;
  const channels = info.channels;

  // 2) collect opaque pixel histogram (for median-cut) — downsample if image is huge
  const histogram = new Map<number, number>();
  const allUniqueBefore = new Set<string>();
  const step = srcW * srcH > 200_000 ? 2 : 1; // stride-2 sampling for big images
  for (let py = 0; py < srcH; py += step) {
    for (let px = 0; px < srcW; px += step) {
      const offset = (py * srcW + px) * channels;
      const alpha = channels >= 4 ? data[offset + 3] : 255;
      if (alpha < 128) continue;
      const r = data[offset], g = data[offset + 1], b = data[offset + 2];
      allUniqueBefore.add(`${r},${g},${b}`);
      const key = (r << 16) | (g << 8) | b;
      histogram.set(key, (histogram.get(key) || 0) + 1);
    }
  }

  const pixels: Pixel[] = [];
  for (const [key, count] of histogram) {
    pixels.push({
      r: (key >> 16) & 0xff,
      g: (key >> 8) & 0xff,
      b: key & 0xff,
      count,
    });
  }

  // 3) median-cut → K clean colors
  const kPalette = medianCut(pixels, k);
  const kLab = kPalette.map(([r, g, b]) => rgbToLab(r, g, b));

  // helper: nearest K index (1-based) for an RGB pixel
  function nearestKIndex(r: number, g: number, b: number): number {
    const lab = rgbToLab(r, g, b);
    let bestIdx = 0, bestDist = Infinity;
    for (let i = 0; i < kLab.length; i++) {
      const d = labDistSq(lab, kLab[i]);
      if (d < bestDist) { bestDist = d; bestIdx = i; }
    }
    return bestIdx + 1; // 1-based; 0 = empty cell
  }

  // 4) per-cell mode on K indices
  const kMatrix: number[][] = [];
  let cellsAnalyzed = 0;

  for (let r = 0; r < rows; r++) {
    const rowArr: number[] = [];
    const cellYStart = Math.floor((r * srcH) / rows);
    const cellYEnd = Math.floor(((r + 1) * srcH) / rows);
    for (let c = 0; c < cols; c++) {
      const cellXStart = Math.floor((c * srcW) / cols);
      const cellXEnd = Math.floor(((c + 1) * srcW) / cols);

      const kCounts = new Map<number, number>();
      let transparentCount = 0;
      let opaqueCount = 0;

      for (let py = cellYStart; py < cellYEnd; py++) {
        for (let px = cellXStart; px < cellXEnd; px++) {
          const offset = (py * srcW + px) * channels;
          const alpha = channels >= 4 ? data[offset + 3] : 255;
          if (alpha < 128) { transparentCount++; continue; }
          opaqueCount++;
          const kIdx = nearestKIndex(data[offset], data[offset + 1], data[offset + 2]);
          kCounts.set(kIdx, (kCounts.get(kIdx) || 0) + 1);
        }
      }

      let winnerKIdx = 0;
      if (transparentBg && transparentCount > opaqueCount) {
        winnerKIdx = 0;
      } else {
        let bestCount = 0;
        for (const [idx, count] of kCounts) {
          if (count > bestCount) { bestCount = count; winnerKIdx = idx; }
        }
        if (winnerKIdx === 0) winnerKIdx = 1; // fallback — shouldn't happen with opaque cell
      }
      rowArr.push(winnerKIdx);
      cellsAnalyzed++;
    }
    kMatrix.push(rowArr);
  }

  // 5) K → 28-palette mapping (one decision per K index).
  // Use RGB Euclidean here (not Lab) — Lab over-weighs lightness for sparse palettes,
  // producing surprises like "green → white" when the allowed set has no green.
  // RGB matches V1's behavior in the match step; the unfake benefit comes from the
  // upstream K-clustering (AA removal), not from the metric choice.
  const paletteMapping: Record<number, number> = {};
  for (let i = 0; i < kPalette.length; i++) {
    const kIdx = i + 1;
    if (opts.paletteOverride && opts.paletteOverride[kIdx]) {
      paletteMapping[kIdx] = opts.paletteOverride[kIdx];
      continue;
    }
    const [kr, kg, kb] = kPalette[i];
    // 팔레트 강제 시 의도 색만 후보로 (없으면 전체 28색 — 기존 동작)
    const candidates = (opts.forcePalette && opts.allowedIds && opts.allowedIds.length > 0)
      ? opts.allowedIds : allPaletteIds;
    // [2026-06-15] hue 계열 게이팅 매칭 (원복: HUE_GATE.enabled=false → 기존 RGB 최근접)
    paletteMapping[kIdx] = nearestPaletteHueGated(kr, kg, kb, candidates);
  }

  // 6) apply K→28 mapping to produce 28-palette matrix
  const matrix: number[][] = kMatrix.map((row) =>
    row.map((kIdx) => (kIdx === 0 ? 0 : paletteMapping[kIdx] || 1)),
  );

  // 6.5) compress to targetFinalColors by cell-frequency top-N + remap rare to nearest-of-top-N (RGB)
  if (targetFinalColors > 0) {
    const counts = new Map<number, number>();
    for (const r of matrix) for (const v of r) if (v !== 0) counts.set(v, (counts.get(v) || 0) + 1);
    if (counts.size > targetFinalColors) {
      const topN = Array.from(counts.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, targetFinalColors)
        .map(([id]) => id);
      const remapCache = new Map<number, number>();
      for (const r of matrix) {
        for (let i = 0; i < r.length; i++) {
          const v = r[i];
          if (v === 0 || topN.includes(v)) continue;
          let mapped = remapCache.get(v);
          if (mapped === undefined) {
            const p = GAME_PALETTE[v];
            // [2026-06-15] hue 게이팅 — top-N 압축 시에도 계열 보존(녹색→회색 방지)
            mapped = nearestPaletteHueGated(p[0], p[1], p[2], topN);
            remapCache.set(v, mapped);
          }
          r[i] = mapped;
        }
      }
      // also update paletteMapping so downstream consumers see the compressed palette
      for (const [kIdxStr, paletteId] of Object.entries(paletteMapping)) {
        if (!topN.includes(paletteId)) {
          paletteMapping[Number(kIdxStr)] = remapCache.get(paletteId) || paletteId;
        }
      }
    }
  }

  // 6.7) 토로이드 재정렬 — PixelLab wrap/offset 보정 (생성 이미지 중앙 정렬).
  // matrix 내용을 in-place 교체 → 이후 render/stats/return 모두 정렬본 사용.
  {
    const centered = recenterMatrixToroidal(matrix);
    matrix.length = 0;
    for (const row of centered) matrix.push(row);
  }

  // 7) render + stats
  const rendered = await renderMatrixToPng(matrix, { transparentBg });

  const uniqueAfter = new Set<number>();
  for (const r of matrix) for (const v of r) uniqueAfter.add(v);

  const dominantCounts = new Map<number, number>();
  for (const r of matrix) for (const v of r) if (v !== 0) dominantCounts.set(v, (dominantCounts.get(v) || 0) + 1);
  const dominantColors = Array.from(dominantCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([id]) => id);

  return {
    matrix,
    base64: rendered.base64,
    width: rendered.width,
    height: rendered.height,
    pixelsPerCell: rendered.pixelsPerCell,
    paletteMapping,
    kPalette,
    stats: {
      cellsAnalyzed,
      uniqueColorsBefore: allUniqueBefore.size,
      uniqueColorsAfter: uniqueAfter.size,
      dominantColors,
      k: kPalette.length,
      pipeline: "unfake_v1",
    },
  };
}
