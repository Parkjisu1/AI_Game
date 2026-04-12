// PixelLab API v2 client
// Schema verified against https://api.pixellab.ai/v2/openapi.json (CreateImagePixfluxRequest)
//
// Field name reference (DO NOT GUESS — verify against openapi.json):
//   - no_background: boolean         (transparent background)
//   - color_image: Base64Image       (palette restriction; PNG containing target colors)
//   - init_image: Base64Image        ({type:"base64", base64:"...", format:"png"})
//   - init_image_strength: int 1~999 (default 300; NOT a 0~1 float)
//   - outline/shading/detail/view/direction: enum strings (see below)
//   - oblique_projection: NOT in schema, do not send

import sharp from "sharp";
import { GAME_PALETTE } from "./palette";

const API = "https://api.pixellab.ai/v2";

function getKey(override?: string) {
  const key = override || process.env.PIXELLAB_API_KEY;
  if (!key) throw new Error("PIXELLAB_API_KEY not set");
  return key;
}

// PixelLab Base64Image schema
interface Base64Image {
  type: "base64";
  base64: string;
  format: "png";
}

// Style enum values — these MUST match the API exactly (full strings)
export type PixelLabView = "side" | "low top-down" | "high top-down";

export type PixelLabDirection =
  | "north" | "north-east" | "east" | "south-east"
  | "south" | "south-west" | "west" | "north-west";

export type PixelLabOutline =
  | "single color black outline"
  | "single color outline"
  | "selective outline"
  | "lineless";

export type PixelLabShading =
  | "flat shading"
  | "basic shading"
  | "medium shading"
  | "detailed shading"
  | "highly detailed shading";

export type PixelLabDetail = "low detail" | "medium detail" | "highly detailed";

export type BackgroundRemovalTask =
  | "remove_simple_background"
  | "remove_complex_background";

export interface PixelLabStyleOptions {
  apiKey?: string;
  noBackground?: boolean;
  backgroundRemovalTask?: BackgroundRemovalTask;
  // init_image — pass raw base64 (without data: prefix); we wrap it as Base64Image
  initImageBase64?: string;
  initImageStrength?: number; // integer 1~999, default 300
  // Style guidance
  view?: PixelLabView;
  direction?: PixelLabDirection;
  outline?: PixelLabOutline;
  shading?: PixelLabShading;
  detail?: PixelLabDetail;
  isometric?: boolean;
  textGuidanceScale?: number; // 1~20, default 8
  seed?: number;
}

// Backwards-compat alias
export type GenerateOptions = PixelLabStyleOptions;

