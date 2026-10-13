// CrewFlow 플레이어블 자산을 public/playable/ 로 가져온다.
//
//   node scripts/sync-playable.mjs
//
// ── 왜 복사하는가 ───────────────────────────────────────────────────────────
// ProjectHub 는 Vercel 에 올라간다. 배포 서버에는 유니티도 없고 E:\ 드라이브도 없다.
// 그래서 <b>미리 빌드해 둔 결과</b>와 <b>레벨 JSON</b>을 레포 안에 넣어 정적 자산으로 서빙한다.
//
// ── 왜 레벨마다 빌드하지 않는가 ─────────────────────────────────────────────
// 유니티 빌드는 레벨과 무관하다. 레벨은 JSON 한 장(최대 18KB)이라, 빌드 1벌 + 레벨 300장이면
// 300종을 즉시 띄울 수 있다. 레벨마다 빌드하면 한 편에 수 분이 들고 서버에 유니티가 있어야 한다.
//
// ── 미리보기와 제출본은 index.html 이 다르다 ────────────────────────────────
// 여기 넣는 것은 <b>미리보기 판</b>이다(?level=NNN 으로 레벨을 fetch).
// 제출용 zip 은 레벨을 파일에 <b>박아</b> 만든다 — 광고망은 런타임 네트워크 요청을 금지한다.
// 그 조립은 브라우저에서 한다(Vercel 서버리스 응답 상한 4.5MB < 번들 4.65MB).

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');

const PLAYABLE_DIST = process.env.CREW_PLAYABLE_DIST
  || 'D:\\Playable\\repo\\CrewFlowPlayable\\dist\\preview';
const LEVELS_SRC = process.env.NEXTPR_LEVELS
  || 'E:\\NextPR\\NextPR\\Assets\\Resources\\Levels';

const OUT = path.join(ROOT, 'public', 'playable');

function die(msg) {
  console.error(`\n[sync-playable] ✗ ${msg}\n`);
  process.exit(1);
}

function copyDir(from, to) {
  fs.mkdirSync(to, { recursive: true });
  let n = 0, bytes = 0;
  for (const e of fs.readdirSync(from, { withFileTypes: true })) {
    const src = path.join(from, e.name);
    const dst = path.join(to, e.name);
    if (e.isDirectory()) {
      const r = copyDir(src, dst);
      n += r.n; bytes += r.bytes;
    } else {
      fs.copyFileSync(src, dst);
      n++; bytes += fs.statSync(src).size;
    }
  }
  return { n, bytes };
}

const mb = (b) => (b / 1048576).toFixed(2) + ' MB';

// ── 빌드 산출물 ─────────────────────────────────────────────────────────────
if (!fs.existsSync(path.join(PLAYABLE_DIST, 'index.html'))) {
  die(`미리보기 판이 없다: ${PLAYABLE_DIST}\n` +
      `플레이어블 레포에서 먼저 만들 것:  node Tools/pack.js --preview`);
}

fs.rmSync(OUT, { recursive: true, force: true });
const build = copyDir(PLAYABLE_DIST, OUT);
console.log(`[sync-playable] 빌드  ${build.n}개  ${mb(build.bytes)}  ← ${PLAYABLE_DIST}`);

// ── 레벨 ────────────────────────────────────────────────────────────────────
if (!fs.existsSync(LEVELS_SRC)) die(`레벨 폴더가 없다: ${LEVELS_SRC}`);

const levelsOut = path.join(OUT, 'levels');
fs.mkdirSync(levelsOut, { recursive: true });

const index = [];
let levelBytes = 0;

for (const name of fs.readdirSync(LEVELS_SRC).sort()) {
  const m = /^Lv(\d{3})\.json$/.exec(name);
  if (!m) continue;

  const raw = fs.readFileSync(path.join(LEVELS_SRC, name), 'utf8');
  let j;
  try { j = JSON.parse(raw); } catch { console.warn(`  ⚠ 파싱 실패, 건너뜀: ${name}`); continue; }

  fs.writeFileSync(path.join(levelsOut, name), raw);
  levelBytes += raw.length;

  // 목록 화면이 필터·정렬에 쓰는 메타. 300개를 매번 파싱하지 않도록 한 파일로 굽는다.
  const cubes = (j.cx || []).length;
  index.push({
    id: j.levelId ?? parseInt(m[1], 10),
    cubes,
    cols: j.cols,
    rows: j.rows,
    colors: new Set(j.cc || []).size,
    holders: (j.hc || []).length,
    queueColumns: j.queueColumns ?? 2,
    bytes: raw.length,
  });
}

if (index.length === 0) die('레벨을 하나도 못 읽었다.');

index.sort((a, b) => a.id - b.id);
fs.writeFileSync(path.join(OUT, 'levels.json'), JSON.stringify({
  generatedAt: new Date().toISOString(),
  count: index.length,
  levels: index,
}, null, 0));

console.log(`[sync-playable] 레벨  ${index.length}개  ${mb(levelBytes)}  ← ${LEVELS_SRC}`);
console.log(`[sync-playable] 큐브  최소 ${Math.min(...index.map(l => l.cubes))}` +
            ` / 최대 ${Math.max(...index.map(l => l.cubes))}`);
console.log(`[sync-playable] ✓ ${path.relative(ROOT, OUT)}  총 ${mb(build.bytes + levelBytes)}`);
