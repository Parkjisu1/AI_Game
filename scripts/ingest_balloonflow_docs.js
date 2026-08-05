#!/usr/bin/env node
/**
 * Ingest BalloonFlow direction/spec markdown docs into design_base.
 * Source: E:/Balloonflow/BalloonFlow_Doc/Recent/*.md (+ docx skipped here)
 * Target: aigame.design_base (project=BalloonFlow, source=internal_original)
 *
 * The 20 existing entries (source=internal_produced) come from YAML system specs.
 * The new entries are richer human-written direction docs — they complement, not replace.
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { MongoClient } = require('mongodb');

const ENV = fs.readFileSync('E:/AI/.env', 'utf8').split(/\r?\n/).reduce((a, l) => {
  const m = l.match(/^([^=]+)=(.*)$/);
  if (m) a[m[1].trim()] = m[2].trim();
  return a;
}, {});

// Recent first (canonical), then dated folder for docs unique to it. Dedup by normalized basename.
const DOCS_DIRS = [
  'E:/Balloonflow/BalloonFlow_Doc/Recent',
  'E:/Balloonflow/BalloonFlow_Doc/2026-05-28',
];
const PROJECT = 'BalloonFlow';
const GENRE = 'Puzzle';
const NOW = new Date().toISOString();

// Filename -> {domain, system, document_role, tags} heuristic
const DOC_MAP = {
  'BalloonFlow_BeatChart_Direction.md':         { domain: 'Content', system: 'BeatChartDirection',     role: 'direction', tags: ['beatchart', 'level_design', 'pacing'] },
  'BalloonFlow_LiveOps_디렉션.md':              { domain: 'LiveOps', system: 'LiveOpsDirection',       role: 'direction', tags: ['liveops', 'events', 'season'] },
  'BalloonFlow_UX플로우_디렉션.md':             { domain: 'UX',      system: 'UXFlowDirection',        role: 'direction', tags: ['ux', 'flow', 'tutorial'] },
  'BalloonFlow_교차검증_체크리스트.md':         { domain: 'InGame',  system: 'CrossValidationChecklist', role: 'checklist', tags: ['validation', 'qa', 'cross_check'] },
  'BalloonFlow_기믹명세.md':                    { domain: 'Content', system: 'GimmickSpec',            role: 'spec',      tags: ['gimmick', 'puzzle_mechanics'] },
  'BalloonFlow_레일초과_코어메카닉_명세.md':    { domain: 'InGame',  system: 'RailOverflowMechanic',   role: 'spec',      tags: ['core_mechanic', 'rail', 'overflow'] },
  'BalloonFlow_봇시뮬레이션_명세.md':           { domain: 'InGame',  system: 'BotSimulationSpec',      role: 'spec',      tags: ['bot', 'simulation', 'testing'] },
  'BalloonFlow_세션핸드오프.md':                { domain: 'Meta',    system: 'SessionHandoff',         role: 'handoff',   tags: ['handoff', 'session'] },
  'BalloonFlow_아웃게임디렉션.md':              { domain: 'OutGame', system: 'OutGameDirection',       role: 'direction', tags: ['outgame', 'lobby', 'menu'] },
  'BalloonFlow_인게임아이템_UX명세.md':         { domain: 'UX',      system: 'InGameItemUXSpec',       role: 'spec',      tags: ['ux', 'ingame_item', 'booster'] },
  'BalloonFlow_인수인계서.md':                  { domain: 'Meta',    system: 'ProjectHandoffDoc',      role: 'handoff',   tags: ['handoff', 'project_overview'] },
  'BalloonFlow_큐생성기_명세.md':               { domain: 'Content', system: 'QueueGeneratorSpec',     role: 'spec',      tags: ['queue', 'generator', 'level_data'] },
  'BalloonFlow_텍스트관리구조_명세.md':         { domain: 'UX',      system: 'TextManagementSpec',     role: 'spec',      tags: ['text', 'localization', 'ui'] },
  'BalloonFlow_팝업텍스트_인벤토리.md':         { domain: 'UX',      system: 'PopupTextInventory',     role: 'inventory', tags: ['ux', 'popup', 'text'] },
  'BalloonFlow_피드백디렉션.md':                { domain: 'Meta',    system: 'FeedbackDirection',      role: 'direction', tags: ['feedback', 'workflow'] },
  'BalloonFlow_픽셀아트_레벨변환_워크플로우.md':{ domain: 'Content', system: 'PixelArtConversionWorkflow', role: 'workflow', tags: ['pixel_art', 'level_conversion', 'workflow'] },
  // --- 2026-06-02 신규 (5-15 이후 추가 문서) ---
  '02_BalloonFlow_필드완성_명세_v1_2.md':        { domain: 'InGame',  system: 'FieldCompletionSpec',          role: 'spec',      tags: ['field_completion', 'core_mechanic', 'spec'] },
  'BalloonFlow_PF_기믹분석_v1.md':               { domain: 'Content', system: 'PixelFlowGimmickAnalysis',     role: 'analysis',  tags: ['gimmick', 'pixelflow', 'analysis', 'reference'] },
  'BalloonFlow_필드완성_공존매트릭스_데이터기반.md':{ domain: 'InGame', system: 'FieldCompletionCoexistenceMatrix', role: 'spec',  tags: ['field_completion', 'coexistence', 'matrix', 'data_driven'] },
  'BalloonLoop_Profile_명세_v1_0.md':            { domain: 'Meta',    system: 'BalloonLoopProfileSpec',       role: 'spec',      tags: ['balloonloop', 'profile', 'meta'] },
  'BalloonLoop_WinningStreak_명세_v1_0.md':      { domain: 'Meta',    system: 'WinningStreakSpec',            role: 'spec',      tags: ['balloonloop', 'winning_streak', 'reward', 'meta'] },
  'BalloonFlow_QA_테스트가이드.md':              { domain: 'Meta',    system: 'QATestGuide',                 role: 'guide',     tags: ['qa', 'testing', 'guide'] },
  'BalloonFlow_상점_상품노출_구현가이드.md':    { domain: 'OutGame', system: 'ShopProductExposureGuide',     role: 'guide',     tags: ['shop', 'product_exposure', 'outgame', 'implementation'] },
  'BalloonFlow_필드완성_평가기준표.md':         { domain: 'InGame',  system: 'FieldCompletionEvalCriteria',  role: 'criteria',  tags: ['field_completion', 'evaluation', 'criteria'] },
};

function hashId(s) {
  return crypto.createHash('sha1').update(s).digest('hex').slice(0, 12);
}

function sectionsFromMd(text) {
  // Extract H1/H2/H3 headings as a flat outline; cap at 30
  const lines = text.split(/\r?\n/);
  const headings = [];
  for (const l of lines) {
    const m = l.match(/^(#{1,3})\s+(.+?)\s*$/);
    if (m) headings.push({ level: m[1].length, title: m[2].trim() });
    if (headings.length >= 30) break;
  }
  return headings;
}

function summarize(text, maxLen = 600) {
  // Take first 2 paragraphs after stripping front matter / blank lines
  const lines = text.split(/\r?\n/);
  const out = [];
  let para = [];
  for (const l of lines) {
    const t = l.trim();
    if (!t) {
      if (para.length) { out.push(para.join(' ')); para = []; }
      if (out.length >= 2) break;
    } else if (!t.startsWith('#') && !t.startsWith('---')) {
      para.push(t);
    }
  }
  if (para.length && out.length < 2) out.push(para.join(' '));
  return out.join('\n').slice(0, maxLen);
}

async function main() {
  const client = new MongoClient(ENV.MONGO_URI);
  await client.connect();
  const db = client.db('aigame');
  const coll = db.collection('design_base');

  // Collect .md from all dirs, dedup by normalized basename (strip " (1)" copy suffix). Earlier dir wins.
  const norm = (f) => f.replace(/\s*\(\d+\)/g, '').trim();
  const seen = new Set();
  const targets = [];
  for (const dir of DOCS_DIRS) {
    if (!fs.existsSync(dir)) continue;
    for (const raw of fs.readdirSync(dir).filter(f => f.endsWith('.md'))) {
      const key = norm(raw);
      if (seen.has(key)) continue;
      seen.add(key);
      targets.push({ fname: key, fpath: path.join(dir, raw) });
    }
  }
  console.log(`Found ${targets.length} unique markdown files across ${DOCS_DIRS.length} dirs`);

  let added = 0, updated = 0, skipped = 0;
  for (const { fname, fpath } of targets) {
    const text = fs.readFileSync(fpath, 'utf8');
    const meta = DOC_MAP[fname] || { domain: 'Meta', system: path.basename(fname, '.md'), role: 'spec', tags: [] };

    const sysId = meta.system.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    const designId = `balloonflow_${meta.domain.toLowerCase()}_direction_${sysId}`;
    const headings = sectionsFromMd(text);
    const summary = summarize(text);

    const doc = {
      designId,
      project: PROJECT,
      genre: GENRE,
      domain: meta.domain,
      system: meta.system,
      data_type: 'direction',
      score: 0.5,
      source: 'internal_original',
      source_file: fpath,
      document_role: meta.role,
      tags: meta.tags,
      content: text,
      content_hash: hashId(text),
      headings,
      summary,
      char_count: text.length,
      provides: [],
      requires: [],
      version: 1,
      timestamp: NOW,
      ingested_at: NOW,
    };

    const result = await coll.updateOne(
      { designId, project: PROJECT },
      {
        $set: doc,
        $unset: { embedding: '', embedded_at: '', embedding_model: '' },  // Force re-embed
      },
      { upsert: true }
    );
    if (result.upsertedCount) { console.log(`  + ${designId}`); added++; }
    else if (result.modifiedCount) { console.log(`  ~ ${designId}`); updated++; }
    else { skipped++; }
  }

  console.log(`\nDone: added=${added}, updated=${updated}, skipped=${skipped}`);
  await client.close();
}

main().catch(e => { console.error(e); process.exit(1); });
