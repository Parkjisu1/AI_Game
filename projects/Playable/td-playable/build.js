const fs = require('fs');
const TMP = process.env.TEMP || process.env.TMP;
const coinB64 = fs.readFileSync(TMP + '/slg_coin.b64', 'utf8').trim();

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="ad.size" content="width=320,height=480">
<title>Tower Defense - Play Now!</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#87CEEB;touch-action:none;user-select:none;-webkit-user-select:none}
canvas{display:block;position:absolute;top:0;left:0}
#cta{display:none;position:absolute;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.82);z-index:10;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#cta.show{display:flex}
#cta-title{font-family:'Segoe UI',Arial,sans-serif;font-size:34px;font-weight:bold;margin-bottom:6px;text-shadow:0 3px 12px rgba(0,0,0,0.4)}
#cta-sub{color:#fff;font-family:'Segoe UI',Arial,sans-serif;font-size:15px;margin-bottom:28px;opacity:0.85}
#cta-btn{background:linear-gradient(135deg,#4CAF50,#2E7D32);color:#fff;border:none;padding:18px 52px;font-size:22px;font-weight:bold;border-radius:50px;cursor:pointer;animation:pulse 1.4s infinite;font-family:'Segoe UI',Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;box-shadow:0 4px 20px rgba(76,175,80,0.5)}
#cta-btn:active{transform:scale(0.95)}
#cta-retry{color:#aaa;font-family:'Segoe UI',Arial,sans-serif;font-size:13px;margin-top:16px;cursor:pointer;text-decoration:underline}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}
</style>
</head>
<body>
<canvas id="gc"></canvas>
<div id="cta">
  <div id="cta-title"></div>
  <div id="cta-sub"></div>
  <button id="cta-btn" onclick="window.open('https://play.google.com/store','_blank')">INSTALL FREE</button>
  <div id="cta-retry" onclick="restart()">Play again</div>
</div>
<script>
'use strict';

// ===== POLYFILL: roundRect for older browsers/WebViews =====
if (!CanvasRenderingContext2D.prototype.roundRect) {
  CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
    if (typeof r === 'number') r = [r, r, r, r];
    else if (!Array.isArray(r)) r = [0, 0, 0, 0];
    const [tl, tr, br, bl] = r;
    this.moveTo(x + tl, y);
    this.lineTo(x + w - tr, y);
    this.arcTo(x + w, y, x + w, y + tr, tr);
    this.lineTo(x + w, y + h - br);
    this.arcTo(x + w, y + h, x + w - br, y + h, br);
    this.lineTo(x + bl, y + h);
    this.arcTo(x, y + h, x, y + h - bl, bl);
    this.lineTo(x, y + tl);
    this.arcTo(x, y, x + tl, y, tl);
    this.closePath();
    return this;
  };
}

// ===== ASSET =====
const coinImg = new Image();
let coinLoaded = false;
coinImg.onload = () => { coinLoaded = true; };
coinImg.src = 'data:image/png;base64,${coinB64}';

// ===== CANVAS =====
const cv = document.getElementById('gc'), cx = cv.getContext('2d');
let W, H, sc, mapOffY;

function resize() {
  W = cv.width = innerWidth;
  H = cv.height = innerHeight;
  sc = Math.min(W / 420, H / 780);
  mapOffY = 45 * sc;
  buildPath();
  buildSlots();
}
resize();
addEventListener('resize', resize);

// ===== PATH (S-curve) =====
// Path defined as grid cells (cellSize based on screen)
const CELL = 38; // base cell size
let cellSz, pathPoints = [], pathLen;

function buildPath() {
  cellSz = CELL * sc;
  // Define path waypoints as grid coords, then convert to pixels
  const waypoints = [
    [-1, 2], [2, 2], [3, 2], [5, 2], [7, 2], [8, 2], [8, 3], [8, 4], [8, 5],
    [7, 5], [5, 5], [3, 5], [2, 5], [2, 6], [2, 7], [2, 8],
    [3, 8], [5, 8], [7, 8], [8, 8], [8, 9], [8, 10], [8, 11],
    [7, 11], [5, 11], [3, 11], [2, 11], [2, 12], [2, 13], [2, 14], [5, 14], [8, 14], [11, 14]
  ];
  const ox = W * 0.08, oy = mapOffY + 15 * sc;
  pathPoints = waypoints.map(([c, r]) => ({
    x: ox + c * cellSz,
    y: oy + r * cellSz
  }));
  // Calc total path length
  pathLen = 0;
  for (let i = 1; i < pathPoints.length; i++) {
    const dx = pathPoints[i].x - pathPoints[i-1].x;
    const dy = pathPoints[i].y - pathPoints[i-1].y;
    pathLen += Math.sqrt(dx*dx + dy*dy);
  }
}

function getPosOnPath(t) {
  // t = 0..1 along path
  const targetDist = t * pathLen;
  let accum = 0;
  for (let i = 1; i < pathPoints.length; i++) {
    const dx = pathPoints[i].x - pathPoints[i-1].x;
    const dy = pathPoints[i].y - pathPoints[i-1].y;
    const segLen = Math.sqrt(dx*dx + dy*dy);
    if (accum + segLen >= targetDist) {
      const frac = (targetDist - accum) / segLen;
      return {
        x: pathPoints[i-1].x + dx * frac,
        y: pathPoints[i-1].y + dy * frac
      };
    }
    accum += segLen;
  }
  return pathPoints[pathPoints.length - 1];
}

