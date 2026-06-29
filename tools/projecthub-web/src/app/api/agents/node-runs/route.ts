import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

/**
 * Hermes 노드 실행 저널 (hermes_node_runs).
 *   ?task_id=...  → { runs: [노드 실행 status 문서들], files: [이 작업이 수정한 파일] }
 *   (no task_id)  → { running: [현재 실행 중(running, 30분 내) 노드들] }  ← 실시간 in-flight
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const taskId = url.searchParams.get("task_id");
  const db = await getDb();
  const coll = db.collection("hermes_node_runs");

  if (taskId) {
    const runs = await coll
      .find({ task_id: taskId, kind: { $ne: "files" } },
        { projection: { task_id: 1, role: 1, model: 1, status: 1, started_at: 1, ended_at: 1 } })
      .sort({ started_at: -1 })
      .limit(60)
      .toArray();
    const filesDoc = await coll.find({ task_id: taskId, kind: "files" }).sort({ created_at: -1 }).limit(1).toArray();
    return NextResponse.json({ runs, files: (filesDoc[0]?.files as string[]) || [] });
  }

  const cutoff = new Date(Date.now() - 30 * 60 * 1000);
  const running = await coll
    .find({ status: "running", started_at: { $gte: cutoff } }, { projection: { task_id: 1, role: 1, started_at: 1 } })
    .sort({ started_at: -1 })
    .limit(40)
    .toArray();
  return NextResponse.json({ running });
}
