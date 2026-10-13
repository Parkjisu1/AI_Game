/**
 * Side-by-side V1 vs V2 comparison on a single level (no DB writes).
 *
 * Usage:
 *   pnpm exec tsx scripts/compare-fieldmap-v1-v2.ts --level 42
 *   pnpm exec tsx scripts/compare-fieldmap-v1-v2.ts --level 42 --verbose
 *
 * Output:
 *   - Field-map rendered with both V1 and V2
 *   - Per-cell diff count and percentage
 *   - V2 palette_mapping (K → 28) table
 *   - Optional: full field-map dump with * on changed cells
 */
import { MongoClient } from "mongodb";
import { parseColorDist, GAME_PALETTE, COLOR_NAMES } from "../src/lib/palette";
import { snapImageToGridAndPalette } from "../src/lib/snapToGrid";
import { snapImageToGridAndPaletteV2 } from "../src/lib/snapToGridV2";
import { matrixToFieldMap } from "../src/lib/matrixRenderer";

interface LevelDoc {
  level_number: number;
  field_columns?: number;
  field_rows?: number;
  image_base64?: string;
  field_map?: string;
  color_distribution?: string;
  generated_num_colors?: number;
  designer_note?: string;
}

function parseArgs() {
  const args = process.argv.slice(2);
  let level: number | undefined;
  let verbose = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--level") level = Number(args[++i]);
    else if (args[i] === "--verbose") verbose = true;
  }
  if (!level) {
    console.error("Usage: --level N [--verbose]");
    process.exit(1);
  }
  return { level, verbose };
}

async function main() {
  const { level, verbose } = parseArgs();
  const uri = process.env.MONGODB_URI;
  if (!uri) { console.error("MONGODB_URI required"); process.exit(1); }
  const dbName = process.env.MONGODB_DB || "aigame";

  const client = new MongoClient(uri);
  await client.connect();
  const doc = await client.db(dbName).collection<LevelDoc>("pixelforge_levels").findOne({ level_number: level });
  if (!doc) { console.error(`Level ${level} not found`); await client.close(); process.exit(1); }
  if (!doc.image_base64) { console.error(`Level ${level} has no image_base64`); await client.close(); process.exit(1); }

  const cols = Number(doc.field_columns) || 20;
  const rows = Number(doc.field_rows) || 20;
  const paletteIds = parseColorDist(String(doc.color_distribution || ""));
  const k = Number(doc.generated_num_colors) || paletteIds.length || undefined;

  console.log(`\n═══ Level ${level} ═══`);
  console.log(`dims: ${cols}×${rows}   note: ${(doc.designer_note || "").slice(0, 60)}`);
  console.log(`color_distribution: ${doc.color_distribution || "(none)"}`);
  console.log(`target K: ${k || "(auto 8)"}`);

  const v1 = await snapImageToGridAndPalette(doc.image_base64, {
    cols, rows,
    allowedIds: paletteIds.length > 0 ? paletteIds : undefined,
    targetColorCount: k && k > 0 ? k : undefined,
  });
  const v2 = await snapImageToGridAndPaletteV2(doc.image_base64, {
    cols, rows,
    allowedIds: paletteIds.length > 0 ? paletteIds : undefined,
    targetColorCount: k && k > 0 ? k : undefined,
  });

  const fm1 = matrixToFieldMap(v1.matrix);
  const fm2 = matrixToFieldMap(v2.matrix);

  // Diff
  const aRows = fm1.split("\n"), bRows = fm2.split("\n");
  let changed = 0, total = 0;
  for (let r = 0; r < Math.min(aRows.length, bRows.length); r++) {
    const aT = aRows[r].trim().split(/\s+/);
    const bT = bRows[r].trim().split(/\s+/);
    for (let c = 0; c < Math.min(aT.length, bT.length); c++) {
      total++;
      if (aT[c] !== bT[c]) changed++;
    }
  }
  const ratio = total > 0 ? ((changed / total) * 100).toFixed(2) : "0.00";

  console.log(`\n── V1 (current snapToGrid) ──`);
  console.log(`unique: ${v1.stats.uniqueColorsBefore}→${v1.stats.uniqueColorsAfter}  dominant: ${v1.stats.dominantColors.join(", ")}`);

  console.log(`\n── V2 (unfake) ──`);
  console.log(`unique: ${v2.stats.uniqueColorsBefore}→${v2.stats.uniqueColorsAfter}  K=${v2.stats.k}  dominant: ${v2.stats.dominantColors.join(", ")}`);
  console.log(`K → 28 palette mapping:`);
  console.log(`  K-idx | K-centroid RGB      | → 28-id | 28-color name`);
  for (const [kIdxStr, paletteId] of Object.entries(v2.paletteMapping)) {
    const kIdx = Number(kIdxStr);
    const centroid = v2.kPalette[kIdx - 1];
    const pal = GAME_PALETTE[paletteId];
    console.log(
      `  ${String(kIdx).padStart(2)}    | rgb(${String(centroid[0]).padStart(3)},${String(centroid[1]).padStart(3)},${String(centroid[2]).padStart(3)}) | c${String(paletteId).padStart(2)}     | ${COLOR_NAMES[paletteId] || "?"} (rgb ${pal?.join(",") || "?"})`,
    );
  }

  console.log(`\n── DIFF ──`);
  console.log(`cells changed: ${changed} / ${total} (${ratio}%)`);

  if (verbose) {
    console.log(`\n── V1 field_map ──\n${fm1}\n\n── V2 field_map ──\n${fm2}`);
  }

  await client.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