// ===== TOWER SLOTS =====
let slots = [];

function buildSlots() {
  const ox = W * 0.08, oy = mapOffY + 15 * sc;
  // Manually placed slots adjacent to path bends
  const slotCoords = [
    [1,1],[4,1],[6,1],  // top row
    [6,3],[4,4],[0,4],  // mid-top
    [4,6],[7,7],[0,6],  // mid
    [4,9],[6,10],[0,9], // mid-bottom
    [4,12],[7,13],[0,12] // bottom
  ];
  slots = slotCoords.map(([c, r]) => ({
    x: ox + c * cellSz + cellSz / 2,
    y: oy + r * cellSz + cellSz / 2,
    tower: null,
    radius: cellSz * 0.55
  }));
}

// ===== GAME CONFIG =====
const TOWER = {
  arrow:  { cost: 5, range: 90, dmg: 8,  rate: 30, color: '#42A5F5', name: 'Arrow',  projColor: '#1565C0', projSpeed: 6 },
  magic:  { cost: 8, range: 80, dmg: 5,  rate: 25, color: '#AB47BC', name: 'Magic',  projColor: '#7B1FA2', projSpeed: 4, splash: 40 },
  cannon: { cost: 10, range: 100, dmg: 25, rate: 70, color: '#FF7043', name: 'Cannon', projColor: '#BF360C', projSpeed: 3.5, splash: 30 }
};

const WAVES = [
  // wave 1: light slimes
  { enemies: Array(6).fill(null).map((_,i) => ({ type: 'slime', delay: i * 40 })) },
  // wave 2: mixed
  { enemies: [
    ...Array(4).fill(null).map((_,i) => ({ type: 'slime', delay: i * 35 })),
    ...Array(3).fill(null).map((_,i) => ({ type: 'knight', delay: 160 + i * 50 }))
  ]},
  // wave 3: boss wave
  { enemies: [
    ...Array(3).fill(null).map((_,i) => ({ type: 'knight', delay: i * 40 })),
    { type: 'boss', delay: 180 }
  ]}
];

const ENEMY = {
  slime:  { hp: 40, speed: 0.0012, radius: 10, color: '#66BB6A', reward: 3, name: 'Slime' },
  knight: { hp: 90, speed: 0.0009, radius: 13, color: '#5C6BC0', reward: 5, name: 'Knight' },
  boss:   { hp: 300, speed: 0.0006, radius: 20, color: '#EF5350', reward: 15, name: 'Boss' }
};

// ===== STATE =====
let coins, lives, wave, waveTimer, waveActive, waveIdx;
let enemies, projectiles, particles, placedTowers;
let dragType, dragX, dragY, dragging;
let gameOver, won, frame, phase;
let tutHint;
// phase: 'place' | 'wave' | 'between' | 'done'

function init() {
  coins = 20;
  lives = 5;
  wave = 0;
  waveTimer = 0;
  waveActive = false;
  waveIdx = 0;
  enemies = [];
  projectiles = [];
  particles = [];
  placedTowers = [];
  dragging = false;
  dragType = null;
  gameOver = false;
  won = false;
  frame = 0;
  phase = 'place';
  tutHint = true;
  buildPath();
  buildSlots();
  for (const s of slots) s.tower = null;
  document.getElementById('cta').classList.remove('show');
}

// ===== INPUT =====
function getP(e) {
  if (e.changedTouches) return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY };
  return { x: e.clientX, y: e.clientY };
}

function onDown(e) {
  e.preventDefault();
  if (gameOver) return;
  const p = getP(e);

  // Check START WAVE button
  if (phase === 'place' || phase === 'between') {
    const sb = getStartBtn();
    if (p.x >= sb.x && p.x <= sb.x + sb.w && p.y >= sb.y && p.y <= sb.y + sb.h) {
      startWave();
      return;
    }
  }

  // Check tray
  if (phase === 'place' || phase === 'between') {
    const tray = getTray();
    for (const t of tray) {
      if (p.x >= t.x && p.x <= t.x + t.w && p.y >= t.y && p.y <= t.y + t.h && coins >= TOWER[t.type].cost) {
        dragging = true;
        dragType = t.type;
        dragX = p.x;
        dragY = p.y;
        tutHint = false;
        return;
      }
    }
  }
}

function onMove(e) {
  e.preventDefault();
  if (dragging) { const p = getP(e); dragX = p.x; dragY = p.y; }
}

function onUp(e) {
  e.preventDefault();
  if (!dragging) return;
  // Find nearest empty slot
  let bestSlot = null, bestDist = 50 * sc;
  for (const s of slots) {
    if (s.tower) continue;
    const dx = dragX - s.x, dy = dragY - s.y;
    const d = Math.sqrt(dx*dx + dy*dy);
    if (d < bestDist) { bestDist = d; bestSlot = s; }
  }
  if (bestSlot && coins >= TOWER[dragType].cost) {
    coins -= TOWER[dragType].cost;
    const def = TOWER[dragType];
    bestSlot.tower = {
      type: dragType,
      x: bestSlot.x,
      y: bestSlot.y,
      range: def.range * sc,
      dmg: def.dmg,
      rate: def.rate,
      color: def.color,
      projColor: def.projColor,
      projSpeed: def.projSpeed * sc,
      splash: def.splash ? def.splash * sc : 0,
      timer: 0,
      angle: 0
    };
    placedTowers.push(bestSlot.tower);
  }
  dragging = false;
  dragType = null;
}

