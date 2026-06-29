import { NextRequest, NextResponse } from "next/server";
import { getSettings, saveSettings, type AssigneeWebhook } from "@/lib/slack";
import { auth, isAdminEmail } from "@/auth";

function maskSecret(s?: string): string {
  if (!s) return "";
  return "***" + s.slice(-8);
}

export async function GET() {
  try {
    const settings = await getSettings();
    const masked = {
      slack_webhook_url: maskSecret(settings.slack_webhook_url),
      slack_bot_token: maskSecret(settings.slack_bot_token),
      slack_assignee_webhooks: (settings.slack_assignee_webhooks || []).map((w) => ({
        assignee: w.assignee,
        webhook_url: maskSecret(w.webhook_url),
        slack_user_id: w.slack_user_id || "",
      })),
      slack_notify_on_create: settings.slack_notify_on_create !== false,
      slack_notify_on_status_change: settings.slack_notify_on_status_change !== false,
    };
    return NextResponse.json({
      ok: true,
      settings: masked,
      hasDefault: !!settings.slack_webhook_url,
      hasBotToken: !!settings.slack_bot_token,
      assigneeCount: (settings.slack_assignee_webhooks || []).filter(
        (w) => w.webhook_url || w.slack_user_id
      ).length,
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    // 설정(Slack webhook/bot token)은 관리자만 변경 — 일반 5인은 GET(마스킹)만.
    const session = await auth();
    if (!isAdminEmail(session?.user?.email)) {
      return NextResponse.json({ ok: false, error: "forbidden (admin only)" }, { status: 403 });
    }
    const body = await req.json();
    const current = await getSettings();
    const next = { ...current };

    if (body.slack_webhook_url !== undefined) {
      next.slack_webhook_url = body.slack_webhook_url;
    }
    if (body.slack_bot_token !== undefined) {
      // 마스킹된 값이면 무시 (기존 보존)
      if (body.slack_bot_token === "" || !body.slack_bot_token.startsWith("***")) {
        next.slack_bot_token = body.slack_bot_token;
      }
    }
    if (body.slack_notify_on_create !== undefined) {
      next.slack_notify_on_create = body.slack_notify_on_create;
    }
    if (body.slack_notify_on_status_change !== undefined) {
      next.slack_notify_on_status_change = body.slack_notify_on_status_change;
    }

    if (Array.isArray(body.slack_assignee_webhooks)) {
      const incoming = body.slack_assignee_webhooks as AssigneeWebhook[];
      const currentList = current.slack_assignee_webhooks || [];
      next.slack_assignee_webhooks = incoming
        .map((w) => {
          const existing = currentList.find(
            (e) => e.assignee.trim().toLowerCase() === w.assignee.trim().toLowerCase()
          );
          // webhook_url: 마스킹된 값이면 기존 보존
          let webhook_url = w.webhook_url || "";
          if (webhook_url.startsWith("***")) {
            webhook_url = existing?.webhook_url || "";
          }
          return {
            assignee: w.assignee,
            webhook_url,
            slack_user_id: (w.slack_user_id || "").trim(),
          };
        })
        .filter((w) => w.assignee.trim());
    }

    await saveSettings(next);
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
