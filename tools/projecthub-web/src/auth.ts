import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

/**
 * Google OAuth + 이메일 화이트리스트 기반 인증.
 *
 * 허용 목록 소스(OR 합집합):
 *   1. env ALLOWED_EMAILS — 안전망/부트스트랩용 (본인 계정)
 *   2. MongoDB projecthub_settings.allowed_users — UI에서 관리자 편집
 * 프로덕션은 fail-closed: env 또는 DB에 최소 1건 이상 필수. 둘 다 비면 모든 로그인 거부.
 * 명시적 dev 모드만 AUTH_DISABLED=true 또는 ALLOW_OPEN_DEFAULT=true로 개방 가능.
 *
 * 환경변수:
 *   AUTH_SECRET, AUTH_TRUST_HOST, AUTH_URL
 *   AUTH_GOOGLE_ID, AUTH_GOOGLE_SECRET
 *   ALLOWED_EMAILS — 쉼표 구분 (예: a@x.com,b@x.com)
 *   ADMIN_EMAILS   — 쉼표 구분, /api/admin/* 접근 가능한 관리자
 *   AUTH_DISABLED  — "true"면 모든 요청 통과 (로컬 dev 전용)
 */

function parseCsv(val: string | undefined): string[] {
  return (val || "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

export const authDisabled = process.env.AUTH_DISABLED === "true";

export function isAdminEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  return parseCsv(process.env.ADMIN_EMAILS).includes(email.toLowerCase());
}

async function loadDbAllowedEmails(): Promise<string[]> {
  try {
    const { getDb } = await import("@/lib/mongodb");
    const db = await getDb();
    const doc = await db
      .collection("projecthub_settings")
      .findOne({ key: "allowed_users" });
    const raw = (doc?.emails || []) as unknown[];
    return raw
      .filter((e): e is string => typeof e === "string")
      .map((e) => e.trim().toLowerCase())
      .filter(Boolean);
  } catch {
    return [];
  }
}

async function isEmailAllowed(email: string): Promise<boolean> {
  const lower = email.toLowerCase();
  const envList = parseCsv(process.env.ALLOWED_EMAILS);
  const dbList = await loadDbAllowedEmails();
  const total = new Set([...envList, ...dbList]);
  if (total.size === 0) {
    // Fail-closed: dev 환경 외엔 거부. 명시적 ALLOW_OPEN_DEFAULT=true 일 때만 개방.
    if (process.env.ALLOW_OPEN_DEFAULT === "true" || process.env.NODE_ENV !== "production") {
      console.warn("[auth] allowlist empty — open default ENABLED (dev or ALLOW_OPEN_DEFAULT=true)");
      return true;
    }
    console.error("[auth] allowlist empty in production — denying all logins (fail-closed)");
    return false;
  }
  return total.has(lower);
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
    }),
  ],
  session: { strategy: "jwt" },
  trustHost: true,
  callbacks: {
    async signIn({ user }) {
      const email = (user?.email || "").toLowerCase();
      if (!email) return false;
      return await isEmailAllowed(email);
    },
    async jwt({ token, user }) {
      if (user?.email) token.email = user.email;
      return token;
    },
    async session({ session, token }) {
      if (token?.email && session.user) {
        session.user.email = String(token.email);
      }
      return session;
    },
  },
});
