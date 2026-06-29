// v47 zone 함수 적용 후 Art batch 8a44a24d 의 41 lv 재실행.
const { MongoClient } = require("/home/aimed/projecthub-web/node_modules/mongodb");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const URI = process.env.MONGODB_URI;
const DB = process.env.MONGODB_DB || "aigame";

const TARGET_LEVELS = [1, 3, 4, 5, 7, 14, 18, 20, 21, 23, 25, 27, 37, 50, 51, 59, 64, 65, 70, 72, 76, 78, 81, 88, 115, 123, 137, 139, 144, 156, 163, 167, 203, 209, 231, 248, 262, 263, 271, 274, 292];
const SOURCE = "Art batch 6a10290214ea55528a44a24d (v47 re-run)";
const LABEL = "v47 regen (Art 8a44a24d 41 lv)";
const N_SEEDS = 10;
const N_FINAL = 2;

const V43_DIR = "/home/aimed/.hermes/watcher/v43";
const OUT_BASE = "/home/aimed/.hermes/v43_out";
const LOG_DIR = "/home/aimed/.hermes/logs/v43";

(async () => {
  const c = new MongoClient(URI);
  await c.connect();
  const db = c.db(DB);
  const v43Coll = db.collection("pixelforge_v43_jobs");
  const lvColl = db.collection("pixelforge_levels");

  const now = new Date().toISOString();
  const ins = await v43Coll.insertOne({
    created_at: now,
    created_by_email: "woohyun.lim@aimed.xyz",
    status: "pending",
    label: LABEL,
    source_job: SOURCE,
    target_levels: TARGET_LEVELS,
    n_seeds: N_SEEDS,
    n_final: N_FINAL,
    pipeline_version: "v47 (gen_42 with v47 zones)",
    legacy: false,
  });
  const id = String(ins.insertedId);
  const outDir = path.join(OUT_BASE, id);
  fs.mkdirSync(outDir, { recursive: true });

  // CSV 합성
  const rows = await lvColl.find(
    { level_number: { $in: TARGET_LEVELS }, status: { $exists: true } },
    { projection: { level_number: 1, field_rows: 1, field_columns: 1, num_colors: 1, bl_metaphor: 1, pf_metaphor: 1 } },
  ).toArray();
  const byLv = new Map(rows.map((r) => [Number(r.level_number), r]));

  const cols = new Array(51).fill("");
  cols[0] = "level_number"; cols[8] = "num_colors"; cols[11] = "field_columns"; cols[12] = "field_rows"; cols[50] = "bl_metaphor";
  const lines = [new Array(51).fill("").join(","), cols.join(","), new Array(51).fill("").join(",")];
  const escape = (v) => { const s = String(v ?? ""); return /[,"\n]/.test(s) ? JSON.stringify(s) : s; };
  let missing = 0;
  for (const lv of TARGET_LEVELS) {
    const r = byLv.get(lv);
    if (!r) { missing++; continue; }
    const a = new Array(51).fill("");
    a[0] = String(lv);
    a[8] = String(r.num_colors ?? 3);
    a[11] = String(r.field_columns ?? 16);
    a[12] = String(r.field_rows ?? 16);
    a[50] = String(r.bl_metaphor ?? r.pf_metaphor ?? "");
    lines.push(a.map(escape).join(","));
  }
  const csvPath = path.join(outDir, "input.csv");
  fs.writeFileSync(csvPath, lines.join("\n"), "utf-8");
  await v43Coll.updateOne({ _id: ins.insertedId }, { $set: { csv_path: csvPath, out_dir: outDir, missing_count: missing } });

  console.log(`[${LABEL}]`);
  console.log(`  id=${id}`);
  console.log(`  target_levels=${TARGET_LEVELS.length} (missing in DB: ${missing})`);
  console.log(`  csv=${csvPath}`);
  console.log(`  out=${outDir}`);

  fs.mkdirSync(LOG_DIR, { recursive: true });
  const logPath = path.join(LOG_DIR, `v43_${id}.log`);
  const out = fs.openSync(logPath, "a");
  const child = spawn(
    "/home/aimed/.hermes/watcher/venv/bin/python",
    [path.join(V43_DIR, "v43_runner.py"), "--job-id", id],
    { cwd: V43_DIR, detached: true, stdio: ["ignore", out, out],
      env: { ...process.env, MONGODB_URI: URI, MONGODB_DB: DB } },
  );
  child.on("error", (e) => console.error(`[v47 ${id}] spawn:`, e));
  child.unref();
  console.log(`  ✓ spawned — log: ${logPath}`);

  await c.close();
})().catch((e) => { console.error("ERROR", e); process.exit(1); });
