// 임의 이미지 → 셀 그리드 + 28색 팔레트로 강제 snap
// PixelLab 출력의 "블러/애매한 경계/팔레트 이탈" 문제를 해결
import sharp from "sharp";
import { GAME_PALETTE } from "./palette";
import { renderMatrixToPng } from "./matrixRenderer";

interface SnapOptions {
  cols: number;
  rows: number;
  allowedIds?: number[]; // 제한 없으면 1~28 전체
  transparentBg?: boolean;
  targetColorCount?: number; // 최대 N개로 축소 (빈도 상위 N개 유지, 나머지는 가까운 색으로 remap)
}

interface SnapResult {
  matrix: number[][];
  base64: string;
  width: number;
  height: number;
  pixelsPerCell: number;
  stats: {
    cellsAnalyzed: number;
    uniqueColorsBefore: number;
    uniqueColorsAfter: number;
    dominantColors: number[]; // 최종 사용된 color ID 배열 (빈도 내림차순)
  };
}

// 두 팔레트 ID의 RGB 거리 (가장 가까운 색 찾기용)
function paletteDistance(a: number, b: number): number {
  const pa = GAME_PALETTE[a];
  const pb = GAME_PALETTE[b];
  if (!pa || !pb) return Infinity;
  const dr = pa[0] - pb[0];
  const dg = pa[1] - pb[1];
  const db = pa[2] - pb[2];
  return dr * dr + dg * dg + db * db;
}

// 특정 색 ID를 주어진 허용 ID 집합에서 가장 가까운 것으로 remap
function nearestAllowedId(targetId: number, allowed: number[]): number {
  if (allowed.length === 0) return targetId;
  let best = allowed[0];
  let bestDist = paletteDistance(targetId, allowed[0]);
  for (let i = 1; i < allowed.length; i++) {
    const d = paletteDistance(targetId, allowed[i]);
    if (d < bestDist) {
      bestDist = d;
      best = allowed[i];
    }
  }
  return best;
}

// RGB → 가장 가까운 28색 중 하나의 ID
function nearestPaletteId(r: number, g: number, b: number, allowedIds: number[]): number {
  let bestId = allowedIds[0] || 1;
  let bestDist = Infinity;
  for (const id of allowedIds) {
    const pal = GAME_PALETTE[id];
    if (!pal) continue;
    const dr = r - pal[0];
    const dg = g - pal[1];
    const db = b - pal[2];
    const d = dr * dr + dg * dg + db * db;
    if (d < bestDist) {
      bestDist = d;
      bestId = id;
    }
  }
  return bestId;
}

