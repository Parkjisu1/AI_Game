// Build PF gimmick index from balloonflow_format/levels/*.json.
// Output: { "<level_number>": { gimmick_wall: 1|0, gimmick_pinata: 1|0, ..., variants: N } }
//
// Union strategy: for each lv N, OR across all variants. If ANY variant has gimmick X,
// then BL lv N may legitimately have gimmick X. If NO variant has X, BL also 0.
//
// For COUNT we set 1 (presence flag). Actual counts → CSV designer 또는 watcher 알고리즘.

const fs = require("fs");
const path = require("path");

const LEVELS_DIR = "E:/AI/pixelflow_game_data/balloonflow_format/levels";
const OUT = "E:/AI/tools/projecthub-web/scripts/pf_gimmick_index.json";

// PF gimmickType → BL gimmick_* column
// 실측 PF JSON gimmickType 값 (17종) 모두 매핑 — Split/Ufo 만 unknown 으로 skip.
const PF_TO_BL = {
  // 필드 기믹
  Wall: "gimmick_wall",
  Cage: "gimmick_wall",            // Cage = Wall variant
  Snake: "gimmick_pin",
  MultiSnake: "gimmick_pin",
  Door: "gimmick_pin",             // Door = Barricade-like
  Wood: "gimmick_pinata",          // 단일 Wooden Board
  Biscuit: "gimmick_pinata",       // Wooden Board variant
  Pumpkin: "gimmick_pinata",       // Wooden Board variant
  Egg: "gimmick_pinata_box",       // EggBox → Target Box
  Ice: "gimmick_ice",
  Surprise: "gimmick_surprise",    // Hidden Balloon
  Curtain: "gimmick_curtain",
  // 큐 기믹
  Pipe: "gimmick_spawner_o",
  Key: "gimmick_lock_key",
  Gate: "gimmick_lock_key",
  // unknown: Split, Ufo (skip)
};

// 사용자 규칙 (2026-05-21): PF presence → BL CSV count 기본값
// "필드 배치 시 N개" — designer 의 의도.
const PF_PRESENCE_TO_BL_COUNT = {
  gimmick_pinata: 2,        // 사용자 룰: lv 31-40 wooden 1종 → BL 필드 2개 배치
  gimmick_wall: 1,
  gimmick_pin: 2,           // Barricade 도 2개 권장
  gimmick_surprise: 8,      // Hidden Balloon 은 다수
  gimmick_pinata_box: 1,
  gimmick_ice: 80,          // Ice 는 cells 단위 (large)
  gimmick_curtain: 1,
  gimmick_spawner_o: 1,
  gimmick_lock_key: 0,      // 1.0 SKIP
  gimmick_chain: 0,
  gimmick_hidden: 0,
  gimmick_glass_pipe: 0,
  gimmick_spawner_t: 0,
  gimmick_frozen_dart: 0,
};

const BL_GIMMICKS = [
  "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
  "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
  "gimmick_spawner_o", "gimmick_spawner_t", "gimmick_pinata_box",
  "gimmick_ice", "gimmick_frozen_dart", "gimmick_curtain",
];

const files = fs.readdirSync(LEVELS_DIR).filter(f => f.endsWith(".json"));
console.log(`Scanning ${files.length} PF level files...`);

const index = {};
const unmapped = new Set();
let skipped = 0;

for (const fname of files) {
  let data;
  try {
    const raw = fs.readFileSync(path.join(LEVELS_DIR, fname), "utf-8");
    data = JSON.parse(raw);
  } catch (e) {
    skipped++;
    continue;
  }
  const lv = Number(data.levelId);
  if (!Number.isFinite(lv) || lv <= 0) { skipped++; continue; }

  const key = String(lv);
  if (!index[key]) {
    index[key] = {
      level_number: lv,
      variants: 0,
      gimmick_types_pf: new Set(),
    };
    for (const g of BL_GIMMICKS) index[key][g] = 0;
  }
  index[key].variants++;

  const gimmicks = Array.isArray(data.gimmickTypes) ? data.gimmickTypes : [];
  for (const pfType of gimmicks) {
    index[key].gimmick_types_pf.add(pfType);
    const blCol = PF_TO_BL[pfType];
    if (blCol) {
      // 사용자 룰: presence → BL count default (덮어쓰기 — variant 여러 개여도 동일 count)
      const cnt = PF_PRESENCE_TO_BL_COUNT[blCol] ?? 1;
      // 다른 variant 가 이미 0이상 값 넣었으면 max 유지 (presence 추가만)
      if ((index[key][blCol] ?? 0) < cnt) {
        index[key][blCol] = cnt;
      }
    } else {
      unmapped.add(pfType);
    }
  }
}

// Set → Array for JSON
for (const k of Object.keys(index)) {
  index[k].gimmick_types_pf = [...index[k].gimmick_types_pf].sort();
}

console.log(`Built index for ${Object.keys(index).length} unique levels`);
console.log(`Skipped: ${skipped}`);
if (unmapped.size > 0) {
  console.log(`Unmapped PF types (not in PF_TO_BL):`, [...unmapped].sort());
}

// Stats: gimmick presence rate
const totals = {};
for (const g of BL_GIMMICKS) totals[g] = 0;
let lvWithAnyGim = 0;
for (const k of Object.keys(index)) {
  let any = false;
  for (const g of BL_GIMMICKS) {
    if (index[k][g] > 0) { totals[g]++; any = true; }
  }
  if (any) lvWithAnyGim++;
}
const n = Object.keys(index).length;
console.log(`\nLevels with any gimmick: ${lvWithAnyGim}/${n} (${(lvWithAnyGim/n*100).toFixed(1)}%)`);
console.log(`Per-gimmick presence:`);
for (const g of BL_GIMMICKS) {
  if (totals[g] > 0) console.log(`  ${g}: ${totals[g]}/${n} (${(totals[g]/n*100).toFixed(1)}%)`);
}

fs.writeFileSync(OUT, JSON.stringify(index, null, 2), "utf-8");
console.log(`\nWrote ${OUT} (${(fs.statSync(OUT).size/1024).toFixed(1)} KB)`);
