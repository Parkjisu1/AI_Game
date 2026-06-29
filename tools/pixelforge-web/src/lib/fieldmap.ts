import sharp from "sharp";
import { GAME_PALETTE } from "./palette";

const PAL_ENTRIES = Object.entries(GAME_PALETTE).map(([id, rgb]) => ({
  id: parseInt(id),
  r: rgb[0], g: rgb[1], b: rgb[2],
}));

function nearestColor(r: number, g: number, b: number, allowedIds?: number[]): number {
  const candidates = allowedIds && allowedIds.length > 0
    ? PAL_ENTRIES.filter((p) => allowedIds.includes(p.id))
    : PAL_ENTRIES;

  let bestId = candidates[0]?.id || 1;
  let bestDist = Infinity;
  for (const p of candidates) {
    const d = (r - p.r) ** 2 + (g - p.g) ** 2 + (b - p.b) ** 2;
    if (d < bestDist) { bestDist = d; bestId = p.id; }
  }
  return bestId;
}

export async function imageToFieldMap(
  base64: string,
  cols: number,
  rows: number,
  allowedColorIds?: number[]
): Promise<string> {
  const clean = base64.replace(/^data:image\/\w+;base64,/, "");
  const buf = Buffer.from(clean, "base64");

  const { data } = await sharp(buf)
    .resize(cols, rows, { fit: "fill" })
    .flatten({ background: { r: 128, g: 128, b: 128 } })
    .raw()
    .toBuffer({ resolveWithObject: true });

  const ch = 3;

  function getPixel(x: number, y: number) {
    const i = (y * cols + x) * ch;
    return { r: data[i], g: data[i + 1], b: data[i + 2] };
  }

  // 배경색 추정: 4 코너 + 4 변 중앙 = 8곳 평균
  const samples = [
    getPixel(0, 0), getPixel(cols-1, 0), getPixel(0, rows-1), getPixel(cols-1, rows-1),
    getPixel(Math.floor(cols/2), 0), getPixel(Math.floor(cols/2), rows-1),
    getPixel(0, Math.floor(rows/2)), getPixel(cols-1, Math.floor(rows/2)),
  ];
  const bgR = samples.reduce((s, c) => s + c.r, 0) / samples.length;
  const bgG = samples.reduce((s, c) => s + c.g, 0) / samples.length;
  const bgB = samples.reduce((s, c) => s + c.b, 0) / samples.length;

  // 1단계: 모든 셀 색상 매핑
  const grid: number[][] = [];
  for (let y = 0; y < rows; y++) {
    const row: number[] = [];
    for (let x = 0; x < cols; x++) {
      const p = getPixel(x, y);
      const bgDist = (p.r - bgR) ** 2 + (p.g - bgG) ** 2 + (p.b - bgB) ** 2;
      if (bgDist < 1500) {
        row.push(0); // 빈 셀
      } else {
        row.push(nearestColor(p.r, p.g, p.b, allowedColorIds));
      }
    }
    grid.push(row);
  }

  // 2단계: 고립 셀 제거 (주변 4셀 중 2개 이상 빈 셀이면 → 빈 셀로)
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      if (grid[y][x] === 0) continue;
      let emptyNeighbors = 0;
      const dirs = [[-1,0],[1,0],[0,-1],[0,1]];
      for (const [dy, dx] of dirs) {
        const ny = y + dy, nx = x + dx;
        if (ny < 0 || ny >= rows || nx < 0 || nx >= cols || grid[ny][nx] === 0) {
          emptyNeighbors++;
        }
      }
      if (emptyNeighbors >= 3) grid[y][x] = 0; // 3면 이상 빈 셀이면 고립 → 제거
    }
  }

  // 3단계: FieldMap 텍스트 생성
  const lines: string[] = [];
  for (let y = 0; y < rows; y++) {
    const tokens: string[] = [];
    for (let x = 0; x < cols; x++) {
      const v = grid[y][x];
      tokens.push(v === 0 ? ".." : String(v).padStart(2, "0"));
    }
    lines.push(tokens.join(" "));
  }

  return lines.join("\n");
}
