#!/usr/bin/env node
/**
 * rag-baseline.js — Hermes RAG 효과 측정용 cycle/reject 베이스라인.
 *
 * RAG 생성 주입 배포일(2026-06-02) 기준 before/after 로 hermes_team_scores 를 나눠
 * cycle 길이 / user_rejected_after_approval / REQUEST_CHANGES 비율을 집계한다.
 *
 * "cycle" 정의: 한 task_id 에 대한 *reviewer* role 평가 레코드 수
 *   (= 그 task 가 몇 번 리뷰됐나 = rework 횟수 + 1).
 *
 * Usage: node scripts/rag-baseline.js [--cutoff 2026-06-02] [--save]
 */
const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env', 'utf8').split(/\r?\n/).reduce((a, l) => {
  const m = l.match(/^([^=]+)=(.*)$/); if (m) a[m[1].trim()] = m[2].trim(); return a;
}, {});
const { MongoClient } = require('mongodb');

const args = process.argv.slice(2);
const cutoff = (args[args.indexOf('--cutoff') + 1] && args.includes('--cutoff')) ? args[args.indexOf('--cutoff') + 1] : '2026-06-02';
const save = args.includes('--save');

function summarize(records) {
  // task_id -> { reviews: n, verdicts: {...} }
  const byTask = {};
  let userReject = 0, requestChanges = 0, approved = 0, totalReviewer = 0;
  for (const r of records) {
    const role = (r.role || '').toLowerCase();
    const isReviewer = role.includes('reviewer') || role === 'reviewer';
    const v = (r.verdict || '').toLowerCase();
    if (!isReviewer) continue;
    totalReviewer++;
    const t = r.task_id || 'unknown';
    byTask[t] = byTask[t] || { reviews: 0 };
    byTask[t].reviews++;
    if (v === 'user_rejected_after_approval') userReject++;
    else if (v === 'request_changes' || v === 'revise') requestChanges++;
    else if (v === 'approved' || v === 'ok') approved++;
  }
  const tasks = Object.values(byTask);
  const nTasks = tasks.length;
  const cycleCounts = tasks.map(t => t.reviews);
  const avgCycles = nTasks ? (cycleCounts.reduce((a, b) => a + b, 0) / nTasks) : 0;
  const maxCycles = nTasks ? Math.max(...cycleCounts) : 0;
  const explode = cycleCounts.filter(c => c >= 5).length; // cycle 폭발
  return {
    tasks: nTasks,
    reviewer_records: totalReviewer,
    avg_cycles_per_task: +avgCycles.toFixed(2),
    max_cycles: maxCycles,
    tasks_ge5_cycles: explode,
    pct_tasks_ge5: nTasks ? +(100 * explode / nTasks).toFixed(1) : 0,
    user_rejected_after_approval: userReject,
    pct_userreject_of_reviews: totalReviewer ? +(100 * userReject / totalReviewer).toFixed(1) : 0,
    request_changes: requestChanges,
    pct_requestchanges_of_reviews: totalReviewer ? +(100 * requestChanges / totalReviewer).toFixed(1) : 0,
    approved,
  };
}

(async () => {
  const c = new MongoClient(env.MONGO_URI); await c.connect();
  const db = c.db('aigame');
  const all = await db.collection('hermes_team_scores')
    .find({}, { projection: { task_id: 1, role: 1, verdict: 1, score: 1, created_at: 1, team: 1, sub_team: 1 } })
    .toArray();

  const cutoffISO = cutoff + 'T00:00:00';
  const before = all.filter(r => (r.created_at || '') < cutoffISO);
  const after = all.filter(r => (r.created_at || '') >= cutoffISO);

  const report = {
    generated_at_note: 'stamp after run',
    cutoff,
    total_records: all.length,
    baseline_before_rag: {
      window: `< ${cutoff}`,
      overall: summarize(before),
      dev_only: summarize(before.filter(r => (r.team || '') === 'dev')),
    },
    after_rag: {
      window: `>= ${cutoff}`,
      overall: summarize(after),
      dev_only: summarize(after.filter(r => (r.team || '') === 'dev')),
    },
  };

  const fmt = (s) => `tasks=${s.tasks} | avg_cycles=${s.avg_cycles_per_task} | max=${s.max_cycles} | ≥5cycle=${s.tasks_ge5_cycles}(${s.pct_tasks_ge5}%) | user_reject=${s.user_rejected_after_approval}(${s.pct_userreject_of_reviews}%) | req_changes=${s.request_changes}(${s.pct_requestchanges_of_reviews}%)`;
  console.log(`\n=== Hermes RAG 베이스라인 (cutoff ${cutoff}, RAG 배포일) ===`);
  console.log(`총 score 레코드: ${all.length}`);
  console.log(`\n[BASELINE — RAG 이전 (< ${cutoff})]`);
  console.log('  overall :', fmt(report.baseline_before_rag.overall));
  console.log('  dev only:', fmt(report.baseline_before_rag.dev_only));
  console.log(`\n[AFTER — RAG 이후 (>= ${cutoff})]`);
  console.log('  overall :', fmt(report.after_rag.overall));
  console.log('  dev only:', fmt(report.after_rag.dev_only));
  console.log('\n※ 해석: avg_cycles / ≥5cycle% / user_reject% 가 RAG 이후 낮아지면 효과 있음.');

  if (save) {
    const out = 'E:/AI/History/ProjectHub/rag_baseline_' + cutoff.replace(/-/g, '') + '.json';
    fs.mkdirSync('E:/AI/History/ProjectHub', { recursive: true });
    fs.writeFileSync(out, JSON.stringify(report, null, 2), 'utf8');
    console.log('\nsaved baseline →', out);
  }
  await c.close();
})().catch(e => { console.error(e.message); process.exit(1); });
