#!/usr/bin/env node
/**
 * build-platform-map.js — webstore 구성도를 만들어 newteam DB 에 저장한다.
 *
 * 왜 스냅샷인가:
 *   구성도의 원천은 qdrant 의 7,176 청크 payload 다. 화면을 열 때마다 전부 훑으면
 *   느리고(스크롤 수십 회) 의미도 없다 — 레포는 커밋이 있을 때만 바뀐다.
 *   한 번 집계해 `newplay_platform_map` 에 넣고, 화면은 그걸 읽는다.
 *
 * 무엇을 집계하나:
 *   area(backend/front-end) → 모듈(경로 2~3단계) → 파일 → 심볼
 *   + kind(api/service/entity/component/test/infra/doc/style) 분포
 *   + API 컨트롤러·엔티티·프런트 라우트 같은 "기능 목록"으로 읽히는 축
 *
 * Usage:
 *   node build-platform-map.js            # 갱신
 *   node build-platform-map.js --dry      # 집계만 출력
 */
'use strict';

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const DRY = args.includes('--dry');
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const QDRANT = argOf('--qdrant', 'http://127.0.0.1:6343');
const COLLECTION = argOf('--collection', 'newplay_code');
const MONGO = argOf('--mongo', 'mongodb://127.0.0.1:27018/?directConnection=true');
const DB = argOf('--db', 'newteam');
const PROJECT = argOf('--project', 'webstore');

/** 경로에서 "모듈" 을 뽑는다. backend 는 modules/<도메인>, front-end 는 src/<영역> 이 의미 단위다. */
function moduleOf(p) {
  const seg = p.split('/');
  const i = seg.indexOf('modules');
  if (i >= 0 && seg[i + 1]) return seg[i + 1];
  const j = seg.indexOf('src');
  if (j >= 0 && seg[j + 1]) return seg[j + 1] === 'pages' || seg[j + 1] === 'components' || seg[j + 1] === 'routes'
    ? `${seg[j + 1]}/${seg[j + 2] || ''}`.replace(/\/$/, '')
    : seg[j + 1];
  return seg[1] || seg[0] || '(root)';
}

async function scrollAll() {
  const points = [];
  let offset = null;
  for (let guard = 0; guard < 200; guard++) {
    const body = {
      limit: 512,
      with_payload: ['path', 'area', 'kind', 'lang', 'symbols', 'startLine', 'endLine', 'sha'],
      with_vector: false,
    };
    if (offset) body.offset = offset;
    const r = await fetch(`${QDRANT}/collections/${COLLECTION}/points/scroll`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`qdrant scroll ${r.status}: ${(await r.text()).slice(0, 200)}`);
    const j = (await r.json()).result;
    points.push(...(j.points || []));
    offset = j.next_page_offset;
    if (!offset) break;
  }
  return points;
}

function build(points) {
  const files = new Map();   // path -> {area, kind, lang, symbols:Set, chunks, minLine, maxLine, sha}
  for (const p of points) {
    const pl = p.payload || {};
    if (!pl.path) continue;
    let f = files.get(pl.path);
    if (!f) {
      f = { path: pl.path, area: pl.area || '(기타)', kind: pl.kind || 'code', lang: pl.lang || '',
            symbols: new Set(), chunks: 0, lines: 0, sha: pl.sha || '' };
      files.set(pl.path, f);
    }
    f.chunks++;
    if (pl.endLine) f.lines = Math.max(f.lines, pl.endLine);
    for (const s of pl.symbols || []) f.symbols.add(s);
  }

  const areas = new Map();
  for (const f of files.values()) {
    if (!areas.has(f.area)) areas.set(f.area, new Map());
    const mods = areas.get(f.area);
    const m = moduleOf(f.path);
    if (!mods.has(m)) mods.set(m, []);
    mods.get(m).push(f);
  }

  const kindCount = {};
  for (const f of files.values()) kindCount[f.kind] = (kindCount[f.kind] || 0) + 1;

  const tree = [...areas.entries()].map(([area, mods]) => ({
    area,
    files: [...mods.values()].reduce((a, v) => a + v.length, 0),
    lines: [...mods.values()].flat().reduce((a, f) => a + f.lines, 0),
    modules: [...mods.entries()]
      .map(([name, fl]) => ({
        name,
        files: fl.length,
        lines: fl.reduce((a, f) => a + f.lines, 0),
        kinds: fl.reduce((a, f) => (a[f.kind] = (a[f.kind] || 0) + 1, a), {}),
        items: fl
          .sort((a, b) => b.lines - a.lines)
          .map((f) => ({
            path: f.path, kind: f.kind, lang: f.lang, lines: f.lines,
            symbols: [...f.symbols].slice(0, 10),
          })),
      }))
      .sort((a, b) => b.lines - a.lines),
  })).sort((a, b) => b.files - a.files);

  // "기능 목록" 축 — 화면에서 바로 읽히는 것들
  const all = [...files.values()];
  const apis = all.filter((f) => f.kind === 'api')
    .map((f) => ({ path: f.path, module: moduleOf(f.path), handlers: [...f.symbols].slice(0, 12) }))
    .sort((a, b) => a.module.localeCompare(b.module));
  const entities = all.filter((f) => f.kind === 'entity')
    .map((f) => ({ path: f.path, name: (f.path.split('/').pop() || '').replace(/\.ts$/, '') }))
    .sort((a, b) => a.name.localeCompare(b.name));

  return {
    project: PROJECT,
    screens: [],   // 아래 extractScreens 가 채운다
    sha: all[0]?.sha || '',
    generatedAt: new Date().toISOString(),
    totals: {
      files: all.length,
      chunks: points.length,
      lines: all.reduce((a, f) => a + f.lines, 0),
      areas: tree.length,
      modules: tree.reduce((a, t) => a + t.modules.length, 0),
    },
    kindCount,
    tree,
    apis,
    entities,
  };
}

