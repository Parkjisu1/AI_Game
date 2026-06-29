import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { ObjectId } from "mongodb";
import { promises as fs } from "fs";
import path from "path";
import { randomUUID } from "crypto";

export const runtime = "nodejs";
export const maxDuration = 120; // 이미지 생성은 최대 2분 소요

// 이미지 엔드포인트는 OpenAI 직접 호출 — LiteLLM proxy가 background/input_fidelity 같은
// 신규 파라미터를 핸들링 못 해서 500 (streaming body 에러). LLM 텍스트 호출만 LiteLLM 사용.
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const OPENAI_BASE_URL = "https://api.openai.com";
const LITELLM_URL = process.env.LITELLM_URL || "http://127.0.0.1:4000";
const LITELLM_KEY = process.env.LITELLM_MASTER_KEY || "sk-anything";
const STORAGE_DIR = process.env.DESIGNS_STORAGE_DIR || "/home/aimed/projecthub-web/data/designs";

/** 이미지 엔드포인트 호출용 base + key — OPENAI_API_KEY 있으면 직접, 없으면 LiteLLM 폴백 */
function imageApiTarget() {
  if (OPENAI_API_KEY) return { base: OPENAI_BASE_URL, key: OPENAI_API_KEY, direct: true };
  return { base: LITELLM_URL, key: LITELLM_KEY, direct: false };
}

interface GenerateBody {
  prompt: string;
  n?: number;
  size?: string;
  tags?: string[];
  quality?: "auto" | "high" | "medium" | "low" | "standard" | "hd";
  /** data URL (data:image/png;base64,...) — 있으면 images/edits 엔드포인트로 분기 */
  ref_image_base64?: string;
  /** Task에서 호출된 경우 — 양방향 추적용 */
  task_id?: string;
  task_title?: string;
  /** 9-slice 모드 — Unity Sprite Border 용 UI 이미지 생성 시 flat fill·noise 제거 가이드 자동 주입 */
  mode_9slice?: boolean;
  /** 9-slice 보더 픽셀 (기본 96) */
  border_px?: number;
}

// 두께 의도 정성 형용사 — gpt-image-2가 픽셀 수치(80px)를 정확히 따르지 않으므로
// thin/medium/thick 같은 단어로 보강하면 모델이 더 잘 따름
function thicknessHint(border: number, imageEdge = 1024): string {
  const ratio = (border / imageEdge) * 100;
  if (ratio < 5) return `very thin (about ${ratio.toFixed(1)}% of image width)`;
  if (ratio < 8) return `thin (about ${ratio.toFixed(1)}% of image width)`;
  if (ratio < 12) return `medium-thick (about ${ratio.toFixed(1)}% of image width)`;
  if (ratio < 18) return `thick (about ${ratio.toFixed(1)}% of image width)`;
  return `very thick chunky (about ${ratio.toFixed(1)}% of image width)`;
}

const NINE_SLICE_PREFIX = (border: number) => {
  const hint = thicknessHint(border);
  return `[9-SLICE MODE — Unity Sprite Border용 UI 패널 — STRUCTURAL RULES ONLY]

These are STRUCTURAL constraints only, not stylistic ones. The visual style
(material, color, era, theme) MUST come ENTIRELY from the user's prompt below.
Do NOT add sci-fi, futuristic, cyberpunk, metal, or any other aesthetic that
the user did not explicitly request. If the user says "wooden" make it wooden,
if "fabric" make it fabric, if "minimal flat" make it minimal flat, etc.

STRUCTURAL CONSTRAINTS (모양/구조만, 스타일 X):
- Border thickness: ${hint}. Decorative outer ring occupies this fraction of edge.
- Interior fill: a single uniform flat color in the WHOLE central region — use
  vivid magenta (#FF00FF) or bright cyan (#00FFFF) so post-processing can chroma-key
  it transparent. NO noise, NO gradient, NO texture, NO content of any kind inside.
- Sharp clean edges, top/bottom/left/right edges uniform along their length.
- Corners may have shape but follow the user's style — do not default to beveled
  metal unless explicitly asked.
- Output: square 1:1, single panel only — no labels, no extra decorations.
- Outside the panel: plain neutral background (also magenta or cyan, chroma-keyable).

User's style and content request (THIS DRIVES THE LOOK):
`;
};

