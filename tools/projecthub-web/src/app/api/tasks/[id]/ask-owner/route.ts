import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { ObjectId } from "mongodb";
import { auth } from "@/auth";
import { resolveRouteByEmail, sendByRoute } from "@/lib/slack";
import { recordAudit } from "@/lib/audit";

/**
 * 담당자(현재 로그인 사용자)가 이 태스크가 뭔지 모르겠다고
 * **태스크 생성자**에게 설명을 요청하는 엔드포인트.
 *
 * 동작:
 *   1. 태스크 조회 → created_by_email 확인
 *   2. 본인이 만든 태스크면 거부 (자기 자신에게는 비활성)
 *   3. 태스크에 "❓ 설명 요청" 코멘트 추가
 *   4. 생성자에게 Slack DM (bot token 매핑 있으면)
 *
 * POST body: { message?: string }   — 선택적 추가 메시지
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  if (!/^[a-f0-9]{24}$/.test(id)) {
    return NextResponse.json({ error: "invalid task id" }, { status: 400 });
  }

  const session = await auth();
  const requesterEmail = String(session?.user?.email || "").toLowerCase();
  if (!requesterEmail) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const requesterName = session?.user?.name || requesterEmail.split("@")[0];

  let message = "";
  try {
    const body = await req.json();
    message = String(body?.message || "").trim().slice(0, 500);
  } catch { /* no body ok */ }

  const db = await getDb();
  const task = await db
    .collection("pixelforge_tasks")
    .findOne({ _id: new ObjectId(id) });
  if (!task) {
    return NextResponse.json({ error: "task not found" }, { status: 404 });
  }

  const ownerEmail = String(task.created_by_email || "").toLowerCase();
  if (!ownerEmail) {
    return NextResponse.json(
      { error: "이 태스크에는 기록된 생성자가 없습니다 (이전 버전 태스크). 직접 확인해주세요." },
      { status: 409 }
    );
  }
  if (ownerEmail === requesterEmail) {
    return NextResponse.json(
      { error: "자신이 만든 태스크에는 요청할 수 없습니다" },
      { status: 400 }
    );
  }

  const title = String(task.title || "(제목 없음)");
  const taskUrl = (() => {
    const base = process.env.AUTH_URL || "";
    return `${base.replace(/\/$/, "")}/tasks#task=${id}`;
  })();

  // 1. 코멘트 추가
  const commentText =
    `❓ **설명 요청** — @${requesterName} 님이 이 태스크가 무엇을 의미하는지 확인을 요청했습니다.` +
    (message ? `\n\n> ${message}` : "") +
    `\n\n_생성자(${ownerEmail})에게 Slack DM이 발송되었습니다._`;

  const ops: Record<string, unknown> = {
    $set: { updated_at: new Date().toISOString() },
    $push: {
      comments: {
        id: new ObjectId().toString(),
        text: commentText,
        author: requesterName,
        created_at: new Date().toISOString(),
        kind: "ask_owner",
      },
    },
  };
  await db.collection("pixelforge_tasks").updateOne({ _id: new ObjectId(id) }, ops);

  // 2. Slack DM 발송
  let slackResult: { ok: boolean; error?: string } = { ok: false, error: "unattempted" };
  try {
    const route = await resolveRouteByEmail(ownerEmail);
    if (route.type === "none") {
      slackResult = { ok: false, error: "no Slack mapping for owner email" };
    } else {
      const body = [
        `❓ *태스크 설명 요청*`,
        `*${title}*`,
        `_${requesterName}_ 님이 이 업무가 어떤 내용인지 확인을 요청했습니다.`,
        message ? `\n> ${message}` : "",
        `\n<${taskUrl}|태스크 열기>`,
      ].filter(Boolean).join("\n");
      slackResult = await sendByRoute(route, { text: body });
    }
  } catch (e) {
    slackResult = { ok: false, error: e instanceof Error ? e.message : "unknown" };
  }

  // 3. 감사 로그
  recordAudit({
    task_id: id,
    event: "task.ask_owner",
    actor: { email: requesterEmail, source: "ui" },
    data: {
      owner: ownerEmail,
      title: title.slice(0, 200),
      slack_ok: slackResult.ok,
      slack_err: slackResult.error || "",
      message: message.slice(0, 200),
    },
  }).catch(() => {});

  return NextResponse.json({
    ok: true,
    comment_added: true,
    slack: slackResult,
  });
}
