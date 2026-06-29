import { NextRequest, NextResponse } from "next/server";
import { auth, isAdminEmail } from "@/auth";
import { getDb } from "@/lib/mongodb";

interface AllowedUsersDoc {
  key: string;
  emails?: string[];
  updated_at?: string;
}

/**
 * 허용 사용자 관리 API — 관리자(ADMIN_EMAILS) 전용.
 *
 * GET    /api/admin/allowed-users        → { emails: [...] }
 * POST   /api/admin/allowed-users        { email }  → 추가 (이미 있으면 무시)
 * DELETE /api/admin/allowed-users?email= → 제거
 *
 * env의 ALLOWED_EMAILS는 여기서 편집 불가 (안전망 역할). DB 목록만 관리.
 */

async function requireAdmin() {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  return null;
}

function validEmail(s: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
}

export async function GET() {
  const blocked = await requireAdmin();
  if (blocked) return blocked;

  const db = await getDb();
  const doc = await db
    .collection<AllowedUsersDoc>("projecthub_settings")
    .findOne({ key: "allowed_users" });
  const raw = (doc?.emails || []) as unknown[];
  const emails = raw
    .filter((e): e is string => typeof e === "string")
    .map((e) => e.trim())
    .filter(Boolean);

  // env 목록도 참고용으로 반환 (읽기 전용 표시용)
  const envEmails = (process.env.ALLOWED_EMAILS || "")
    .split(",")
    .map((e) => e.trim())
    .filter(Boolean);

  return NextResponse.json({ emails, envEmails });
}

export async function POST(req: NextRequest) {
  const blocked = await requireAdmin();
  if (blocked) return blocked;

  const body = await req.json().catch(() => null);
  const email = (body?.email || "").trim().toLowerCase();
  if (!email || !validEmail(email)) {
    return NextResponse.json({ error: "invalid email" }, { status: 400 });
  }

  const db = await getDb();
  await db.collection<AllowedUsersDoc>("projecthub_settings").updateOne(
    { key: "allowed_users" },
    {
      $addToSet: { emails: email },
      $set: { updated_at: new Date().toISOString() },
    },
    { upsert: true }
  );
  return NextResponse.json({ ok: true, email });
}

export async function DELETE(req: NextRequest) {
  const blocked = await requireAdmin();
  if (blocked) return blocked;

  const url = new URL(req.url);
  const email = (url.searchParams.get("email") || "").trim().toLowerCase();
  if (!email) {
    return NextResponse.json({ error: "email query required" }, { status: 400 });
  }

  const db = await getDb();
  await db.collection<AllowedUsersDoc>("projecthub_settings").updateOne(
    { key: "allowed_users" },
    {
      $pull: { emails: email },
      $set: { updated_at: new Date().toISOString() },
    }
  );
  return NextResponse.json({ ok: true, email });
}
