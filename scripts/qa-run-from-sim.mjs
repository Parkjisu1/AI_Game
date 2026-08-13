#!/usr/bin/env node
/**
 * qa-run-from-sim.mjs — BalloonFlowSim 결과를 기능 QA 실행 관측으로 변환.
 *
 * ⚠ 등급 주의: BalloonFlowSim 은 게임 코드가 아니라 **재구현 시뮬레이터**다.
 *   (정합성 감사로 게임 로직과 대조는 했지만, Unity 빌드가 도는 증거는 아니다.)
 *   그래서 confidence="proxy" 로 기록한다. 화면에서 초록(=된다)이 되지 않고
 *   "◐ 대리관측" 으로 따로 표시된다. 이 구분을 없애면 거짓 초록이 된다.
 *
 * 실기 관측(confidence="direct")은 analytics 이벤트 로그나 PlayMode 테스트에서 와야 하며,
 * 그건 POST /api/qa/runs 로 넣는다. 이 스크립트는 그 자리를 대신하지 않는다.
 *
 * 사용: MONGODB_URI=... node qa-run-from-sim.mjs [--project balloonflow]
 */
import fs from "fs";
import { MongoClient } from "mongodb";

const arg = (n, d = null) => { const i = process.argv.indexOf(`--${n}`); return i >= 0 ? process.argv[i + 1] : d; };
const PROJECT = (arg("project", "balloonflow") || "").toLowerCase();

// .env 직접 로드 — cron 에서 `. .env` 로 소싱하면 URI 쿼리스트링의 `&` 를 sh 가
// 백그라운드 연산자로 읽어 값이 잘린다. 셸에 맡기지 않는다.
try {
  for (const line of fs.readFileSync(process.env.HERMES_ENV_FILE || "/home/aimed/.hermes/watcher/.env", "utf8").split("\n")) {
    const s = line.trim();
    if (!s || s.startsWith("#")) continue;
    const i = s.indexOf("=");
    if (i > 0 && !process.env[s.slice(0, i).trim()]) process.env[s.slice(0, i).trim()] = s.slice(i + 1).trim().replace(/^["']|["']$/g, "");
  }
} catch { /* 없으면 진행 */ }

const uri = process.env.MONGODB_URI;
if (!uri) { console.error("MONGODB_URI 필요"); process.exit(1); }

const cli = new MongoClient(uri, { serverSelectionTimeoutMS: 15000 });
await cli.connect();
const db = cli.db(process.env.MONGODB_DB || "aigame");

const sim = await db.collection("bf_sim_results").findOne({}, { sort: { created_at: -1 } });
if (!sim) { console.log(JSON.stringify({ skipped: true, reason: "bf_sim_results 없음" })); await cli.close(); process.exit(0); }

const rows = Array.isArray(sim.results) ? sim.results : [];
const sum = sim.summary || {};
const totalDarts = rows.reduce((a, r) => a + (Number(r.totalDarts) || 0), 0);
const cleared = rows.filter((r) => Number(r.clearRate) > 0).length;
const avgClear = Number(sum.avgClearRate) || 0;
const observedAt = sim.created_at instanceof Date ? sim.created_at.toISOString() : String(sim.created_at || new Date().toISOString());

// 시뮬이 실제로 무엇을 수행했는지에서만 신호를 만든다 — 없는 지표를 지어내지 않는다.
const runs = [
  {
    featureId: "bf.level.start", ok: rows.length > 0,
    detail: `시뮬이 레벨 ${rows.length}개를 로드해 시작 (levelCount=${sum.levelCount ?? rows.length})`,
  },
  {
    featureId: "bf.ingame.dart_launch", ok: totalDarts > 0,
    detail: `다트 발사 누적 ${totalDarts}개`,
  },
  {
    featureId: "bf.ingame.balloon_pop", ok: cleared > 0,
    detail: `${cleared}개 레벨에서 클리어 발생 = 풍선 파괴가 실제로 일어남`,
  },
  {
    featureId: "bf.ingame.level_clear", ok: avgClear > 0,
    detail: `평균 클리어율 ${(avgClear * 100).toFixed(1)}% (클리어율 0인 레벨 ${rows.filter((r) => !Number(r.clearRate)).length}개)`,
  },
];

const col = db.collection("qa_feature_runs");
let n = 0;
for (const r of runs) {
  await col.updateOne(
    { project: PROJECT, featureId: r.featureId, source: "bf_sim", observedAt },
    { $set: { ...r, project: PROJECT, source: "bf_sim", confidence: "proxy", observedAt, simTaskId: String(sim.task_id || "") } },
    { upsert: true },
  );
  n++;
}
console.log(JSON.stringify({ project: PROJECT, upserted: n, observedAt, avgClearRate: avgClear, totalDarts }));
await cli.close();
