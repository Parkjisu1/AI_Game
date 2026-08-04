import { NextRequest, NextResponse } from "next/server";
import { auth, authDisabled } from "@/auth";

/**
 * 미리보기 앱의 API 프록시 — `/preview-api/*` → `https://qa-api.newplay.store/*`
 *
 * 왜 필요한가:
 *   미리보기 문서는 우리 오리진에서 뜨는데, 앱이 qa-api.newplay.store 를 직접 부르면
 *   cross-origin 이라 CORS 에 막힌다. 실제로 그래서 화면이 비어 있었다:
 *     "Access to fetch at 'https://qa-api.newplay.store/api/payment/level/policies'
 *      from origin '...' has been blocked by CORS policy"
 *   상대 서버(회사 QA)의 CORS 허용 목록을 건드리는 건 공용 환경을 바꾸는 일이라 하지 않는다.
 *   대신 우리가 중계하면 브라우저 입장에서 same-origin 이 되어 CORS 자체가 성립하지 않는다.
 *
 * 안전장치:
 *   - 대상 호스트를 qa-api.newplay.store 로 **고정**한다(경로만 받는다). 임의 프록시가 되면 안 된다.
 *   - 로그인 필요 — 비로그인에게 사내 QA API 를 열어주지 않는다.
 *   - 우리 세션 쿠키는 전달하지 않는다. 앱은 Authorization 헤더를 쓰므로 그것만 넘긴다.
 */
export const dynamic = "force-dynamic";

const UPSTREAM = "https://qa-api.newplay.store";
const PASS_REQ = ["authorization", "content-type", "accept", "accept-language", "x-requested-with"];
const PASS_RES = ["content-type", "cache-control", "newplay-total-count"];

async function handle(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> }) {
  if (!authDisabled) {
    const s = await auth();
    if (!s?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { path: seg } = await ctx.params;
  const rel = (seg || []).join("/");
  const qs = new URL(req.url).search;
  const target = `${UPSTREAM}/${rel}${qs}`;

  const headers = new Headers();
  for (const k of PASS_REQ) {
    const v = req.headers.get(k);
    if (v) headers.set(k, v);
  }

  let body: BodyInit | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await req.arrayBuffer();
  }

  try {
    const r = await fetch(target, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
      signal: AbortSignal.timeout(30_000),
    });
    const buf = await r.arrayBuffer();
    const out = new Headers();
    for (const k of PASS_RES) {
      const v = r.headers.get(k);
      if (v) out.set(k, v);
    }
    out.set("Cache-Control", "no-store");
    return new NextResponse(buf, { status: r.status, headers: out });
  } catch (e: unknown) {
    return NextResponse.json(
      { error: "upstream 실패", detail: e instanceof Error ? e.message : String(e) },
      { status: 502 },
    );
  }
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const HEAD = handle;
