import { createRequire } from 'node:module';
import { readFile, writeFile, mkdir, appendFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import path from 'node:path';

const webRoot = process.env.PROJECTHUB_WEB_ROOT || '/home/aimed/projecthub-web';
const require = createRequire(path.join(webRoot, 'package.json'));
const { MongoClient } = require('mongodb');
for (const file of ['.env.local', '.env.production']) {
  try {
    for (const line of (await readFile(path.join(webRoot, file), 'utf8')).split(/\r?\n/)) {
      const m = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^(["'])(.*)\1$/, '$2');
    }
  } catch { /* EnvironmentFile may already supply configuration. */ }
}
if (!process.env.MONGODB_URI) throw new Error('MONGODB_URI is required');
const client = await new MongoClient(process.env.MONGODB_URI).connect();
const db = client.db(process.env.MONGODB_DB || 'aigame');
const jobs = db.collection('projecthub_3d_jobs');
const state = db.collection('projecthub_3d_worker');
const dataRoot = process.env.PROJECTHUB_3D_DATA || path.join(webRoot, 'data', 'asset-studio');
const host = 'user@100.92.43.9';
const remoteRoot = 'D:/ProjectHub3D';
const sshOptions = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=30'];
await mkdir(dataRoot, { recursive: true });
await jobs.createIndex({ status: 1, created_at: 1 });
await jobs.createIndex({ created_at: -1 });

function command(program, args, timeout = 120000) {
  return new Promise((resolve, reject) => {
    const child = spawn(program, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '';
    const keep = chunk => { output = (output + chunk.toString()).slice(-30000); };
    child.stdout.on('data', keep); child.stderr.on('data', keep);
    const timer = setTimeout(() => { child.kill('SIGTERM'); reject(new Error('Command timeout; remote state requires review')); }, timeout);
    child.on('error', err => { clearTimeout(timer); reject(err); });
    child.on('close', code => { clearTimeout(timer); code === 0 ? resolve(output) : reject(new Error(output.slice(-6000) || `Exit ${code}`)); });
  });
}
function powershell(script, timeout) {
  const encoded = Buffer.from("$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; " + script, 'utf16le').toString('base64');
  return command('ssh', [...sshOptions, host, 'powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded], timeout);
}
async function knowledge(brief) {
  try {
    const res = await fetch('http://100.87.87.59:11434/api/embed', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'nomic-embed-text', input: 'search_query: ' + brief.slice(0, 3000) }), signal: AbortSignal.timeout(20000),
    });
    if (!res.ok) throw new Error(`Embedding ${res.status}`);
    const { embeddings } = await res.json();
    const search = await fetch('http://127.0.0.1:6333/collections/projecthub_3d_knowledge/points/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vector: embeddings[0], limit: 4, with_payload: true }), signal: AbortSignal.timeout(10000),
    });
    if (!search.ok) throw new Error(`Knowledge search ${search.status}`);
    return { status: 'retrieved', sources: (await search.json()).result.map(r => ({ score: r.score, ...r.payload })) };
  } catch (err) { return { status: 'unavailable', reason: String(err.message).slice(0, 160), sources: [] }; }
}
async function run(job) {
  const id = String(job._id);
  if (!/^[a-f0-9]{24}$/.test(id)) throw new Error('Invalid job ID');
  const dir = path.join(dataRoot, id);
  await mkdir(dir, { recursive: true });
  const context = await knowledge(job.brief || 'stylized game character retopology UV texture rig weight LOD export');
  await writeFile(path.join(dir, 'research.json'), JSON.stringify(context, null, 2));
  await jobs.updateOne({ _id: job._id }, { $set: { knowledge: context, stage: 'preflight', updated_at: new Date() } });
  await powershell(`if (Get-Process Unity -ErrorAction SilentlyContinue) { throw 'BUSY: Unity is running' }; if (-not (Test-Path '${remoteRoot}/installation.json')) { throw 'Blender installation not ready' }; New-Item -ItemType Directory -Force '${remoteRoot}/jobs/${id}' | Out-Null`);
  const payload = { mode: job.mode, profile: job.profile, output: `${remoteRoot}/jobs/${id}/output` };
  if (job.mode === 'import') {
    if (!['.blend', '.glb', '.fbx', '.obj'].includes(job.extension)) throw new Error('Invalid extension');
    payload.source = `${remoteRoot}/jobs/${id}/input${job.extension}`;
    await command('scp', [...sshOptions, path.join(dir, `input${job.extension}`), `${host}:${payload.source}`]);
  } else if (job.mode === 'image') {
    const images = ['.png', '.jpg', '.jpeg', '.webp'];
    if (!images.includes(job.extension) || !images.includes(job.back_extension)) throw new Error('Invalid image extension');
    await jobs.updateOne({ _id: job._id }, { $set: { stage: 'image_reconstruction', updated_at: new Date() } });
    const shapeDir = path.join(dir, 'shape');
    const log = await command('/home/aimed/projecthub-3d/ai3d-venv/bin/python',
      ['/home/aimed/projecthub-3d/image_to_shape.py', '--image', path.join(dir, `input${job.extension}`), '--output', shapeDir], 1200000);
    await writeFile(path.join(dir, 'generation.log'), log);
    payload.source = `${remoteRoot}/jobs/${id}/shape.glb`;
    payload.front = `${remoteRoot}/jobs/${id}/front${job.extension}`;
    payload.back = `${remoteRoot}/jobs/${id}/back${job.back_extension}`;
    payload.rig_template = `${remoteRoot}/pipeline/rig-template.blend`;
    for (const [local, remote] of [[path.join(shapeDir, 'shape.glb'), payload.source],
      [path.join(dir, `input${job.extension}`), payload.front], [path.join(dir, `back${job.back_extension}`), payload.back]]) {
      await command('scp', [...sshOptions, local, `${host}:${remote}`], 300000);
    }
  } else if (job.mode !== 'demo') { throw new Error('Unsupported execution mode'); }
  await writeFile(path.join(dir, 'job.json'), JSON.stringify(payload));
  await command('scp', [...sshOptions, path.join(dir, 'job.json'), `${host}:${remoteRoot}/jobs/${id}/job.json`]);
  await jobs.updateOne({ _id: job._id }, { $set: { stage: 'blender', updated_at: new Date() } });
  const output = await powershell(`& '${remoteRoot}/pipeline/run-job.ps1' -JobId '${id}'; if (-not $?) { exit 1 }`, 2800000);
  await writeFile(path.join(dir, 'worker.log'), output);
  for (const file of ['report.json', 'manifest.json', 'preview.png', 'model-pack.zip', 'character_LOD0.glb']) {
    await command('scp', [...sshOptions, `${host}:${remoteRoot}/jobs/${id}/output/${file}`, path.join(dir, file)], 300000);
  }
  const report = JSON.parse(await readFile(path.join(dir, 'report.json'), 'utf8'));
  await jobs.updateOne({ _id: job._id }, { $set: {
    status: 'needs_review', stage: 'review', report, artifacts_ready: true,
    build_path: `${remoteRoot}/jobs/${id}/output`, updated_at: new Date(), completed_at: new Date(),
  } });
}

let currentJob = null;
let stopping = false;
process.on('SIGTERM', () => { stopping = true; });
const heartbeat = setInterval(() => {
    state.updateOne({ _id: 'mother' }, { $set: { last_seen: new Date(), job_id: currentJob, host: 'Mother / Build PC' } }, { upsert: true }).catch(() => {});
}, 15000);
// An interrupted remote render must be inspected; never silently execute it twice.
await jobs.updateMany({ status: 'running' }, { $set: { status: 'interrupted', stage: 'review', error: 'Worker restarted; inspect build PC output before retrying.', updated_at: new Date() } });
console.log('ProjectHub 3D worker online');
while (!stopping) {
  const job = await jobs.findOneAndUpdate({ status: 'queued', $or: [{ retry_after: { $exists: false } }, { retry_after: { $lte: new Date() } }] },
    { $set: { status: 'running', stage: 'starting', updated_at: new Date() } }, { sort: { created_at: 1 }, returnDocument: 'after' });
  if (job) {
    currentJob = String(job._id);
    try { await run(job); }
    catch (err) {
      const busy = String(err.message).includes('BUSY:');
      await jobs.updateOne({ _id: job._id }, { $set: { status: busy ? 'queued' : 'failed', stage: busy ? 'waiting_for_build_pc' : 'failed',
        error: String(err.message).slice(-3000), updated_at: new Date(), ...(busy ? { retry_after: new Date(Date.now() + 60000) } : {}) } });
      console.error(currentJob, String(err.message).slice(-500));
    }
    currentJob = null;
  } else { await new Promise(resolve => setTimeout(resolve, 5000)); }
}
clearInterval(heartbeat);
await client.close();
