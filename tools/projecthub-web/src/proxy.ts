import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { auth, authDisabled } from "@/auth";

/**
 * 1) Rate limit (모든 요청, 인증 전 단계) — 단일 인스턴스 in-memory bucket.
 * 2) 인증 게이트 (페이지/일반 API).
 *
 * AUTH_DISABLED=true 이면 인증만 통과시키고 rate limit은 여전히 적용.
 */

// ──────────────────────────────────────────
// In-memory rate limiter (token bucket)
// ──────────────────────────────────────────
type Bucket = { count: number; resetAt: number };
const buckets = new Map<string, Bucket>();
const MAX_KEYS = 10_000;

interface Tier { windowMs: number; max: number; label: string }

function tierFor(pathname: string): Tier {
  // /api/auth/* 가장 엄격 — login brute force 방어선
  if (pathname.startsWith("/api/auth/")) return { windowMs: 60_000, max: 30, label: "auth" };
  // Slack webhook — 시그니처 검증은 별도, DoS 방어
  if (pathname.startsWith("/api/slack/")) return { windowMs: 60_000, max: 60, label: "slack" };
  // 일반 API — 5명 내부 도구라 매우 완화
  if (pathname.startsWith("/api/")) return { windowMs: 60_000, max: 600, label: "api" };
  // 페이지 — 보수적
  return { windowMs: 60_000, max: 1_000, label: "page" };
}

function getIP(req: NextRequest): string {
  const xff = req.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0].trim();
  const xri = req.headers.get("x-real-ip");
  if (xri) return xri.trim();
  return "unknown";
}

function applyRateLimit(req: NextRequest): NextResponse | null {
  const tier = tierFor(req.nextUrl.pathname);
  const key = `${getIP(req)}:${tier.label}`;
  const now = Date.now();

  // GC: 폭주 방지
  if (buckets.size > MAX_KEYS) {
    for (const [k, v] of buckets) {
      if (v.resetAt < now) buckets.delete(k);
      if (buckets.size <= MAX_KEYS / 2) break;
    }
  }

  let b = buckets.get(key);
  if (!b || b.resetAt < now) {
    b = { count: 0, resetAt: now + tier.windowMs };
    buckets.set(key, b);
  }
  b.count += 1;

  if (b.count > tier.max) {
    const retrySec = Math.max(1, Math.ceil((b.resetAt - now) / 1000));
    return new NextResponse(
      JSON.stringify({ error: "rate_limited", retry_after: retrySec, tier: tier.label }),
      {
        status: 429,
        headers: {
          "Content-Type": "application/json",
          "Retry-After": String(retrySec),
          "X-RateLimit-Limit": String(tier.max),
          "X-RateLimit-Remaining": "0",
          "X-RateLimit-Reset": String(Math.floor(b.resetAt / 1000)),
        },
      },
    );
  }
  return null;
}

function attachRateHeaders(res: NextResponse, req: NextRequest): NextResponse {
  const tier = tierFor(req.nextUrl.pathname);
  const key = `${getIP(req)}:${tier.label}`;
  const b = buckets.get(key);
  if (b) {
    res.headers.set("X-RateLimit-Limit", String(tier.max));
    res.headers.set("X-RateLimit-Remaining", String(Math.max(0, tier.max - b.count)));
    res.headers.set("X-RateLimit-Reset", String(Math.floor(b.resetAt / 1000)));
  }
  return res;
}

// ──────────────────────────────────────────
// Proxy entrypoint
// ──────────────────────────────────────────
export async function proxy(req: NextRequest) {
  // 1. Rate limit (먼저). 429면 즉시 반환.
  const limited = applyRateLimit(req);
  if (limited) return limited;

  // 2. 인증 우회 경로: /api/auth/* (NextAuth 자체), /api/slack/events (Slack webhook).
  //    이 경로들은 매처가 포함하지만 auth() 통과 없이 다음으로.
  const path = req.nextUrl.pathname;
  if (path.startsWith("/api/auth/") || path.startsWith("/api/slack/events")) {
    return attachRateHeaders(NextResponse.next(), req);
  }

  if (authDisabled) return attachRateHeaders(NextResponse.next(), req);

  // 3. Hermes 내부 호출 — pre-shared key
  const expectedKey = process.env.HERMES_INTERNAL_API_KEY || "";
  if (expectedKey) {
    const authHeader = (req.headers.get("authorization") || "").trim();
    const bearer = authHeader.toLowerCase().startsWith("bearer ")
      ? authHeader.slice(7).trim()
      : "";
    const customKey = req.headers.get("x-hermes-key") || "";
    const presented = bearer || customKey;
    if (presented && presented === expectedKey) {
      return attachRateHeaders(NextResponse.next(), req);
    }
  }

  // 4. 세션 체크
  const session = await auth();
  if (session?.user?.email) return attachRateHeaders(NextResponse.next(), req);

  // 5. 미인증 처리
  if (path.startsWith("/api/")) {
    return new NextResponse(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  const url = req.nextUrl.clone();
  const callback = url.pathname + url.search;
  url.pathname = "/api/auth/signin";
  url.search = `?callbackUrl=${encodeURIComponent(callback || "/")}`;
  return NextResponse.redirect(url);
}

export const config = {
  // SSE는 long-lived → 라우트 자체에서 auth() 처리. 정적 자산도 제외.
  // /api/auth/* 와 /api/slack/events 는 매처에 포함하여 rate limit만 적용.
  matcher: [
    "/((?!api/tasks/stream|api/agents/sessions/stream|_next/static|_next/image|pixelforge/_next|favicon\.ico|.*\.(?:png|jpg|jpeg|gif|svg|webp|ico|woff|woff2|ttf|eot|css|js|map)$).*)",
  ],
};
