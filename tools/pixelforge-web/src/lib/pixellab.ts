// PixelLab API v2 client
// Schema verified against https://api.pixellab.ai/v2/openapi.json
//
// Primary endpoint: generate-image-v2 (async, style_image + style_options)
// Fallback: create-image-pixflux (sync, lower quality)

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

function stripDataUrlPrefix(s: string): string {
  return s.startsWith("data:") ? s.split(",")[1] || s : s;
}

// ===================================================================
// Balance
// ===================================================================

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

// ===================================================================
// generate-image-v2 (async, style_image 지원, color_palette: false)
// ===================================================================

export interface GenerateV2Options {
  apiKey?: string;
  noBackground?: boolean;
  seed?: number;
  // style_image — 스타일 레퍼런스 (형태/쉐이딩/디테일은 따라하되 색상은 안 따라함)
  styleImageBase64?: string;
  styleImageWidth?: number;
  styleImageHeight?: number;
}

// 비동기 요청 시작 → jobId 반환
export async function generateImageV2Start(
  prompt: string,
  width: number,
  height: number,
  options: GenerateV2Options = {}
): Promise<{ jobId: string; usage: unknown }> {
  const payload: Record<string, unknown> = {
    description: prompt,
    image_size: {
      width: Math.min(Math.max(width, 16), 792),
      height: Math.min(Math.max(height, 16), 688),
    },
    no_background: options.noBackground ?? false,
    // ★ style_options: 형태/디테일/쉐이딩은 따라하되, 색상은 무시
    style_options: {
      color_palette: false,
      outline: true,
      detail: true,
      shading: true,
    },
  };

  // style_image: ReferenceImage { image: Base64Image, size: { width, height } }
  if (options.styleImageBase64) {
    const b64 = stripDataUrlPrefix(options.styleImageBase64);
    payload.style_image = {
      image: { type: "base64", base64: b64, format: "png" } satisfies Base64Image,
      size: {
        width: options.styleImageWidth || 64,
        height: options.styleImageHeight || 64,
      },
    };
  }

  if (typeof options.seed === "number") payload.seed = options.seed;

  const res = await fetch(`${API}/generate-image-v2`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${getKey(options.apiKey)}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`PixelLab v2 ${res.status}: ${text.substring(0, 500)}`);
  }

  const data = await res.json();
  return {
    jobId: data.background_job_id,
    usage: data.usage,
  };
}

// ===================================================================
// Job 폴링
// ===================================================================

export async function pollBackgroundJob(
  jobId: string,
  apiKey?: string,
  options: { maxWaitMs?: number; intervalMs?: number } = {}
): Promise<{ status: string; lastResponse: Record<string, unknown> | null }> {
  const maxWait = options.maxWaitMs || 45000;
  const interval = options.intervalMs || 4000;
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
    await new Promise((r) => setTimeout(r, interval));
  }
  throw new Error(`PixelLab job timeout (${maxWait}ms) — job ${jobId} still processing`);
}

// ===================================================================
// pixflux (sync, fallback — Free key용)
// ===================================================================

export type PixelLabView = "side" | "low top-down" | "high top-down";
export type PixelLabDirection =
  | "north" | "north-east" | "east" | "south-east"
  | "south" | "south-west" | "west" | "north-west";
export type PixelLabOutline =
  | "single color black outline" | "single color outline" | "selective outline" | "lineless";
export type PixelLabShading =
  | "flat shading" | "basic shading" | "medium shading" | "detailed shading" | "highly detailed shading";
export type PixelLabDetail = "low detail" | "medium detail" | "highly detailed";

export interface PixelLabStyleOptions {
  apiKey?: string;
  noBackground?: boolean;
  view?: PixelLabView;
  direction?: PixelLabDirection;
  outline?: PixelLabOutline;
  shading?: PixelLabShading;
  detail?: PixelLabDetail;
  isometric?: boolean;
  textGuidanceScale?: number;
  seed?: number;
}

export async function generateImagePixflux(
  prompt: string,
  width: number,
  height: number,
  options: PixelLabStyleOptions = {}
): Promise<{ base64: string; usage: unknown }> {
  const payload: Record<string, unknown> = {
    description: prompt,
    image_size: {
      width: Math.min(Math.max(width, 16), 400),
      height: Math.min(Math.max(height, 16), 400),
    },
    no_background: options.noBackground === true,
  };

  if (options.view !== undefined) payload.view = options.view;
  if (options.direction !== undefined) payload.direction = options.direction;
  if (options.outline !== undefined) payload.outline = options.outline;
  if (options.shading !== undefined) payload.shading = options.shading;
  if (options.detail !== undefined) payload.detail = options.detail;
  if (options.isometric !== undefined) payload.isometric = options.isometric;
  if (options.textGuidanceScale !== undefined) payload.text_guidance_scale = options.textGuidanceScale;
  if (typeof options.seed === "number") payload.seed = options.seed;

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
    throw new Error(`PixelLab pixflux ${res.status}: ${text.substring(0, 500)}`);
  }

  const data = await res.json();
  let base64: string = data?.image?.base64 || "";
  if (base64.startsWith("data:")) base64 = base64.split(",")[1] || base64;
  return { base64, usage: data.usage };
}

// Backwards compat alias
export const generateImage = generateImagePixflux;
export type GenerateOptions = PixelLabStyleOptions;
