#!/usr/bin/env node
/**
 * split-task-images.js — pixelforge_tasks 의 image_base64 를 별도 컬렉션으로 분리한다.
 *
 * 왜 (실측, 2026-08-03):
 *   pixelforge_tasks 796건 중 158건이 이미지를 품고 있어 컬렉션이 106.3MB (평균 136.8KB).
 *   목록 API 는 이미 image_base64 를 projection 으로 빼고 있었지만, projection 은
 *   "서버가 읽는 양"을 줄이지 못한다. 파이프라인 순서를 바꿔 측정해도
 *     스코프없음 89.6s → 86.8s / balloonflow 86.7s → 89.7s  (차이 없음)
 *   반면 이미지가 없는 nextpr(102건 0.07MB)은 0.92s. 병목은 문서 자체의 크기다.
 *   따라서 물리적으로 떼어내는 것 외에 방법이 없다.
 *
 * 어떻게:
 *   $merge 로 **서버 안에서** 복사한다. 클라이언트로 95MB 를 왕복시키면
 *   Atlas 대역폭 기준 0.4MB findOne 하나가 4.5초라 몇십 분이 걸린다.
 *   복사 → 서버 측 대조($lookup 으로 길이 비교) → 원본 $unset 순서.
 *   대조에서 한 건이라도 불일치면 unset 하지 않는다.
 *
 * Usage:
 *   node scripts/split-task-images.js --dry
 *   node scripts/split-task-images.js
 *   node scripts/split-task-images.js --rollback   # 되돌리기 (side → task)
 */
'use strict';

const fs = require('fs');
const path = require('path');

const SIDE = 'pixelforge_task_images';
const MAIN = 'pixelforge_tasks';
const HAS_IMAGE = { image_base64: { $nin: [null, ''] } };

function loadEnv() {
  const envUri = process.env.MONGO_URI || process.env.MONGODB_URI;
  if (envUri) return { uri: envUri, db: process.env.MONGO_DB_NAME || process.env.MONGODB_DB || 'aigame' };
  const candidates = [
    path.resolve(__dirname, '../.env'),
    path.join(process.env.HOME || '', '.hermes/watcher/.env'),
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
    } catch { /* 다음 후보 */ }
  }
  throw new Error('MONGO_URI 를 찾지 못했습니다');
}

const args = process.argv.slice(2);
const DRY = args.includes('--dry');
const ROLLBACK = args.includes('--rollback');

async function main() {
  const { uri, db: dbName } = loadEnv();
  const { MongoClient } = require('mongodb');
  const client = new MongoClient(uri, { serverSelectionTimeoutMS: 30000, socketTimeoutMS: 600000 });
  await client.connect();
  const db = client.db(dbName);
  const main_ = db.collection(MAIN);
  const side = db.collection(SIDE);

  if (ROLLBACK) {
    const n = await side.countDocuments({});
    console.log(`되돌리기 대상 ${n}건`);
    if (!DRY) {
      await side.aggregate([
        { $project: { _id: 1, image_base64: 1 } },
        { $merge: { into: MAIN, on: '_id', whenMatched: 'merge', whenNotMatched: 'discard' } },
      ]).toArray();
      console.log(`복원 완료 (${SIDE} 컬렉션은 지우지 않음 — 확인 후 수동 drop)`);
    }
    await client.close();
    return;
  }

  const before = await main_.countDocuments(HAS_IMAGE);
  const stBefore = await db.command({ collStats: MAIN });
  console.log(`분리 대상 ${before}건 · 현재 컬렉션 ${(stBefore.size / 1048576).toFixed(1)}MB (평균 ${(stBefore.avgObjSize / 1024).toFixed(1)}KB)`);
  if (DRY) { console.log('[예행] 아무것도 쓰지 않았습니다.'); await client.close(); return; }

  // 1) 서버 내부 복사
  console.log('복사 중 ($merge — 서버 안에서 처리)...');
  let t = Date.now();
  await main_.aggregate([
    { $match: HAS_IMAGE },
    { $project: { _id: 1, image_base64: 1, migrated_at: new Date().toISOString() } },
    { $merge: { into: SIDE, on: '_id', whenMatched: 'replace', whenNotMatched: 'insert' } },
  ], { allowDiskUse: true }).toArray();
  console.log(`  복사 완료 ${((Date.now() - t) / 1000).toFixed(1)}s · side ${await side.countDocuments({})}건`);

  // 2) 서버 측 대조 — 바이트 길이가 원본과 다른 건이 하나라도 있으면 중단
  console.log('대조 중 (길이 비교, 서버 안에서 처리)...');
  t = Date.now();
  const bad = await main_.aggregate([
    { $match: HAS_IMAGE },
    { $lookup: { from: SIDE, localField: '_id', foreignField: '_id', as: 'side' } },
    {
      $project: {
        srcLen: { $strLenBytes: '$image_base64' },
        dstLen: { $strLenBytes: { $ifNull: [{ $first: '$side.image_base64' }, ''] } },
      },
    },
    { $match: { $expr: { $ne: ['$srcLen', '$dstLen'] } } },
    { $limit: 20 },
  ], { allowDiskUse: true }).toArray();
  console.log(`  대조 완료 ${((Date.now() - t) / 1000).toFixed(1)}s · 불일치 ${bad.length}건`);
  if (bad.length) {
    console.error('불일치가 있어 원본을 지우지 않고 중단합니다:');
    bad.forEach((b) => console.error(`  ${b._id} src=${b.srcLen} dst=${b.dstLen}`));
    await client.close();
    process.exit(1);
  }

  // 3) 원본 제거 + 플래그 확정
  const r = await main_.updateMany(HAS_IMAGE, { $unset: { image_base64: '' }, $set: { has_image: true } });
  console.log(`원본 제거 ${r.modifiedCount}건`);

  const after = await main_.countDocuments(HAS_IMAGE);
  const sideN = await side.countDocuments({});
  const flagged = await main_.countDocuments({ has_image: true });
  const stAfter = await db.command({ collStats: MAIN });
  console.log(`검증 — 본 컬렉션 잔여 ${after}건 / side ${sideN}건 / has_image=true ${flagged}건`);
  console.log(`본 컬렉션 크기 ${(stBefore.size / 1048576).toFixed(1)}MB → ${(stAfter.size / 1048576).toFixed(1)}MB (평균 ${(stAfter.avgObjSize / 1024).toFixed(1)}KB)`);

  await client.close();
}

main().catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
