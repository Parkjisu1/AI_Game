/**
 * 9-slice 모드 후처리 — gpt-image-2가 만든 이미지에서 키 색상(마젠타/시안)을
 * 알파 0으로 바꿔 투명 배경 PNG로 저장. Unity 9-slice import 시 중앙이 비어있어야
 * 의미 있는 패널이 됨.
 *
 * 동작:
 *   1. 이미지 중앙 32x32 패치 평균 RGB 계산 → 키 색상 자동 감지
 *      - magenta (R>180, G<80, B>180)
 *      - cyan    (R<80, G>180, B>180)
 *      - 둘 다 아니면 후처리 스킵
 *   2. 모든 픽셀 순회, 키 색상과 Euclidean 거리 < threshold이면 alpha=0
 *   3. PNG로 in-place 재저장
 */
import sharp from "sharp";

interface RGB { r: number; g: number; b: number }

function detectKeyColor(samples: RGB[]): RGB | null {
  // 평균
  const n = samples.length;
  if (n === 0) return null;
  const avg = samples.reduce(
    (acc, s) => ({ r: acc.r + s.r, g: acc.g + s.g, b: acc.b + s.b }),
    { r: 0, g: 0, b: 0 }
  );
  avg.r /= n; avg.g /= n; avg.b /= n;
  // magenta
  if (avg.r > 180 && avg.g < 80 && avg.b > 180) {
    return { r: 255, g: 0, b: 255 };
  }
  // cyan
  if (avg.r < 80 && avg.g > 180 && avg.b > 180) {
    return { r: 0, g: 255, b: 255 };
  }
  // detected nothing keyable
  return null;
}

function colorDistance(p: RGB, key: RGB): number {
  const dr = p.r - key.r;
  const dg = p.g - key.g;
  const db = p.b - key.b;
  return Math.sqrt(dr * dr + dg * dg + db * db);
}

export interface ChromaKeyResult {
  applied: boolean;
  keyColor?: "magenta" | "cyan";
  keyedPixels?: number;
  totalPixels?: number;
  reason?: string;
}

/**
 * 키 색상 자동 감지 후 chroma key 적용. 키 색상 미발견 시 원본 유지.
 * 거리 임계값 기본 80 (255 스케일).
 */
export async function applyChromaKey(
  filePath: string,
  threshold = 80,
): Promise<ChromaKeyResult> {
  let raw: { data: Buffer; info: sharp.OutputInfo };
  try {
    raw = await sharp(filePath).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  } catch (e) {
    return { applied: false, reason: `read failed: ${(e as Error).message}` };
  }

  const { data, info } = raw;
  const { width, height, channels } = info;
  if (channels !== 4) {
    return { applied: false, reason: `expected 4 channels, got ${channels}` };
  }

  // 중앙 32x32 패치 샘플링
  const samples: RGB[] = [];
  const cx = Math.floor(width / 2);
  const cy = Math.floor(height / 2);
  for (let y = cy - 16; y < cy + 16; y++) {
    for (let x = cx - 16; x < cx + 16; x++) {
      const idx = (y * width + x) * 4;
      samples.push({ r: data[idx], g: data[idx + 1], b: data[idx + 2] });
    }
  }
  const key = detectKeyColor(samples);
  if (!key) {
    return { applied: false, reason: "no chroma key color detected in center" };
  }

  // 모든 픽셀 순회 — 키 색상 근처는 알파 0
  let keyed = 0;
  const totalPixels = width * height;
  for (let i = 0; i < data.length; i += 4) {
    const p = { r: data[i], g: data[i + 1], b: data[i + 2] };
    if (colorDistance(p, key) < threshold) {
      data[i + 3] = 0;
      keyed++;
    }
  }

  // 다시 PNG로 저장
  try {
    await sharp(data, { raw: { width, height, channels: 4 } })
      .png()
      .toFile(filePath + ".tmp");
    // atomic-ish replace
    const fs = await import("fs/promises");
    await fs.rename(filePath + ".tmp", filePath);
  } catch (e) {
    return { applied: false, reason: `write failed: ${(e as Error).message}` };
  }

  return {
    applied: true,
    keyColor: key.r > 200 && key.b > 200 && key.g < 50 ? "magenta" : "cyan",
    keyedPixels: keyed,
    totalPixels,
  };
}
