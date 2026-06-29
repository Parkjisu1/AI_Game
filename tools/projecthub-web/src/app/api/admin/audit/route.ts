import { NextRequest, NextResponse } from "next/server";
import { auth, isAdminEmail } from "@/auth";
import { listAudit } from "@/lib/audit";

/**
 * 감사 로그 조회 — 관리자 전용.
 * GET /api/admin/audit?limit=100&task_id=...
 */
export async function GET(req: NextRequest) {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!isAdminEmail(email)) return NextResponse.json({ error: "forbidden" }, { status: 403 });

  const url = new URL(req.url);
  const limit = parseInt(url.searchParams.get("limit") || "100", 10);
  const task_id = url.searchParams.get("task_id") || undefined;
  const entries = await listAudit({ limit, task_id });
  return NextResponse.json({ entries });
}
