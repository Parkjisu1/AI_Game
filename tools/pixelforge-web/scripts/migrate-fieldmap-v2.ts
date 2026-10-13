/**
 * Field-map migration script — V1 (snapToGrid) → V2 (unfake-style).
 *
 * Three modes:
 *   --backup      Copy each doc's `field_map` → `field_map_v1_backup` (one-time, idempotent).
 *   --dry-run     Compute V2 field_map in memory, print per-level diff stats, DO NOT write DB.
 *   --migrate     Compute V2 and overwrite `field_map` + `palette_mapping` + `field_map_pipeline`.
 *
 * Usage:
 *   pnpm exec tsx scripts/migrate-fieldmap-v2.ts --backup
 *   pnpm exec tsx scripts/migrate-fieldmap-v2.ts --dry-run
 *   pnpm exec tsx scripts/migrate-fieldmap-v2.ts --dry-run --level 42
 *   pnpm exec tsx scripts/migrate-fieldmap-v2.ts --migrate
 *
 * Rollback:
 *   pnpm exec tsx scripts/migrate-fieldmap-v2.ts --rollback
 *
 * Safety:
 *   - Run --backup FIRST. Script refuses --migrate if any doc lacks `field_map_v1_backup`.
 *   - Dry-run output goes to stdout; pipe to a file to archive.
 *   - Each doc is processed independently; a single failure doesn't abort the batch.
 */
import { MongoClient } from "mongodb";
import { parseColorDist } from "../src/lib/palette";
import { snapImageToGridAndPaletteV2 } from "../src/lib/snapToGridV2";
import { matrixToFieldMap } from "../src/lib/matrixRenderer";

interface LevelDoc {
  _id: unknown;
  level_number: number;
  field_columns?: number;
  field_rows?: number;
  image_base64?: string;
  field_map?: string;
  field_map_v1_backup?: string;
  color_distribution?: string;
  generated_num_colors?: number;
}

type Mode = "backup" | "dry-run" | "migrate" | "rollback";

function parseArgs(): { mode: Mode; onlyLevel?: number } {
  const args = process.argv.slice(2);
  let mode: Mode | null = null;
  let onlyLevel: number | undefined;
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "--backup") mode = "backup";
    else if (a === "--dry-run") mode = "dry-run";
    else if (a === "--migrate") mode = "migrate";
    else if (a === "--rollback") mode = "rollback";
    else if (a === "--level") onlyLevel = Number(args[++i]);
  }
  if (!mode) {
    console.error("Usage: --backup | --dry-run | --migrate | --rollback  [--level N]");
    process.exit(1);
  }
  return { mode, onlyLevel };
}

function countDiff(a: string, b: string): { changed: number; total: number } {
  const aRows = a.split("\n");
  const bRows = b.split("\n");
  let changed = 0, total = 0;
  const rows = Math.min(aRows.length, bRows.length);
  for (let r = 0; r < rows; r++) {
    const aTok = aRows[r].trim().split(/\s+/);
    const bTok = bRows[r].trim().split(/\s+/);
    const cols = Math.min(aTok.length, bTok.length);
    for (let c = 0; c < cols; c++) {
      total++;
      if (aTok[c] !== bTok[c]) changed++;
    }
  }
  return { changed, total };
}

