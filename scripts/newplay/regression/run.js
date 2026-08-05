#!/usr/bin/env node
/**
 * run.js — NewPlay 파이프라인 회귀 세트 러너.
 *
 * 왜 필요한가:
 *   같은 입력에 매번 다른 결과가 나온다(실측 — Game Key 재현에서 질문 내용이 달랐다).
 *   그 상태에서 학습이나 그래프를 붙이면 "좋아졌는지" 를 말할 근거가 없다.
 *   고정 입력으로 눈금을 먼저 만든다.
 *
 * 두 단계로 나눈 이유:
 *   full 은 케이스당 코더+검수로 10~20분이 든다. 매번 돌릴 수 없다.
 *   라우팅·되묻기 회귀는 fast(수 초)로 잡히므로 자주 돌릴 수 있게 분리했다.
 *
 *   --fast   Translator + PM 까지만. 라우팅 정확도 / 되묻기 여부.
 *   --full   실제 작업 + 검수까지. 파일 recall / 검수 점수 / 소요 시간.
 *
 * 회귀 태스크는 수집 후 **삭제한다.** 보드에 실험물이 쌓이면 진짜 작업과 섞인다.
 * 결과만 newplay_regression_runs 에 남는다.
 *
 * Usage:
 *   node run.js --fast
 *   node run.js --full [--only payment-label,footer-year]
 *   node run.js --compare            # 최근 2회 실행 비교
 */
'use strict';

const fs = require('fs');
const path = require('path');

const MONGO = process.env.NEWTEAM_MONGO_URI || 'mongodb://127.0.0.1:27018/?directConnection=true';
const DB = 'newteam';
const args = process.argv.slice(2);
const FAST = args.includes('--fast');
const FULL = args.includes('--full');
const COMPARE = args.includes('--compare');
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const ONLY = (argOf('--only', '') || '').split(',').map((s) => s.trim()).filter(Boolean);

const CASES = JSON.parse(fs.readFileSync(path.join(__dirname, 'cases.json'), 'utf8')).cases;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 결과 문서에서 파일 경로를 뽑는다 — 패치 대상 + 본문에 인용된 경로 둘 다. */
function mentionedFiles(task) {
  const out = new Set();
  for (const f of task.patch_files || []) out.add(String(f));
  const text = String(task.deliverable || '');
  // `backend/src/...` `front-end/src/...` 형태의 경로를 본문에서 수집
  for (const m of text.matchAll(/\b((?:backend|front-end)\/[A-Za-z0-9_./-]+\.[A-Za-z]{1,5})/g)) out.add(m[1]);
  return [...out];
}

function scoreCase(c, task) {
  const asked = (task.comments || []).some((cm) => String(cm.text || '').includes('정보 확인 필요'));
  const team = String(task.team || '');
  const sub = String(task.sub_team || '');
  const files = mentionedFiles(task);
  const expected = c.expect_files || [];
  const hit = expected.filter((e) => files.includes(e));
  const verdictC = (task.comments || []).find((cm) => String(cm.text || '').includes('검수:'));
  const vm = verdictC ? String(verdictC.text).match(/검수: `(\w+)`(?:\s*\((\d+)점\))?/) : null;

  return {
    id: c.id,
    status: task.status,
    team, sub_team: sub,
    team_ok: !c.expect.team || team === c.expect.team,
    sub_ok: !c.expect.sub_team || sub === c.expect.sub_team,
    asked,
    ask_ok: c.expect.no_ask === undefined ? true : (c.expect.no_ask ? !asked : true),
    files_found: files.length,
    recall: expected.length ? +(hit.length / expected.length).toFixed(2) : null,
    missed: expected.filter((e) => !files.includes(e)),
    verdict: vm ? vm[1] : '',
    score: vm && vm[2] ? Number(vm[2]) : null,
    criteria: (task.acceptance_criteria || []).length,
    comments: (task.comments || []).length,
  };
}

