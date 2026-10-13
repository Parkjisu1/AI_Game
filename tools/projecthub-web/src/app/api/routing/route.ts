import { NextRequest, NextResponse } from "next/server";
import { auth, isAdminEmail } from "@/auth";
import { getDb } from "@/lib/mongodb";

/**
 * 배선(라우팅) 규칙 — 담당 미지정으로 등록된 작업을 조건에 따라 AI 역할/팀원에 자동 배정.
 * 저장: projecthub_settings { key: "routing_rules", rules: [...] }
 * 규칙: { id, name, enabled, match: { project, keyword }, assign: { assignee, ai_role, reviewer } }
 * 순서 = 우선순위 (첫 매칭 규칙 적용). 적용 지점: POST /api/tasks.
 */

export interface RoutingRule {
  id: string;
  name?: string;
  enabled: boolean;
  match: { project?: string; keyword?: string };
  assign: { assignee?: string; ai_role?: string; reviewer?: string };
}

function sanitize(raw: unknown): RoutingRule[] {
  if (!Array.isArray(raw)) return [];
  return raw.slice(0, 50).flatMap((r) => {
    if (!r || typeof r !== "object") return [];
    const o = r as Record<string, unknown>;
    const m = (o.match || {}) as Record<string, unknown>;
    const a = (o.assign || {}) as Record<string, unknown>;
    const rule: RoutingRule = {
      id: String(o.id || "").slice(0, 40) || Math.random().toString(36).slice(2, 10),
      name: String(o.name || "").slice(0, 60),
      enabled: o.enabled !== false,
      match: {
        project: String(m.project || "").slice(0, 60),
        keyword: String(m.keyword || "").slice(0, 60),
      },
      assign: {
        assignee: String(a.assignee || "").slice(0, 120),
        ai_role: String(a.ai_role || "").slice(0, 60),
        reviewer: String(a.reviewer || "").slice(0, 120),
      },
    };
    if (!rule.assign.assignee) return []; // 담당 없는 규칙은 무의미
    return [rule];
  });
}

export async function GET() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const db = await getDb();
  const doc = await db.collection("projecthub_settings").findOne({ key: "routing_rules" });
  return NextResponse.json({ rules: sanitize(doc?.rules) });
}

export async function PUT(req: NextRequest) {
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  if (!isAdminEmail(email)) return NextResponse.json({ error: "forbidden" }, { status: 403 });

  const body = await req.json().catch(() => null);
  const rules = sanitize(body?.rules);
  const db = await getDb();
  await db.collection("projecthub_settings").updateOne(
    { key: "routing_rules" },
    { $set: { key: "routing_rules", rules, updated_at: new Date().toISOString(), updated_by: email.toLowerCase() } },
    { upsert: true },
  );
  return NextResponse.json({ ok: true, rules });
}