async function main() {
  const { mode, onlyLevel } = parseArgs();
  const uri = process.env.MONGODB_URI;
  if (!uri) {
    console.error("MONGODB_URI env var required");
    process.exit(1);
  }
  const dbName = process.env.MONGODB_DB || "aigame";

  const client = new MongoClient(uri);
  await client.connect();
  const db = client.db(dbName);
  const coll = db.collection<LevelDoc>("pixelforge_levels");

  const filter: Record<string, unknown> = { image_base64: { $exists: true, $ne: "" } };
  if (typeof onlyLevel === "number") filter.level_number = onlyLevel;

  const docs = await coll.find(filter).toArray();
  console.log(`[migrate] mode=${mode} docs=${docs.length}${onlyLevel ? ` (level=${onlyLevel})` : ""}`);

  if (docs.length === 0) {
    await client.close();
    return;
  }

  // ─────────── BACKUP ───────────
  if (mode === "backup") {
    let backedUp = 0, skipped = 0;
    for (const d of docs) {
      if (d.field_map_v1_backup) { skipped++; continue; }
      if (!d.field_map) { skipped++; continue; }
      await coll.updateOne(
        { _id: d._id },
        { $set: { field_map_v1_backup: d.field_map, field_map_v1_backup_at: new Date().toISOString() } },
      );
      backedUp++;
    }
    console.log(`[backup] new=${backedUp} already_backed_up=${skipped}`);
    await client.close();
    return;
  }

  // ─────────── ROLLBACK ───────────
  if (mode === "rollback") {
    let restored = 0, skipped = 0;
    for (const d of docs) {
      if (!d.field_map_v1_backup) { skipped++; continue; }
      await coll.updateOne(
        { _id: d._id },
        {
          $set: { field_map: d.field_map_v1_backup, field_map_pipeline: "v1_rollback", updated_at: new Date().toISOString() },
          $unset: { palette_mapping: "" },
        },
      );
      restored++;
    }
    console.log(`[rollback] restored=${restored} no_backup=${skipped}`);
    await client.close();
    return;
  }

  // ─────────── DRY-RUN / MIGRATE (shared conversion logic) ───────────
  if (mode === "migrate") {
    const missingBackup = docs.filter((d) => !d.field_map_v1_backup).map((d) => d.level_number);
    if (missingBackup.length > 0) {
      console.error(`[migrate] ABORT — ${missingBackup.length} docs lack field_map_v1_backup. Run --backup first.`);
      console.error(`[migrate] missing: ${missingBackup.slice(0, 10).join(", ")}${missingBackup.length > 10 ? "..." : ""}`);
      await client.close();
      process.exit(1);
    }
  }

  const summary = {
    processed: 0,
    succeeded: 0,
    failed: 0,
    unchanged: 0,
    totalCellsChanged: 0,
    totalCells: 0,
  };
  const perLevel: Array<{ level: number; changed: number; total: number; ratio: string; k: number }> = [];

  for (const d of docs) {
    summary.processed++;
    const lv = d.level_number;
    try {
      if (!d.image_base64) { summary.failed++; continue; }
      const cols = Number(d.field_columns) || 20;
      const rows = Number(d.field_rows) || 20;
      const paletteIds = parseColorDist(String(d.color_distribution || ""));
      const k = Number(d.generated_num_colors) || paletteIds.length || undefined;

      const snapped = await snapImageToGridAndPaletteV2(d.image_base64, {
        cols, rows,
        allowedIds: paletteIds.length > 0 ? paletteIds : undefined,
        targetColorCount: k && k > 0 ? k : undefined,
      });
      const newFieldMap = matrixToFieldMap(snapped.matrix);
      const oldFieldMap = d.field_map || "";

      const diff = countDiff(oldFieldMap, newFieldMap);
      summary.totalCellsChanged += diff.changed;
      summary.totalCells += diff.total;
      const ratio = diff.total > 0 ? ((diff.changed / diff.total) * 100).toFixed(1) : "0.0";
      if (diff.changed === 0) summary.unchanged++;
      perLevel.push({ level: lv, changed: diff.changed, total: diff.total, ratio, k: snapped.stats.k });

      if (mode === "migrate") {
        await coll.updateOne(
          { _id: d._id },
          {
            $set: {
              field_map: newFieldMap,
              field_map_pipeline: snapped.stats.pipeline,
              palette_mapping: snapped.paletteMapping,
              field_map_migrated_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
          },
        );
      }
      summary.succeeded++;
    } catch (e) {
      summary.failed++;
      console.error(`[${mode}] level=${lv} FAILED:`, e instanceof Error ? e.message : e);
    }

    if (summary.processed % 20 === 0) {
      console.error(`[${mode}] progress: ${summary.processed}/${docs.length}`);
    }
  }

  // ─────────── REPORT ───────────
  perLevel.sort((a, b) => b.changed - a.changed);
  console.log("\n=== PER-LEVEL DIFF (top 20 most-changed) ===");
  console.log("level | cells_changed / total | ratio | K");
  for (const p of perLevel.slice(0, 20)) {
    console.log(`${String(p.level).padStart(5)} | ${String(p.changed).padStart(5)} / ${String(p.total).padStart(5)} | ${p.ratio.padStart(5)}% | K=${p.k}`);
  }

  const overallRatio = summary.totalCells > 0
    ? ((summary.totalCellsChanged / summary.totalCells) * 100).toFixed(2) : "0.00";
  console.log("\n=== SUMMARY ===");
  console.log(`mode             : ${mode}`);
  console.log(`docs processed   : ${summary.processed}`);
  console.log(`succeeded        : ${summary.succeeded}`);
  console.log(`failed           : ${summary.failed}`);
  console.log(`unchanged        : ${summary.unchanged}`);
  console.log(`cells changed    : ${summary.totalCellsChanged} / ${summary.totalCells} (${overallRatio}%)`);
  if (mode === "dry-run") console.log("NOTE: dry-run — no DB writes performed.");
  if (mode === "migrate") console.log("DB updated. Run with --rollback to restore from field_map_v1_backup.");

  await client.close();
}

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(1);
});
