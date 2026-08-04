import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, authDisabled } from "@/auth";

/**
 * 산출물 — 에이전트가 낸 결과 문서와 확인 항목.
 *
 * 왜 별도 화면인가:
 *   design·data 결과는 코드가 아니라 문서라 미리보기에 나타날 수 없다.
 *   그렇다고 태스크 코멘트에 두면 긴 문서가 스크롤에 묻혀 읽지도, 판정하지도 못한다.
 *   문서로 읽고 항목별로 O/X 를 찍는 자리를 따로 둔다.
 *
 * GET               목록(본문 제외) 또는 ?id= 로 본문 포함 한 건
 * PATCH {id,cid,state}  확인 항목 판정 저장 (ok | ng | pending)
 */
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  if (!authDisabled) {
    const s = await auth();
    if (!s?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const id = new URL(req.url).searchParams.get("id");
  const db = await getDb();
  const col = db.collection("pixelforge_tasks");

  if (id) {
    if (!/^[a-f0-9]{24}$/i.test(id)) return NextResponse.json({ error: "invalid id" }, { status: 400 });
    const { ObjectId } = await import("mongodb");
    const t = await col.findOne(
      { _id: new ObjectId(id) },
      { projection: { title: 1, team: 1, sub_team: 1, status: 1, deliverable: 1, deliverable_role: 1, deliverable_at: 1, acceptance_criteria: 1 } },
    );
    if (!t) return NextResponse.json({ error: "not found" }, { status: 404 });
    return NextResponse.json({ item: t });
  }

  // 목록에서는 본문(최대 60KB)을 빼고 길이만 준다 — 목록 한 번에 수 MB 를 보낼 이유가 없다.
  const rows = await col
    .find(
      { deliverable: { $exists: true, $ne: "" } },
      { projection: { title: 1, team: 1, sub_team: 1, status: 1, deliverable_role: 1, deliverable_at: 1, acceptance_criteria: 1, deliverable: 1 } },
    )
    .sort({ deliverable_at: -1 })
    .limit(30)
    .toArray();

  const items = rows.map((t) => {
    const cs = Array.isArray(t.acceptance_criteria) ? t.acceptance_criteria : [];
    return {
      _id: t._id, title: t.title, team: t.team, sub_team: t.sub_team, status: t.status,
      deliverable_role: t.deliverable_role, deliverable_at: t.deliverable_at,
      chars: String(t.deliverable || "").length,
      criteria: { total: cs.length, ok: cs.filter((c) => c.state === "ok").length, ng: cs.filter((c) => c.state === "ng").length },
    };
  });
  return NextResponse.json({ items });
}

export async function PATCH(req: NextRequest) {
  let email = "";
  if (!authDisabled) {
    const s = await auth();
    email = String(s?.user?.email || "");
    if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const body = await req.json().catch(() => null);
  const id = String(body?.id || "");
  const cid = String(body?.cid || "");
  const state = String(body?.state || "");
  if (!/^[a-f0-9]{24}$/i.test(id) || !cid || !["ok", "ng", "pending"].includes(state)) {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }

  const { ObjectId } = await import("mongodb");
  const db = await getDb();
  // 누가 언제 판정했는지 남긴다 — 나중에 "이거 누가 OK 했지" 를 답할 수 있어야 한다.
  const r = await db.collection("pixelforge_tasks").updateOne(
    { _id: new ObjectId(id), "acceptance_criteria.id": cid },
    {
      $set: {
        "acceptance_criteria.$.state": state,
        "acceptance_criteria.$.judged_by": email,
        "acceptance_criteria.$.judged_at": new Date().toISOString(),
      },
    },
  );
  if (!r.matchedCount) return NextResponse.json({ error: "항목을 찾지 못했습니다" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
