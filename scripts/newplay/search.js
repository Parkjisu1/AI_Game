#!/usr/bin/env node
/**
 * search.js — NewPlay 코드 지식베이스 검색. (qdrant-newteam :6343)
 *
 * 에이전트가 쓸 검색 경로다. 적재만 해두고 읽는 쪽이 없으면 지식베이스가 아니라 죽은 데이터라,
 * 이 파일이 그 소비자 역할을 한다.
 *
 * Usage:
 *   node search.js "결제 승인 orderId 검증"                     # 전체
 *   node search.js "환불 정책" --kind service --area backend     # 필터
 *   node search.js "쿠폰 발급" --top 8 --json                    # 기계 소비용
 */
'use strict';

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const QUERY = args.filter((a, i) => !a.startsWith('--') && (i === 0 || !args[i - 1].startsWith('--'))).join(' ').trim();
const QDRANT = argOf('--qdrant', 'http://127.0.0.1:6343');
const COLLECTION = argOf('--collection', 'newplay_code');
const MODEL = 'text-embedding-3-small';
const TOP = Number(argOf('--top', '6'));
const JSON_OUT = args.includes('--json');

function apiKey() {
  if (process.env.OPENAI_API_KEY) return process.env.OPENAI_API_KEY;
  for (const p of [
    path.join(process.env.HOME || '', 'projecthub-newteam/.env.production'),
    path.resolve(__dirname, '../../.env'),
  ]) {
    try {
      if (p && fs.existsSync(p)) {
        const m = fs.readFileSync(p, 'utf8').match(/^OPENAI_API_KEY=(.*)$/m);
        if (m) return m[1].trim().replace(/^["']|["']$/g, '');
      }
    } catch { /* 다음 후보 */ }
  }
  throw new Error('OPENAI_API_KEY 를 찾지 못했습니다');
}

async function main() {
  if (!QUERY) { console.error('사용법: node search.js "<질문>" [--kind api] [--area backend] [--top N] [--json]'); process.exit(1); }

  const r = await fetch('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey()}` },
    body: JSON.stringify({ model: MODEL, input: QUERY }),
  });
  if (!r.ok) throw new Error(`embeddings ${r.status}: ${(await r.text()).slice(0, 200)}`);
  const vector = (await r.json()).data[0].embedding;

  const must = [];
  for (const f of ['kind', 'area', 'lang', 'project']) {
    const v = argOf('--' + f, null);
    if (v) must.push({ key: f, match: { value: v } });
  }

  const res = await fetch(`${QDRANT}/collections/${COLLECTION}/points/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      vector, limit: TOP, with_payload: true,
      filter: must.length ? { must } : undefined,
    }),
  });
  if (!res.ok) throw new Error(`qdrant search ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const hits = (await res.json()).result || [];

  if (JSON_OUT) {
    console.log(JSON.stringify(hits.map((h) => ({
      score: h.score, path: h.payload.path, kind: h.payload.kind, area: h.payload.area,
      lines: [h.payload.startLine, h.payload.endLine], symbols: h.payload.symbols,
      text: h.payload.text,
    })), null, 2));
    return;
  }

  console.log(`질문: ${QUERY}${must.length ? '  [필터 ' + must.map((m) => m.key + '=' + m.match.value).join(', ') + ']' : ''}\n`);
  hits.forEach((h, i) => {
    const p = h.payload;
    console.log(`${i + 1}. ${h.score.toFixed(3)}  ${p.path}:${p.startLine}-${p.endLine}  (${p.kind}/${p.area})`);
    if (p.symbols && p.symbols.length) console.log(`   symbols: ${p.symbols.join(', ')}`);
    const body = String(p.text).split('\n').slice(2).filter((l) => l.trim()).slice(0, 4);
    body.forEach((l) => console.log(`   │ ${l.slice(0, 110)}`));
    console.log('');
  });
  if (!hits.length) console.log('(결과 없음)');
}

main().catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
