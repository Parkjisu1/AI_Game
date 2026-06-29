import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { ObjectId } from "mongodb";
import { auth } from "@/auth";

export const runtime = "nodejs";

/**
 * 레벨 상세 — cells + 경쟁 팀 메타 포함.
 *
 * GET   ?download=1 : JSON 첨부 다운로드
 * PATCH {user_score: 1-5}  : 사용자 별점 기록 (NextAuth 세션 또는 Hermes 키)
 */

function getUserEmail(req: NextRequest): { email: string; isHermes: boolean } | null {
  const auth_h = (req.headers.get("authorization") || "").trim();
  const bearer = auth_h.toLowerCase().startsWith("bearer ") ? auth_h.slice(7).trim() : "";
  const customKey = req.headers.get("x-hermes-key") || "";
  const presented = bearer || customKey;
  const expected = process.env.HERMES_INTERNAL_API_KEY || "";
  if (expected && presented === expected) {
    return { email: req.headers.get("x-hermes-on-behalf-of") || "hermes", isHermes: true };
  }
  return null;
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!id || !/^[a-f0-9]{24}$/i.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  const url = new URL(req.url);
  const download = url.searchParams.get("download") === "1";

  const db = await getDb();
  const doc = await db.collection("pixelforge_grid_levels").findOne({ _id: new ObjectId(id) });
  if (!doc) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const body = {
    _id: String(doc._id),
    name: doc.name,
    task_id: doc.task_id,
    task_title: doc.task_title,
    created_by_email: doc.created_by_email,
    created_at: doc.created_at,
    width: doc.width,
    height: doc.height,
    symmetry: doc.symmetry,
    palette: doc.palette,
    per_color_count: doc.per_color_count,
    seed: doc.seed,
    cells: doc.cells,
    png_filename: doc.png_filename,
    validation: doc.validation,
    team_id: doc.team_id || null,
    pattern_chosen: doc.pattern_chosen || null,
    user_score: doc.user_score ?? null,
    user_score_at: doc.user_score_at ?? null,
    user_score_by: doc.user_score_by ?? null,
  };

  if (download) {
    return new NextResponse(JSON.stringify(body, null, 2), {
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": `attachment; filename="${doc.name || id}.json"`,
      },
    });
  }
  return NextResponse.json(body);
}


export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!id || !/^[a-f0-9]{24}$/i.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  // Auth: NextAuth session OR Hermes key
  const session = await auth();
  let email = session?.user?.email || "";
  if (!email) {
    const ha = getUserEmail(req);
    if (!ha) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    email = ha.email;
  }

  let body: { user_score?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }
  const score = Number(body.user_score);
  if (!Number.isInteger(score) || score < 1 || score > 5) {
    return NextResponse.json({ error: "user_score must be integer 1..5" }, { status: 400 });
  }

  const db = await getDb();
  const oid = new ObjectId(id);
  const now = new Date().toISOString();
  const result = await db.collection("pixelforge_grid_levels").findOneAndUpdate(
    { _id: oid },
    {
      $set: {
        user_score: score,
        user_score_at: now,
        user_score_by: email,
      },
    },
    { returnDocument: "after" },
  );
  if (!result) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  // 팀별 누적 점수 컬렉션에도 기록 (T5에서 사용 — 약팀 자동 개선 트리거용)
  if (result.team_id) {
    try {
      await db.collection("hermes_design_team_scores").insertOne({
        team_id: result.team_id,
        level_id: String(result._id),
        task_id: result.task_id || null,
        score,
        scored_by: email,
        pattern_chosen: result.pattern_chosen || null,
        created_at: now,
      });
    } catch (e) {
      console.error("[levels PATCH] team_scores insert failed:", e);
    }
  }

  return NextResponse.json({
    ok: true,
    user_score: score,
    user_score_at: now,
  });
}