export async function getBalance(apiKey?: string) {
  const res = await fetch(`${API}/balance`, {
    headers: { Authorization: `Bearer ${getKey(apiKey)}` },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PixelLab balance ${res.status}: ${text.substring(0, 200)}`);
  }
  return res.json();
}

// Build a Base64Image PNG containing the target palette colors.
// PixelLab uses this image to restrict generation to ONLY these colors.
// We render each color as an 8x8 block stacked horizontally.
async function colorIdsToColorImage(colorIds: number[]): Promise<Base64Image | null> {
  const colors = colorIds
    .map((id) => GAME_PALETTE[id])
    .filter((c): c is [number, number, number] => Array.isArray(c));

  if (colors.length === 0) return null;

  const blockSize = 8;
  const width = colors.length * blockSize;
  const height = blockSize;
  const channels = 3;
  const buffer = Buffer.alloc(width * height * channels);

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const colorIdx = Math.floor(x / blockSize);
      const [r, g, b] = colors[colorIdx];
      const offset = (y * width + x) * channels;
      buffer[offset] = r;
      buffer[offset + 1] = g;
      buffer[offset + 2] = b;
    }
  }

  const png = await sharp(buffer, {
    raw: { width, height, channels: 3 },
  })
    .png()
    .toBuffer();

  return {
    type: "base64",
    base64: png.toString("base64"),
    format: "png",
  };
}

function stripDataUrlPrefix(s: string): string {
  return s.startsWith("data:") ? s.split(",")[1] || s : s;
}

export async function generateImage(
  prompt: string,
  width: number,
  height: number,
  colorIds?: number[],
  options: GenerateOptions = {}
): Promise<{ base64: string; usage: unknown }> {
  const payload: Record<string, unknown> = {
    description: prompt,
    image_size: {
      width: Math.min(Math.max(width, 32), 400),
      height: Math.min(Math.max(height, 32), 400),
    },
    no_background: options.noBackground === true,
  };

  // color_image 비활성화 — PixelLab이 자유롭게 고퀄리티로 생성하도록 허용
  // 색상 제한은 snap-to-grid 후처리에서 28색 팔레트로 매핑 (이중 제한 방지)

  // init_image: Base64Image (NOT {image, width, height})
  if (options.initImageBase64) {
    const b64 = stripDataUrlPrefix(options.initImageBase64);
    payload.init_image = {
      type: "base64",
      base64: b64,
      format: "png",
    } satisfies Base64Image;
    if (typeof options.initImageStrength === "number") {
      // Schema: integer 1~999, default 300
      const v = Math.round(options.initImageStrength);
      payload.init_image_strength = Math.max(1, Math.min(999, v));
    }
  }

  // Optional style guidance — only include if explicitly set
  if (options.view !== undefined) payload.view = options.view;
  if (options.direction !== undefined) payload.direction = options.direction;
  if (options.outline !== undefined) payload.outline = options.outline;
  if (options.shading !== undefined) payload.shading = options.shading;
  if (options.detail !== undefined) payload.detail = options.detail;
  if (options.isometric !== undefined) payload.isometric = options.isometric;
  if (options.textGuidanceScale !== undefined) payload.text_guidance_scale = options.textGuidanceScale;
  if (typeof options.seed === "number") payload.seed = options.seed;
  if (options.backgroundRemovalTask !== undefined) {
    payload.background_removal_task = options.backgroundRemovalTask;
  }

  const res = await fetch(`${API}/create-image-pixflux`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${getKey(options.apiKey)}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PixelLab ${res.status}: ${text.substring(0, 500)}`);
  }

  const data = await res.json();
  // Response: { image: { type: "base64", base64: "..." }, usage: { credits } }
  let base64: string = data?.image?.base64 || "";
  if (base64.startsWith("data:")) {
    base64 = base64.split(",")[1] || base64;
  }
  return { base64, usage: data.usage };
}

// ===================================================================
// Pro endpoint: generate-image-v2 (async, style_image 지원)
// ===================================================================

export interface ProGenerateOptions {
  apiKey?: string;
  noBackground?: boolean;
  seed?: number;
  // style_image — 스타일 레퍼런스 (base64 PNG)
  styleImageBase64?: string;
  styleImageWidth?: number;
  styleImageHeight?: number;
  // generate-with-style-v2: 텍스트 스타일 설명
  styleDescription?: string;
  // subject reference 이미지 (최대 4개)
  referenceImages?: Array<{ base64: string; width: number; height: number }>;
}

export interface ProGenerateResult {
  base64: string; // 첫 번째 이미지
  allImages: string[]; // 전체 (grid split)
  usage: unknown;
  jobId: string;
}

