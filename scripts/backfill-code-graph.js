#!/usr/bin/env node
/**
 * backfill-code-graph.js — 관계 필드가 비어 있는 code_base 문서를 복구한다.
 *
 * 왜 필요한가 (실측 진단, 2026-08-03):
 *   code_base 는 두 경로로 채워진다.
 *     ① scripts/parser.js         — uses/usedBy/integration/provides/requires 를 모두 추출
 *     ② delta_embed / graph_refresh — 임베딩과 메타만 upsert
 *   ②로 처음 들어온 파일은 파서를 한 번도 거치지 않아 관계 필드가 영구히 비어 있다.
 *   (BalloonFlow 181건 중 24건이 integration·provides·filePath 전부 없음)
 *
 *   흔한 오해: "$set 이 기존 필드를 지운다" — 아니다. $set 은 나열한 필드만 바꾼다.
 *   실제로 델타 태그(embedded_from_sha)를 가진 143건은 uses 를 그대로 갖고 있다.
 *   문제는 덮어쓰기가 아니라 **신규 문서가 파싱 단계를 건너뛰는 것**이다.
 *
 * 무엇을 하나:
 *   원문(text/content)이 저장돼 있으므로 소스 레포 없이 그 자리에서 재추출한다.
 *   비어 있는 필드만 채우고, 이미 값이 있는 필드는 건드리지 않는다.
 *
 * Usage:
 *   node scripts/backfill-code-graph.js --dry                 # 대상만 출력
 *   node scripts/backfill-code-graph.js --project BalloonFlow # 실제 반영
 *   node scripts/backfill-code-graph.js --all                 # 전 프로젝트
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { CSharpParser } = require('./parser.js');

/**
 * 접속 정보 — 환경변수 우선, 없으면 .env 파일을 찾는다.
 * Mother(워처 서버)에서도 돌아야 하므로 E:\AI 경로에 묶지 않는다.
 */
function loadEnv() {
  // 1) 환경변수 (서버 cron 에서 이 방식으로 넘긴다)
  const envUri = process.env.MONGO_URI || process.env.MONGODB_URI;
  if (envUri) {
    return { uri: envUri, db: process.env.MONGO_DB_NAME || process.env.MONGODB_DB || 'aigame' };
  }
  // 2) .env 후보 경로 순회
  const candidates = [
    path.resolve(__dirname, '../.env'),          // E:\AI\.env
    path.resolve(__dirname, '.env'),             // 스크립트와 같은 폴더
    path.join(process.env.HOME || '', '.hermes/.env'),
    path.join(process.env.HOME || '', 'projecthub-web/.env.production'),
  ];
  for (const p of candidates) {
    try {
      if (!p || !fs.existsSync(p)) continue;
      const txt = fs.readFileSync(p, 'utf8');
      const get = (k) => {
        const m = txt.match(new RegExp('^' + k + '=(.*)$', 'm'));
        return m ? m[1].trim().replace(/^["']|["']$/g, '') : null;
      };
      const uri = get('MONGO_URI') || get('MONGODB_URI');
      if (uri) return { uri, db: get('MONGO_DB_NAME') || get('MONGODB_DB') || 'aigame' };
    } catch { /* 다음 후보로 */ }
  }
  throw new Error('MONGO_URI 를 찾지 못했습니다 (환경변수 또는 .env)');
}

const args = process.argv.slice(2);
const DRY = args.includes('--dry');
const ALL = args.includes('--all');
const projIdx = args.indexOf('--project');
const PROJECT = projIdx >= 0 ? args[projIdx + 1] : (ALL ? null : 'BalloonFlow');

/** 관계 필드가 실질적으로 비어 있는가 */
function needsBackfill(d) {
  const empty = (v) => v == null || (Array.isArray(v) && v.length === 0);
  const noIntegration = !d.integration || Object.values(d.integration).every(empty);
  return empty(d.uses) && empty(d.provides) && noIntegration;
}

async function main() {
  const { uri, db: dbName } = loadEnv();
  const { MongoClient } = require('mongodb');
  const client = new MongoClient(uri, { serverSelectionTimeoutMS: 30000 });
  await client.connect();
  const col = client.db(dbName).collection('code_base');

  const q = PROJECT ? { project: PROJECT } : {};
  const docs = await col.find(q).project({ embedding: 0 }).toArray();
  const targets = docs.filter(needsBackfill);

  console.log(`대상 프로젝트: ${PROJECT || '(전체)'}`);
  console.log(`전체 ${docs.length}건 중 관계 필드 비어 있음: ${targets.length}건`);

  const parser = new CSharpParser();
  let filled = 0, noText = 0, failed = 0;
  const report = [];

  for (const d of targets) {
    const text = d.text || d.content || '';
    if (!text || text.length < 20) { noText++; report.push({ id: d.fileId, result: '원문 없음' }); continue; }

    let patch = {};
    try {
      const fileId = d.fileId || d.className || 'Unknown';
      const integration = parser.extractIntegration(text, fileId);
      // uses — integration 에서 실제 참조 대상만 모은다 (파서의 uses 추출과 같은 소스)
      const uses = new Set();
      for (const sa of integration.singleton_access || []) if (sa && sa.target) uses.add(sa.target);
      for (const ic of integration.instantiate_calls || []) {
        const t = typeof ic === 'string' ? ic : ic && (ic.type || ic.target);
        if (t) uses.add(t);
      }
      const hasAny = Object.values(integration).some((v) => Array.isArray(v) && v.length);
      if (!hasAny && uses.size === 0) { report.push({ id: d.fileId, result: '추출 결과 없음' }); continue; }

      patch.integration = integration;
      if (uses.size) patch.uses = [...uses];
      patch.backfilled_at = new Date().toISOString();
      patch.backfill_source = 'stored_text';
    } catch (e) {
      failed++; report.push({ id: d.fileId, result: '실패: ' + e.message });
      continue;
    }

    const summary = [
      patch.uses ? `uses ${patch.uses.length}` : null,
      (patch.integration.singleton_access || []).length ? `calls ${patch.integration.singleton_access.length}` : null,
      (patch.integration.event_subscribe || []).length ? `sub ${patch.integration.event_subscribe.length}` : null,
      (patch.integration.event_publish || []).length ? `pub ${patch.integration.event_publish.length}` : null,
    ].filter(Boolean).join(' / ') || '빈 integration';

    report.push({ id: d.fileId, result: summary });
    if (!DRY) {
      await col.updateOne({ _id: d._id }, { $set: patch });
    }
    filled++;
  }

  console.log('');
  for (const r of report.slice(0, 40)) console.log(`  ${String(r.id).padEnd(30)} ${r.result}`);
  if (report.length > 40) console.log(`  … 외 ${report.length - 40}건`);

  console.log('');
  console.log(`${DRY ? '[예행] ' : ''}복구 ${filled}건 · 원문 없음 ${noText}건 · 실패 ${failed}건`);
  if (DRY) console.log('실제 반영하려면 --dry 를 빼고 다시 실행하세요.');

  await client.close();
}

main().catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