cv.addEventListener('mousedown', onDown);
cv.addEventListener('mousemove', onMove);
cv.addEventListener('mouseup', onUp);
cv.addEventListener('touchstart', onDown, { passive: false });
cv.addEventListener('touchmove', onMove, { passive: false });
cv.addEventListener('touchend', onUp, { passive: false });

// ===== UI AREAS =====
function getTray() {
  const trayY = H - 88 * sc;
  const tw = 88 * sc, th = 75 * sc, gap = 10 * sc;
  const total = 3 * tw + 2 * gap;
  const sx = (W - total) / 2;
  return ['arrow', 'magic', 'cannon'].map((t, i) => ({
    type: t, x: sx + i * (tw + gap), y: trayY, w: tw, h: th
  }));
}

function getStartBtn() {
  return { x: W / 2 - 60 * sc, y: H - 100 * sc - 44 * sc, w: 120 * sc, h: 36 * sc };
}

// ===== WAVE LOGIC =====
function startWave() {
  if (wave >= WAVES.length) return;
  phase = 'wave';
  waveActive = true;
  waveTimer = 0;
  waveIdx = 0;
}

function updateWave() {
  if (!waveActive) return;
  const w = WAVES[wave];
  waveTimer++;

  // Spawn enemies based on delay
  while (waveIdx < w.enemies.length && waveTimer >= w.enemies[waveIdx].delay) {
    const eDef = w.enemies[waveIdx];
    const base = ENEMY[eDef.type];
    enemies.push({
      type: eDef.type,
      t: 0, // position on path 0..1
      hp: base.hp,
      maxHp: base.hp,
      speed: base.speed,
      radius: base.radius * sc,
      color: base.color,
      reward: base.reward,
      x: 0, y: 0,
      dead: false,
      reached: false,
      hitFlash: 0
    });
    waveIdx++;
  }

  // Move enemies
  for (const en of enemies) {
    if (en.dead || en.reached) continue;
    en.t += en.speed;
    const pos = getPosOnPath(en.t);
    en.x = pos.x;
    en.y = pos.y;
    if (en.hitFlash > 0) en.hitFlash--;

    if (en.t >= 1) {
      en.reached = true;
      lives--;
      spawnParticles(en.x, en.y, '#F44336', 8);
      if (lives <= 0) {
        gameOver = true;
        won = false;
        setTimeout(showResult, 600);
      }
    }
  }

  // Tower targeting
  for (const tw of placedTowers) {
    tw.timer++;
    if (tw.timer < tw.rate) continue;

    // Find nearest enemy in range
    let best = null, bestD = tw.range;
    for (const en of enemies) {
      if (en.dead || en.reached) continue;
      const dx = en.x - tw.x, dy = en.y - tw.y;
      const d = Math.sqrt(dx*dx + dy*dy);
      if (d < bestD) { bestD = d; best = en; }
    }

    if (best) {
      tw.timer = 0;
      tw.angle = Math.atan2(best.y - tw.y, best.x - tw.x);
      projectiles.push({
        x: tw.x, y: tw.y - 10 * sc,
        tx: best.x, ty: best.y,
        target: best,
        speed: tw.projSpeed,
        dmg: tw.dmg,
        color: tw.projColor,
        splash: tw.splash,
        size: tw.splash > 0 ? 5 * sc : 3 * sc
      });
    }
  }

  // Update projectiles
  for (let i = projectiles.length - 1; i >= 0; i--) {
    const p = projectiles[i];
    // Track moving target
    if (p.target && !p.target.dead && !p.target.reached) {
      p.tx = p.target.x;
      p.ty = p.target.y;
    }
    const dx = p.tx - p.x, dy = p.ty - p.y;
    const d = Math.sqrt(dx*dx + dy*dy);
    if (d < p.speed + 2) {
      // Hit
      if (p.splash > 0) {
        // Splash damage
        for (const en of enemies) {
          if (en.dead || en.reached) continue;
          const sdx = en.x - p.tx, sdy = en.y - p.ty;
          if (Math.sqrt(sdx*sdx + sdy*sdy) < p.splash) {
            en.hp -= p.dmg;
            en.hitFlash = 8;
            if (en.hp <= 0) { en.dead = true; coins += en.reward; }
          }
        }
        spawnParticles(p.tx, p.ty, p.color, 12);
      } else {
        if (p.target && !p.target.dead) {
          p.target.hp -= p.dmg;
          p.target.hitFlash = 6;
          if (p.target.hp <= 0) { p.target.dead = true; coins += p.target.reward; }
        }
        spawnParticles(p.tx, p.ty, p.color, 6);
      }
      projectiles.splice(i, 1);
    } else {
      p.x += dx / d * p.speed;
      p.y += dy / d * p.speed;
    }
  }

  // Particles
  for (let i = particles.length - 1; i >= 0; i--) {
    const pt = particles[i];
    pt.x += pt.vx;
    pt.y += pt.vy;
    pt.vy += 0.08;
    pt.life -= pt.decay;
    if (pt.life <= 0) particles.splice(i, 1);
  }

  // Check wave complete
  const allSpawned = waveIdx >= w.enemies.length;
  const allDone = enemies.every(en => en.dead || en.reached);
  if (allSpawned && allDone && !gameOver) {
    wave++;
    if (wave >= WAVES.length) {
      gameOver = true;
      won = true;
      setTimeout(showResult, 600);
    } else {
      phase = 'between';
      waveActive = false;
    }
  }
}

