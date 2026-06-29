import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const runtime = "nodejs";

const STORAGE_DIR = process.env.LEVELS_STORAGE_DIR || "/home/aimed/projecthub-web/data/levels";

/**
 * 레벨 PNG 파일 서빙. proxy.ts가 인증 처리.
 * 경로 예: /api/levels/image/2026-04-28/<id>.png
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path: segments } = await params;
  if (!segments || segments.length === 0) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

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
    return new NextResponse(new Uint8Array(buf), {
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "private, max-age=86400",
      },
    });
  } catch {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
}