interface DesignDoc {
  _id: InstanceType<typeof ObjectId>;
  prompt: string;
  tags: string[];
  model: string;
  size: string;
  n: number;
  images: Array<{ filename: string; width: number; height: number }>;
  created_by_email: string;
  created_at: string;
}

export async function POST(req: NextRequest) {
  // Hermes 내부 호출(서버 간, 쿠키 없음) 은 Authorization Bearer 또는 X-Hermes-Key 둘 다 허용.
  // Next.js 16 일부 환경에서 커스텀 X-* 헤더가 라우트 핸들러까지 도달하지 않는 케이스 회피용 fallback.
  const authHeader = (req.headers.get("authorization") || "").trim();
  const bearerKey = authHeader.toLowerCase().startsWith("bearer ")
    ? authHeader.slice(7).trim()
    : "";
  const customKey = req.headers.get("x-hermes-key") || "";
  const hermesKey = bearerKey || customKey;
  const expectedKey = process.env.HERMES_INTERNAL_API_KEY || "";
  let email: string | null | undefined;
  if (hermesKey && expectedKey && hermesKey === expectedKey) {
    const onBehalfOf = (req.headers.get("x-hermes-on-behalf-of") || "").trim().toLowerCase();
    email = onBehalfOf || "hermes@aimed.local";
  } else {
    const session = await auth();
    email = session?.user?.email;
  }
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  let body: GenerateBody;
  try {
    body = (await req.json()) as GenerateBody;
  } catch {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }

  const userPrompt = (body.prompt || "").trim();
  if (!userPrompt) return NextResponse.json({ error: "prompt required" }, { status: 400 });
  const n = Math.min(4, Math.max(1, body.n || 1));
  const quality = body.quality || "auto";
  let size = body.size || "auto";
  const tags = Array.isArray(body.tags) ? body.tags.filter((t) => typeof t === "string").slice(0, 10) : [];
  const hasRef = Boolean(body.ref_image_base64 && body.ref_image_base64.length > 100);

  // 9-slice 모드 — flat fill 가이드 prepend + tag 자동 주입 + size 정사각 강제
  const mode9 = Boolean(body.mode_9slice);
  let borderPx = Number(body.border_px) || 96;
  if (borderPx < 8) borderPx = 8;
  if (borderPx > 256) borderPx = 256;
  let prompt = userPrompt;
  if (mode9) {
    prompt = NINE_SLICE_PREFIX(borderPx) + userPrompt;
    if (size === "auto" || size.includes("x") && !size.startsWith("1024x1024")) {
      size = "1024x1024";  // 9-slice는 정사각이 표준
    }
    for (const t of ["9slice", "tileable", "ui_panel"]) {
      if (!tags.includes(t)) tags.push(t);
    }
  }

  // gpt-image-2 통일 — OpenAI 공식 사양상 background "transparent" 미지원이므로
  // 9-slice 모드도 동일 모델 사용. 투명 배경은 후처리(post-processing)로 별도 처리 권장.
  const modelName = "gpt-image-2";

  // 이미지 엔드포인트 호출 — 참조 이미지 있으면 /v1/images/edits, 없으면 /v1/images/generations
  let openaiRes: Response;
  try {
    if (hasRef) {
      // data URL의 base64 부분만 추출
      const raw = String(body.ref_image_base64);
      const b64 = raw.includes(",") ? raw.split(",", 2)[1] : raw;
      const mimeMatch = /^data:(image\/\w+);base64,/.exec(raw);
      const mime = mimeMatch ? mimeMatch[1] : "image/png";
      const ext = mime.split("/")[1] || "png";
      const imgBuf = Buffer.from(b64, "base64");

      const form = new FormData();
      form.append("model", modelName);
      form.append("prompt", prompt);
      form.append("n", String(n));
      if (size && size !== "auto") form.append("size", size);
      if (quality && quality !== "auto") form.append("quality", quality);
      // gpt-image-2는 background "transparent" 미지원 — opaque 또는 auto만. 9-slice 모드는
      // 후처리 단계에서 chroma key 또는 명시적 alpha mask로 투명화 처리해야 함.
      // input_fidelity는 gpt-image-2에서도 supported (edits 엔드포인트 한정).
      form.append("input_fidelity", "high");
      form.append("image", new Blob([new Uint8Array(imgBuf)], { type: mime }), `ref.${ext}`);

      const tgt = imageApiTarget();
      openaiRes = await fetch(`${tgt.base}/v1/images/edits`, {
        method: "POST",
        headers: { Authorization: `Bearer ${tgt.key}` },
        body: form,
      });
    } else {
      const payload: Record<string, unknown> = {
        model: modelName,
        prompt,
        n,
      };
      if (size && size !== "auto") payload.size = size;
      if (quality && quality !== "auto") payload.quality = quality;
      // gpt-image-2 background 옵션은 opaque/auto만 지원 — transparent 안 보냄.
      // 9-slice 모드는 후처리 단계에서 chroma key 기반으로 투명화 처리.

      const tgt = imageApiTarget();
      openaiRes = await fetch(`${tgt.base}/v1/images/generations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${tgt.key}`,
        },
        body: JSON.stringify(payload),
      });
    }
  } catch (e) {
    return NextResponse.json({ error: `LiteLLM 연결 실패: ${String(e)}` }, { status: 502 });
  }

  if (!openaiRes.ok) {
    const errText = await openaiRes.text();
    return NextResponse.json({ error: `OpenAI 에러 ${openaiRes.status}: ${errText.slice(0, 400)}` }, { status: 502 });
  }

  const json = (await openaiRes.json()) as {
    data?: Array<{ b64_json?: string; url?: string }>;
  };
  const rawImages = json.data || [];
  if (rawImages.length === 0) {
    return NextResponse.json({ error: "no images returned" }, { status: 502 });
  }

  // 날짜 폴더 + uuid 파일명으로 저장
  const today = new Date().toISOString().slice(0, 10);
  const dir = path.join(STORAGE_DIR, today);
  await fs.mkdir(dir, { recursive: true });

  const id = new ObjectId();
  const savedImages: DesignDoc["images"] = [];
  // size가 "auto" 일 수도 있고 "1024x1024" 일 수도. 일단 hint로만 쓰고 실제 값은 sharp이 측정.
  // (이전 버전: parseInt("auto") = NaN → height: undefined → DB에 None 저장돼 변환 시 클램프 깨짐)
  const sizeHint = size.split("x").map((x) => parseInt(x, 10));
  const wHint = sizeHint[0] && !isNaN(sizeHint[0]) ? sizeHint[0] : 1024;
  const hHint = sizeHint[1] && !isNaN(sizeHint[1]) ? sizeHint[1] : wHint;

  // 참조 이미지가 있으면 같은 날짜 폴더에 별도 저장 — 갤러리 상세에서 원본 비교용
  let referenceFilename: string | null = null;
  if (hasRef) {
    try {
      const raw = String(body.ref_image_base64);
      const refB64 = raw.includes(",") ? raw.split(",", 2)[1] : raw;
      const refMime = /^data:(image\/\w+);base64,/.exec(raw);
      const refExt = (refMime?.[1] || "image/png").split("/")[1] || "png";
      referenceFilename = `${today}/${String(id)}-ref-${randomUUID().slice(0, 8)}.${refExt}`;
      await fs.writeFile(
        path.join(STORAGE_DIR, referenceFilename),
        Buffer.from(refB64, "base64"),
      );
    } catch (e) {
      console.error("[designs/generate] ref save failed:", e);
      referenceFilename = null;
    }
  }

  for (let i = 0; i < rawImages.length; i++) {
    const img = rawImages[i];
    const uid = randomUUID().slice(0, 8);
    const filename = `${today}/${String(id)}-${i}-${uid}.png`;
    const absPath = path.join(STORAGE_DIR, filename);
    try {
      if (img.b64_json) {
        await fs.writeFile(absPath, Buffer.from(img.b64_json, "base64"));
      } else if (img.url) {
        const r = await fetch(img.url);
        if (!r.ok) throw new Error(`url fetch ${r.status}`);
        const buf = Buffer.from(await r.arrayBuffer());
        await fs.writeFile(absPath, buf);
      } else {
        continue;
      }

      // 9-slice 모드: 중앙 키 색상(마젠타/시안)을 알파 0으로 변환 (post-processing)
      if (mode9) {
        try {
          const { applyChromaKey } = await import("@/lib/chroma_key");
          const ck = await applyChromaKey(absPath);
          if (ck.applied) {
            console.log(`[designs/generate] chroma key applied (${ck.keyColor}): ${ck.keyedPixels}/${ck.totalPixels} pixels`);
          } else {
            console.log(`[designs/generate] chroma key skipped: ${ck.reason}`);
          }
        } catch (e) {
          console.error("[designs/generate] chroma_key failed:", e);
        }
      }

      // sharp으로 실제 width/height 측정해서 DB에 저장 — auto 사이즈 대응
      let realW = wHint, realH = hHint;
      try {
        const sharpMod = (await import("sharp")).default;
        const meta = await sharpMod(absPath).metadata();
        if (meta.width) realW = meta.width;
        if (meta.height) realH = meta.height;
      } catch (e) {
        console.error("[designs/generate] dimension probe failed:", e);
      }
      savedImages.push({ filename, width: realW, height: realH });
    } catch (e) {
      console.error("[designs/generate] save failed:", e);
    }
  }

  if (savedImages.length === 0) {
    return NextResponse.json({ error: "no images saved" }, { status: 502 });
  }

  const taskId = (body.task_id || "").trim();
  const taskTitle = (body.task_title || "").trim();
  const source = taskId ? "task" : "gallery";

  // task_id가 있으면 태그에 `task:<id>` 추가 (검색 편의)
  const finalTags = taskId ? Array.from(new Set([...tags, `task:${taskId.slice(-8)}`])) : tags;

  const doc: DesignDoc & {
    quality?: string;
    has_ref?: boolean;
    reference_filename?: string | null;
    source?: string;
    task_id?: string;
    task_title?: string;
    mode_9slice?: boolean;
    border_px?: number;
    user_prompt?: string;
  } = {
    _id: id,
    prompt,
    user_prompt: userPrompt,
    tags: finalTags,
    model: "gpt-image-2",
    size,
    n: savedImages.length,
    images: savedImages,
    created_by_email: String(email).toLowerCase(),
    created_at: new Date().toISOString(),
    quality,
    has_ref: hasRef,
    reference_filename: referenceFilename,
    source,
    task_id: taskId || undefined,
    task_title: taskTitle || undefined,
    mode_9slice: mode9 || undefined,
    border_px: mode9 ? borderPx : undefined,
  };

  const db = await getDb();
  await db.collection<DesignDoc>("pixelforge_designs").insertOne(doc);

  // Task 문서에도 역참조 — generated_design_ids에 이 design id 추가
  if (taskId) {
    try {
      const { ObjectId } = await import("mongodb");
      await db.collection("pixelforge_tasks").updateOne(
        { _id: new ObjectId(taskId) },
        {
          $addToSet: { generated_design_ids: String(id) },
          $set: { updated_at: new Date().toISOString() },
        }
      );
    } catch { /* ignore */ }
  }

  return NextResponse.json({
    ok: true,
    id: String(id),
    images: savedImages,
  });
}