function spawnParticles(x, y, color, count) {
  for (let i = 0; i < count; i++) {
    particles.push({
      x, y,
      vx: (Math.random() - 0.5) * 4,
      vy: (Math.random() - 0.5) * 4 - 1.5,
      life: 1,
      decay: 0.03 + Math.random() * 0.02,
      size: 2 + Math.random() * 3,
      color
    });
  }
}

function showResult() {
  const el = document.getElementById('cta');
  const title = document.getElementById('cta-title');
  const sub = document.getElementById('cta-sub');
  if (won) {
    title.textContent = 'VICTORY!';
    title.style.color = '#FFD700';
    sub.textContent = 'You defended the kingdom!  Can you beat harder levels?';
  } else {
    title.textContent = 'GAME OVER';
    title.style.color = '#EF5350';
    sub.textContent = 'The enemies broke through!  Try the full game!';
  }
  el.classList.add('show');
}

function restart() { init(); }

// ===== DRAW FUNCTIONS =====

function drawSky() {
  const g = cx.createLinearGradient(0, 0, 0, H * 0.5);
  g.addColorStop(0, '#87CEEB');
  g.addColorStop(1, '#E0F7FA');
  cx.fillStyle = g;
  cx.fillRect(0, 0, W, H);
  // Ground
  const gg = cx.createLinearGradient(0, H * 0.3, 0, H);
  gg.addColorStop(0, '#81C784');
  gg.addColorStop(0.3, '#66BB6A');
  gg.addColorStop(1, '#4CAF50');
  cx.fillStyle = gg;
  cx.fillRect(0, mapOffY, W, H - mapOffY);
}

function drawClouds() {
  cx.fillStyle = 'rgba(255,255,255,0.6)';
  const t = frame * 0.15;
  for (let i = 0; i < 4; i++) {
    const cx_ = ((t + i * 200) % (W + 200)) - 80;
    const cy_ = 12 + i * 12 * sc;
    const cw = 60 + i * 15;
    cx.beginPath();
    cx.ellipse(cx_, cy_, cw * sc * 0.5, 12 * sc, 0, 0, Math.PI * 2);
    cx.fill();
    cx.beginPath();
    cx.ellipse(cx_ - 20 * sc, cy_ - 4 * sc, cw * sc * 0.35, 10 * sc, 0, 0, Math.PI * 2);
    cx.fill();
    cx.beginPath();
    cx.ellipse(cx_ + 18 * sc, cy_ - 2 * sc, cw * sc * 0.3, 9 * sc, 0, 0, Math.PI * 2);
    cx.fill();
  }
}

function drawPath() {
  if (pathPoints.length < 2) return;
  // Path shadow
  cx.strokeStyle = 'rgba(0,0,0,0.1)';
  cx.lineWidth = cellSz * 0.95;
  cx.lineCap = 'round';
  cx.lineJoin = 'round';
  cx.beginPath();
  cx.moveTo(pathPoints[0].x, pathPoints[0].y + 3 * sc);
  for (let i = 1; i < pathPoints.length; i++) cx.lineTo(pathPoints[i].x, pathPoints[i].y + 3 * sc);
  cx.stroke();

  // Main path
  cx.strokeStyle = '#D7CCC8';
  cx.lineWidth = cellSz * 0.85;
  cx.beginPath();
  cx.moveTo(pathPoints[0].x, pathPoints[0].y);
  for (let i = 1; i < pathPoints.length; i++) cx.lineTo(pathPoints[i].x, pathPoints[i].y);
  cx.stroke();

  // Path center line
  cx.strokeStyle = '#BCAAA4';
  cx.lineWidth = cellSz * 0.6;
  cx.beginPath();
  cx.moveTo(pathPoints[0].x, pathPoints[0].y);
  for (let i = 1; i < pathPoints.length; i++) cx.lineTo(pathPoints[i].x, pathPoints[i].y);
  cx.stroke();

  // Dashed center
  cx.setLineDash([6 * sc, 8 * sc]);
  cx.strokeStyle = 'rgba(255,255,255,0.25)';
  cx.lineWidth = 2 * sc;
  cx.beginPath();
  cx.moveTo(pathPoints[0].x, pathPoints[0].y);
  for (let i = 1; i < pathPoints.length; i++) cx.lineTo(pathPoints[i].x, pathPoints[i].y);
  cx.stroke();
  cx.setLineDash([]);

  // Start / End markers
  const startP = pathPoints[0], endP = pathPoints[pathPoints.length - 1];
  // Start flag
  cx.fillStyle = '#4CAF50';
  cx.beginPath();
  cx.arc(startP.x, startP.y, 8 * sc, 0, Math.PI * 2);
  cx.fill();
  cx.fillStyle = '#fff';
  cx.font = 'bold ' + (10 * sc) + 'px sans-serif';
  cx.textAlign = 'center';
  cx.fillText('S', startP.x, startP.y + 4 * sc);

  // End (base to defend)
  cx.fillStyle = '#F44336';
  cx.beginPath();
  cx.arc(endP.x, endP.y, 10 * sc, 0, Math.PI * 2);
  cx.fill();
  // Heart icon
  cx.fillStyle = '#fff';
  cx.font = (12 * sc) + 'px sans-serif';
  cx.fillText('\\u2665', endP.x, endP.y + 4 * sc);
  cx.textAlign = 'left';
}