// 1. Pro 생성 요청 (비동기 — job ID 반환)
// generate-with-style-v2: style_images + description + style_description
// style_description으로 텍스트 스타일 지시 가능 (generate-image-v2보다 정확)
export async function generateImageProStart(
  prompt: string,
  width: number,
  height: number,
  options: ProGenerateOptions = {}
): Promise<{ jobId: string; usage: unknown }> {
  // StyleImage schema: { image: Base64Image, width, height }
  const styleImages: Array<Record<string, unknown>> = [];
  if (options.styleImageBase64) {
    const b64 = stripDataUrlPrefix(options.styleImageBase64);
    styleImages.push({
      image: { type: "base64", base64: b64, format: "png" } satisfies Base64Image,
      width: options.styleImageWidth || width,
      height: options.styleImageHeight || height,
    });
  }

  const payload: Record<string, unknown> = {
    description: prompt,
    image_size: {
      width: Math.min(Math.max(width, 16), 512),
      height: Math.min(Math.max(height, 16), 512),
    },
    no_background: options.noBackground ?? true,
    style_images: styleImages,
    // ★ style_description — 텍스트로 스타일 지시 (핵심 차별점)
    style_description: options.styleDescription ||
      "modern casual mobile puzzle game, cute chibi pixel art, clean outlines, soft shading, vibrant colors",
  };

  if (typeof options.seed === "number") payload.seed = options.seed;

  const res = await fetch(`${API}/generate-with-style-v2`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${getKey(options.apiKey)}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PixelLab Pro ${res.status}: ${text.substring(0, 500)}`);
  }

  const data = await res.json();
  return {
    jobId: data.background_job_id,
    usage: data.usage,
  };
}

// 2. Job 폴링 — status가 completed/failed가 될 때까지 반복
export async function pollBackgroundJob(
  jobId: string,
  apiKey?: string,
  options: { maxWaitMs?: number; intervalMs?: number } = {}
): Promise<{ status: string; lastResponse: Record<string, unknown> | null }> {
  const maxWait = options.maxWaitMs || 45000; // 45초 (snap + save에 15초 여유)
  const interval = options.intervalMs || 4000; // 4초 간격
  const startTime = Date.now();

  while (Date.now() - startTime < maxWait) {
    const res = await fetch(`${API}/background-jobs/${encodeURIComponent(jobId)}`, {
      headers: { Authorization: `Bearer ${getKey(apiKey)}` },
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`PixelLab job poll ${res.status}: ${text.substring(0, 300)}`);
    }
    const data = await res.json();
    if (data.status === "completed") {
      return { status: "completed", lastResponse: data.last_response || null };
    }
    if (data.status === "failed") {
      throw new Error(`PixelLab job failed: ${JSON.stringify(data.last_response || {}).substring(0, 300)}`);
    }
    // 아직 processing → 대기
    await new Promise((r) => setTimeout(r, interval));
  }
  throw new Error(`PixelLab job timeout (${maxWait}ms) — job ${jobId} still processing`);
}

// 3. Pro 생성 전체 (start + poll + extract images)
export async function generateImagePro(
  prompt: string,
  width: number,
  height: number,
  options: ProGenerateOptions = {}
): Promise<ProGenerateResult> {
  // Step 1: 요청 시작
  const { jobId, usage } = await generateImageProStart(prompt, width, height, options);

  // Step 2: 폴링
  const { lastResponse } = await pollBackgroundJob(jobId, options.apiKey);

  // Step 3: 이미지 추출
  // last_response 구조: { images: [Base64Image] } 또는 grid image
  let allImages: string[] = [];

  if (lastResponse) {
    // images 배열인 경우
    if (Array.isArray(lastResponse.images)) {
      allImages = (lastResponse.images as Array<{ base64?: string }>)
        .map((img) => {
          let b64 = img.base64 || "";
          if (b64.startsWith("data:")) b64 = b64.split(",")[1] || b64;
          return b64;
        })
        .filter((b) => b.length > 0);
    }
    // image 단일 객체인 경우
    else if (lastResponse.image) {
      let b64 = (lastResponse.image as { base64?: string }).base64 || "";
      if (b64.startsWith("data:")) b64 = b64.split(",")[1] || b64;
      if (b64) allImages = [b64];
    }
  }

  if (allImages.length === 0) {
    throw new Error(`PixelLab Pro: 이미지 없음. job response keys: ${Object.keys(lastResponse || {}).join(", ")}`);
  }

  return {
    base64: allImages[0], // 첫 번째 이미지 사용
    allImages,
    usage,
    jobId,
  };
}
