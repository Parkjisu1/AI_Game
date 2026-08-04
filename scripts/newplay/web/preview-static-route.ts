import { NextRequest, NextResponse } from "next/server";
import { auth, authDisabled } from "@/auth";
import { promises as fs } from "fs";
import path from "path";

/**
 * 수정안 미리보기 정적 서빙 — `~/newplay-preview/serve` 의 빌드 산출물을 그대로 내보낸다.
 *
 * 왜 Next 가 직접 서빙하나:
 *   별도 포트로 띄우면 iframe 이 cross-origin 이 되어 CSP frame-src 를 또 열어야 한다.
 *   같은 오리진에서 내보내면 그럴 일이 없고, 로그인 가드도 그대로 적용된다.
 *   (미리보기는 사내 화면이라 비로그인 노출을 막아야 한다)
 *
 * SPA 라우팅: 파일이 없으면 index.html 로 폴백한다 — /preview/:gameSlug/order 같은
 * 클라이언트 라우트는 디스크에 파일이 없다.
 */
export const dynamic = "force-dynamic";

const ROOT = path.join(process.env.HOME || "/home/aimed", "newplay-preview", "serve");

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

export async function GET(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> }) {
  if (!authDisabled) {
    const s = await auth();
    if (!s?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { path: seg } = await ctx.params;
  const rel = (seg || []).join("/");

  // 경로 탈출 차단 — resolve 후 ROOT 밖이면 거부한다.
  const target = path.resolve(ROOT, rel);
  if (target !== ROOT && !target.startsWith(ROOT + path.sep)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  let file = target;
  try {
    const st = await fs.stat(file);
    if (st.isDirectory()) file = path.join(file, "index.html");
  } catch {
    // 없는 경로 — 에셋이면 404, 그 외에는 SPA 폴백
    if (/\.[a-z0-9]{2,5}$/i.test(rel)) {
      return NextResponse.json({ error: "not found" }, { status: 404 });
    }
    file = path.join(ROOT, "index.html");
  }

  try {
    const buf = await fs.readFile(file);
    const ext = path.extname(file).toLowerCase();
    return new NextResponse(new Uint8Array(buf), {
      headers: {
        "Content-Type": MIME[ext] || "application/octet-stream",
        // 미리보기는 매번 최신이어야 한다. 재빌드했는데 옛 화면이 보이면 쓸모가 없다.
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "미리보기 빌드가 아직 없습니다. preview-build.sh 를 먼저 실행하세요." },
      { status: 404 },
    );
  }
}
