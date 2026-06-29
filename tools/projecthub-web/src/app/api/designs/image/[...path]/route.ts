import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const runtime = "nodejs";

const STORAGE_DIR = process.env.DESIGNS_STORAGE_DIR || "/home/aimed/projecthub-web/data/designs";

/**
 * 이미지 파일 서빙. 인증 필요 (proxy.ts가 이 경로도 감시).
 * 경로 예: /api/designs/image/2026-04-24/abc-0-xx.png
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path: segments } = await params;
  if (!segments || segments.length === 0) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  // 경로 검증 — .. 금지
  const joined = segments.join("/");
  if (joined.includes("..") || joined.startsWith("/")) {
    return NextResponse.json({ error: "invalid path" }, { status: 400 });
  }
  const abs = path.resolve(STORAGE_DIR, joined);
  if (!abs.startsWith(path.resolve(STORAGE_DIR))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  try {
    const buf = await fs.readFile(abs);
    const ext = path.extname(abs).toLowerCase();
    const mime =
      ext === ".png" ? "image/png" :
      ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" :
      ext === ".webp" ? "image/webp" :
      "application/octet-stream";
    return new NextResponse(new Uint8Array(buf), {
      headers: {
        "Content-Type": mime,
        "Cache-Control": "private, max-age=86400",
      },
    });
  } catch {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
}
