import { NextRequest, NextResponse } from "next/server";
import { MongoClient } from "mongodb";

/**
 * 기능 QA — 실행 관측(③등급) 수집·조회.
 *
 * 구조(①)는 git 과 함께 움직이니 파일(`<project>-features.json`)로 서빙하지만,
 * 실행 관측은 git 과 무관하게 들어온다(테스트 러너·실기 로그·시뮬). 그래서 DB 로 분리하고
 * 화면이 이 API 로 최신 상태를 덧입힌다. push 가 없어도 실행 결과는 즉시 반영된다.
 *
 * GET  /api/qa/runs?project=balloonflow      → 기능별 최신 관측 1건
 * POST /api/qa/runs                          → 관측 기록
 *   { project, featureId, ok, source, detail?, confidence?: "direct"|"proxy", observedAt? }
 *
 * confidence 는 기본 "direct"(실기 관측). 게임 코드가 아닌 대리물(시뮬레이터 등)의 관측은
 * 반드시 "proxy" 로 넣어야 한다 — 화면에서 초록으로 세지 않기 위한 구분이다.
 */

const uri = process.env.MONGODB_URI || "";
const dbName = process.env.MONGODB_DB || "aigame";

let cached: MongoClient | null = null;
async function db() {
  if (!uri) throw new Error("MONGODB_URI 미설정");
  if (!cached) cached = await new MongoClient(uri, { serverSelectionTimeoutMS: 10000 }).connect();
  return cached.db(dbName);
}

export async function GET(req: NextRequest) {
  const project = (req.nextUrl.searchParams.get("project") || "balloonflow").toLowerCase();
  try {
    const rows = await (await db())
      .collection("qa_feature_runs")
      .find({ project }, { projection: { _id: 0 } })
      .sort({ observedAt: -1 })
      .limit(500)
      .toArray();

    // 기능별 최신 1건. 단, 직접 관측이 있으면 대리 관측이 그것을 가리지 않게 한다.
    const latest: Record<string, unknown> = {};
    for (const r of rows as unknown as { featureId: string; confidence?: string }[]) {
      const cur = latest[r.featureId] as { confidence?: string } | undefined;
      if (!cur) latest[r.featureId] = r;
      else if (cur.confidence === "proxy" && r.confidence !== "proxy") latest[r.featureId] = r;
    }
    return NextResponse.json({ project, runs: Object.values(latest), seen: rows.length });
  } catch (e) {
    return NextResponse.json({ project, runs: [], error: (e as Error).message }, { status: 200 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const b = await req.json();
    const project = String(b.project || "").toLowerCase();
    const featureId = String(b.featureId || "");
    if (!project || !featureId) {
      return NextResponse.json({ error: "project, featureId 필수" }, { status: 400 });
    }
    if (typeof b.ok !== "boolean") {
      // 판정 없는 관측은 받지 않는다 — "된다/안 된다"가 이 판의 목적이다.
      return NextResponse.json({ error: "ok(boolean) 필수" }, { status: 400 });
    }
    const confidence = b.confidence === "proxy" ? "proxy" : "direct";
    const observedAt = String(b.observedAt || new Date().toISOString());
    const doc = {
      project, featureId, ok: b.ok, confidence, observedAt,
      source: String(b.source || "manual"),
      detail: String(b.detail || ""),
      build: b.build ? String(b.build) : undefined,
    };
    await (await db()).collection("qa_feature_runs").updateOne(
      { project, featureId, source: doc.source, observedAt },
      { $set: doc },
      { upsert: true },
    );
    return NextResponse.json({ ok: true, recorded: doc });
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}
