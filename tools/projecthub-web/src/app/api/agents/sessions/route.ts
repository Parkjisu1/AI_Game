import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

/**
 * 최근 Hermes 에이전트 세션 조회 (초기 로드용).
 * SSE 스트림은 /api/agents/sessions/stream 에서 실시간 갱신.
 *
 * Query:
 *   ?limit=50     최대 반환 건수 (기본 50, 상한 200)
 *   ?task_id=...  특정 task에 속한 세션만
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const limit = Math.min(200, Math.max(1, parseInt(url.searchParams.get("limit") || "50", 10)));
  const taskId = url.searchParams.get("task_id");

  const db = await getDb();
  const filter: Record<string, unknown> = {};
  if (taskId) filter.task_id = taskId;

  const docs = await db
    .collection("hermes_agent_sessions")
    .find(filter, {
      projection: {
        task_id: 1,
        task_title: 1,
        role: 1,
        model: 1,
        duration_sec: 1,
        success: 1,
        error: 1,
        output_len: 1,
        output_preview: 1,
        created_at: 1,
      },
    })
    .sort({ created_at: -1 })
    .limit(limit)
    .toArray();

  return NextResponse.json({ sessions: docs });
}
