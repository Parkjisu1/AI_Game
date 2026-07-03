import { NextRequest, NextResponse } from "next/server";
import { ObjectId } from "mongodb";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";

export const runtime = "nodejs";

/**
 * 레벨별 온디맨드 리플레이 생성 요청.
 *
 * POST { result_id, level } — 기존 배치 결과의 시드/정책 그대로 해당 레벨 리플레이만
 * hermes 태스크(sim_params.replay_only)로 요청. 완료 시 executor가
 * bf_sim_results.replays.{level} 에 리플레이 id를 연결 → 페이지 폴링으로 감지.
 */
export async function POST(req: NextRequest) {
  const db = await getDb();
  const body = await req.json().catch(() => null);
  const resultId = String(body?.result_id || "");
  const level = parseInt(body?.level);
  if (!ObjectId.isValid(resultId) || !Number.isFinite(level) || level < 1) {
    return NextResponse.json({ error: "result_id/level 확인" }, { status: 400 });
  }

  const doc = await db.collection("bf_sim_results").findOne(
    { _id: new ObjectId(resultId) },
    { projection: { params: 1, replays: 1, replay_id: 1, replay_level: 1 } },
  );
  if (!doc) return NextResponse.json({ error: "결과 없음" }, { status: 404 });

  // 이미 있으면 생성 생략
  const existing = doc.replays?.[String(level)]
    || (doc.replay_level === level ? doc.replay_id : null);
  if (existing) return NextResponse.json({ ok: true, ready: true });

  const policy = doc.params?.policy || "smart";
  const seed = doc.params?.seed || 12345;

  let email = "";
  try {
    const session = await auth();
    email = (session?.user?.email || "").toLowerCase();
  } catch { /* 인증 우회 모드 */ }

  const now = new Date().toISOString();
  const task = {
    title: `🎬 리플레이: 레벨 ${level} (${policy})`,
    // 주의: 설명에 ObjectId hex를 넣지 않는다 — 라우터 키워드 매칭이 hex 속 "db" 등에 오탐된 실사례.
    // (라우터는 sim_params 존재로 결정론 라우팅하지만 이중 방어) 결과 id는 sim_params.result_id에만.
    description:
      `BalloonFlow 클리어율 시뮬레이션 리플레이 생성 (시뮬레이터 탭에서 레벨 선택).\n` +
      `레벨 ${level} · 정책 ${policy} · 시드 ${seed}`,
    assignee: "hermes",
    status: "todo",
    priority: "medium",
    tags: ["시뮬", "balloonflow"],
    sim_params: {
      levels: String(level), runs: 1, policy, seed,
      replay: true, replay_level: level, replay_only: true, result_id: resultId,
    },
    created_by_email: email,
    created_at: now,
    updated_at: now,
  };
  const ins = await db.collection("pixelforge_tasks").insertOne(task);
  return NextResponse.json({ ok: true, ready: false, task_id: String(ins.insertedId) });
}

/** 생성 태스크 상태 폴링 — 실패를 즉시 UI에 노출 (⚠️ 코멘트 = 실패) */
export async function GET(req: NextRequest) {
  const db = await getDb();
  const url = new URL(req.url);
  const taskId = url.searchParams.get("task_id") || "";
  if (!ObjectId.isValid(taskId)) return NextResponse.json({ error: "invalid task_id" }, { status: 400 });
  const t = await db.collection("pixelforge_tasks").findOne(
    { _id: new ObjectId(taskId) },
    { projection: { status: 1, comments: { $slice: -1 } } },
  );
  if (!t) return NextResponse.json({ status: "missing", failed: true, message: "태스크가 삭제됨" });
  const last = String(t.comments?.[0]?.text || t.comments?.[0]?.body || "");
  const failed = last.startsWith("⚠️");
  return NextResponse.json({ status: t.status, failed, message: failed ? last.slice(0, 400) : null });
}