// 이미지 base64를 셀 그리드 기반으로 분석하여 clean matrix + PNG 반환
export async function snapImageToGridAndPalette(
  inputBase64: string,
  opts: SnapOptions
): Promise<SnapResult> {
  const { cols, rows, transparentBg = false } = opts;
  const allowedIds =
    opts.allowedIds && opts.allowedIds.length > 0
      ? opts.allowedIds
      : Array.from({ length: 28 }, (_, i) => i + 1);

  // 1) sharp로 이미지 로드 + raw RGBA 추출
  const inputBuf = Buffer.from(inputBase64, "base64");
  const img = sharp(inputBuf).ensureAlpha();
  const { data, info } = await img.raw().toBuffer({ resolveWithObject: true });
  const srcW = info.width;
  const srcH = info.height;
  const channels = info.channels; // 4 (RGBA)

  // 2) 각 셀에 대해 가장 많이 나타나는 팔레트 색을 결정 (mode)
  const matrix: number[][] = [];
  let cellsAnalyzed = 0;
  const allUniqueBefore = new Set<string>();

  for (let r = 0; r < rows; r++) {
    const row: number[] = [];
    const cellYStart = Math.floor((r * srcH) / rows);
    const cellYEnd = Math.floor(((r + 1) * srcH) / rows);
    for (let c = 0; c < cols; c++) {
      const cellXStart = Math.floor((c * srcW) / cols);
      const cellXEnd = Math.floor(((c + 1) * srcW) / cols);

      // 셀 안의 모든 픽셀을 팔레트 ID로 매핑 + 투명 카운트
      const colorCounts = new Map<number, number>();
      let transparentCount = 0;
      let opaqueCount = 0;

      for (let py = cellYStart; py < cellYEnd; py++) {
        for (let px = cellXStart; px < cellXEnd; px++) {
          const offset = (py * srcW + px) * channels;
          const alpha = channels >= 4 ? data[offset + 3] : 255;
          if (alpha < 128) {
            transparentCount++;
            continue;
          }
          opaqueCount++;
          const red = data[offset];
          const green = data[offset + 1];
          const blue = data[offset + 2];
          allUniqueBefore.add(`${red},${green},${blue}`);
          const id = nearestPaletteId(red, green, blue, allowedIds);
          colorCounts.set(id, (colorCounts.get(id) || 0) + 1);
        }
      }

      // 투명이 절반 이상이면 빈 셀
      let winnerId = 0;
      if (transparentBg && transparentCount > opaqueCount) {
        winnerId = 0;
      } else {
        // 가장 많이 등장한 팔레트 색 선택
        let bestCount = 0;
        for (const [id, count] of colorCounts) {
          if (count > bestCount) {
            bestCount = count;
            winnerId = id;
          }
        }
        if (winnerId === 0) winnerId = allowedIds[0] || 1; // fallback
      }
      row.push(winnerId);
      cellsAnalyzed++;
    }
    matrix.push(row);
  }

  // 3) ★ 색상 수 축소 (targetColorCount 지정 시)
  // 전역 빈도 계산 → 상위 N개 유지 → 나머지는 가장 가까운 상위 색으로 remap
  let dominantColors: number[] = [];
  if (opts.targetColorCount && opts.targetColorCount > 0) {
    const globalCounts = new Map<number, number>();
    for (const r of matrix) {
      for (const v of r) {
        if (v === 0) continue;
        globalCounts.set(v, (globalCounts.get(v) || 0) + 1);
      }
    }
    // 빈도 내림차순 정렬
    const sorted = Array.from(globalCounts.entries()).sort((a, b) => b[1] - a[1]);
    dominantColors = sorted.slice(0, opts.targetColorCount).map(([id]) => id);

    if (dominantColors.length > 0 && globalCounts.size > dominantColors.length) {
      // 나머지 색상을 상위 N개 중 가장 가까운 색으로 remap
      const remapCache = new Map<number, number>();
      for (const r of matrix) {
        for (let i = 0; i < r.length; i++) {
          const v = r[i];
          if (v === 0 || dominantColors.includes(v)) continue;
          let mapped = remapCache.get(v);
          if (mapped === undefined) {
            mapped = nearestAllowedId(v, dominantColors);
            remapCache.set(v, mapped);
          }
          r[i] = mapped;
        }
      }
    }
  }

  // 4) matrix를 깨끗한 PNG로 렌더링
  const rendered = await renderMatrixToPng(matrix, { transparentBg });

  // unique color 통계
  const uniqueAfter = new Set<number>();
  for (const r of matrix) for (const v of r) uniqueAfter.add(v);
  if (dominantColors.length === 0) {
    // targetColorCount 미지정 시: 최종 매트릭스의 모든 색을 빈도순으로
    const counts = new Map<number, number>();
    for (const r of matrix) for (const v of r) if (v !== 0) counts.set(v, (counts.get(v) || 0) + 1);
    dominantColors = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]).map(([id]) => id);
  }

  return {
    matrix,
    base64: rendered.base64,
    width: rendered.width,
    height: rendered.height,
    pixelsPerCell: rendered.pixelsPerCell,
    stats: {
      cellsAnalyzed,
      uniqueColorsBefore: allUniqueBefore.size,
      uniqueColorsAfter: uniqueAfter.size,
      dominantColors,
    },
  };
}