function drawSlots() {
  for (const s of slots) {
    if (s.tower) continue;
    // Empty slot - dashed circle
    cx.strokeStyle = 'rgba(255,255,255,0.5)';
    cx.lineWidth = 2 * sc;
    cx.setLineDash([4 * sc, 3 * sc]);
    cx.beginPath();
    cx.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
    cx.stroke();
    cx.setLineDash([]);

    // Plus icon
    cx.fillStyle = 'rgba(255,255,255,0.3)';
    cx.fillRect(s.x - 5 * sc, s.y - 1.5 * sc, 10 * sc, 3 * sc);
    cx.fillRect(s.x - 1.5 * sc, s.y - 5 * sc, 3 * sc, 10 * sc);
  }
}

function drawTowerShape(x, y, type, color, angle) {
  const sz = 14 * sc;
  cx.save();
  cx.translate(x, y);

  // Shadow
  cx.fillStyle = 'rgba(0,0,0,0.15)';
  cx.beginPath();
  cx.ellipse(0, 6 * sc, sz * 0.8, 4 * sc, 0, 0, Math.PI * 2);
  cx.fill();

  if (type === 'arrow') {
    // Blue tower - cylinder with pointed top
    cx.fillStyle = color;
    cx.fillRect(-sz * 0.4, -sz * 1.1, sz * 0.8, sz * 1.2);
    // Darker edge
    cx.fillStyle = '#1E88E5';
    cx.fillRect(-sz * 0.4, -sz * 1.1, sz * 0.2, sz * 1.2);
    // Pointed top
    cx.fillStyle = '#0D47A1';
    cx.beginPath();
    cx.moveTo(-sz * 0.5, -sz * 1.1);
    cx.lineTo(0, -sz * 1.7);
    cx.lineTo(sz * 0.5, -sz * 1.1);
    cx.closePath();
    cx.fill();
    // Window
    cx.fillStyle = '#BBDEFB';
    cx.fillRect(-sz * 0.15, -sz * 0.7, sz * 0.3, sz * 0.35);
    // Arrow pointing at target
    cx.strokeStyle = '#FFD54F';
    cx.lineWidth = 2 * sc;
    cx.beginPath();
    cx.moveTo(0, -sz * 0.5);
    cx.lineTo(Math.cos(angle) * sz * 0.8, -sz * 0.5 + Math.sin(angle) * sz * 0.8);
    cx.stroke();
  }
  else if (type === 'magic') {
    // Purple crystal tower
    cx.fillStyle = color;
    cx.beginPath();
    cx.moveTo(-sz * 0.45, 0);
    cx.lineTo(-sz * 0.3, -sz * 1.3);
    cx.lineTo(0, -sz * 1.7);
    cx.lineTo(sz * 0.3, -sz * 1.3);
    cx.lineTo(sz * 0.45, 0);
    cx.closePath();
    cx.fill();
    // Inner glow
    cx.fillStyle = '#CE93D8';
    cx.beginPath();
    cx.moveTo(-sz * 0.2, -sz * 0.2);
    cx.lineTo(-sz * 0.15, -sz * 1.0);
    cx.lineTo(0, -sz * 1.3);
    cx.lineTo(sz * 0.15, -sz * 1.0);
    cx.lineTo(sz * 0.2, -sz * 0.2);
    cx.closePath();
    cx.fill();
    // Sparkle on top
    const sparkle = 0.5 + 0.5 * Math.sin(frame * 0.1);
    cx.globalAlpha = sparkle;
    cx.fillStyle = '#E1BEE7';
    cx.beginPath();
    cx.arc(0, -sz * 1.7, 3 * sc, 0, Math.PI * 2);
    cx.fill();
    cx.globalAlpha = 1;
  }
  else if (type === 'cannon') {
    // Orange chunky tower
    cx.fillStyle = color;
    cx.fillRect(-sz * 0.5, -sz * 0.9, sz, sz);
    // Darker top
    cx.fillStyle = '#E64A19';
    cx.fillRect(-sz * 0.55, -sz * 0.95, sz * 1.1, sz * 0.25);
    // Barrel
    cx.fillStyle = '#4E342E';
    cx.save();
    cx.translate(0, -sz * 0.5);
    cx.rotate(angle);
    cx.fillRect(0, -3 * sc, sz * 0.9, 6 * sc);
    // Barrel tip
    cx.fillStyle = '#3E2723';
    cx.fillRect(sz * 0.7, -4 * sc, sz * 0.2, 8 * sc);
    cx.restore();
    // Detail
    cx.fillStyle = '#FFAB91';
    cx.fillRect(-sz * 0.2, -sz * 0.6, sz * 0.15, sz * 0.3);
  }

  cx.restore();
}

function drawTowers() {
  for (const s of slots) {
    if (!s.tower) continue;
    const tw = s.tower;
    drawTowerShape(tw.x, tw.y, tw.type, tw.color, tw.angle);

    // Range indicator while dragging
    if (dragging) {
      cx.globalAlpha = 0.08;
      cx.fillStyle = tw.color;
      cx.beginPath();
      cx.arc(tw.x, tw.y, tw.range, 0, Math.PI * 2);
      cx.fill();
      cx.globalAlpha = 1;
    }
  }
}