/**
 * 앱 화면 목록 — React Router 정의에서 뽑는다.
 *
 * 레포 체크아웃 없이 지식베이스에 적재된 원문에서 추출한다.
 * (aimed-sub 에는 레포가 없고, 재임베딩하면 화면 목록도 같이 최신화되는 게 맞다)
 */
async function fetchRouterChunks(points) {
  // 전체 스크롤은 text 를 안 받아온다(약 9MB). 라우터 파일 청크만 원문을 따로 가져온다.
  const p = points.find((x) => /containers\/Router\.tsx$/i.test(String(x.payload?.path || '')));
  if (!p) return [];
  const r = await fetch(`${QDRANT}/collections/${COLLECTION}/points/scroll`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      limit: 128,
      filter: { must: [{ key: 'path', match: { value: p.payload.path } }] },
      with_payload: ['path', 'text', 'startLine'],
      with_vector: false,
    }),
  });
  if (!r.ok) return [];
  return ((await r.json()).result.points || []);
}

function extractScreens(chunks) {
  if (!chunks.length) return [];
  chunks = [...chunks].sort((a, b) => (a.payload.startLine || 0) - (b.payload.startLine || 0));

  // 청크는 겹침이 있어 중복 라우트가 생긴다 — path 로 유일화한다.
  const text = chunks.map((c) => String(c.payload.text || '')).join('\n');
  const seen = new Map();
  // `<Route ... />` 는 여러 줄로 쓰이고 element={<Comp />} 안에 '>' 가 들어간다.
  // 그래서 한 정규식으로 통째로 잡으려 하면 컴포넌트명을 놓친다(실측: 47개 전부 빈 값).
  // path 를 먼저 찾고, 그 뒤 240자 안에서 element 를 따로 본다.
  const re = /path=["'`]([^"'`]+)["'`]/g;
  let m;
  while ((m = re.exec(text))) {
    const p = m[1];
    // '*' 는 catch-all(404) 이라 화면이 아니다.
    if (!p || p === '*' || seen.has(p)) continue;
    const near = text.slice(m.index, m.index + 240);
    const el = near.match(/element=\{\s*<\s*([A-Za-z0-9_]+)/);
    const section = p.startsWith('/admin') ? 'admin'
      : p.startsWith('/dashboard') ? 'dashboard'
      : p.startsWith('/auth') ? 'auth'
      : 'store';
    seen.set(p, {
      path: p,
      component: el ? el[1] : '',
      section,
      // :gameSlug 같은 동적 구간이 있으면 그대로는 열 수 없다 — 화면에서 알려주기 위해 표시.
      params: (p.match(/:[A-Za-z0-9_]+/g) || []),
    });
  }
  const order = { store: 0, auth: 1, dashboard: 2, admin: 3 };
  return [...seen.values()].sort(
    (a, b) => (order[a.section] - order[b.section]) || a.path.localeCompare(b.path),
  );
}

async function main() {
  console.log(`qdrant ${QDRANT}/${COLLECTION} 에서 청크 수집 중...`);
  const points = await scrollAll();
  console.log(`  청크 ${points.length}개`);
  const map = build(points);
  map.screens = extractScreens(await fetchRouterChunks(points));
  map.liveBaseUrl = argOf('--live-url', 'https://newplay.store');
  const bySec = map.screens.reduce((a, s) => (a[s.section] = (a[s.section] || 0) + 1, a), {});
  console.log(`앱 화면 ${map.screens.length}개 —`, Object.entries(bySec).map(([k, v]) => `${k}:${v}`).join(' '));
  console.log(`파일 ${map.totals.files} · 모듈 ${map.totals.modules} · 영역 ${map.totals.areas} · 총 ${map.totals.lines}줄`);
  console.log('종류별:', Object.entries(map.kindCount).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k}:${v}`).join(' '));
  console.log(`API 파일 ${map.apis.length} · 엔티티 ${map.entities.length}`);
  for (const t of map.tree) {
    console.log(`  [${t.area}] 파일 ${t.files} · 모듈 ${t.modules.length} — 상위: ${t.modules.slice(0, 6).map((m) => m.name).join(', ')}`);
  }

  if (DRY) { console.log('\n[예행] 저장하지 않았습니다.'); return; }

  const { MongoClient } = require('mongodb');
  const cli = new MongoClient(MONGO, { serverSelectionTimeoutMS: 10000 });
  await cli.connect();
  await cli.db(DB).collection('newplay_platform_map').updateOne(
    { project: PROJECT }, { $set: map }, { upsert: true },
  );
  await cli.close();
  console.log(`\n저장 완료 → ${DB}.newplay_platform_map (project=${PROJECT})`);
}

main().catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
