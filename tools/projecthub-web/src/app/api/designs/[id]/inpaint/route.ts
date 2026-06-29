import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, isAdminEmail } from "@/auth";
import { ObjectId } from "mongodb";
import { promises as fs } from "fs";
import path from "path";
import { randomUUID } from "crypto";

export const runtime = "nodejs";
export const maxDuration = 120;

const STORAGE_DIR = process.env.DESIGNS_STORAGE_DIR || "/home/aimed/projecthub-web/data/designs";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";
const OPENAI_BASE_URL = "https://api.openai.com";

/**
 * 인페인팅 (부분 재생성) — 마스크 영역만 새 프롬프트로 재생성.
 *
 * Body (multipart/form-data):
 *   - design_id: 원본 디자인 ID (path param에서)
 *   - filename: 대상 이미지 파일명 (생략 시 첫 번째)
 *   - prompt: 새 프롬프트 (영문 권장)
 *   - mask: PNG 파일 — 알파 채널이 0인 영역이 "재생성될 부분", 불투명한 영역은 보존
 *
 * 동작:
 *   1. 원본 PNG + 사용자 mask PNG → OpenAI /v1/images/edits
 *   2. 결과 새 PNG 저장
 *   3. 새 Design 도큐먼트 생성 (source_design_id로 원본 역참조)
 */
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  // 인증
  const authHeader = (req.headers.get("authorization") || "").trim();
  const bearerKey = authHeader.toLowerCase().startsWith("bearer ")
    ? authHeader.slice(7).trim()
    : "";
  const expectedKey = process.env.HERMES_INTERNAL_API_KEY || "";
  let email: string | null | undefined;
  if (bearerKey && expectedKey && bearerKey === expectedKey) {
    email = req.headers.get("x-hermes-on-behalf-of") || "hermes@aimed.local";
  } else {
    const session = await auth();
    email = session?.user?.email;
  }
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  if (!/^[a-f0-9]{24}$/.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  // 권한 확인
  const db = await getDb();
  const orig = await db.collection("pixelforge_designs").findOne({ _id: new ObjectId(id) });
  if (!orig) return NextResponse.json({ error: "design not found" }, { status: 404 });
  const isOwner = (orig.created_by_email || "").toLowerCase() === email.toLowerCase();
  if (!isOwner && !isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden — owner or admin only" }, { status: 403 });
  }

  // multipart 파싱
  const fd = await req.formData();
  const filename = String(fd.get("filename") || (orig.images?.[0]?.filename || ""));
  const prompt = String(fd.get("prompt") || "").trim().slice(0, 4000);
  const maskBlob = fd.get("mask") as Blob | null;
  if (!filename) return NextResponse.json({ error: "filename required" }, { status: 400 });
  if (!prompt) return NextResponse.json({ error: "prompt required" }, { status: 400 });
  if (!maskBlob) return NextResponse.json({ error: "mask file required" }, { status: 400 });

  const target = (orig.images || []).find((im: { filename: string }) => im.filename === filename);
  if (!target) return NextResponse.json({ error: "target image not found" }, { status: 400 });

  // 원본 이미지 + 마스크를 OpenAI edits 로 전달
  let openaiRes: Response;
  try {
    const imgBuf = await fs.readFile(path.join(STORAGE_DIR, filename));
    const maskBuf = Buffer.from(await maskBlob.arrayBuffer());

    const form = new FormData();
    form.append("model", "gpt-image-2");
    form.append("prompt", prompt);
    form.append("n", "1");
    form.append("size", `${target.width}x${target.height}`);
    form.append("quality", "high");
    form.append("input_fidelity", "high");
    form.append("image", new Blob([new Uint8Array(imgBuf)], { type: "image/png" }), "src.png");
    form.append("mask",  new Blob([new Uint8Array(maskBuf)], { type: "image/png" }), "mask.png");

    if (!OPENAI_API_KEY) {
      return NextResponse.json({ error: "OPENAI_API_KEY not configured" }, { status: 500 });
    }
    openaiRes = await fetch(`${OPENAI_BASE_URL}/v1/images/edits`, {
      method: "POST",
      headers: { Authorization: `Bearer ${OPENAI_API_KEY}` },
      body: form,
    });
  } catch (e) {
    return NextResponse.json({ error: `edits call failed: ${(e as Error).message}` }, { status: 502 });
  }

  if (!openaiRes.ok) {
    const errText = await openaiRes.text();
    return NextResponse.json(
      { error: `OpenAI ${openaiRes.status}: ${errText.slice(0, 400)}` },
      { status: 502 }
    );
  }
  const json = (await openaiRes.json()) as { data?: Array<{ b64_json?: string; url?: string }> };
  const out = json.data?.[0];
  if (!out || (!out.b64_json && !out.url)) {
    return NextResponse.json({ error: "no image in response" }, { status: 502 });
  }

  // 저장
  const today = new Date().toISOString().slice(0, 10);
  const dir = path.join(STORAGE_DIR, today);
  await fs.mkdir(dir, { recursive: true });
  const newId = new ObjectId();
  const uid = randomUUID().slice(0, 8);
  const newFilename = `${today}/${String(newId)}-inpaint-${uid}.png`;
  const dstAbs = path.join(STORAGE_DIR, newFilename);

  try {
    if (out.b64_json) {
      await fs.writeFile(dstAbs, Buffer.from(out.b64_json, "base64"));
    } else if (out.url) {
      const r = await fetch(out.url);
      const buf = Buffer.from(await r.arrayBuffer());
      await fs.writeFile(dstAbs, buf);
    }
  } catch (e) {
    return NextResponse.json({ error: `save failed: ${(e as Error).message}` }, { status: 500 });
  }

  // 새 Design 도큐먼트 (source_design_id로 원본 역참조)
  const newDoc = {
    _id: newId,
    prompt: `[Inpaint] ${prompt}`,
    user_prompt: prompt,
    parent_prompt: orig.prompt || orig.user_prompt || "",
    tags: Array.from(new Set([...(orig.tags || []), "inpaint", "post_processed"])),
    model: "gpt-image-2",
    size: `${target.width}x${target.height}`,
    n: 1,
    images: [{ filename: newFilename, width: target.width, height: target.height }],
    created_by_email: String(email).toLowerCase(),
    created_at: new Date().toISOString(),
    quality: "high",
    has_ref: true,
    reference_filename: filename,  // 인페인팅 원본을 참조 이미지로 표시
    source: "gallery",
    source_design_id: String(orig._id),
    inpaint: true,
  };
  await db.collection("pixelforge_designs").insertOne(newDoc);

  return NextResponse.json({
    ok: true,
    new_id: String(newId),
    new_filename: newFilename,
  });
}
