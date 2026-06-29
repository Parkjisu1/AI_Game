import { getDb } from "./mongodb";
import { ObjectId } from "mongodb";

/**
 * 감사 로그 — 누가 언제 무엇을 바꿨는지 불변 기록.
 *
 * 이벤트 타입:
 *   task.created / task.updated / task.status_changed
 *   task.comment_added / task.deleted
 *   settings.updated / allowed_users.updated
 *   agents.role_updated / agents.role_deleted
 *
 * Actor source:
 *   "ui"       — ProjectHub 웹에서 로그인 사용자
 *   "hermes"   — Hermes watcher/executor가 직접
 *   "slack_dm" — Slack DM을 통해 들어온 코멘트
 *   "system"   — 자동화·catch-up 같은 무인 경로
 */

export interface AuditActor {
  email: string;
  source: "ui" | "hermes" | "slack_dm" | "system";
}

export interface AuditEntry {
  task_id?: string | null;
  event: string;
  actor: AuditActor;
  data?: Record<string, unknown>;
  created_at: string;
}

export async function recordAudit(entry: Omit<AuditEntry, "created_at">): Promise<void> {
  try {
    const db = await getDb();
    await db.collection("pixelforge_audit").insertOne({
      ...entry,
      _id: new ObjectId(),
      created_at: new Date().toISOString(),
    });
  } catch (e) {
    // 감사 로그 실패는 본 API 호출 실패로 연결되지 않음
    console.error("[audit] recordAudit failed:", e);
  }
}

export async function listAudit(params: { limit?: number; task_id?: string }): Promise<AuditEntry[]> {
  const db = await getDb();
  const q: Record<string, unknown> = {};
  if (params.task_id) q.task_id = params.task_id;
  const limit = Math.min(500, Math.max(1, params.limit ?? 100));
  const docs = await db
    .collection("pixelforge_audit")
    .find(q)
    .sort({ created_at: -1 })
    .limit(limit)
    .toArray();
  return docs.map((d) => ({
    task_id: (d.task_id as string | null) ?? null,
    event: String(d.event || ""),
    actor: (d.actor as AuditActor) ?? { email: "", source: "system" },
    data: (d.data as Record<string, unknown>) ?? {},
    created_at: String(d.created_at || ""),
  }));
}
