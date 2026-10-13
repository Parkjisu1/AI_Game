// BalloonFlow 시뮬레이터 연동 — 로컬 exe(spawn) 기반.
// GET  /api/sim/levels           레벨 목록 + 메타 (git EditorData/Episodes 실시간 파싱)
// POST /api/sim/run              배치 시뮬 잡 시작 {levels, runs, policy, seed, continues} → {jobId}
// GET  /api/sim/job/:id          잡 진행률/결과 폴링
// POST /api/sim/replay           1회 리플레이 실행 {level, seed, policy} → 리플레이 JSON
const express = require('express');
const { spawn, execFile } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const router = express.Router();

const SIM_EXE = process.env.BF_SIM_EXE || 'E:\\AI_Simualator\\publish\\BalloonFlowSim.exe';
const EPISODES_DIR = process.env.BF_EPISODES_DIR
  || 'E:\\Balloonflow\\BallonFlow_Git\\BalloonFlow\\Assets\\EditorData\\Episodes';
const GIT_REPO = process.env.BF_GIT_REPO || 'E:\\Balloonflow\\BallonFlow_Git';

const PURPOSE_NAMES = ['Tutorial', 'Normal', 'Hard', 'SuperHard', 'Rest', 'Intro'];

function simAvailable() {
  return fs.existsSync(SIM_EXE) && fs.existsSync(EPISODES_DIR);
}

// ── 레벨 목록 (Git 데이터 실시간) ──────────────────────────────────────────
let levelCache = { mtimeKey: '', levels: [] };

