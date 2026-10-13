import { NextRequest, NextResponse } from "next/server";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { Readable } from "node:stream";
import path from "node:path";
import { assetDataRoot, assetUser } from "@/lib/asset-studio";

export const runtime = "nodejs";
const allowed: Record<string, string> = {
  "model-pack.zip": "application/zip", "preview.png": "image/png", "character_LOD0.glb": "model/gltf-binary",
  "report.json": "application/json", "manifest.json": "application/json", "research.json": "application/json",
  "input.png": "image/png", "input.jpg": "image/jpeg", "input.jpeg": "image/jpeg", "input.webp": "image/webp",
};
export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string; file: string }> }) {
  if (!await assetUser(_req)) return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  const { id, file } = await params;
  if (!/^[a-f0-9]{24}$/.test(id) || !Object.hasOwn(allowed, file)) return NextResponse.json({ error: "파일 없음" }, { status: 404 });
  const target = path.join(assetDataRoot, id, file);
  try {
    const info = await stat(target);
    return new NextResponse(Readable.toWeb(createReadStream(target)) as ReadableStream, { headers: {
      "Content-Type": allowed[file], "Content-Length": String(info.size), "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff", "Content-Disposition": `${file.endsWith(".zip") ? "attachment" : "inline"}; filename="${file}"`,
    } });
  } catch { return NextResponse.json({ error: "파일이 아직 준비되지 않았습니다." }, { status: 404 }); }
}