async function main() {
  const { MongoClient, ObjectId } = require('mongodb');
  const cli = new MongoClient(MONGO, { serverSelectionTimeoutMS: 10000 });
  await cli.connect();
  const db = cli.db(DB);
  const col = db.collection('pixelforge_tasks');
  const runs = db.collection('newplay_regression_runs');

  if (COMPARE) {
    const last = await runs.find({}).sort({ started_at: -1 }).limit(2).toArray();
    if (last.length < 2) { console.log('비교할 실행이 2회 미만입니다.'); await cli.close(); return; }
    const [now, prev] = last;
    console.log(`비교: ${prev.started_at} (${prev.mode})  →  ${now.started_at} (${now.mode})\n`);
    const key = (r) => r.id;
    const pm = new Map(prev.results.map((r) => [key(r), r]));
    for (const r of now.results) {
      const p = pm.get(key(r));
      if (!p) { console.log(`  ${r.id.padEnd(16)} (신규)`); continue; }
      const bits = [];
      if (p.team_ok !== r.team_ok) bits.push(`팀 ${p.team_ok ? 'OK' : 'X'}→${r.team_ok ? 'OK' : 'X'}`);
      if (p.asked !== r.asked) bits.push(`되묻기 ${p.asked ? 'Y' : 'N'}→${r.asked ? 'Y' : 'N'}`);
      if (p.recall !== null && r.recall !== null && p.recall !== r.recall) bits.push(`recall ${p.recall}→${r.recall}`);
      if (p.score !== null && r.score !== null && p.score !== r.score) bits.push(`검수 ${p.score}→${r.score}`);
      console.log(`  ${r.id.padEnd(16)} ${bits.length ? bits.join(' · ') : '변화 없음'}`);
    }
    await cli.close();
    return;
  }

  if (!FAST && !FULL) { console.log('--fast 또는 --full 을 지정하세요.'); await cli.close(); return; }

  const cases = ONLY.length ? CASES.filter((c) => ONLY.includes(c.id)) : CASES;
  const mode = FULL ? 'full' : 'fast';
  const runId = `reg_${new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 14)}`;
  console.log(`회귀 실행 ${runId} · 모드=${mode} · 케이스 ${cases.length}건`);
  console.log(FAST ? '(fast: 라우팅·되묻기만 — 작업 시작 직후 중단)' : '(full: 작업+검수 완료까지 대기)');

  const started = new Date().toISOString();
  const results = [];
  const ids = [];

  // 케이스를 한 번에 넣으면 워커 2슬롯에서 순차 처리되어 오래 걸린다.
  // fast 는 순차, full 은 2건씩 흘려보낸다.
  for (const c of cases) {
    const now = new Date().toISOString();
    const doc = {
      title: `[회귀:${runId}] ${c.title}`,
      description: c.description,
      status: 'todo', assignee: 'hermes', project: 'webstore',
      regression_run: runId, regression_case: c.id,
      created_at: now, updated_at: now, comments: [], has_image: false,
    };
    if (c.expect.team && FAST) { /* fast 에서도 라우팅은 AI 가 하게 둔다 — 그게 측정 대상이다 */ }
    const r = await col.insertOne(doc);
    ids.push({ id: r.insertedId, c });
    process.stdout.write(`  넣음 ${c.id}\n`);
    await sleep(FULL ? 1500 : 800);
  }

  // 대기 — fast 는 팀 배정만 되면 끝, full 은 review 까지
  const deadline = Date.now() + (FULL ? 90 : 8) * 60 * 1000;
  const done = new Set();
  while (done.size < ids.length && Date.now() < deadline) {
    await sleep(FAST ? 5000 : 20000);
    for (const { id, c } of ids) {
      if (done.has(String(id))) continue;
      const t = await col.findOne({ _id: id });
      if (!t) { done.add(String(id)); continue; }
      const routed = !!t.team || String(t.status) === 'review';
      const finished = FULL ? (t.status === 'review' || t.status === 'done') : routed;
      if (finished) {
        results.push(scoreCase(c, t));
        done.add(String(id));
        process.stdout.write(`  완료 ${c.id} (${done.size}/${ids.length})\n`);
      }
    }
  }
  // 시간 초과분도 현재 상태로 기록한다 — 침묵보다 낫다
  for (const { id, c } of ids) {
    if (done.has(String(id))) continue;
    const t = await col.findOne({ _id: id });
    if (t) results.push({ ...scoreCase(c, t), timeout: true });
  }

  // 보드 청소 — 회귀 태스크는 흔적을 남기지 않는다
  await col.deleteMany({ regression_run: runId });

  const summary = {
    cases: results.length,
    team_ok: results.filter((r) => r.team_ok).length,
    sub_ok: results.filter((r) => r.sub_ok).length,
    ask_ok: results.filter((r) => r.ask_ok).length,
    recall_avg: (() => {
      const rs = results.map((r) => r.recall).filter((x) => x !== null);
      return rs.length ? +(rs.reduce((a, b) => a + b, 0) / rs.length).toFixed(2) : null;
    })(),
    timeouts: results.filter((r) => r.timeout).length,
  };

  await runs.insertOne({ run_id: runId, mode, started_at: started, finished_at: new Date().toISOString(), summary, results });

  console.log('\n=== 결과 ===');
  console.log('케이스'.padEnd(16), '팀', '분과', '되묻기', 'recall', '검수', '파일');
  for (const r of results) {
    console.log(
      r.id.padEnd(16),
      (r.team_ok ? 'O' : 'X') + ` ${r.team || '-'}`.padEnd(9),
      (r.sub_ok ? 'O' : 'X') + ` ${r.sub_team || '-'}`.padEnd(10),
      (r.asked ? 'Y' : 'N') + (r.ask_ok ? ' ' : '!') + '  ',
      String(r.recall === null ? '-' : r.recall).padEnd(6),
      String(r.score === null ? '-' : r.score).padEnd(4),
      String(r.files_found).padEnd(4),
      r.timeout ? '(시간초과)' : '',
    );
    if (r.missed && r.missed.length) console.log('   놓친 파일:', r.missed.join(', '));
  }
  console.log('\n요약:', JSON.stringify(summary));
  console.log(`저장됨 → ${DB}.newplay_regression_runs (${runId})`);

  await cli.close();
}

main().catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
