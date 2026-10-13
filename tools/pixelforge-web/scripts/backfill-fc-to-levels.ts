/**
 * Backfill: pixelforge_field_complete_jobs → pixelforge_levels.
 *
 * 각 FC job 의 ok 결과를 디자이너 행에 merge.
 * - field_map: 디자이너 행에 이미 있으면 보존, 없을 때만 FC balloons 로 계산해서 채움
 * - field_completed / balloons / gimmicks / field_analysis / field_complete_score / field_complete_job_id / warnings / escalated: 최신 FC job 의 값으로 덮어씀
 * - 같은 level_number 가 여러 FC job 에 있으면 job.created_at 최신 우선
 *
 * Usage:
 *   pnpm tsx scripts/backfill-fc-to-levels.ts            # 실제 적용
 *   pnpm tsx scripts/backfill-fc-to-levels.ts --dry-run  # 변경 없이 카운트만
 *   pnpm tsx scripts/backfill-fc-to-levels.ts --overwrite-field-map  # 기존 field_map 도 덮어씀
 */
import { MongoClient, ObjectId } from "mongodb";
import * as fs from "fs";
import * as path from "path";

// Minimal .env.local loader (dotenv 미설치 환경 대응)
function loadEnv(p: string) {
  if (!fs.existsSync(p)) return;
  for (const line of fs.readFileSync(p, "utf8").split(/\r?\n/)) {
    const m = line.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}
loadEnv(path.resolve(__dirname, "..", ".env.local"));

const URI = process.env.MONGODB_URI;
const DB = process.env.MONGODB_DB || "aigame";
if (!URI) {
  console.error("MONGODB_URI not set");
  process.exit(1);
}

const DRY_RUN = process.argv.includes("--dry-run");
const OVERWRITE_FM = process.argv.includes("--overwrite-field-map");

interface FCBalloon { row: number; col: number; color: number; life?: number; }
interface FCGimmick { type?: string; row?: number; col?: number; cells?: unknown[]; color?: number; hidden_color?: number; }
interface FCResult {
  level_number: number;
  ok: boolean;
  score?: number;
  balloons?: FCBalloon[];
  gimmicks?: FCGimmick[];
  field_analysis?: { field_rows?: number; field_columns?: number; [k: string]: unknown };
  warnings?: string[];
  escalated?: boolean;
}
interface FCJob {
  _id: ObjectId;
  created_at?: Date | string;
  status?: string;
  results?: FCResult[];
  csv_rows?: Array<{ level_number?: number; field_rows?: number | string; field_columns?: number | string; [k: string]: unknown }>;
}

function buildFieldMap(balloons: FCBalloon[], gimmicks: FCGimmick[], rows: number, cols: number): string {
  if (rows <= 0 || cols <= 0) return "";
  const grid: string[][] = Array.from({ length: rows }, () => Array(cols).fill(".."));
  for (const b of balloons) {
    if (b.row >= 0 && b.row < rows && b.col >= 0 && b.col < cols) {
      grid[b.row][b.col] = String(b.color).padStart(2, "0");
    }
  }
  for (const g of gimmicks) {
    const cells: [number, number][] = [];
    if (Array.isArray(g.cells)) {
      for (const c of g.cells) {
        if (Array.isArray(c) && c.length >= 2 && typeof c[0] === "number" && typeof c[1] === "number") {
          cells.push([c[0], c[1]]);
        }
      }
    } else if (typeof g.row === "number" && typeof g.col === "number") {
      cells.push([g.row, g.col]);
    }
    for (const [r, c] of cells) {
      if (r >= 0 && r < rows && c >= 0 && c < cols && grid[r][c] === "..") {
        if (g.type === "Hidden_Balloon" && typeof g.hidden_color === "number") {
          grid[r][c] = String(g.hidden_color).padStart(2, "0");
        } else if (typeof g.color === "number") {
          grid[r][c] = String(g.color).padStart(2, "0");
        }
      }
    }
  }
  return grid.map((row) => row.join(" ")).join("\n");
}

async function main() {
  const c = new MongoClient(URI!);
  await c.connect();
  const db = c.db(DB);
  const jobs = await db
    .collection<FCJob>("pixelforge_field_complete_jobs")
    .find({ status: "done" })
    .sort({ created_at: 1 })
    .toArray();
  console.log(`[backfill] FC jobs (done): ${jobs.length}`);

  // Index latest result per level_number
  type Pick = { job: FCJob; result: FCResult; csvRow: Record<string, unknown> };
  const latestByLv: Map<number, Pick> = new Map();
  for (const job of jobs) {
    const csvByLv = new Map<number, Record<string, unknown>>();
    for (const r of job.csv_rows || []) {
      if (typeof r.level_number !== "undefined") {
        csvByLv.set(Number(r.level_number), r as Record<string, unknown>);
      }
    }
    for (const r of job.results || []) {
      if (!r.ok || !Array.isArray(r.balloons) || r.balloons.length === 0) continue;
      const lv = r.level_number;
      // jobs already sorted ascending → last write wins (latest)
      latestByLv.set(lv, { job, result: r, csvRow: csvByLv.get(lv) || {} });
    }
  }
  console.log(`[backfill] Unique levels covered by FC ok results: ${latestByLv.size}`);

  let filledFm = 0, skippedFm = 0, updatedDocs = 0, noDesignerRow = 0, errors = 0;
  for (const [lv, pick] of latestByLv) {
    const designer = await db.collection("pixelforge_levels").findOne({ level_number: lv, status: { $exists: true } });
    if (!designer) {
      noDesignerRow++;
      continue;
    }

    const r = pick.result;
    const csvRow = pick.csvRow;
    const rows =
      Number(designer.field_rows) ||
      Number(csvRow.field_rows) ||
      Number(r.field_analysis?.field_rows) || 0;
    const cols =
      Number(designer.field_columns) ||
      Number(csvRow.field_columns) ||
      Number(r.field_analysis?.field_columns) || 0;

    const update: Record<string, unknown> = {
      field_completed: true,
      field_complete_job_id: String(pick.job._id),
      field_complete_score: r.score,
      balloons: r.balloons,
      gimmicks: r.gimmicks,
      field_analysis: r.field_analysis,
      field_complete_warnings: r.warnings,
      field_complete_escalated: r.escalated || false,
      updated_at: new Date().toISOString(),
    };

    const hasExistingFm = typeof designer.field_map === "string" && designer.field_map.trim().length > 0;
    const shouldWriteFm = !hasExistingFm || OVERWRITE_FM;
    if (shouldWriteFm) {
      const fm = buildFieldMap(r.balloons || [], r.gimmicks || [], rows, cols);
      if (fm) {
        update.field_map = fm;
        update.field_map_source = "field_complete_v1";
        filledFm++;
      } else {
        skippedFm++;
      }
    } else {
      skippedFm++;
    }

    if (DRY_RUN) {
      updatedDocs++;
      continue;
    }
    try {
      await db.collection("pixelforge_levels").updateOne(
        { level_number: lv, status: { $exists: true } },
        { $set: update },
      );
      updatedDocs++;
    } catch (e) {
      errors++;
      console.error(`[backfill] lv ${lv} error:`, (e as Error).message);
    }
  }

  console.log(`\n[backfill] Summary:`);
  console.log(`  updatedDocs:     ${updatedDocs}`);
  console.log(`  filledFieldMap:  ${filledFm}`);
  console.log(`  skippedFieldMap: ${skippedFm} (already has field_map or no rows/cols)`);
  console.log(`  noDesignerRow:   ${noDesignerRow}`);
  console.log(`  errors:          ${errors}`);
  if (DRY_RUN) console.log(`  (DRY RUN — no DB writes)`);
  await c.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
