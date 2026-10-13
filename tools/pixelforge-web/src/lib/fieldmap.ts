import sharp from "sharp";
import { GAME_PALETTE } from "./palette";

// ─────────────────────────────────────────────────────────────────────────────
// [2026-06-15 색상매칭 개선] 탁한 색(예: 초원 풀색)이 순수 RGB 유클리드 거리로
// 회색(24)·검정(8)에 빨려가는 문제 수정. → 제작 이미지(초록)와 저장 JSON 레벨(회색)
// 디자인 불일치 발생. 원인: 팔레트에 "중간 톤 녹색"이 없어 honest 최근접이 무채색이 됨.
// 해결: hue(색조) 계열을 1차 게이팅한 뒤, 그 계열 안에서만 RGB 최근접을 고른다.
//       ("초록 계열이면 초록 후보 중에서만 선택" — 결정론적, AI 비전 불필요)
//
// ▼▼ 원복(ROLLBACK) 방법 ▼▼
//   USE_HUE_GATE = false  → 즉시 기존 순수-RGB 동작으로 복귀 (아래 nearestColorLegacy와 동일).
//   완전 제거하려면 이 주석 블록과 신규 함수를 지우고
//   nearestColorLegacy 를 nearestColor 로 이름만 되돌리면 원본과 100% 동일.
//
// 튜닝 파라미터(검증된 기본값 — 탁한 풀색 4종 → 초록/연초록, 진짜 회색은 회색 유지):
//   PX_NEUTRAL_FLOOR=18  HUE_WINDOW=50  PAL_NEUTRAL_FLOOR=20
// 참고: snapToGrid.ts / snapToGridV2.ts 의 nearestPaletteId 도 동일한 RGB-유클리드라
//       같은 증상 있음 — 필요 시 동일 패치 적용(이번 변경 범위 아님).
// ─────────────────────────────────────────────────────────────────────────────
const USE_HUE_GATE = true;       // ← false 로 바꾸면 원복(순수 RGB 유클리드)
const PX_NEUTRAL_FLOOR = 18;     // 픽셀 chroma(max-min)가 이 값 미만이면 "무채색"으로 취급
const HUE_WINDOW = 50;           // 같은 색 계열로 묶는 hue 허용 범위(deg)
const PAL_NEUTRAL_FLOOR = 20;    // 팔레트 색의 chroma가 이 값 미만이면 무채색 후보로 분류

function rgbHue(r: number, g: number, b: number): number {
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), c = mx - mn;
  if (c === 0) return 0;
  let h: number;
  if (mx === r) h = ((g - b) / c) % 6;
  else if (mx === g) h = (b - r) / c + 2;
  else h = (r - g) / c + 4;
  h *= 60;
  return h < 0 ? h + 360 : h;
}
function hueDist(a: number, b: number): number {
  const d = Math.abs(a - b) % 360;
  return Math.min(d, 360 - d);
}

// 팔레트 1회 전처리: hue / chroma / 무채색 여부 캐싱
const PAL_ENTRIES = Object.entries(GAME_PALETTE).map(([id, rgb]) => {
  const [r, g, b] = rgb;
  const chroma = Math.max(r, g, b) - Math.min(r, g, b);
  return { id: parseInt(id), r, g, b, hue: rgbHue(r, g, b), chroma, neutral: chroma < PAL_NEUTRAL_FLOOR };
});
type PalEntry = (typeof PAL_ENTRIES)[number];

function pickNearest(r: number, g: number, b: number, cands: PalEntry[]): number {
  let bestId = cands[0]?.id || 1;
  let bestDist = Infinity;
  for (const p of cands) {
    const d = (r - p.r) ** 2 + (g - p.g) ** 2 + (b - p.b) ** 2;
    if (d < bestDist) { bestDist = d; bestId = p.id; }
  }
  return bestId;
}

// [LEGACY] 기존 순수 RGB 유클리드 최근접 — 원복용으로 보존(미사용)
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function nearestColorLegacy(r: number, g: number, b: number, allowedIds?: number[]): number {
  const candidates = allowedIds && allowedIds.length > 0
    ? PAL_ENTRIES.filter((p) => allowedIds.includes(p.id))
    : PAL_ENTRIES;
  return pickNearest(r, g, b, candidates);
}

function nearestColor(r: number, g: number, b: number, allowedIds?: number[]): number {
  const base = allowedIds && allowedIds.length > 0
    ? PAL_ENTRIES.filter((p) => allowedIds.includes(p.id))
    : PAL_ENTRIES;
  if (base.length === 0) return 1;

  // 원복 스위치: 끄면 기존 순수-RGB 동작
  if (!USE_HUE_GATE) return pickNearest(r, g, b, base);

  // 1차: hue 계열 게이팅
  const chroma = Math.max(r, g, b) - Math.min(r, g, b);
  let cands: PalEntry[];
  if (chroma < PX_NEUTRAL_FLOOR) {
    // 무채색 픽셀 → 무채색 팔레트끼리만 (후보 없으면 전체로 폴백)
    cands = base.filter((p) => p.neutral);
    if (cands.length === 0) cands = base;
  } else {
    // 유채색 픽셀 → 같은 hue 계열(유채색)만. 없으면 유채색 전체, 그래도 없으면 전체.
    const h = rgbHue(r, g, b);
    cands = base.filter((p) => !p.neutral && hueDist(h, p.hue) < HUE_WINDOW);
    if (cands.length === 0) cands = base.filter((p) => !p.neutral);
    if (cands.length === 0) cands = base;
  }
  // 2차: 계열 안에서 RGB 최근접
  return pickNearest(r, g, b, cands);
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
