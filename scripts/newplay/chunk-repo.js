#!/usr/bin/env node
/**
 * chunk-repo.js — 레포를 임베딩용 청크 JSONL 로 만든다. (NewPlay 전용)
 *
 * 왜 워크스테이션에서 도는가:
 *   blocore 레포는 `jisupark-tech` 자격이 있는 워크스테이션·머신 B 에서만 열린다.
 *   Mother/aimed-sub/newplay 는 아직 GitHub 접근이 없다(newplay 의 deploy_webstore 는 미등록).
 *   그래서 추출은 여기서 하고, 임베딩·적재만 aimed-sub 로 넘긴다.
 *
 * 청킹 규칙:
 *   - 코드는 최상위 선언(export/function/class/interface/describe...) 경계를 우선 끊고,
 *     그래도 크면 줄 단위로 겹침을 두고 자른다. 경계를 무시하면 검색 결과가
 *     "함수 중간부터 시작하는 조각"이 되어 사람이 못 읽는다.
 *   - 문서(md/yaml)는 헤딩 경계를 우선한다.
 *
 * Usage:
 *   node scripts/newplay/chunk-repo.js --repo <path> --project webstore --out chunks.jsonl
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const args = process.argv.slice(2);
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const REPO = argOf('--repo', '.');
const PROJECT = argOf('--project', 'webstore');
const OUT = argOf('--out', 'chunks.jsonl');

const MAX_CHARS = 1500;   // 약 400토큰 — 검색 단위로 너무 크지도 잘게 쪼개지도 않는 지점
const OVERLAP_LINES = 6;  // 경계에서 문맥이 끊기지 않게

const KEEP = /\.(ts|tsx|js|jsx|scss|css|md|yaml|yml|json|hbs|html|sql)$/i;
const SKIP = /(^|\/)(node_modules|dist|build|\.yarn|coverage|public\/)|yarn\.lock|package-lock|\.min\./i;
const MAX_FILE = 400 * 1024;

/** 최상위 선언처럼 보이는 줄 — 여기서 끊으면 사람이 읽을 수 있는 조각이 된다. */
const BOUNDARY = /^(\s{0,2})(export\s|async\s+function\s|function\s|class\s|interface\s|type\s|enum\s|const\s+[A-Za-z_$][\w$]*\s*[:=]\s*(async\s*)?\(|describe\(|it\(|test\(|@[A-Z]\w+\()/;
const MD_BOUNDARY = /^#{1,4}\s/;

function langOf(f) {
  const e = f.split('.').pop().toLowerCase();
  return ({ ts: 'typescript', tsx: 'tsx', js: 'javascript', jsx: 'jsx', scss: 'scss', css: 'css',
    md: 'markdown', yaml: 'yaml', yml: 'yaml', json: 'json', hbs: 'handlebars', html: 'html', sql: 'sql' })[e] || e;
}

/** 이 파일이 무슨 역할인지 — 검색 결과에 붙여 사람이 바로 알아보게 한다. */
function kindOf(f) {
  if (/\.(test|spec)\.[jt]sx?$/i.test(f)) return 'test';
  if (/\/migrations?\//i.test(f)) return 'migration';
  if (/\/entities?\//i.test(f) || /\.entity\.ts$/i.test(f)) return 'entity';
  if (/\/(controllers?|routes?)\//i.test(f) || /\.(controller|router)\.ts$/i.test(f)) return 'api';
  if (/\/services?\//i.test(f) || /\.service\.ts$/i.test(f)) return 'service';
  if (/\/helm\//i.test(f) || /\.ya?ml$/i.test(f)) return 'infra';
  if (/\.(scss|css)$/i.test(f)) return 'style';
  if (/\.md$/i.test(f)) return 'doc';
  if (/\.tsx$/i.test(f)) return 'component';
  return 'code';
}

/** 청크 안에서 export 되는 이름들 — 키워드 검색 보조용 */
function symbolsOf(text) {
  const out = new Set();
  const re = /export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|interface|type|enum)\s+([A-Za-z_$][\w$]*)/g;
  let m;
  while ((m = re.exec(text))) out.add(m[1]);
  return [...out].slice(0, 12);
}

function chunkLines(lines, isDoc) {
  const boundary = isDoc ? MD_BOUNDARY : BOUNDARY;
  const chunks = [];
  let start = 0, buf = [], size = 0;

  const flush = (end) => {
    if (!buf.length) return;
    const text = buf.join('\n');
    if (text.trim()) chunks.push({ start: start + 1, end, text });
    buf = []; size = 0;
  };

  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    const atBoundary = boundary.test(ln);
    // 이미 충분히 찼고 경계에 닿았으면 여기서 끊는다
    if (size >= MAX_CHARS * 0.6 && atBoundary && buf.length) {
      flush(i);
      start = Math.max(0, i - OVERLAP_LINES);
      for (let k = start; k < i; k++) { buf.push(lines[k]); size += lines[k].length + 1; }
      start = i - buf.length;
    } else if (size >= MAX_CHARS) {
      // 경계를 못 만났는데 너무 커짐 — 그냥 끊되 겹침을 준다
      flush(i);
      start = Math.max(0, i - OVERLAP_LINES);
      for (let k = start; k < i; k++) { buf.push(lines[k]); size += lines[k].length + 1; }
      start = i - buf.length;
    }
    buf.push(ln); size += ln.length + 1;
  }
  flush(lines.length);
  return chunks;
}

function main() {
  const repo = path.resolve(REPO);
  const files = execSync('git ls-files', { cwd: repo, maxBuffer: 1e8 }).toString().trim().split('\n');
  const sha = execSync('git rev-parse HEAD', { cwd: repo }).toString().trim();
  const out = fs.createWriteStream(OUT, { encoding: 'utf8' });

  let nFiles = 0, nChunks = 0, chars = 0;
  for (const rel of files) {
    if (!KEEP.test(rel) || SKIP.test(rel)) continue;
    const abs = path.join(repo, rel);
    let st;
    try { st = fs.statSync(abs); } catch { continue; }
    if (!st.isFile() || st.size > MAX_FILE) continue;

    const text = fs.readFileSync(abs, 'utf8');
    if (!text.trim()) continue;
    const isDoc = /\.(md|ya?ml)$/i.test(rel);
    const area = rel.split('/')[0];
    const kind = kindOf(rel);
    const lang = langOf(rel);

    for (const c of chunkLines(text.split('\n'), isDoc)) {
      const id = `${PROJECT}:${rel}:${c.start}`;
      out.write(JSON.stringify({
        id,
        project: PROJECT,
        area,          // backend | front-end | .github ...
        path: rel,
        kind,          // api | service | entity | component | test | infra | doc | style | code
        lang,
        startLine: c.start,
        endLine: c.end,
        symbols: symbolsOf(c.text),
        sha,
        // 임베딩 입력에는 경로·역할을 앞에 붙인다 — 본문만 넣으면
        // "어느 파일 얘긴지"가 벡터에 안 실려 검색 품질이 떨어진다.
        text: `[${PROJECT}/${area}] ${rel} (${kind}, ${lang}) L${c.start}-${c.end}\n\n${c.text}`,
      }) + '\n');
      nChunks++; chars += c.text.length;
    }
    nFiles++;
  }
  out.end();
  console.log(`레포: ${repo} @ ${sha.slice(0, 7)}`);
  console.log(`파일 ${nFiles} → 청크 ${nChunks} · 본문 ${(chars / 1048576).toFixed(2)}MB → ${OUT}`);
  console.log(`예상 토큰 약 ${Math.round(chars / 3.5 / 1000)}k (text-embedding-3-small 기준 약 $${(chars / 3.5 / 1e6 * 0.02).toFixed(3)})`);
}

main();
