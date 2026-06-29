// Trigger 2 v43 jobs directly (server-side bypass for terminal use).
// Job A: FC 6a102f7114ea55528a44a254 의 37 lv
// Job B: Art 6a10290214ea55528a44a24d 의 41 lv

const { MongoClient, ObjectId } = require("/home/aimed/projecthub-web/node_modules/mongodb");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const URI = process.env.MONGODB_URI;
const DB = process.env.MONGODB_DB || "aigame";

const JOBS = [
  {
    label: "v43 regen (FC 8a44a254 37 lv)",
    target_levels: [1, 3, 4, 14, 18, 20, 21, 23, 25, 27, 37, 50, 51, 59, 64, 65, 70, 72, 76, 78, 81, 88, 115, 123, 137, 139, 144, 163, 167, 203, 209, 231, 248, 262, 263, 274, 292],
    source: "FC 6a102f7114ea55528a44a254",
  },
  {
    label: "v43 regen (Art 8a44a24d 41 lv)",
    target_levels: [1, 3, 4, 5, 7, 14, 18, 20, 21, 23, 25, 27, 37, 50, 51, 59, 64, 65, 70, 72, 76, 78, 81, 88, 115, 123, 137, 139, 144, 156, 163, 167, 203, 209, 231, 248, 262, 263, 271, 274, 292],
    source: "Art batch 6a10290214ea55528a44a24d",
  },
];

const V43_DIR = "/home/aimed/.hermes/watcher/v43";
const OUT_BASE = "/home/aimed/.hermes/v43_out";
const LOG_DIR = "/home/aimed/.hermes/logs/v43";

(async () => {
  const c = new MongoClient(URI);
  await c.connect();
  const db = c.db(DB);
  const v43Coll = db.collection("pixelforge_v43_jobs");
  const lvColl = db.collection("pixelforge_levels");

  const N_SEEDS = 10, N_FINAL = 2;

  for (const J of JOBS) {
    const now = new Date().toISOString();
    const insertDoc = {
      created_at: now,
      created_by_email: "woohyun.lim@aimed.xyz",
      status: "pending",
      label: J.label,
      source_job: J.source,
      target_levels: J.target_levels,
      n_seeds: N_SEEDS,
      n_final: N_FINAL,
    };
    const ins = await v43Coll.insertOne(insertDoc);
    const id = String(ins.insertedId);
    const outDir = path.join(OUT_BASE, id);
    fs.mkdirSync(outDir, { recursive: true });

    // CSV 합성 (51 컬럼, gen_43 parse_csv_levels 형식)
    const rows = await lvColl.find(
      { level_number: { $in: J.target_levels }, status: { $exists: true } },
      { projection: { level_number: 1, field_rows: 1, field_columns: 1, num_colors: 1, bl_metaphor: 1, pf_metaphor: 1 } },
    ).toArray();
    const byLv = new Map(rows.map(r => [Number(r.level_number), r]));

    const lines = [
      new Array(51).fill("").join(","),
      (() => { const a = new Array(51).fill(""); a[0]="level_number"; a[8]="num_colors"; a[11]="field_columns"; a[12]="field_rows"; a[50]="bl_metaphor"; return a.join(","); })(),
      new Array(51).fill("").join(","),
    ];
    const escape = (v) => { const s = String(v ?? ""); return /[,"\n]/.test(s) ? JSON.stringify(s) : s; };
    let missingCount = 0;
    for (const lv of J.target_levels) {
      const r = byLv.get(lv);
      if (!r) { missingCount++; continue; }
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
    await v43Coll.updateOne({ _id: ins.insertedId }, { $set: { csv_path: csvPath, out_dir: outDir, missing_count: missingCount } });

    console.log(`[${J.label}]`);
    console.log(`  id=${id}`);
    console.log(`  target_levels=${J.target_levels.length} (missing in DB: ${missingCount})`);
    console.log(`  csv=${csvPath}`);
    console.log(`  out=${outDir}`);

    // spawn runner — gen_43 함수 호출 (알고리즘 0 변경)
    fs.mkdirSync(LOG_DIR, { recursive: true });
    const logPath = path.join(LOG_DIR, `v43_${id}.log`);
    const out = fs.openSync(logPath, "a");
    const child = spawn(
      "/home/aimed/.hermes/watcher/venv/bin/python",
      [path.join(V43_DIR, "v43_runner.py"), "--job-id", id],
      {
        cwd: V43_DIR,
        detached: true,
        stdio: ["ignore", out, out],
        env: { ...process.env, MONGODB_URI: URI, MONGODB_DB: DB },
      },
    );
    child.on("error", (e) => console.error(`[v43 ${id}] spawn:`, e));
    child.unref();
    console.log(`  ✓ spawned (log: ${logPath})`);
    console.log();
  }

  await c.close();
  console.log("ALL JOBS DISPATCHED.");
})().catch(e => { console.error("ERROR", e); process.exit(1); });
