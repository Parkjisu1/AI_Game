// BalloonFlow 시뮬레이터 페이지 — 배치 분석 + 캔버스 리플레이 플레이어
(() => {
  const $ = id => document.getElementById(id);

  // ── 탭 ──────────────────────────────────────────────────────────────
  const tabs = { batch: [$('tabBatch'), $('panelBatch')], replay: [$('tabReplay'), $('panelReplay')] };
  function switchTab(name) {
    for (const [key, [btn, panel]] of Object.entries(tabs)) {
      const on = key === name;
      btn.classList.toggle('bg-gf-accent/15', on);
      btn.classList.toggle('text-gf-accent', on);
      btn.classList.toggle('text-zinc-400', !on);
      panel.classList.toggle('hidden', !on);
    }
  }
  $('tabBatch').onclick = () => switchTab('batch');
  $('tabReplay').onclick = () => switchTab('replay');

  // ── 레벨 목록 로드 (Git 데이터 기반) ─────────────────────────────────
  let levelMeta = [];
  async function loadLevels() {
    try {
      const res = await fetch('/api/sim/levels');
      if (res.status === 503) { $('localOnlyWarn').classList.remove('hidden'); return; }
      const data = await res.json();
      levelMeta = data.levels || [];
      if (data.git) {
        $('gitInfo').innerHTML =
          `<i class="fa-brands fa-git-alt mr-1"></i>레벨데이터 최종 커밋: ` +
          `<span class="text-zinc-300">${data.git.hash}</span> · ${(data.git.date || '').slice(0, 16)} · ${escapeHtml(data.git.subject || '')} ` +
          `<button onclick="location.reload()" class="ml-2 text-gf-accent hover:text-gf-accent2"><i class="fa-solid fa-rotate mr-0.5"></i>새로고침</button>`;
      }
      const sel = $('replayLevel');
      sel.innerHTML = levelMeta.map(l =>
        `<option value="${l.levelId}">L${l.levelId} — ${l.purpose} · ${l.numColors}색 · 풍선${l.balloonCount}` +
        `${l.gimmicks.length ? ' · ' + l.gimmicks.join(',') : ''}</option>`).join('');
    } catch (e) {
      $('gitInfo').textContent = '레벨 목록 로드 실패: ' + e.message;
    }
  }

  function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  // ── 배치 분석 ────────────────────────────────────────────────────────
  let pollTimer = null;
  let lastResults = null;

  $('batchRunBtn').onclick = async () => {
    const body = {
      levels: $('batchLevels').value.trim(),
      runs: parseInt($('batchRuns').value) || 50,
      policy: $('batchPolicy').value,
      seed: parseInt($('batchSeed').value) || 12345,
      continues: $('batchContinues').checked,
    };
    $('batchRunBtn').disabled = true;
    $('batchProgress').classList.remove('hidden');
    $('batchResults').classList.add('hidden');
    $('batchProgressBars').innerHTML = '';
    $('batchProgressText').textContent = '시작 중…';

    try {
      const res = await fetch('/api/sim/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (res.status === 503) { $('localOnlyWarn').classList.remove('hidden'); throw new Error('local-only'); }
      const { jobId } = await res.json();
      pollJob(jobId);
    } catch (e) {
      $('batchProgressText').textContent = '실패: ' + e.message;
      $('batchRunBtn').disabled = false;
    }
  };

  function pollJob(jobId) {
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      const job = await (await fetch(`/api/sim/job/${jobId}`)).json();
      renderProgress(job);
      if (job.status !== 'running') {
        clearInterval(pollTimer);
        $('batchRunBtn').disabled = false;
        if (job.status === 'done') {
          $('batchProgress').classList.add('hidden');
          renderResults(job.results, job.params);
        } else {
          $('batchProgressText').textContent = '오류: ' + (job.error || '알 수 없음');
        }
      }
    }, 1000);
  }

  function renderProgress(job) {
    $('batchProgressText').textContent = `${job.progress.length}개 레벨 완료 (${job.params.runs}회/레벨)`;
    $('batchProgressBars').innerHTML = job.progress.map(p => {
      const pct = Math.round(p.clearRate * 100);
      const color = pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500';
      return `<div class="flex items-center gap-2 text-xs">
        <span class="w-12 text-gf-muted">L${p.levelId}</span>
        <div class="flex-1 bg-gf-surface rounded h-4 overflow-hidden">
          <div class="${color} h-full transition-all" style="width:${pct}%"></div>
        </div>
        <span class="w-12 text-right ${pct < 50 ? 'text-red-400 font-bold' : 'text-zinc-300'}">${pct}%</span>
      </div>`;
    }).join('');
  }

  function renderResults(results, params) {
    lastResults = results;
    $('batchResults').classList.remove('hidden');

    const avg = results.reduce((s, r) => s + r.clearRate, 0) / Math.max(1, results.length);
    const below50 = results.filter(r => r.clearRate < 0.5);
    const worst = [...results].sort((a, b) => a.clearRate - b.clearRate)[0];
    const cards = [
      ['평균 클리어율', (avg * 100).toFixed(1) + '%', avg >= 0.8 ? 'text-green-400' : 'text-amber-400'],
      ['분석 레벨 수', `${results.length}개 × ${params.runs}회`, 'text-zinc-200'],
      ['점검 후보 (50%↓)', below50.length + '개', below50.length ? 'text-red-400' : 'text-green-400'],
      ['최난 레벨', worst ? `L${worst.levelId} (${(worst.clearRate * 100).toFixed(0)}%)` : '-', 'text-zinc-200'],
    ];
    $('batchSummaryCards').innerHTML = cards.map(([label, val, cls]) =>
      `<div class="bg-gf-card border border-gf-border rounded-xl p-3">
        <div class="text-[11px] text-gf-muted">${label}</div>
        <div class="text-lg font-bold ${cls}">${val}</div>
      </div>`).join('');

    $('batchTable').innerHTML = results.map(r => {
      const pct = Math.round(r.clearRate * 100);
      const barColor = pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500';
      const hard = r.difficultyScore >= 70;
      return `<tr class="border-b border-gf-border/50 ${hard ? 'bg-red-500/10' : ''}">
        <td class="py-1.5 pr-2 font-bold text-white">L${r.levelId}</td>
        <td class="pr-2 text-gf-muted">${r.purpose}</td>
        <td class="pr-2">${r.numColors}</td>
        <td class="pr-2">${r.balloonCount}</td>
        <td class="pr-2">${r.totalDarts}</td>
        <td class="pr-2">
          <div class="flex items-center gap-1.5">
            <div class="flex-1 bg-gf-surface rounded h-3 overflow-hidden min-w-[80px]">
              <div class="${barColor} h-full" style="width:${pct}%"></div>
            </div>
            <span class="w-10 text-right ${pct < 50 ? 'text-red-400 font-bold' : ''}">${pct}%</span>
          </div>
        </td>
        <td class="pr-2">
          <span class="text-red-400">${r.failRailOverflow}</span> /
          <span class="text-amber-400">${r.failNoMoves}</span> /
          <span class="text-purple-400">${r.failTimeout}</span>
        </td>
        <td class="pr-2">${r.avgClearTime ? r.avgClearTime + 's' : '-'}</td>
        <td class="pr-2">${Math.round(r.avgPeakOccupancy * 100)}%</td>
        <td class="pr-2 font-bold ${hard ? 'text-red-400' : 'text-zinc-300'}">${r.difficultyScore}</td>
        <td><button class="text-gf-accent hover:text-gf-accent2 text-[11px]" onclick="window.bfReplayLevel(${r.levelId})">
          <i class="fa-solid fa-circle-play mr-0.5"></i>보기</button></td>
      </tr>`;
    }).join('');
  }

  $('batchCsvBtn').onclick = () => {
    if (!lastResults) return;
    const cols = Object.keys(lastResults[0]);
    const csv = [cols.join(','), ...lastResults.map(r => cols.map(c => r[c]).join(','))].join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `bfsim_results_${Date.now()}.csv`;
    a.click();
  };

  // 결과 테이블에서 바로 리플레이 열기
  window.bfReplayLevel = (levelId) => {
    switchTab('replay');
    $('replayLevel').value = String(levelId);
    $('replayLoadBtn').click();
  };

  // ── 리플레이 플레이어 ────────────────────────────────────────────────
  let replay = null;          // 서버 JSON
  let balloonState = new Map(); // id → {x,z,c,mark,concealed,popped}
  let frameIdx = 0;
  let playing = false;
  let playAccum = 0;
  let lastTs = 0;
  let logRendered = 0;

  $('replayLoadBtn').onclick = async () => {
    $('replayStatus').textContent = '생성 중… (수 초 소요)';
    $('replayLoadBtn').disabled = true;
    try {
      const res = await fetch('/api/sim/replay', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          level: parseInt($('replayLevel').value) || 1,
          seed: parseInt($('replaySeed').value) || 12345,
          policy: $('replayPolicy').value,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).error || res.statusText);
      replay = await res.json();
      initPlayer();
      $('replayStatus').innerHTML = replay.result.cleared
        ? `<span class="text-green-400">클리어 (${replay.result.simTime}s)</span>`
        : `<span class="text-red-400">실패: ${replay.result.failReason} (${replay.result.simTime}s)</span>`;
    } catch (e) {
      $('replayStatus').textContent = '실패: ' + e.message;
    }
    $('replayLoadBtn').disabled = false;
  };

  function initPlayer() {
    $('replayPlayer').classList.remove('hidden');
    $('rpSeek').max = String(replay.frames.length - 1);
    $('rpLog').innerHTML = '';
    logRendered = 0;
    rebuildTo(0);
    playing = false;
    updatePlayBtn();
    resizeCanvas();
    render();
  }

  function resetBalloons() {
    balloonState = new Map();
    for (const [id, x, z, c, mark, concealed] of replay.balloons)
      balloonState.set(id, { x, z, c, mark, concealed: !!concealed, popped: false });
  }

  function applyFrame(f) {
    for (const id of f.pop) { const b = balloonState.get(id); if (b) b.popped = true; }
    for (const id of f.reveal) { const b = balloonState.get(id); if (b) b.concealed = false; }
    for (const [id, mark] of f.mark) { const b = balloonState.get(id); if (b) b.mark = mark; }
  }

  function rebuildTo(idx) {
    resetBalloons();
    for (let i = 0; i <= idx && i < replay.frames.length; i++) applyFrame(replay.frames[i]);
    frameIdx = Math.min(idx, replay.frames.length - 1);
  }

  function stepTo(idx) {
    idx = Math.max(0, Math.min(replay.frames.length - 1, idx));
    if (idx === frameIdx + 1) { frameIdx = idx; applyFrame(replay.frames[idx]); }
    else rebuildTo(idx);
    render();
  }

  function updatePlayBtn() {
    $('rpPlay').innerHTML = playing ? '<i class="fa-solid fa-pause"></i>' : '<i class="fa-solid fa-play"></i>';
  }

  $('rpPlay').onclick = () => { playing = !playing; lastTs = 0; updatePlayBtn(); if (playing) requestAnimationFrame(tick); };
  $('rpStepF').onclick = () => { playing = false; updatePlayBtn(); stepTo(frameIdx + 1); };
  $('rpStepB').onclick = () => { playing = false; updatePlayBtn(); stepTo(frameIdx - 1); };
  $('rpSeek').oninput = e => { playing = false; updatePlayBtn(); stepTo(parseInt(e.target.value)); };

  function tick(ts) {
    if (!playing || !replay) return;
    if (!lastTs) lastTs = ts;
    const dt = (ts - lastTs) / 1000;
    lastTs = ts;
    const speed = parseFloat($('rpSpeed').value);
    playAccum += dt * speed;
    while (playAccum >= 0.1) {   // 프레임 = 0.1s 간격
      playAccum -= 0.1;
      if (frameIdx >= replay.frames.length - 1) { playing = false; updatePlayBtn(); break; }
      frameIdx++;
      applyFrame(replay.frames[frameIdx]);
    }
    render();
    if (playing) requestAnimationFrame(tick);
  }

  // ── 캔버스 렌더 ──────────────────────────────────────────────────────
  const canvas = $('rpCanvas');
  const ctx = canvas.getContext('2d');

  function resizeCanvas() {
    const cssW = canvas.clientWidth || 600;
    const cssH = Math.round(cssW * 1.45);   // 세로 게임 비율 + 홀더 스트립
    const dpr = window.devicePixelRatio || 1;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    canvas.style.height = cssH + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener('resize', () => { if (replay) { resizeCanvas(); render(); } });

  function render() {
    if (!replay) return;
    const f = replay.frames[frameIdx];
    const W = canvas.clientWidth, H = canvas.clientHeight;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#14161c';
    ctx.fillRect(0, 0, W, H);

    const boardH = H * 0.72, holderY = H * 0.73;
    const w = replay.world;
    const scale = Math.min((W - 16) / (w.halfW * 2), (boardH - 16) / (w.halfH * 2));
    const ox = W / 2 - w.cx * scale;
    const oy = boardH / 2 + w.cz * scale;
    const X = x => ox + x * scale;
    const Y = z => oy - z * scale;

    // 레일
    ctx.strokeStyle = '#3a4150';
    ctx.lineWidth = Math.max(4, scale * 0.5);
    ctx.lineJoin = 'round';
    ctx.beginPath();
    replay.railPath.forEach(([x, z], i) => i ? ctx.lineTo(X(x), Y(z)) : ctx.moveTo(X(x), Y(z)));
    if (replay.closedLoop) ctx.closePath();
    ctx.stroke();

    // 풍선
    const r = Math.max(1.5, w.cell * scale * 0.48);
    const showMark = r >= 6;
    ctx.font = `bold ${Math.max(7, r * 0.9)}px Consolas, monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const b of balloonState.values()) {
      if (b.popped) continue;
      const px = X(b.x), py = Y(b.z);
      let fill = b.concealed ? '#5a5a64' : replay.palette[b.c] || '#f0f';
      if (b.mark.startsWith('I')) fill = '#96c8eb';
      ctx.fillStyle = fill;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
      const mark = b.concealed ? '?' : b.mark;
      if (mark && showMark) { ctx.fillStyle = '#000'; ctx.fillText(mark, px, py); }
    }

    // 레일 다트
    for (const [c, x, z, head] of f.darts) {
      ctx.fillStyle = replay.palette[c] || '#f0f';
      ctx.beginPath();
      ctx.arc(X(x), Y(z), 4, 0, Math.PI * 2);
      ctx.fill();
      if (head) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.2; ctx.stroke(); }
    }

    // 발사체
    for (const [c, x, z] of f.proj) {
      ctx.fillStyle = replay.palette[c] || '#f0f';
      ctx.beginPath();
      ctx.arc(X(x), Y(z), 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#fde047';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // 홀더 스트립
    ctx.fillStyle = '#1c1f27';
    ctx.fillRect(0, holderY, W, H - holderY);
    ctx.font = '10px Consolas, monospace';
    ctx.textAlign = 'left';
    const cols = f.holders.length;
    const colW = (W - 12) / Math.max(1, cols);
    for (const hc of f.holders) {
      const x0 = 6 + hc.col * colW;
      let y0 = holderY + 6;
      for (const [id, c, mag, state, tags] of hc.entries) {
        const fill = tags.includes('?') ? '#50505a' : (replay.palette[c] || '#888');
        ctx.fillStyle = fill;
        ctx.fillRect(x0, y0, colW - 6, 18);
        ctx.strokeStyle = '#000';
        ctx.strokeRect(x0, y0, colW - 6, 18);
        const bright = parseInt(fill.slice(1, 3), 16) * 0.4 + parseInt(fill.slice(3, 5), 16) * 0.5;
        ctx.fillStyle = bright > 110 ? '#000' : '#fff';
        const stateKo = state === 'deploy' ? '▶' : state === 'wait' ? '◇' : state === 'front' ? '' : '·';
        ctx.fillText(`${stateKo}c${c}×${mag}${tags}`, x0 + 3, y0 + 9, colW - 12);
        y0 += 21;
      }
      if (hc.more > 0) { ctx.fillStyle = '#71717a'; ctx.fillText(`+${hc.more}`, x0 + 3, y0 + 8); }
    }

    // 상단 정보/시크바 갱신
    const s = f.stat;
    const occPct = s.cap > 0 ? Math.round(s.occ / s.cap * 100) : 0;
    $('rpTime').textContent = `${f.t.toFixed(1)}s / ${replay.frames[replay.frames.length - 1].t.toFixed(1)}s`;
    $('rpSeek').value = String(frameIdx);
    $('rpStats').innerHTML = `
      <div class="text-sm font-bold text-white mb-2">L${replay.level.id} · ${replay.level.policy} · 시드 ${replay.level.seed}</div>
      <div class="space-y-1 text-xs text-zinc-300">
        <div>잔여 풍선 <b class="text-white">${s.remain}</b></div>
        <div>레일 점유 <b class="${occPct > 90 ? 'text-red-400' : occPct > 75 ? 'text-amber-400' : 'text-green-400'}">${s.occ}/${s.cap} (${occPct}%)</b></div>
        <div class="bg-gf-surface rounded h-2 overflow-hidden"><div class="h-full ${occPct > 90 ? 'bg-red-500' : occPct > 75 ? 'bg-amber-500' : 'bg-green-500'}" style="width:${Math.min(100, occPct)}%"></div></div>
        <div>발사 ${s.fired} · 헛발 ${s.wasted} · 남은 매거진 ${s.mag}</div>
        ${s.deadlock >= 0 ? `<div class="text-orange-400 font-bold">⚠ 데드락 모드 (홀더${s.deadlock})</div>` : ''}
        ${s.almost ? '<div class="text-green-400 font-bold">★ Almost There (1.8×)</div>' : ''}
      </div>`;
    $('rpColors').innerHTML = f.colors.map(([c, exp, sup]) => {
      const dead = sup > 0 && exp === 0;
      return `<div class="flex items-center gap-2 ${dead ? 'text-red-400' : 'text-zinc-300'}">
        <span class="w-3 h-3 rounded-sm inline-block border border-black/40" style="background:${replay.palette[c]}"></span>
        <span class="w-8">c${c}</span><span>노출 ${exp}</span><span>레일 ${sup}</span>${dead ? '<span>← 죽은 다트</span>' : ''}
      </div>`;
    }).join('');

    // 로그 (앞으로 재생 시에만 누적)
    if (frameIdx >= logRendered) {
      const logEl = $('rpLog');
      for (let i = logRendered; i <= frameIdx; i++)
        for (const line of replay.frames[i].log)
          logEl.insertAdjacentHTML('beforeend', `<div>[${replay.frames[i].t.toFixed(1)}s] ${escapeHtml(line)}</div>`);
      logRendered = frameIdx + 1;
      logEl.scrollTop = logEl.scrollHeight;
    }
  }

  loadLevels();
})();