function drawEnemyShape(en) {
  if (en.dead || en.reached) return;
  const r = en.radius;

  // Hit flash
  if (en.hitFlash > 0) {
    cx.globalAlpha = 0.6;
    cx.fillStyle = '#fff';
    cx.beginPath();
    cx.arc(en.x, en.y, r * 1.4, 0, Math.PI * 2);
    cx.fill();
    cx.globalAlpha = 1;
  }

  // Shadow
  cx.fillStyle = 'rgba(0,0,0,0.12)';
  cx.beginPath();
  cx.ellipse(en.x, en.y + r * 0.5, r * 0.8, r * 0.3, 0, 0, Math.PI * 2);
  cx.fill();

  if (en.type === 'slime') {
    // Cute green blob
    const bounce = Math.abs(Math.sin(frame * 0.08 + en.t * 20)) * 3 * sc;
    cx.fillStyle = en.color;
    cx.beginPath();
    cx.ellipse(en.x, en.y - bounce, r, r * 0.85, 0, 0, Math.PI * 2);
    cx.fill();
    // Highlight
    cx.fillStyle = '#A5D6A7';
    cx.beginPath();
    cx.ellipse(en.x - r * 0.25, en.y - bounce - r * 0.25, r * 0.3, r * 0.25, -0.3, 0, Math.PI * 2);
    cx.fill();
    // Eyes
    cx.fillStyle = '#fff';
    cx.beginPath();
    cx.arc(en.x - r * 0.25, en.y - bounce - r * 0.1, r * 0.22, 0, Math.PI * 2);
    cx.arc(en.x + r * 0.25, en.y - bounce - r * 0.1, r * 0.22, 0, Math.PI * 2);
    cx.fill();
    cx.fillStyle = '#1B5E20';
    cx.beginPath();
    cx.arc(en.x - r * 0.2, en.y - bounce - r * 0.1, r * 0.1, 0, Math.PI * 2);
    cx.arc(en.x + r * 0.3, en.y - bounce - r * 0.1, r * 0.1, 0, Math.PI * 2);
    cx.fill();
  }
  else if (en.type === 'knight') {
    const bob = Math.sin(frame * 0.06 + en.t * 15) * 2 * sc;
    // Body
    cx.fillStyle = en.color;
    cx.fillRect(en.x - r * 0.6, en.y - r + bob, r * 1.2, r * 1.3);
    // Helmet
    cx.fillStyle = '#3F51B5';
    cx.beginPath();
    cx.arc(en.x, en.y - r * 0.8 + bob, r * 0.6, Math.PI, 0);
    cx.fill();
    cx.fillRect(en.x - r * 0.6, en.y - r * 0.8 + bob, r * 1.2, r * 0.3);
    // Visor
    cx.fillStyle = '#1A237E';
    cx.fillRect(en.x - r * 0.4, en.y - r * 0.6 + bob, r * 0.8, r * 0.15);
    // Shield
    cx.fillStyle = '#7986CB';
    cx.beginPath();
    cx.ellipse(en.x + r * 0.5, en.y - r * 0.1 + bob, r * 0.3, r * 0.45, 0, 0, Math.PI * 2);
    cx.fill();
  }
  else if (en.type === 'boss') {
    const bob = Math.sin(frame * 0.04) * 2 * sc;
    // Big red body
    cx.fillStyle = en.color;
    cx.beginPath();
    cx.arc(en.x, en.y - r * 0.3 + bob, r, 0, Math.PI * 2);
    cx.fill();
    // Darker belly
    cx.fillStyle = '#C62828';
    cx.beginPath();
    cx.ellipse(en.x, en.y + bob, r * 0.6, r * 0.4, 0, 0, Math.PI * 2);
    cx.fill();
    // Eyes (angry)
    cx.fillStyle = '#fff';
    cx.beginPath();
    cx.arc(en.x - r * 0.3, en.y - r * 0.45 + bob, r * 0.22, 0, Math.PI * 2);
    cx.arc(en.x + r * 0.3, en.y - r * 0.45 + bob, r * 0.22, 0, Math.PI * 2);
    cx.fill();
    cx.fillStyle = '#B71C1C';
    cx.beginPath();
    cx.arc(en.x - r * 0.25, en.y - r * 0.45 + bob, r * 0.1, 0, Math.PI * 2);
    cx.arc(en.x + r * 0.35, en.y - r * 0.45 + bob, r * 0.1, 0, Math.PI * 2);
    cx.fill();
    // Angry eyebrows
    cx.strokeStyle = '#4A0000';
    cx.lineWidth = 2.5 * sc;
    cx.beginPath();
    cx.moveTo(en.x - r * 0.5, en.y - r * 0.7 + bob);
    cx.lineTo(en.x - r * 0.15, en.y - r * 0.55 + bob);
    cx.moveTo(en.x + r * 0.5, en.y - r * 0.7 + bob);
    cx.lineTo(en.x + r * 0.15, en.y - r * 0.55 + bob);
    cx.stroke();
    // Crown
    cx.fillStyle = '#FFD700';
    cx.beginPath();
    cx.moveTo(en.x - r * 0.5, en.y - r * 1.0 + bob);
    cx.lineTo(en.x - r * 0.35, en.y - r * 1.4 + bob);
    cx.lineTo(en.x - r * 0.15, en.y - r * 1.1 + bob);
    cx.lineTo(en.x, en.y - r * 1.5 + bob);
    cx.lineTo(en.x + r * 0.15, en.y - r * 1.1 + bob);
    cx.lineTo(en.x + r * 0.35, en.y - r * 1.4 + bob);
    cx.lineTo(en.x + r * 0.5, en.y - r * 1.0 + bob);
    cx.closePath();
    cx.fill();
  }

  // HP bar
  if (en.hp < en.maxHp) {
    const bw = r * 2.2, bh = 3 * sc;
    const bx = en.x - bw / 2, by = en.y - r * 1.5 - (en.type === 'boss' ? 12 * sc : 0);
    cx.fillStyle = 'rgba(0,0,0,0.4)';
    cx.beginPath();
    cx.roundRect(bx - 1, by - 1, bw + 2, bh + 2, 2);
    cx.fill();
    cx.fillStyle = '#333';
    cx.beginPath();
    cx.roundRect(bx, by, bw, bh, 2);
    cx.fill();
    const pct = en.hp / en.maxHp;
    cx.fillStyle = pct > 0.5 ? '#66BB6A' : pct > 0.25 ? '#FFA726' : '#EF5350';
    cx.beginPath();
    cx.roundRect(bx, by, bw * pct, bh, 2);
    cx.fill();
  }
}

