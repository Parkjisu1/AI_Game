// 이미지 생성 관련 공유 유틸

// PixelLab pixflux 허용 범위: 32~400.
// 픽셀-퍼펙트 그리드: 셀 1개 = 정확히 N픽셀 → image_size = (cols × N, rows × N)
const TARGET_LONG = 128;
const MIN = 32;
const MAX = 400;

export function computeImageSize(cols: number, rows: number): {
  width: number;
  height: number;
  pixelsPerCell: number;
} {
  if (!Number.isFinite(cols) || cols <= 0) cols = 20;
  if (!Number.isFinite(rows) || rows <= 0) rows = 20;
  const maxDim = Math.max(cols, rows);

  // pixelsPerCell 후보: 1~10, TARGET_LONG에 가장 가까운 값으로 픽셀-퍼펙트 보장
  // 단 결과가 MIN~MAX 범위 내에 있어야 함
  let bestPpc = 1;
  let bestDiff = Infinity;
  for (let ppc = 1; ppc <= 10; ppc++) {
    const longSide = maxDim * ppc;
    if (longSide < MIN || longSide > MAX) continue;
    const diff = Math.abs(longSide - TARGET_LONG);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestPpc = ppc;
    }
  }
  // 후보가 전혀 없으면 (예: maxDim=500) → 비율만 맞춰 클램핑
  if (bestDiff === Infinity) {
    const w = Math.min(MAX, Math.max(MIN, Math.round((cols / maxDim) * TARGET_LONG)));
    const h = Math.min(MAX, Math.max(MIN, Math.round((rows / maxDim) * TARGET_LONG)));
    return { width: w, height: h, pixelsPerCell: 0 };
  }

  return {
    width: cols * bestPpc,
    height: rows * bestPpc,
    pixelsPerCell: bestPpc,
  };
}

// colorIds 배열을 maxColors로 제한 (앞에서 N개 사용)
// maxColors가 0/undefined면 그대로 반환
export function limitColors(colorIds: number[], maxColors?: number): number[] {
  if (!maxColors || maxColors <= 0 || maxColors >= colorIds.length) return colorIds;
  // 균등 샘플링 (앞에서 자르지 않고 분포 유지)
  const step = colorIds.length / maxColors;
  const out: number[] = [];
  for (let i = 0; i < maxColors; i++) {
    out.push(colorIds[Math.floor(i * step)]);
  }
  return out;
}

// 1~28 전체 팔레트에서 무작위 N개 선택 (시드 없이)
export function randomPalette(n: number): number[] {
  const all = Array.from({ length: 28 }, (_, i) => i + 1);
  for (let i = all.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [all[i], all[j]] = [all[j], all[i]];
  }
  return all.slice(0, Math.max(1, Math.min(28, n)));
}
