#!/usr/bin/env node
/**
 * embed-upsert.js — 청크 JSONL 을 임베딩해서 qdrant-newteam 에 적재한다. (NewPlay 전용)
 *
 * 격리 전제:
 *   NewPlay 는 게임팀과 완전히 분리돼 있다.
 *     - Mongo   : aimed-sub 로컬 27018 / DB `newteam`  (게임팀은 Atlas)
 *     - Qdrant  : aimed-sub 127.0.0.1:6343            (게임팀은 :6333)
 *   이 스크립트는 :6343 외에는 절대 쓰지 않는다. 포트를 바꿔 실행하지 말 것.
 *
 * 왜 Qdrant 인가:
 *   게임팀 RAG 는 Atlas `$vectorSearch` 를 쓰는데, NewPlay 의 Mongo 는 로컬 커뮤니티 서버라
 *   `$vectorSearch` 자체가 없다. 그래서 벡터 저장소는 Qdrant 가 유일한 선택지다.
 *
 * 재실행 안전:
 *   포인트 id 를 청크 키(project:path:line)의 md5 → UUID 로 고정한다. 같은 커밋을 다시 넣어도
 *   중복이 안 생기고, 바뀐 줄만 덮어써진다.
 *
 * Usage:
 *   node embed-upsert.js --in chunks.jsonl [--collection newplay_code] [--limit N] [--dry]
 */
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const args = process.argv.slice(2);
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const IN = argOf('--in', 'chunks.jsonl');
const COLLECTION = argOf('--collection', 'newplay_code');
const QDRANT = argOf('--qdrant', 'http://127.0.0.1:6343');
const MODEL = argOf('--model', 'text-embedding-3-small');
const DIM = 1536;
const LIMIT = Number(argOf('--limit', '0')) || 0;
const DRY = args.includes('--dry');

const EMBED_BATCH = 96;    // OpenAI 한 요청당 입력 수
const UPSERT_BATCH = 256;  // Qdrant 한 요청당 포인트 수

function loadEnv() {
  if (process.env.OPENAI_API_KEY) return process.env.OPENAI_API_KEY;
  const candidates = [
    path.join(process.env.HOME || '', 'projecthub-newteam/.env.production'),
    path.resolve(__dirname, '../../.env'),
  ];
  for (const p of candidates) {
    try {
      if (!p || !fs.existsSync(p)) continue;
      const m = fs.readFileSync(p, 'utf8').match(/^OPENAI_API_KEY=(.*)$/m);
      if (m) return m[1].trim().replace(/^["']|["']$/g, '');
    } catch { /* 다음 후보 */ }
  }
  throw new Error('OPENAI_API_KEY 를 찾지 못했습니다');
}

/** 청크 키를 결정적 UUID 로 — Qdrant 는 문자열 id 를 안 받는다 */
function pointId(key) {
  const h = crypto.createHash('md5').update(key).digest('hex');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
}

async function qdrant(method, url, body) {
  const r = await fetch(QDRANT + url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const txt = await r.text();
  if (!r.ok) throw new Error(`qdrant ${method} ${url} → ${r.status} ${txt.slice(0, 300)}`);
  return txt ? JSON.parse(txt) : null;
}

async function embed(key, inputs) {
  for (let attempt = 1; attempt <= 5; attempt++) {
    const r = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
      body: JSON.stringify({ model: MODEL, input: inputs }),
    });
    if (r.ok) {
      const j = await r.json();
      return j.data.sort((a, b) => a.index - b.index).map((d) => d.embedding);
    }
    const txt = await r.text();
    // 429/5xx 는 지수 백오프로 재시도 — 7천 청크를 넣다 중간에 죽으면 처음부터가 된다
    if (r.status === 429 || r.status >= 500) {
      const wait = Math.min(30000, 1000 * 2 ** attempt);
      console.log(`  임베딩 ${r.status} — ${wait / 1000}s 후 재시도 (${attempt}/5)`);
      await new Promise((s) => setTimeout(s, wait));
      continue;
    }
    throw new Error(`embeddings ${r.status}: ${txt.slice(0, 300)}`);
  }
  throw new Error('임베딩 재시도 5회 초과');
}

async function ensureCollection() {
  const list = await qdrant('GET', '/collections');
  const exists = (list.result.collections || []).some((c) => c.name === COLLECTION);
  if (exists) {
    const info = await qdrant('GET', `/collections/${COLLECTION}`);
    const size = info.result.config.params.vectors.size;
    if (size !== DIM) throw new Error(`기존 컬렉션 차원 불일치: ${size} != ${DIM}`);
    console.log(`컬렉션 ${COLLECTION} 존재 (points ${info.result.points_count})`);
    return;
  }
  await qdrant('PUT', `/collections/${COLLECTION}`, {
    vectors: { size: DIM, distance: 'Cosine' },
  });
  // 필터 걸 필드는 인덱스를 만들어야 실제로 빨라진다
  for (const [field, type] of [['project', 'keyword'], ['area', 'keyword'], ['kind', 'keyword'], ['path', 'keyword'], ['lang', 'keyword']]) {
    await qdrant('PUT', `/collections/${COLLECTION}/index?wait=true`, { field_name: field, field_schema: type });
  }
  console.log(`컬렉션 ${COLLECTION} 생성 (dim ${DIM}, Cosine) + 페이로드 인덱스 5종`);
}

async function main() {
  const key = loadEnv();
  let rows = fs.readFileSync(IN, 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  if (LIMIT) rows = rows.slice(0, LIMIT);
  console.log(`입력 ${rows.length}청크 · 모델 ${MODEL} · 대상 ${QDRANT}/${COLLECTION}`);
  if (DRY) { console.log('[예행] 아무것도 쓰지 않았습니다.'); return; }

  await ensureCollection();

  const t0 = Date.now();
  let done = 0;
  let pending = [];

  const flush = async () => {
    if (!pending.length) return;
    await qdrant('PUT', `/collections/${COLLECTION}/points?wait=true`, { points: pending });
    pending = [];
  };

  for (let i = 0; i < rows.length; i += EMBED_BATCH) {
    const batch = rows.slice(i, i + EMBED_BATCH);
    const vecs = await embed(key, batch.map((r) => r.text));
    for (let k = 0; k < batch.length; k++) {
      const r = batch[k];
      pending.push({
        id: pointId(r.id),
        vector: vecs[k],
        payload: {
          project: r.project, area: r.area, path: r.path, kind: r.kind, lang: r.lang,
          startLine: r.startLine, endLine: r.endLine, symbols: r.symbols, sha: r.sha,
          text: r.text,
        },
      });
    }
    if (pending.length >= UPSERT_BATCH) await flush();
    done += batch.length;
    if (done % (EMBED_BATCH * 10) < EMBED_BATCH || done === rows.length) {
      const rate = done / ((Date.now() - t0) / 1000);
      const eta = Math.round((rows.length - done) / rate);
      console.log(`  ${done}/${rows.length} (${(done / rows.length * 100).toFixed(0)}%) · ${rate.toFixed(0)}청크/s · 남은 ${eta}s`);
    }
  }
  await flush();

  const info = await qdrant('GET', `/collections/${COLLECTION}`);
  console.log(`완료 — points ${info.result.points_count} · ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}

main().catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
