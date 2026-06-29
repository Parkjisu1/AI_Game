import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, isAdminEmail } from "@/auth";

export const runtime = "nodejs";

/**
 * Hermes 자가 진화 — 자동 학습된 프롬프트 패치 목록.
 *
 * GET: active + recently reverted 패치 표시 (모니터링용)
 * DELETE ?id=...: 특정 패치 즉시 revert (admin만)
 */
export async function GET() {
  const db = await getDb();
  const coll = db.collection("hermes_prompt_patches");

  const [active, reverted, badCases] = await Promise.all([
    coll.find({ status: "active" }).sort({ created_at: -1 }).limit(50).toArray(),
    coll.find({ status: "reverted" }).sort({ reverted_at: -1 }).limit(20).toArray(),
    coll.find({ status: "bad_case" }).sort({ marked_bad_at: -1 }).limit(20).toArray(),
  ]);

  const fmt = (r: Record<string, unknown>) => ({
    _id: String(r._id),
    role: r.role,
    patch_text: r.patch_text,
    rationale: r.rationale,
    addresses_category: r.addresses_category,
    status: r.status,
    score_before: r.score_before,
    score_after: r.score_after,
    samples_after: r.samples_after,
    created_at: r.created_at,
    reverted_at: r.reverted_at,
    revert_reason: r.revert_reason,
    bad_case_reason: r.bad_case_reason,
    bad_case_note: r.bad_case_note,
    marked_bad_at: r.marked_bad_at,
  });

  return NextResponse.json({
    active: active.map(fmt),
    reverted: reverted.map(fmt),
    bad_cases: badCases.map(fmt),
    counts: {
      active: active.length,
      reverted: reverted.length,
      bad_cases: badCases.length,
    },
  });
}

/**
 * PATCH: 패치 상태 변경 (revert / bad_case 승격)
 * Body: { id, action: "revert" | "bad_case", reason?: string, note?: string }
 *
 * - revert: 단순 비활성화 (LLM이 다시 비슷한 방향 제안 가능)
 * - bad_case: 영구 anti-pattern 등록 — reflection이 절대 다시 제안 안 함
 *
 * 이미 reverted 상태인 패치도 bad_case로 승격 가능.
 */
export async function PATCH(req: NextRequest) {
  const session = await auth();
  const email = String(session?.user?.email || "").toLowerCase();
  if (!email || !isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  const body = await req.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }
  const id = String(body.id || "");
  const action = String(body.action || "");
  const reason = String(body.reason || "").slice(0, 100);
  const note = String(body.note || "").slice(0, 500);

  if (!/^[a-f0-9]{24}$/.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  const { ObjectId } = await import("mongodb");
  const db = await getDb();
  const coll = db.collection("hermes_prompt_patches");

  if (action === "revert") {
    const res = await coll.updateOne(
      { _id: new ObjectId(id), status: "active" },
      {
        $set: {
          status: "reverted",
          reverted_at: new Date().toISOString(),
          revert_reason: `manual revert by ${email}${note ? ` — ${note}` : ""}`,
        },
      }
    );
    return NextResponse.json({ ok: res.modifiedCount > 0 });
  }

  if (action === "bad_case") {
    const validReasons = new Set(["off_direction", "wrong_result", "other"]);
    const finalReason = validReasons.has(reason) ? reason : "off_direction";
    const res = await coll.updateOne(
      { _id: new ObjectId(id), status: { $in: ["active", "reverted"] } },
      {
        $set: {
          status: "bad_case",
          bad_case_reason: finalReason,
          bad_case_note: `${email}: ${note}`.slice(0, 500),
          marked_bad_at: new Date().toISOString(),
        },
      }
    );
    return NextResponse.json({ ok: res.modifiedCount > 0 });
  }

  return NextResponse.json({ error: "invalid action" }, { status: 400 });
}

// 하위 호환 — 단순 DELETE는 revert로 매핑
export async function DELETE(req: NextRequest) {
  const session = await auth();
  const email = String(session?.user?.email || "").toLowerCase();
  if (!email || !isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const url = new URL(req.url);
  const id = url.searchParams.get("id") || "";
  if (!/^[a-f0-9]{24}$/.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  const { ObjectId } = await import("mongodb");
  const db = await getDb();
  const res = await db.collection("hermes_prompt_patches").updateOne(
    { _id: new ObjectId(id), status: "active" },
    {
      $set: {
        status: "reverted",
        reverted_at: new Date().toISOString(),
        revert_reason: `manual revert by ${email}`,
      },
    }
  );
  return NextResponse.json({ ok: res.modifiedCount > 0 });
}
