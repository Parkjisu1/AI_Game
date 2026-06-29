// 색 ID 매트릭스 → PNG base64
// sharp를 사용하여 raw RGBA 버퍼에서 PNG 생성
import sharp from "sharp";
import { GAME_PALETTE } from "./palette";
import { computeImageSize } from "./genUtils";

// 셀 1개 = ppc × ppc 픽셀로 확대 렌더링
export async function renderMatrixToPng(
  matrix: number[][],
  options: { transparentBg?: boolean } = {}
): Promise<{ base64: string; width: number; height: number; pixelsPerCell: number }> {
  const rows = matrix.length;
  const cols = rows > 0 ? matrix[0].length : 0;
  if (rows === 0 || cols === 0) {
    throw new Error("Empty matrix");
  }

  const { width, height, pixelsPerCell } = computeImageSize(cols, rows);
  const ppc = pixelsPerCell > 0 ? pixelsPerCell : Math.max(1, Math.floor(width / cols));
  const transparent = options.transparentBg === true;

  // RGBA 버퍼 생성
  const channels = 4;
  const buf = Buffer.alloc(width * height * channels);

  for (let py = 0; py < height; py++) {
    const cellY = Math.min(rows - 1, Math.floor(py / ppc));
    const row = matrix[cellY];
    for (let px = 0; px < width; px++) {
      const cellX = Math.min(cols - 1, Math.floor(px / ppc));
      const colorId = row[cellX] || 0;
      const offset = (py * width + px) * channels;
      if (colorId === 0) {
        // 빈 셀 — 투명 또는 흰색
        if (transparent) {
          buf[offset] = 0;
          buf[offset + 1] = 0;
          buf[offset + 2] = 0;
          buf[offset + 3] = 0;
        } else {
          buf[offset] = 255;
          buf[offset + 1] = 255;
          buf[offset + 2] = 255;
          buf[offset + 3] = 255;
        }
      } else {
        const rgb = GAME_PALETTE[colorId] || [128, 128, 128];
        buf[offset] = rgb[0];
        buf[offset + 1] = rgb[1];
        buf[offset + 2] = rgb[2];
        buf[offset + 3] = 255;
      }
    }
  }

  const png = await sharp(buf, {
    raw: { width, height, channels: 4 },
  })
    .png({ compressionLevel: 9 })
    .toBuffer();

  return {
    base64: png.toString("base64"),
    width,
    height,
    pixelsPerCell: ppc,
  };
}

// 매트릭스를 게임 FieldMap 텍스트 형식으로 변환
// "07 07 .. 07\n.. 07 ..\n..."
export function matrixToFieldMap(matrix: number[][]): string {
  return matrix
    .map((row) =>
      row
        .map((id) => (id === 0 ? ".." : String(id).padStart(2, "0")))
        .join(" ")
    )
    .join("\n");
}
