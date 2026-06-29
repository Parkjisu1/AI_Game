import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, isAdminEmail } from "@/auth";
import { ObjectId } from "mongodb";
import { promises as fs } from "fs";
import path from "path";
import { randomUUID } from "crypto";
import sharp from "sharp";

export const runtime = "nodejs";

const STORAGE_DIR = process.env.DESIGNS_STORAGE_DIR || "/home/aimed/projecthub-web/data/designs";

interface To9SliceBody {
  /** 동일 폭 보더(권장). 4면 모두 같은 값 */
  border_px?: number;
  /** 비대칭 보더 — 지정 시 4면 개별. border_px보다 우선 */
  border_top?: number;
  border_bottom?: number;
  border_left?: number;
  border_right?: number;
  /** 대상 이미지 파일명 (생략 시 첫 번째) */
  filename?: string;
}

/**
 * 이미 생성된 디자인의 이미지를 받아서 9-slice용 변형 이미지 생성:
 *  - 외곽 border 영역은 그대로 유지
 *  - 내부 중앙 영역은 alpha 0 (투명) 처리
 *  - 새 PNG 파일로 저장하고, 새 Design 도큐먼트로 갤러리에 등록
 *  - 원본은 보존 (source_design_id로 역참조)
 *
 * Body: { border_px?, border_top/bottom/left/right?, filename? }
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  // 인증 — 로그인 사용자 또는 hermes 키
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
    return NextResponse.json({ error: "invalid design id" }, { status: 400 });
  }

  const body = (await req.json().catch(() => null)) as To9SliceBody | null;
  if (!body) return NextResponse.json({ error: "invalid body" }, { status: 400 });

  const db = await getDb();
  const original = await db
    .collection("pixelforge_designs")
    .findOne({ _id: new ObjectId(id) });
  if (!original) {
    return NextResponse.json({ error: "design not found" }, { status: 404 });
  }

  // 권한: 생성자 또는 admin만
  const isOwner = (original.created_by_email || "").toLowerCase() === email.toLowerCase();
  if (!isOwner && !isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden — not owner or admin" }, { status: 403 });
  }

  // 대상 이미지 선택
  const images = (original.images as Array<{ filename: string; width: number; height: number }>) || [];
  if (images.length === 0) {
    return NextResponse.json({ error: "no images on this design" }, { status: 400 });
  }
  const target = body.filename
    ? images.find((im) => im.filename === body.filename)
    : images[0];
  if (!target) {
    return NextResponse.json({ error: "target image not found" }, { status: 400 });
  }

  // 원본 PNG 먼저 읽고 sharp이 측정한 실제 dimension 사용 — DB 메타(target.width/height)는
  // size:auto 로 생성된 이미지에서 height=None으로 저장된 케이스가 있어 신뢰할 수 없음
  const srcAbs = path.join(STORAGE_DIR, target.filename);
  let raw: { data: Buffer; info: sharp.OutputInfo };
  try {
    raw = await sharp(srcAbs).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  } catch (e) {
    return NextResponse.json({ error: `read failed: ${(e as Error).message}` }, { status: 500 });
  }
  const { data, info } = raw;
  const { width, height, channels } = info;
  if (channels !== 4) {
    return NextResponse.json({ error: `expected 4 channels, got ${channels}` }, { status: 500 });
  }

  // 보더 값 결정 — sharp이 측정한 실제 width/height 기준
  const def = Math.max(8, Math.min(512, Math.floor(body.border_px || 96)));
  const bTop    = clampBorder(body.border_top ?? def, height);
  const bBot    = clampBorder(body.border_bottom ?? def, height);
  const bLeft   = clampBorder(body.border_left ?? def, width);
  const bRight  = clampBorder(body.border_right ?? def, width);

  if (bTop + bBot >= height || bLeft + bRight >= width) {
    return NextResponse.json({
      error: `border too large — top+bottom(${bTop+bBot}) must be < image height(${height}); left+right(${bLeft+bRight}) must be < width(${width})`,
    }, { status: 400 });
  }

  // 중앙 영역(borderLeft <= x < width-borderRight, borderTop <= y < height-borderBottom) → alpha 0
  let zeroed = 0;
  for (let y = bTop; y < height - bBot; y++) {
    for (let x = bLeft; x < width - bRight; x++) {
      const idx = (y * width + x) * 4;
      data[idx + 3] = 0;
      zeroed++;
    }
  }

  // 새 파일명: 같은 날짜 폴더에 -9s 접미
  const today = new Date().toISOString().slice(0, 10);
  const dir = path.join(STORAGE_DIR, today);
  await fs.mkdir(dir, { recursive: true });
  const newId = new ObjectId();
  const uid = randomUUID().slice(0, 8);
  const newFilename = `${today}/${String(newId)}-9s-${uid}.png`;
  const dstAbs = path.join(STORAGE_DIR, newFilename);

  try {
    await sharp(data, { raw: { width, height, channels: 4 } }).png().toFile(dstAbs);
  } catch (e) {
    return NextResponse.json({ error: `write failed: ${(e as Error).message}` }, { status: 500 });
  }

  // 새 Design 도큐먼트 생성 (source_design_id로 원본 역참조)
  const newDoc = {
    _id: newId,
    prompt: `[9-Slice 변환] 원본: ${String(original._id).slice(-8)} · border ${bTop}/${bRight}/${bBot}/${bLeft}`,
    user_prompt: original.user_prompt || original.prompt || "",
    tags: Array.from(new Set([...(original.tags || []), "9slice", "post_processed"])),
    model: original.model || "gpt-image-2",
    size: `${width}x${height}`,
    n: 1,
    images: [{ filename: newFilename, width, height }],
    created_by_email: String(email).toLowerCase(),
    created_at: new Date().toISOString(),
    quality: original.quality,
    has_ref: false,
    reference_filename: null,
    source: "gallery",
    mode_9slice: true,
    border_px: def,
    border_top: bTop,
    border_bottom: bBot,
    border_left: bLeft,
    border_right: bRight,
    source_design_id: String(original._id),
  };

  await db.collection("pixelforge_designs").insertOne(newDoc);

  return NextResponse.json({
    ok: true,
    new_id: String(newId),
    new_filename: newFilename,
    zeroed_pixels: zeroed,
    total_pixels: width * height,
    border: { top: bTop, right: bRight, bottom: bBot, left: bLeft },
  });
}

function clampBorder(v: number, dim: number): number {
  const n = Math.max(0, Math.floor(v || 0));
  return Math.min(n, Math.floor(dim / 2) - 1);
}
