// Slack Incoming Webhook 발송 util
import { getDb } from "./mongodb";

const SETTINGS_COLLECTION = "projecthub_settings";
const SETTINGS_KEY = "current";

// 작업자 매핑: webhook URL 또는 Slack User ID
export interface AssigneeWebhook {
  assignee: string;
  email?: string;         // 로그인 이메일 — NextAuth 세션과 매칭해 created_by에 사용
  webhook_url?: string;   // 채널 webhook (개인 DM이면 발신자가 설치자로 표시됨)
  slack_user_id?: string; // Slack User ID (U01ABC...) — bot token과 함께 쓰면 봇 이름으로 DM
}

export interface ProjectHubSettings {
  // 기본 fallback webhook (채널용)
  slack_webhook_url?: string;
  // Bot User OAuth Token (xoxb-...) — chat.postMessage 호출용
  slack_bot_token?: string;
  // 작업자별 매핑
  slack_assignee_webhooks?: AssigneeWebhook[];
  slack_notify_on_create?: boolean;
  slack_notify_on_status_change?: boolean;
}

export interface AssigneeRoute {
  type: "bot_dm" | "webhook" | "default_webhook" | "none";
  url?: string;
  userId?: string;
  botToken?: string;
}

// 작업자 이름으로 라우팅 결정
// 우선순위: 1) bot token + user_id (DM via chat.postMessage)
//          2) assignee의 webhook_url
//          3) default webhook
export function resolveAssigneeRoute(
  settings: ProjectHubSettings,
  assignee?: string
): AssigneeRoute {
  if (assignee && settings.slack_assignee_webhooks?.length) {
    const trimmed = assignee.trim().toLowerCase();
    const match = settings.slack_assignee_webhooks.find(
      (w) => w.assignee.trim().toLowerCase() === trimmed
    );
    if (match) {
      if (match.slack_user_id && settings.slack_bot_token) {
        return {
          type: "bot_dm",
          userId: match.slack_user_id,
          botToken: settings.slack_bot_token,
        };
      }
      if (match.webhook_url) {
        return { type: "webhook", url: match.webhook_url };
      }
    }
  }
  if (settings.slack_webhook_url) {
    return { type: "default_webhook", url: settings.slack_webhook_url };
  }
  return { type: "none" };
}

export async function getSettings(): Promise<ProjectHubSettings> {
  const db = await getDb();
  const doc = await db.collection(SETTINGS_COLLECTION).findOne({ key: SETTINGS_KEY });
  if (!doc) return {};
  return (doc.settings || {}) as ProjectHubSettings;
}

export async function saveSettings(settings: ProjectHubSettings): Promise<void> {
  const db = await getDb();
  await db.collection(SETTINGS_COLLECTION).updateOne(
    { key: SETTINGS_KEY },
    { $set: { key: SETTINGS_KEY, settings, updated_at: new Date().toISOString() } },
    { upsert: true }
  );
}

export interface SlackBlock {
  type: string;
  text?: { type: string; text: string };
  fields?: Array<{ type: string; text: string }>;
}

export interface SlackPayload {
  text: string;
  blocks?: SlackBlock[];
}

export async function sendSlackMessage(payload: SlackPayload, webhookOverride?: string): Promise<{ ok: boolean; error?: string }> {
  const url = webhookOverride || (await getSettings()).slack_webhook_url;
  if (!url) return { ok: false, error: "webhook URL not configured" };
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const text = await res.text();
      return { ok: false, error: `Slack ${res.status}: ${text.substring(0, 100)}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "unknown" };
  }
}

// chat.postMessage로 사용자에게 DM (메시지가 봇 이름으로 표시됨)
export async function sendBotDM(
  botToken: string,
  userId: string,
  payload: SlackPayload
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fetch("https://slack.com/api/chat.postMessage", {
      method: "POST",
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        Authorization: `Bearer ${botToken}`,
      },
      body: JSON.stringify({
        channel: userId,  // user ID를 channel로 넘기면 자동으로 DM 채널 사용
        text: payload.text,
        blocks: payload.blocks,
      }),
    });
    const json = await res.json();
    if (!json.ok) {
      return { ok: false, error: `Slack API: ${json.error || "unknown"}` };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "unknown" };
  }
}

// 이메일 → Slack DM 라우트 (Settings의 slack_assignee_webhooks 매핑 사용)
export async function resolveRouteByEmail(email: string): Promise<AssigneeRoute> {
  const settings = await getSettings();
  const low = email.trim().toLowerCase();
  const match = (settings.slack_assignee_webhooks || []).find(
    (w) => (w.email || "").trim().toLowerCase() === low
  );
  if (!match) return { type: "none" };
  if (match.slack_user_id && settings.slack_bot_token) {
    return { type: "bot_dm", userId: match.slack_user_id, botToken: settings.slack_bot_token };
  }
  if (match.webhook_url) return { type: "webhook", url: match.webhook_url };
  return { type: "none" };
}

// 이메일에 바로 DM 보내기 (Hermes 질문 등)
export async function sendDmToEmail(
  email: string,
  payload: SlackPayload
): Promise<{ ok: boolean; error?: string }> {
  const route = await resolveRouteByEmail(email);
  if (route.type === "none") return { ok: false, error: `no DM route for email: ${email}` };
  return sendByRoute(route, payload);
}

// 라우팅 결정 + 발송 (한 번에)
export async function sendByRoute(route: AssigneeRoute, payload: SlackPayload): Promise<{ ok: boolean; error?: string }> {
  if (route.type === "bot_dm" && route.botToken && route.userId) {
    return sendBotDM(route.botToken, route.userId, payload);
  }
  if ((route.type === "webhook" || route.type === "default_webhook") && route.url) {
    return sendSlackMessage(payload, route.url);
  }
  return { ok: false, error: "no route configured" };
}

// 작업 생성 알림
export function buildTaskCreatedPayload(task: {
  title: string;
  description?: string;
  assignee?: string;
  priority?: string;
  related_levels?: string;
}): SlackPayload {
  const priorityEmoji: Record<string, string> = {
    urgent: "🔴",
    high: "🟠",
    medium: "🔵",
    low: "⚪",
  };
  const emoji = priorityEmoji[task.priority || "medium"] || "🔵";
  return {
    text: `${emoji} 새 작업: ${task.title}`,
    blocks: [
      {
        type: "section",
        text: { type: "mrkdwn", text: `${emoji} *새 작업 등록*\n*${task.title}*` },
      },
      {
        type: "section",
        fields: [
          { type: "mrkdwn", text: `*담당자:*\n${task.assignee || "(미지정)"}` },
          { type: "mrkdwn", text: `*우선순위:*\n${task.priority || "medium"}` },
        ],
      },
      ...(task.description
        ? [{
            type: "section",
            text: { type: "mrkdwn", text: `*설명:*\n${task.description.substring(0, 500)}` },
          } as SlackBlock]
        : []),
    ],
  };
}

// 작업 상태 변경 알림
export function buildTaskStatusPayload(task: {
  title: string;
  assignee?: string;
}, oldStatus: string, newStatus: string): SlackPayload {
  const statusLabel: Record<string, string> = {
    todo: "할 일",
    in_progress: "진행 중",
    review: "리뷰",
    done: "완료",
  };
  return {
    text: `📋 ${task.title}: ${statusLabel[oldStatus] || oldStatus} → ${statusLabel[newStatus] || newStatus}`,
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `📋 *${task.title}*\n${statusLabel[oldStatus] || oldStatus} → *${statusLabel[newStatus] || newStatus}*${task.assignee ? `\n담당: ${task.assignee}` : ""}`,
        },
      },
    ],
  };
}
