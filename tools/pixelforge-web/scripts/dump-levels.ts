/**
 * Full collection dump — `pixelforge_levels` → local JSON file.
 * Safety net before --migrate. Use to restore via db.insert/replace if needed.
 *
 * Usage:
 *   npx tsx scripts/dump-levels.ts --out backup-YYYYMMDD.json
 */
import { MongoClient } from "mongodb";
import { writeFileSync } from "fs";

function parseArgs() {
  const args = process.argv.slice(2);
  let out = `backup-pixelforge_levels-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--out") out = args[++i];
  }
  return { out };
}

async function main() {
  const { out } = parseArgs();
  const uri = process.env.MONGODB_URI;
  if (!uri) { console.error("MONGODB_URI required"); process.exit(1); }
  const dbName = process.env.MONGODB_DB || "aigame";

  const client = new MongoClient(uri);
  await client.connect();
  const docs = await client.db(dbName).collection("pixelforge_levels").find({}).toArray();
  writeFileSync(out, JSON.stringify(docs, null, 2));
  const sizeKB = (Buffer.byteLength(JSON.stringify(docs)) / 1024).toFixed(1);
  console.log(`dumped ${docs.length} docs (${sizeKB} KB) → ${out}`);
  await client.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
