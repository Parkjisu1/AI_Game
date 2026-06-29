import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { getSettings, sendByRoute, buildTaskCreatedPayload, buildTaskStatusPayload, resolveAssigneeRoute } from "@/lib/slack";
import { auth } from "@/auth";
import { recordAudit, AuditActor } from "@/lib/audit";

export async function GET() {
  const db = await getDb();
  // 목록은 슬림화: 무거운 필드 제외 + has_image flag, 댓글은 마지막 5개만(검색 보조용).
  // image_base64/attachments/description full text는 상세 GET /api/tasks/[id]에서.
  const tasks = await db.collection("pixelforge_tasks")
    .aggregate([
      { $sort: { created_at: -1 } },
      {
        $addFields: {
          has_image: {
            $cond: [
              { $and: [{ $ne: ["$image_base64", null] }, { $ne: ["$image_base64", ""] }] },
              true,
              false,
            ],
          },
          comments: { $slice: [{ $ifNull: ["$comments", []] }, -5] },
        },
      },
      {
        $project: {
          image_base64: 0,   // has_image 계산 후 제거
          attachments: 0,
        },
      },
    ])
    .toArray();
  return NextResponse.json(tasks);
}

export async function POST(req: NextRequest) {
  const db = await getDb();
  const body = await req.json();
  body.created_at = new Date().toISOString();
  body.updated_at = new Date().toISOString();

  // 로그인된 사용자 이메일을 created_by_email로 자동 주입 (Hermes 질문 DM 대상)
  try {
    const session = await auth();
    const email = session?.user?.email;
    if (email) {
      body.created_by_email = String(email).toLowerCase();
    }
  } catch { /* 인증 우회 모드면 스킵 */ }

  const result = await db.collection("pixelforge_tasks").insertOne(body);

  // 감사 로그
  const actor: AuditActor = {
    email: String(body.created_by_email || ""),
    source: "ui",
  };
  recordAudit({
    task_id: String(result.insertedId),
    event: "task.created",
    actor,
    data: {
      title: body.title,
      assignee: body.assignee,
      priority: body.priority,
    },
  }).catch(() => {});

  // Slack 알림 (optional, fire-and-forget — 실패해도 응답엔 영향 없음)
  try {
    const settings = await getSettings();
    if (settings.slack_notify_on_create !== false) {
      const route = resolveAssigneeRoute(settings, body.assignee);
      if (route.type !== "none") {
        const payload = buildTaskCreatedPayload(body);
        sendByRoute(route, payload).catch(() => {});
      }
    }
  } catch { /* ignore */ }

  return NextResponse.json({ ok: true, id: result.insertedId });
}

export async function PATCH(req: NextRequest) {
  const db = await getDb();
  const { _id, add_comment, delete_comment_index, ...update } = await req.json();
  const { ObjectId } = await import("mongodb");
  update.updated_at = new Date().toISOString();

  // 행위자 식별 (세션 이메일 있으면 ui, 없으면 system)
  let actorEmail = "";
  try {
    const session = await auth();
    actorEmail = String(session?.user?.email || "").toLowerCase();
  } catch { /* ignore */ }
  const actor: AuditActor = {
    email: actorEmail,
    source: actorEmail ? "ui" : "system",
  };

  // Slack 알림용으로 이전 task를 가져옴 (status 변경 감지)
  let prev: { title?: string; status?: string; assignee?: string } | null = null;
  try {
    prev = await db.collection("pixelforge_tasks").findOne({ _id: new ObjectId(_id) }) as { title?: string; status?: string; assignee?: string } | null;
  } catch { /* ignore */ }

  // 댓글 추가/삭제
  const ops: Record<string, unknown> = { $set: update };
  if (add_comment && typeof add_comment === "object" && add_comment.text) {
    ops.$push = {
      comments: {
        id: new ObjectId().toString(),
        text: add_comment.text,
        author: add_comment.author || "",
        created_at: new Date().toISOString(),
      },
    };
  }
  await db.collection("pixelforge_tasks").updateOne({ _id: new ObjectId(_id) }, ops);

  // 댓글 삭제
  if (delete_comment_index !== undefined) {
    const idx = Number(delete_comment_index);
    const doc = await db.collection("pixelforge_tasks").findOne({ _id: new ObjectId(_id) });
    if (doc?.comments && Array.isArray(doc.comments) && idx >= 0 && idx < doc.comments.length) {
      doc.comments.splice(idx, 1);
      await db.collection("pixelforge_tasks").updateOne(
        { _id: new ObjectId(_id) },
        { $set: { comments: doc.comments, updated_at: new Date().toISOString() } }
      );
    }
    // $set에서 delete_comment_index 제거 (DB 필드로 저장 방지)
  }

  // 감사 로그 (fire-and-forget)
  if (add_comment && add_comment.text) {
    recordAudit({
      task_id: String(_id),
      event: "task.comment_added",
      actor,
      data: { text: String(add_comment.text).slice(0, 500), author: add_comment.author || "" },
    }).catch(() => {});
  }
  if (prev && update.status && update.status !== prev.status) {
    recordAudit({
      task_id: String(_id),
      event: "task.status_changed",
      actor,
      data: { from: prev.status || "todo", to: update.status, title: prev.title },
    }).catch(() => {});
  }
  // 상태 외 필드 변경
  const otherChanged = Object.keys(update).filter(
    (k) => k !== "status" && k !== "updated_at"
  );
  if (otherChanged.length > 0) {
    recordAudit({
      task_id: String(_id),
      event: "task.updated",
      actor,
      data: { fields: otherChanged },
    }).catch(() => {});
  }

  // Slack 알림: status 변경 시 (담당자 DM으로 push)
  try {
    if (prev && update.status && update.status !== prev.status) {
      const settings = await getSettings();
      if (settings.slack_notify_on_status_change !== false) {
        const route = resolveAssigneeRoute(settings, prev.assignee);
        if (route.type !== "none") {
          const payload = buildTaskStatusPayload(
            { title: prev.title || "(no title)", assignee: prev.assignee },
            prev.status || "todo",
            update.status
          );
          sendByRoute(route, payload).catch(() => {});
        }
      }
    }
  } catch { /* ignore */ }

  return NextResponse.json({ ok: true });
}