function drawEnemies() {
  // Sort by y for depth
  const alive = enemies.filter(e => !e.dead && !e.reached);
  alive.sort((a, b) => a.y - b.y);
  alive.forEach(drawEnemyShape);
}

function drawProjectiles() {
  for (const p of projectiles) {
    cx.fillStyle = p.color;
    cx.beginPath();
    cx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    cx.fill();
    // Trail
    cx.globalAlpha = 0.3;
    cx.beginPath();
    cx.arc(p.x - (p.tx - p.x) * 0.05, p.y - (p.ty - p.y) * 0.05, p.size * 0.7, 0, Math.PI * 2);
    cx.fill();
    cx.globalAlpha = 1;
  }
}

function drawParticles() {
  for (const pt of particles) {
    cx.globalAlpha = pt.life;
    cx.fillStyle = pt.color;
    cx.beginPath();
    cx.arc(pt.x, pt.y, pt.size * pt.life, 0, Math.PI * 2);
    cx.fill();
  }
  cx.globalAlpha = 1;
}

function drawGrassDecor() {
  // Small flowers and grass tufts
  cx.fillStyle = '#FFE082';
  const seed = 42;
  for (let i = 0; i < 20; i++) {
    const fx = ((seed * (i + 1) * 7) % W);
    const fy = mapOffY + 30 * sc + ((seed * (i + 3) * 13) % (H * 0.55));
    const fsz = 2 + (i % 3);
    cx.beginPath();
    cx.arc(fx, fy, fsz * sc, 0, Math.PI * 2);
    cx.fill();
  }
  // White flowers
  cx.fillStyle = '#fff';
  for (let i = 0; i < 12; i++) {
    const fx = ((seed * (i + 7) * 11) % W);
    const fy = mapOffY + 50 * sc + ((seed * (i + 5) * 17) % (H * 0.5));
    cx.globalAlpha = 0.5;
    cx.beginPath();
    cx.arc(fx, fy, 2.5 * sc, 0, Math.PI * 2);
    cx.fill();
  }
  cx.globalAlpha = 1;
}

