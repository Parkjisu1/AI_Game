import { NextRequest, NextResponse } from "next/server";
import { sendSlackMessage, sendBotDM, getSettings } from "@/lib/slack";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const url = body.webhook_url; // 즉석 webhook URL 테스트
    const userId = body.slack_user_id; // 즉석 user ID + 저장된 bot token 테스트

    const payload = {
      text: "🚀 ProjectHub Slack 연결 테스트",
      blocks: [
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: "🚀 *ProjectHub Slack 연결 테스트*\nWebhook 또는 Bot DM이 정상 작동합니다.",
          },
        },
      ],
    };

    let result;
    if (userId) {
      const settings = await getSettings();
      if (!settings.slack_bot_token) {
        return NextResponse.json(
          { ok: false, error: "Bot Token이 저장되어 있지 않습니다 — 먼저 저장 후 테스트하세요" },
          { status: 400 }
        );
      }
      result = await sendBotDM(settings.slack_bot_token, userId, payload);
    } else {
      result = await sendSlackMessage(payload, url);
    }

    if (!result.ok) {
      return NextResponse.json({ ok: false, error: result.error }, { status: 400 });
    }
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
