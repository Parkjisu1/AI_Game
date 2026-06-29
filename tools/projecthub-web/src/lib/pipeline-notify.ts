// Pipeline session stage 전환 시 Slack 통지.
// stage 별 1회만 발송 — pixelforge_pipeline_sessions.slack_notified_at_{stage} 플래그로 dedup.
import type { Db } from "mongodb";
import { ObjectId } from "mongodb";
import { sendDmToEmail, sendSlackMessage, getSettings, type SlackPayload } from "./slack";

type PipelineSession = Record<string, unknown>;

interface NotifyParams {
  db: Db;
  sess: PipelineSession;
  newStage: string;
  // 추가 context (totals, error 등) — payload 메시지 구성용
  context?: {
    totals?: { ok?: number; fail?: number; escalated?: number; avg_score?: number };
    total_levels?: number;
    error?: string;
  };
}

/**
 * stage 전이 알림. 다음 단계에 진입했을 때 1회 발송.
 * - art_done / curated_pending : Art 생성 완료
 * - field_done                 : Field Complete 완료
 * - failed                     : 실패
 * 그 외 stage 는 skip (curate/download 같은 사용자 액션 stage 는 통지 의미 적음).
 */
export async function notifyPipelineStage({ db, sess, newStage, context }: NotifyParams): Promise<void> {
  // 통지 대상 stage 만 화이트리스트
  const NOTIFY_STAGES: Record<string, string> = {
    art_done: "🎨 Art 생성 완료",
    curated_pending: "🎨 Art 생성 완료 (큐레이션 대기)",
    field_done: "🧩 Field Complete 완료",
    done: "✅ Pipeline 완료",
    failed: "❌ Pipeline 실패",
  };
  const label = NOTIFY_STAGES[newStage];
  if (!label) return;

  // dedup 플래그 키
  const flagKey = `slack_notified_at_${newStage}`;
  if ((sess as Record<string, unknown>)[flagKey]) return; // 이미 발송

  const sessId = String(sess._id);
  const label_sess = String(sess.label || `Pipeline ${sessId.slice(-6)}`);
  const targetLvs = ((sess.target_levels as number[]) || []).slice();
  const email = String(sess.created_by_email || "");

  // 발송 라우트 결정 — 요청자 email 우선, fallback default webhook
  let routeOk = false;
  let routeErr: string | undefined;

  const lvSummary = targetLvs.length <= 6
    ? targetLvs.join(", ")
    : `${targetLvs.slice(0, 5).join(", ")}, … (${targetLvs.length} lv)`;

  const lines: string[] = [
    `*${label}*`,
    `세션: ${label_sess}`,
    `대상: ${lvSummary}`,
  ];
  if (context?.total_levels !== undefined) {
    lines.push(`처리: ${context.total_levels} 레벨`);
  }
  if (context?.totals) {
    const t = context.totals;
    lines.push(`결과: ok=${t.ok ?? 0} / fail=${t.fail ?? 0}` +
      ((t.escalated ?? 0) > 0 ? ` · escalated=${t.escalated}` : "") +
      (t.avg_score !== undefined ? ` · avg_score=${t.avg_score.toFixed(3)}` : ""));
  }
  if (context?.error) {
    lines.push(`오류: ${String(context.error).substring(0, 200)}`);
  }
  lines.push(`id: ${sessId}`);

  const payload: SlackPayload = {
    text: `${label} — ${label_sess}`,
    blocks: [
      {
        type: "section",
        text: { type: "mrkdwn", text: lines.join("\n") },
      },
    ],
  };

  if (email) {
    const r = await sendDmToEmail(email, payload);
    if (r.ok) routeOk = true;
    else routeErr = r.error;
  }

  // DM 실패하거나 email 없으면 default webhook fallback
  if (!routeOk) {
    const settings = await getSettings();
    if (settings.slack_webhook_url) {
      const r = await sendSlackMessage(payload);
      if (r.ok) routeOk = true;
      else routeErr = (routeErr ? `${routeErr}; default: ${r.error}` : r.error);
    }
  }

  // flag 갱신 — 발송 결과(성공/실패) 모두 마킹해서 retry 폭주 방지.
  // 실패 시 routeErr 도 같이 기록.
  const update: Record<string, unknown> = { [flagKey]: new Date().toISOString() };
  if (!routeOk && routeErr) update[`${flagKey}_error`] = routeErr;
  try {
    await db.collection("pixelforge_pipeline_sessions").updateOne(
      { _id: sess._id as ObjectId },
      { $set: update },
    );
  } catch { /* ignore — 다음 sync 때 다시 시도될 수 있음 */ }
}
