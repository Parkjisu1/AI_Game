import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, authDisabled } from "@/auth";

/**
 * 플랫폼 현황 — webstore 가 어떤 기능으로 구성돼 있는지 + 지금 살아 있는지.
 *
 * 구성도(tree/apis/entities)는 `newplay_platform_map` 스냅샷을 읽는다.
 * 원천은 qdrant 의 7,176 청크인데 화면 열 때마다 훑으면 느리고, 레포는 커밋 때만 바뀐다.
 * 갱신: node ~/newplay-index/build-platform-map.js
 *
 * 실시간(status)은 매 호출마다 실제로 확인한다 — 캐시하면 "살아 있다"는 거짓말을 하게 된다.
 */
export const dynamic = "force-dynamic";

const QDRANT = process.env.NEWPLAY_QDRANT_URL || "http://127.0.0.1:6343";
const KB_COLLECTION = process.env.NEWPLAY_KB_COLLECTION || "newplay_code";

type Svc = { name: string; label: string; ok: boolean; detail: string; ms: number };

async function timed<T>(fn: () => Promise<T>): Promise<[T | null, number, string]> {
  const t = Date.now();
  try {
    const v = await fn();
    return [v, Date.now() - t, ""];
  } catch (e: unknown) {
    return [null, Date.now() - t, e instanceof Error ? e.message : String(e)];
  }
}

export async function GET(req: NextRequest) {
  if (!authDisabled) {
    const s = await auth();
    if (!s?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const url = new URL(req.url);
  const project = url.searchParams.get("project") || "webstore";
  // ?live=1 — 구성도(약 220KB)를 빼고 상태만. 10초 폴링이 매번 트리를 받을 이유가 없다.
  const liveOnly = url.searchParams.get("live") === "1";

  const db = await getDb();
  const services: Svc[] = [];

  // 1) Mongo — 여기까지 왔으면 붙은 것이다. 왕복 시간만 잰다.
  {
    const [v, ms, err] = await timed(async () => db.command({ ping: 1 }));
    services.push({ name: "mongo", label: "MongoDB (newteam)", ok: !!v, detail: err || "rs0 · 27018", ms });
  }

  // 2) Qdrant 지식베이스 — 포인트 수까지 봐야 "비어 있는데 살아 있다" 를 안 본다.
  let kb: { points?: number; dim?: number } = {};
  {
    const [v, ms, err] = await timed(async () => {
      const r = await fetch(`${QDRANT}/collections/${KB_COLLECTION}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return (await r.json()).result;
    });
    const pts = v?.points_count ?? 0;
    kb = { points: pts, dim: v?.config?.params?.vectors?.size };
    services.push({
      name: "qdrant", label: "지식베이스 (qdrant :6343)",
      ok: !!v && pts > 0,
      detail: err || `${pts.toLocaleString()} 청크 · ${kb.dim}차원`,
      ms,
    });
  }

  // 3) Hermes 워처 — heartbeat 로 판정. 프로세스 존재가 아니라 "최근에 살아 있었나" 가 기준이다.
  {
    const [v, ms, err] = await timed(async () =>
      db.collection("hermes_workers").find({}).sort({ ts: -1 }).limit(3).toArray());
    const rows = v || [];
    const newest = rows[0]?.ts ? new Date(rows[0].ts).getTime() : 0;
    const ageSec = newest ? Math.round((Date.now() - newest) / 1000) : -1;
    const alive = ageSec >= 0 && ageSec < 180;
    services.push({
      name: "watcher", label: "Hermes 워처",
      ok: alive,
      detail: err || (ageSec < 0 ? "heartbeat 없음" : `${ageSec}초 전 · 워커 ${rows.length}`),
      ms,
    });
  }

  // 4) LLM 게이트웨이 (Mother 의 LiteLLM 공유)
  {
    const base = process.env.LITELLM_URL || "";
    const [v, ms, err] = await timed(async () => {
      if (!base) throw new Error("LITELLM_URL 미설정");
      const r = await fetch(`${base}/health/liveliness`, { cache: "no-store", signal: AbortSignal.timeout(5000) });
      return r.ok;
    });
    services.push({ name: "litellm", label: "LLM 게이트웨이", ok: !!v, detail: err || base, ms });
  }

  // 실시간 작업 현황
  const tasks = db.collection("pixelforge_tasks");
  const [counts, recent, sessions] = await Promise.all([
    Promise.all(["todo", "in_progress", "review", "done"].map((s) => tasks.countDocuments({ status: s }))),
    tasks.find({}, { projection: { title: 1, status: 1, team: 1, sub_team: 1, updated_at: 1 } })
      .sort({ updated_at: -1 }).limit(6).toArray(),
    db.collection("hermes_agent_sessions")
      .find({}, { projection: { role: 1, model: 1, success: 1, duration_sec: 1, created_at: 1, task_title: 1 } })
      .sort({ created_at: -1 }).limit(10).toArray(),
  ]);

  const map = liveOnly ? null : await db.collection("newplay_platform_map").findOne({ project });

  return NextResponse.json({
    services,
    kb,
    tasks: { todo: counts[0], in_progress: counts[1], review: counts[2], done: counts[3], recent },
    sessions,
    composition: map
      ? {
          project: map.project, sha: map.sha, generatedAt: map.generatedAt,
          totals: map.totals, kindCount: map.kindCount,
          tree: map.tree, apis: map.apis, entities: map.entities,
          screens: map.screens, liveBaseUrl: map.liveBaseUrl,
        }
      : null,
  });
}
