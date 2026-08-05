#!/usr/bin/env node
/**
 * tasks-snapshot.js — /api/tasks 응답을 미리 만들어 디스크에 둔다.
 *
 * 왜 (실측):
 *   pixelforge_tasks 811건을 매 요청마다 Atlas 에서 전량 읽는다(834KB).
 *   그런데 **하루에 바뀌는 건 11건**이다. 811건을 매번 읽을 이유가 없다.
 *   더 큰 문제는 속도가 아니라 **변동성**이다 — 같은 쿼리가 0.37초였다가 82초가 된다(25배).
 *   Canva 가 세션 취소 조회를 MySQL 에서 S3 스냅샷으로 옮긴 것과 같은 이유다:
 *   핫패스에서 트랜잭션 스토어를 걷어내면 그 스토어의 컨디션과 무관해진다.
 *
 * 무엇을 하나:
 *   API 가 쓰는 것과 **똑같은 파이프라인**으로 만들어 파일로 쓴다(모양을 바꾸지 않는다 —
 *   화면이 description·comments·related_levels 등을 실제로 읽고 있어서 줄이면 깨진다).
 *   change stream 으로 바뀐 순간 다시 만들고, 그와 별개로 주기적으로도 다시 만든다
 *   (change stream 이 조용히 끊겨도 스냅샷이 낡은 채 남지 않게).
 *
 * 원자적 교체: tmp 에 쓰고 rename. 읽는 쪽이 반쪽짜리 JSON 을 보지 않게.
 *
 * Usage:
 *   node tasks-snapshot.js --once     # 한 번 만들고 종료
 *   node tasks-snapshot.js --watch    # change stream + 주기 재생성 (systemd 용)
 */
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');

const args = process.argv.slice(2);
const ONCE = args.includes('--once');
const WATCH = args.includes('--watch');
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };

const OUT = argOf('--out', path.join(os.homedir(), '.hermes', 'cache', 'tasks-snapshot.json'));
const DEBOUNCE_MS = Number(argOf('--debounce', '1500'));
const PERIOD_MS = Number(argOf('--period', String(5 * 60 * 1000)));

function loadEnv() {
  const envUri = process.env.MONGODB_URI || process.env.MONGO_URI;
  if (envUri) return { uri: envUri, db: process.env.MONGODB_DB || 'aigame' };
  for (const p of [
    path.join(os.homedir(), '.hermes/watcher/.env'),
    path.resolve(__dirname, '../.env'),
  ]) {
    try {
      if (!fs.existsSync(p)) continue;
      const txt = fs.readFileSync(p, 'utf8');
      const get = (k) => {
        const m = txt.match(new RegExp('^' + k + '=(.*)$', 'm'));
        return m ? m[1].trim().replace(/^["']|["']$/g, '') : null;
      };
      const uri = get('MONGODB_URI') || get('MONGO_URI');
      if (uri) return { uri, db: get('MONGODB_DB') || 'aigame' };
    } catch { /* 다음 후보 */ }
  }
  throw new Error('MONGODB_URI 를 찾지 못했습니다');
}

/** /api/tasks GET 과 **동일한** 파이프라인. 여기가 어긋나면 화면이 조용히 달라진다. */
const PIPELINE = [
  { $match: {} },
  { $project: { image_base64: 0, attachments: 0, embedding: 0 } },
  { $sort: { created_at: -1 } },
  {
    $addFields: {
      has_image: { $ifNull: ['$has_image', false] },
      comments: { $slice: [{ $ifNull: ['$comments', []] }, -5] },
    },
  },
];

async function build(col) {
  const t0 = Date.now();
  const tasks = await col.aggregate(PIPELINE, { allowDiskUse: true }).toArray();
  const payload = {
    generatedAt: new Date().toISOString(),
    buildMs: Date.now() - t0,
    count: tasks.length,
    tasks,
  };
  const body = JSON.stringify(payload);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const tmp = OUT + '.tmp';
  fs.writeFileSync(tmp, body);
  fs.renameSync(tmp, OUT);   // 원자적 교체
  return { n: tasks.length, ms: payload.buildMs, bytes: Buffer.byteLength(body) };
}

async function main() {
  const { uri, db } = loadEnv();
  const { MongoClient } = require('mongodb');
  const cli = new MongoClient(uri, { serverSelectionTimeoutMS: 20000, socketTimeoutMS: 600000 });
  await cli.connect();
  const col = cli.db(db).collection('pixelforge_tasks');

  const r = await build(col);
  console.log(`스냅샷 생성 ${r.n}건 · ${(r.bytes / 1024).toFixed(0)}KB · ${r.ms}ms → ${OUT}`);

  if (ONCE || !WATCH) { await cli.close(); return; }

  let timer = null;
  const schedule = (why) => {
    if (timer) return;
    timer = setTimeout(async () => {
      timer = null;
      try {
        const x = await build(col);
        console.log(`갱신(${why}) ${x.n}건 · ${x.ms}ms`);
      } catch (e) {
        console.error('갱신 실패:', e.message);
      }
    }, DEBOUNCE_MS);
  };

  // 주기 재생성 — change stream 이 조용히 끊겨도 스냅샷이 낡은 채 남지 않게 하는 안전망
  setInterval(() => schedule('주기'), PERIOD_MS);

  // change stream — 바뀐 순간 반영
  const startStream = () => {
    const stream = col.watch([], { fullDocument: 'default' });
    stream.on('change', () => schedule('변경'));
    stream.on('error', (e) => {
      console.error('change stream 오류 — 30초 후 재연결:', e.message);
      try { stream.close(); } catch { /* ignore */ }
      setTimeout(startStream, 30000);
    });
    console.log('change stream 감시 시작');
  };
  startStream();

  process.on('SIGTERM', async () => { await cli.close(); process.exit(0); });
}

main().catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
