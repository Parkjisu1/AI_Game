import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * Slack Event Subscriptions 수신 엔드포인트.
 *
 * 처리하는 이벤트:
 *   1. url_verification     — App 설정에서 URL 등록 시 challenge 응답
 *   2. event_callback(message.im)
 *        — Bot과의 DM에 사용자가 답변 → 최근 "Hermes 질문"이 걸린 Task를
 *          찾아 코멘트로 역동기화 → 기존 rework 루프가 자동 감지해 파이프라인 재개
 *
 * 검증:
 *   - SLACK_SIGNING_SECRET 환경변수가 있으면 HMAC 서명 검증 (권장)
 *   - 없으면 검증 생략 (dev 편의)
 *
 * 주의:
 *   - 이 라우트는 proxy(middleware) matcher에서 제외되어야 함 (NextAuth 쿠키 없음)
 *   - 3초 안에 응답해야 Slack이 retry하지 않음
 */

function verifySlackSignature(
  signingSecret: string,
  rawBody: string,
  timestamp: string,
  signature: string,
): boolean {
  // 5분 이내 요청만 허용 (리플레이 공격 방어)
  const ts = parseInt(timestamp, 10);
  if (!ts || Math.abs(Date.now() / 1000 - ts) > 300) return false;
  const base = `v0:${timestamp}:${rawBody}`;
  const mac = crypto.createHmac("sha256", signingSecret).update(base).digest("hex");
  const expected = `v0=${mac}`;
  try {
    return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
  } catch {
    return false;
  }
}

export async function POST(req: NextRequest) {
  const rawBody = await req.text();

  // 서명 검증 — 이 라우트는 미들웨어 인증 제외(Slack이 직접 POST)라 서명이 유일한 인증.
  // SLACK_SIGNING_SECRET 미설정 시 검증 불가 → 무인증 수락 금지(이전엔 그냥 통과하던 구멍).
  const signingSecret = process.env.SLACK_SIGNING_SECRET;
  if (!signingSecret) {
    return NextResponse.json({ error: "slack signing secret not configured" }, { status: 401 });
  }
  const ts = req.headers.get("x-slack-request-timestamp") || "";
  const sig = req.headers.get("x-slack-signature") || "";
  if (!verifySlackSignature(signingSecret, rawBody, ts, sig)) {
    return NextResponse.json({ error: "invalid signature" }, { status: 401 });
  }

  let body: Record<string, unknown>;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  // 1) URL verification — App 설정에서 URL 등록 시
  if (body.type === "url_verification") {
    return NextResponse.json({ challenge: body.challenge });
  }

  // 2) Event callback
  if (body.type === "event_callback") {
    const ev = (body.event || {}) as Record<string, unknown>;
    const evType = ev.type;
    const channelType = ev.channel_type;
    const botId = ev.bot_id;
    const subtype = ev.subtype;

    // Bot 자기 자신 메시지 / edit / delete 등은 무시
    // ⚠️ 2026-07-06: DM(message.im) 처리는 Mother의 slack_inbound.py 폴러로 일원화.
    //   - 여기의 매칭("24h 내 review + 이메일 일치 최신 1건")은 답변 소실/오첨부 사례가 있었고,
    //   - 폴러는 hermes_dm_context로 대상 task를 정확히 특정 + 승인/중단/상태 등 명령 지원.
    //   - 두 경로가 같은 DM을 이중 처리(코멘트 2번)하는 것을 막기 위해 여기는 수신만 하고 스킵.
    //   복원하려면 아래 주석 해제 (slack_inbound.service 중지 필수).
    if (evType === "message" && channelType === "im" && !botId && !subtype) {
      console.log("[slack/events] message.im 수신 — slack_inbound 폴러가 처리하므로 스킵");
      void handleDmReply; // 미사용 경고 억제 (복원 대비 함수 유지)
      // const slackUserId = String(ev.user || "");
      // const text = String(ev.text || "").trim();
      // if (slackUserId && text) {
      //   handleDmReply(slackUserId, text).catch((err) => {
      //     console.error("[slack/events] DM reply handler failed:", err);
      //   });
      // }
    }
  }

  // Slack에는 무조건 200 빨리 응답 (retry 방지)
  return NextResponse.json({ ok: true });
}

/**
 * Slack DM 답변을 Task 코멘트로 역동기화.
 * 매핑 방식:
 *   - slack_assignee_webhooks 테이블에서 slack_user_id로 이메일 조회
 *   - hermes가 최근 (24h) 질문을 남긴 review 상태 태스크 중
 *     created_by_email == 이메일 & status == "review" 조건으로 최신 태스크 하나 선택
 *   - 그 태스크에 사용자 코멘트 추가 → rework 루프가 자동 감지
 */
async function handleDmReply(slackUserId: string, text: string): Promise<void> {
  const db = await getDb();

  // slack_user_id → email
  const settings = await db
    .collection("projecthub_settings")
    .findOne({ key: "current" });
  const webhooks = (settings?.settings?.slack_assignee_webhooks || []) as Array<{
    assignee?: string;
    email?: string;
    slack_user_id?: string;
  }>;
  const match = webhooks.find((w) => w.slack_user_id === slackUserId);
  const email = (match?.email || "").toLowerCase();
  if (!email) {
    console.warn("[slack/events] no email mapping for slack_user_id", slackUserId);
    return;
  }

  // 최근 24h 내 "review" 상태이면서 created_by_email 일치하는 태스크 하나
  const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const task = await db.collection("pixelforge_tasks").findOne(
    {
      created_by_email: email,
      status: "review",
      updated_at: { $gte: cutoff },
    },
    { sort: { updated_at: -1 } },
  );
  if (!task) {
    console.warn("[slack/events] no review task found for", email);
    return;
  }

  const { ObjectId } = await import("mongodb");
  interface TaskDoc {
    _id: InstanceType<typeof ObjectId>;
    comments?: Array<{ id: string; text: string; author: string; created_at: string; via?: string }>;
    updated_at?: string;
  }
  await db.collection<TaskDoc>("pixelforge_tasks").updateOne(
    { _id: new ObjectId(String(task._id)) },
    {
      $push: {
        comments: {
          id: new ObjectId().toString(),
          text,
          author: match?.assignee || email,
          created_at: new Date().toISOString(),
          via: "slack_dm",
        },
      },
      $set: { updated_at: new Date().toISOString() },
    },
  );
  console.log("[slack/events] routed DM reply to task", String(task._id));
}