router.get('/levels', (req, res) => {
  if (!simAvailable()) {
    return res.status(503).json({ error: 'local-only', message: '시뮬레이터 exe/레벨데이터를 찾을 수 없음 (로컬 PC 전용 기능)' });
  }
  try {
    const files = fs.readdirSync(EPISODES_DIR).filter(f => /^episode_\d+\.json$/.test(f)).sort();
    const mtimeKey = files.map(f => {
      const st = fs.statSync(path.join(EPISODES_DIR, f));
      return `${f}:${st.mtimeMs}`;
    }).join('|');

    if (levelCache.mtimeKey !== mtimeKey) {
      const levels = [];
      for (const f of files) {
        const ep = JSON.parse(fs.readFileSync(path.join(EPISODES_DIR, f), 'utf8'));
        const mtime = fs.statSync(path.join(EPISODES_DIR, f)).mtime;
        for (const lv of ep.levels || []) {
          const gimmicks = new Set(lv.gimmickTypes || []);
          for (const h of lv.holders || []) if (h.queueGimmick) gimmicks.add(h.queueGimmick);
          for (const b of lv.balloons || []) if (b.gimmickType) gimmicks.add(b.gimmickType);
          levels.push({
            levelId: lv.levelId,
            purpose: PURPOSE_NAMES[lv.difficultyPurpose] || String(lv.difficultyPurpose),
            numColors: lv.numColors,
            balloonCount: lv.balloonCount,
            totalDarts: (lv.holders || []).reduce((s, h) => s + (h.magazineCount || 0), 0),
            queueColumns: lv.queueColumns,
            railCapacity: lv.railCapacity,
            gimmicks: [...gimmicks],
            episodeFile: f,
            fileMtime: mtime,
          });
        }
      }
      levels.sort((a, b) => a.levelId - b.levelId);
      levelCache = { mtimeKey, levels };
    }

    // 레벨데이터 최종 커밋 정보 (실패해도 무시)
    execFile('git', ['-C', GIT_REPO, 'log', '-1', '--format=%h|%ci|%s', '--',
      'BalloonFlow/Assets/EditorData/Episodes'], { timeout: 5000 }, (err, stdout) => {
      let git = null;
      if (!err && stdout.trim()) {
        const [hash, date, subject] = stdout.trim().split('|');
        git = { hash, date, subject };
      }
      res.json({ levels: levelCache.levels, git, episodesDir: EPISODES_DIR });
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── 배치 시뮬 잡 ─────────────────────────────────────────────────────────────
const jobs = new Map();   // jobId → {status, progress[], results, error, startedAt}
let jobSeq = 0;

router.post('/run', (req, res) => {
  if (!simAvailable()) return res.status(503).json({ error: 'local-only' });
  const { levels = '1-20', runs = 50, policy = 'smart', seed = 12345, continues = false } = req.body || {};
  if (!/^[\d,\-\s]+$/.test(String(levels))) return res.status(400).json({ error: 'levels 형식 오류' });
  const runsN = Math.min(500, Math.max(1, parseInt(runs) || 50));

  const jobId = `job_${Date.now()}_${++jobSeq}`;
  const jsonOut = path.join(os.tmpdir(), `bfsim_${jobId}.json`);
  const job = { status: 'running', progress: [], results: null, error: null, startedAt: Date.now(),
    params: { levels, runs: runsN, policy, seed } };
  jobs.set(jobId, job);

  const args = ['--levels', String(levels), '--runs', String(runsN), '--policy', String(policy),
    '--seed', String(seed), '--json', jsonOut, '--episodes', EPISODES_DIR];
  if (continues) args.push('--continues');

  const proc = spawn(SIM_EXE, args, { windowsHide: true });
  let buffer = '';
  proc.stdout.on('data', chunk => {
    buffer += chunk.toString();
    let idx;
    while ((idx = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      // "L  16 | clear  70.0% | time ..." 진행 라인 파싱
      const m = line.match(/^L\s*(\d+)\s*\|\s*clear\s*([\d.]+)%.*?fail\(RO\/NM\/TO\)\s*(\d+)\/(\d+)\/(\d+)/);
      if (m) {
        job.progress.push({
          levelId: parseInt(m[1]), clearRate: parseFloat(m[2]) / 100,
          failRO: parseInt(m[3]), failNM: parseInt(m[4]), failTO: parseInt(m[5]),
        });
      }
    }
  });
  proc.on('error', err => { job.status = 'error'; job.error = String(err); });
  proc.on('close', code => {
    if (job.status === 'error') return;
    try {
      if (fs.existsSync(jsonOut)) {
        job.results = JSON.parse(fs.readFileSync(jsonOut, 'utf8'));
        fs.unlinkSync(jsonOut);
        job.status = 'done';
      } else {
        job.status = 'error';
        job.error = `결과 파일 없음 (exit ${code})`;
      }
    } catch (e) {
      job.status = 'error';
      job.error = e.message;
    }
  });

  // 오래된 잡 정리 (30분)
  for (const [id, j] of jobs) {
    if (Date.now() - j.startedAt > 30 * 60 * 1000) jobs.delete(id);
  }
  res.json({ jobId });
});

router.get('/job/:id', (req, res) => {
  const job = jobs.get(req.params.id);
  if (!job) return res.status(404).json({ error: 'job not found' });
  res.json(job);
});

// ── 리플레이 (1회 실행 → 프레임 JSON) ────────────────────────────────────────
router.post('/replay', (req, res) => {
  if (!simAvailable()) return res.status(503).json({ error: 'local-only' });
  const { level = 1, seed = 12345, policy = 'smart', continues = false } = req.body || {};
  const lv = Math.min(300, Math.max(1, parseInt(level) || 1));
  const outFile = path.join(os.tmpdir(), `bfreplay_${Date.now()}_${++jobSeq}.json`);

  const args = ['--levels', String(lv), '--seed', String(parseInt(seed) || 12345),
    '--policy', String(policy), '--replay', outFile, '--episodes', EPISODES_DIR];
  if (continues) args.push('--continues');

  execFile(SIM_EXE, args, { timeout: 180000, windowsHide: true, maxBuffer: 10 * 1024 * 1024 }, (err) => {
    if (err || !fs.existsSync(outFile)) {
      return res.status(500).json({ error: '리플레이 생성 실패', detail: err ? String(err) : 'no output' });
    }
    res.setHeader('Content-Type', 'application/json');
    fs.createReadStream(outFile).pipe(res).on('close', () => {
      try { fs.unlinkSync(outFile); } catch { /* 무시 */ }
    });
  });
});

module.exports = router;