function drawTray() {
  if (phase === 'wave' && !gameOver) return;
  const tray = getTray();

  // Background panel
  const panelY = H - 100 * sc;
  cx.fillStyle = 'rgba(62,39,35,0.8)';
  cx.beginPath();
  cx.roundRect(8, panelY, W - 16, H - panelY - 4, 14 * sc);
  cx.fill();
  cx.strokeStyle = 'rgba(255,215,0,0.3)';
  cx.lineWidth = 1.5;
  cx.beginPath();
  cx.roundRect(8, panelY, W - 16, H - panelY - 4, 14 * sc);
  cx.stroke();

  for (const t of tray) {
    const def = TOWER[t.type];
    const afford = coins >= def.cost;

    // Card
    cx.fillStyle = afford ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.03)';
    cx.beginPath();
    cx.roundRect(t.x, t.y, t.w, t.h, 8 * sc);
    cx.fill();
    cx.strokeStyle = afford ? def.color : 'rgba(255,255,255,0.1)';
    cx.lineWidth = afford ? 2 : 1;
    cx.beginPath();
    cx.roundRect(t.x, t.y, t.w, t.h, 8 * sc);
    cx.stroke();

    // Tower preview
    cx.globalAlpha = afford ? 1 : 0.3;
    drawTowerShape(t.x + t.w / 2, t.y + t.h * 0.5, t.type, def.color, 0);
    cx.globalAlpha = 1;

    // Name
    cx.fillStyle = afford ? '#fff' : '#666';
    cx.font = (9 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    cx.fillText(def.name, t.x + t.w / 2, t.y + t.h - 16 * sc);

    // Cost
    if (coinLoaded) {
      const csz = 12 * sc;
      cx.drawImage(coinImg, t.x + t.w / 2 - csz - 2, t.y + t.h - 13 * sc, csz, csz);
    }
    cx.fillStyle = afford ? '#FFD700' : '#666';
    cx.font = 'bold ' + (11 * sc) + 'px "Segoe UI",sans-serif';
    cx.fillText(def.cost, t.x + t.w / 2 + 10 * sc, t.y + t.h - 4 * sc);
    cx.textAlign = 'left';
  }

  // Start Wave button
  const sb = getStartBtn();
  const waveTxt = wave === 0 ? 'START WAVE 1' : 'WAVE ' + (wave + 1);
  cx.fillStyle = '#4CAF50';
  cx.beginPath();
  cx.roundRect(sb.x, sb.y, sb.w, sb.h, 18 * sc);
  cx.fill();
  cx.fillStyle = '#2E7D32';
  cx.beginPath();
  cx.roundRect(sb.x, sb.y + 2 * sc, sb.w, sb.h - 2 * sc, 18 * sc);
  cx.fill();
  cx.fillStyle = '#4CAF50';
  cx.beginPath();
  cx.roundRect(sb.x, sb.y, sb.w, sb.h - 3 * sc, 18 * sc);
  cx.fill();
  cx.fillStyle = '#fff';
  cx.font = 'bold ' + (13 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  cx.fillText(waveTxt, sb.x + sb.w / 2, sb.y + sb.h / 2 + 4 * sc);
  cx.textAlign = 'left';
}

function drawHUD() {
  // Coins
  cx.fillStyle = 'rgba(62,39,35,0.75)';
  cx.beginPath();
  cx.roundRect(8, 6, 100 * sc, 30 * sc, 15 * sc);
  cx.fill();
  if (coinLoaded) cx.drawImage(coinImg, 14, 9, 22 * sc, 22 * sc);
  cx.fillStyle = '#FFD700';
  cx.font = 'bold ' + (15 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText(coins, 14 + 26 * sc, 25 * sc);

  // Lives
  cx.fillStyle = 'rgba(62,39,35,0.75)';
  const lvX = W - 90 * sc;
  cx.beginPath();
  cx.roundRect(lvX, 6, 82 * sc, 30 * sc, 15 * sc);
  cx.fill();
  cx.fillStyle = '#EF5350';
  cx.font = (16 * sc) + 'px sans-serif';
  cx.fillText('\\u2665', lvX + 10, 26 * sc);
  cx.fillStyle = '#fff';
  cx.font = 'bold ' + (15 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText('x ' + lives, lvX + 28 * sc, 25 * sc);

  // Wave info
  cx.fillStyle = 'rgba(255,255,255,0.6)';
  cx.font = (11 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  const waveText = phase === 'wave' ? 'Wave ' + (wave + 1) + '/' + WAVES.length + ' - FIGHTING!'
    : wave >= WAVES.length ? 'All waves cleared!'
    : 'Wave ' + (wave + 1) + '/' + WAVES.length;
  cx.fillText(waveText, W / 2, 25 * sc);
  cx.textAlign = 'left';
}

function drawTutorial() {
  if (!tutHint || phase !== 'place' || placedTowers.length > 0) return;
  cx.globalAlpha = 0.5 + 0.5 * Math.sin(frame * 0.06);
  cx.fillStyle = '#fff';
  cx.font = 'bold ' + (14 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  cx.fillText('Drag towers to the + spots!', W / 2, mapOffY + 5 * sc);
  // Down arrow
  cx.font = (20 * sc) + 'px sans-serif';
  cx.fillText('\\u2B07', W / 2, H - 102 * sc);
  cx.textAlign = 'left';
  cx.globalAlpha = 1;
}

function drawDragPreview() {
  if (!dragging || !dragType) return;

  // Range preview
  const def = TOWER[dragType];
  cx.globalAlpha = 0.12;
  cx.fillStyle = def.color;
  cx.beginPath();
  cx.arc(dragX, dragY, def.range * sc, 0, Math.PI * 2);
  cx.fill();
  cx.globalAlpha = 0.7;
  drawTowerShape(dragX, dragY, dragType, def.color, 0);
  cx.globalAlpha = 1;

  // Highlight nearest valid slot
  let bestSlot = null, bestDist = 50 * sc;
  for (const s of slots) {
    if (s.tower) continue;
    const dx = dragX - s.x, dy = dragY - s.y;
    const d = Math.sqrt(dx*dx + dy*dy);
    if (d < bestDist) { bestDist = d; bestSlot = s; }
  }
  if (bestSlot) {
    cx.strokeStyle = '#FFD700';
    cx.lineWidth = 3 * sc;
    cx.beginPath();
    cx.arc(bestSlot.x, bestSlot.y, bestSlot.radius + 3 * sc, 0, Math.PI * 2);
    cx.stroke();
  }
}

// ===== MAIN LOOP =====
function loop() {
  frame++;
  if (phase === 'wave') updateWave();

  drawSky();
  drawClouds();
  drawGrassDecor();
  drawPath();
  drawSlots();
  drawTowers();
  drawEnemies();
  drawProjectiles();
  drawParticles();
  drawDragPreview();
  drawHUD();
  if (phase !== 'wave') drawTray();
  drawTutorial();

  requestAnimationFrame(loop);
}

// ===== START =====
init();
loop();
</script>
</body>
</html>`;

const outPath = 'E:/AI/projects/td-playable/output/playable.html';
fs.writeFileSync(outPath, html, 'utf8');
const s = fs.statSync(outPath);
console.log('Written: ' + outPath);
console.log('Size: ' + (s.size / 1024).toFixed(1) + ' KB (' + s.size + ' bytes)');
console.log('Under 2MB (all networks): ' + (s.size < 2097152 ? 'YES' : 'NO'));
