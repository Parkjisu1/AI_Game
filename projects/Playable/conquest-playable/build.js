const fs = require('fs');
const TMP = process.env.TEMP || process.env.TMP || 'C:/Users/user/AppData/Local/Temp';

function b64(name) { return fs.readFileSync(TMP + '/' + name, 'utf8').trim(); }

const A = {
  chars: b64('idle_chars.b64'),
  coin: b64('idle_coin.b64'),
  tower: b64('idle_tower.b64'),
  tree: b64('idle_tree.b64'),
  castle: b64('idle_castle.b64'),
  bld: b64('cq_bld.b64'),
  star: b64('idle_star.b64')
};

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="ad.size" content="width=320,height=480">
<title>Kingdom Conquest - Play Now!</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#1a2a1a;touch-action:none;user-select:none;-webkit-user-select:none}
canvas{display:block;position:absolute;top:0;left:0}
#cta{display:none;position:absolute;top:0;left:0;width:100%;height:100%;background:rgba(10,15,30,0.92);z-index:10;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#cta.show{display:flex}
#cta-title{font-family:'Segoe UI',Arial,sans-serif;font-size:30px;font-weight:bold;margin-bottom:8px;text-shadow:0 3px 15px rgba(255,200,50,0.5)}
#cta-sub{color:#B0C4DE;font-family:'Segoe UI',Arial,sans-serif;font-size:15px;margin-bottom:6px}
#cta-score{color:#FFD700;font-family:'Segoe UI',Arial,sans-serif;font-size:18px;font-weight:bold;margin-bottom:24px}
#cta-btn{background:linear-gradient(135deg,#4CAF50,#2E7D32);color:#fff;border:none;padding:18px 52px;font-size:22px;font-weight:bold;border-radius:50px;cursor:pointer;animation:pulse 1.4s infinite;font-family:'Segoe UI',Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;box-shadow:0 4px 24px rgba(76,175,80,0.5)}
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
  <div id="cta-score"></div>
  <button id="cta-btn" onclick="window.open('https://play.google.com/store','_blank')">INSTALL FREE</button>
  <div id="cta-retry" onclick="restart()">Play again</div>
</div>
<script>
'use strict';

// ===== POLYFILL: roundRect =====
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

// ===== ASSETS =====
const IMG = {};
let loaded = 0, total = 7;
function ld(k, d) {
  const i = new Image();
  i.onload = i.onerror = () => { IMG[k] = i; loaded++; if (loaded >= total) startApp(); };
  i.src = 'data:image/png;base64,' + d;
}
ld('chars', '${A.chars}');
ld('coin', '${A.coin}');
ld('tower', '${A.tower}');
ld('tree', '${A.tree}');
ld('castle', '${A.castle}');
ld('bld', '${A.bld}');
ld('star', '${A.star}');

// Sprite crops
const LULU = { x: 30, y: 60, w: 430, h: 480 };
const BEARON = { x: 530, y: 20, w: 470, h: 530 };

// ===== CANVAS =====
const cv = document.getElementById('gc'), cx = cv.getContext('2d');
let W, H, sc;
function resize() {
  W = cv.width = innerWidth;
  H = cv.height = innerHeight;
  sc = Math.min(W / 420, H / 780);
}
resize();
addEventListener('resize', resize);

// ===== TERRITORY MAP =====
// Each node: { x, y (0-1 normalized), connections[], owner, troops, maxTroops, radius, buildingType }
// owner: 0=neutral, 1=player, 2=enemy
const MAP_NODES = [
  // Row 1 (top)
  { nx: 0.25, ny: 0.10, conns: [1, 3] },
  { nx: 0.50, ny: 0.08, conns: [0, 2, 4] },
  { nx: 0.75, ny: 0.10, conns: [1, 5] },
  // Row 2
  { nx: 0.15, ny: 0.27, conns: [0, 4, 6] },
  { nx: 0.50, ny: 0.24, conns: [1, 3, 5, 7] },
  { nx: 0.85, ny: 0.27, conns: [2, 4, 8] },
  // Row 3
  { nx: 0.22, ny: 0.44, conns: [3, 7, 9] },
  { nx: 0.50, ny: 0.42, conns: [4, 6, 8, 10] },
  { nx: 0.78, ny: 0.44, conns: [5, 7, 11] },
  // Row 4
  { nx: 0.15, ny: 0.60, conns: [6, 10, 12] },
  { nx: 0.50, ny: 0.58, conns: [7, 9, 11, 13] },
  { nx: 0.85, ny: 0.60, conns: [8, 10, 14] },
  // Row 5 (bottom)
  { nx: 0.25, ny: 0.75, conns: [9, 13] },
  { nx: 0.50, ny: 0.73, conns: [10, 12, 14] },
  { nx: 0.75, ny: 0.75, conns: [11, 13] }
];

// ===== GAME STATE =====
let nodes, marchingArmies, particles, floatTexts;
let selectedNode, gameOver, won, frame, startTime;
let aiTimer, aiSpeed;
let tutStep;
const MAX_TIME = 50000;
const OWNER_NEUTRAL = 0, OWNER_PLAYER = 1, OWNER_ENEMY = 2;
const COLORS = {
  0: { main: '#78909C', light: '#B0BEC5', dark: '#546E7A', glow: 'rgba(120,144,156,0.3)' },
  1: { main: '#42A5F5', light: '#90CAF9', dark: '#1565C0', glow: 'rgba(66,165,245,0.4)' },
  2: { main: '#EF5350', light: '#EF9A9A', dark: '#C62828', glow: 'rgba(239,83,80,0.4)' }
};

function init() {
  const mapH = H * 0.82;
  const mapOY = H * 0.10;

  nodes = MAP_NODES.map((n, i) => ({
    idx: i,
    x: n.nx * W,
    y: mapOY + n.ny * mapH,
    conns: n.conns,
    owner: OWNER_NEUTRAL,
    troops: 3 + Math.floor(Math.random() * 3),
    maxTroops: 30,
    radius: 28 * sc,
    pulse: Math.random() * Math.PI * 2,
    building: null
  }));

  // Player starts bottom-left
  nodes[12].owner = OWNER_PLAYER;
  nodes[12].troops = 10;
  nodes[12].building = 'castle';

  // Enemy starts top-right
  nodes[2].owner = OWNER_ENEMY;
  nodes[2].troops = 10;
  nodes[2].building = 'castle';

  // Some neutral nodes get buildings
  nodes[4].building = 'tower';
  nodes[7].building = 'bld';
  nodes[10].building = 'tower';

  marchingArmies = [];
  particles = [];
  floatTexts = [];
  selectedNode = null;
  gameOver = false;
  won = false;
  frame = 0;
  startTime = Date.now();
  aiTimer = 0;
  aiSpeed = 90; // frames between AI actions
  tutStep = 0;

  document.getElementById('cta').classList.remove('show');
}

// ===== INPUT =====
function getP(e) {
  if (e.changedTouches) return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY };
  return { x: e.clientX, y: e.clientY };
}

function findNode(px, py) {
  for (const n of nodes) {
    const dx = px - n.x, dy = py - n.y;
    if (Math.sqrt(dx * dx + dy * dy) < n.radius * 1.5) return n;
  }
  return null;
}

function onDown(e) {
  e.preventDefault();
  if (gameOver) return;
  const p = getP(e);
  const hit = findNode(p.x, p.y);

  if (!hit) { selectedNode = null; return; }

  if (selectedNode === null) {
    // Select a player-owned node
    if (hit.owner === OWNER_PLAYER && hit.troops > 1) {
      selectedNode = hit;
      tutStep = Math.max(tutStep, 1);
    }
  } else {
    // Send troops to connected node
    if (hit.idx !== selectedNode.idx && selectedNode.conns.includes(hit.idx)) {
      sendArmy(selectedNode, hit, OWNER_PLAYER);
      tutStep = Math.max(tutStep, 2);
    }
    selectedNode = null;
  }
}

cv.addEventListener('mousedown', onDown);
cv.addEventListener('touchstart', onDown, { passive: false });
cv.addEventListener('touchmove', e => e.preventDefault(), { passive: false });
cv.addEventListener('mousemove', e => e.preventDefault());
cv.addEventListener('touchend', e => e.preventDefault(), { passive: false });
cv.addEventListener('mouseup', e => e.preventDefault());

// ===== ARMY LOGIC =====
function sendArmy(from, to, owner) {
  const count = Math.ceil(from.troops * 0.6);
  if (count < 1) return;
  from.troops -= count;
  marchingArmies.push({
    fromIdx: from.idx,
    toIdx: to.idx,
    owner,
    troops: count,
    x: from.x, y: from.y,
    progress: 0,
    speed: 0.018 + Math.random() * 0.005
  });
}

function resolveArrival(army) {
  const target = nodes[army.toIdx];
  if (target.owner === army.owner) {
    // Reinforce
    target.troops = Math.min(target.maxTroops, target.troops + army.troops);
    spawnEffect(target.x, target.y, COLORS[army.owner].light, 6);
  } else {
    // Attack
    target.troops -= army.troops;
    spawnEffect(target.x, target.y, '#FFD700', 10);
    if (target.troops <= 0) {
      // Captured!
      target.owner = army.owner;
      target.troops = Math.abs(target.troops) || 1;
      spawnEffect(target.x, target.y, COLORS[army.owner].main, 15);
      floatTexts.push({
        x: target.x, y: target.y - 30 * sc,
        text: army.owner === OWNER_PLAYER ? 'CAPTURED!' : 'LOST!',
        life: 1.5,
        color: COLORS[army.owner].main,
        size: 16
      });
    }
  }
}

// ===== AI =====
function aiTurn() {
  const enemyNodes = nodes.filter(n => n.owner === OWNER_ENEMY && n.troops > 3);
  if (enemyNodes.length === 0) return;

  // Pick strongest node
  enemyNodes.sort((a, b) => b.troops - a.troops);
  const from = enemyNodes[0];

  // Find best target: prefer player nodes, then neutral, avoid own
  let targets = from.conns
    .map(i => nodes[i])
    .filter(n => n.owner !== OWNER_ENEMY);

  if (targets.length === 0) return;

  // Prefer weaker targets and player targets
  targets.sort((a, b) => {
    const aScore = (a.owner === OWNER_PLAYER ? -20 : 0) + a.troops;
    const bScore = (b.owner === OWNER_PLAYER ? -20 : 0) + b.troops;
    return aScore - bScore;
  });

  sendArmy(from, targets[0], OWNER_ENEMY);
}

// ===== EFFECTS =====
function spawnEffect(x, y, color, count) {
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 1.5 + Math.random() * 3;
    particles.push({
      x, y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 1,
      life: 1,
      decay: 0.02 + Math.random() * 0.02,
      size: 2 + Math.random() * 4,
      color
    });
  }
}

// ===== UPDATE =====
function update() {
  frame++;

  // Troop generation
  if (frame % 45 === 0) {
    for (const n of nodes) {
      if (n.owner !== OWNER_NEUTRAL && n.troops < n.maxTroops) {
        const bonus = n.building ? 2 : 1;
        n.troops = Math.min(n.maxTroops, n.troops + bonus);
      }
    }
  }

  // AI
  if (!gameOver) {
    aiTimer++;
    if (aiTimer >= aiSpeed) {
      aiTimer = 0;
      aiTurn();
      // AI gets slightly faster over time
      aiSpeed = Math.max(50, aiSpeed - 1);
    }
  }

  // Marching armies
  for (let i = marchingArmies.length - 1; i >= 0; i--) {
    const a = marchingArmies[i];
    a.progress += a.speed;
    const target = nodes[a.toIdx];
    const source = nodes[a.fromIdx];
    a.x = source.x + (target.x - source.x) * a.progress;
    a.y = source.y + (target.y - source.y) * a.progress;

    if (a.progress >= 1) {
      resolveArrival(a);
      marchingArmies.splice(i, 1);
    }
  }

  // Node pulse
  for (const n of nodes) {
    n.pulse += 0.03;
  }

  // Particles
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx; p.y += p.vy; p.vy += 0.05;
    p.life -= p.decay;
    if (p.life <= 0) particles.splice(i, 1);
  }

  // Float texts
  for (let i = floatTexts.length - 1; i >= 0; i--) {
    const ft = floatTexts[i];
    ft.y -= 0.8;
    ft.life -= 0.02;
    if (ft.life <= 0) floatTexts.splice(i, 1);
  }

  // Win/Lose check
  if (!gameOver) {
    const playerCount = nodes.filter(n => n.owner === OWNER_PLAYER).length;
    const enemyCount = nodes.filter(n => n.owner === OWNER_ENEMY).length;

    if (enemyCount === 0) {
      gameOver = true; won = true;
      setTimeout(showResult, 800);
    } else if (playerCount === 0) {
      gameOver = true; won = false;
      setTimeout(showResult, 800);
    } else if (Date.now() - startTime >= MAX_TIME) {
      gameOver = true;
      won = playerCount > enemyCount;
      setTimeout(showResult, 600);
    }
  }
}

// ===== DRAW =====
function drawBg() {
  const g = cx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#0D1B2A');
  g.addColorStop(0.5, '#1B2838');
  g.addColorStop(1, '#0A1628');
  cx.fillStyle = g;
  cx.fillRect(0, 0, W, H);

  // Stars
  cx.fillStyle = 'rgba(255,255,255,0.25)';
  for (let i = 0; i < 40; i++) {
    const sx = (i * 137.5 + 50) % W;
    const sy = (i * 73.7 + 30) % H;
    const ss = 0.5 + Math.sin(frame * 0.02 + i * 1.7) * 0.5;
    cx.beginPath();
    cx.arc(sx, sy, ss, 0, Math.PI * 2);
    cx.fill();
  }

  // Subtle grid pattern
  cx.strokeStyle = 'rgba(255,255,255,0.03)';
  cx.lineWidth = 1;
  const step = 40 * sc;
  for (let gx = 0; gx < W; gx += step) {
    cx.beginPath(); cx.moveTo(gx, 0); cx.lineTo(gx, H); cx.stroke();
  }
  for (let gy = 0; gy < H; gy += step) {
    cx.beginPath(); cx.moveTo(0, gy); cx.lineTo(W, gy); cx.stroke();
  }
}

function drawConnections() {
  for (const n of nodes) {
    for (const ci of n.conns) {
      if (ci > n.idx) { // draw each connection once
        const other = nodes[ci];
        // Color based on ownership
        const sameOwner = n.owner === other.owner && n.owner !== OWNER_NEUTRAL;
        cx.strokeStyle = sameOwner ? COLORS[n.owner].glow : 'rgba(255,255,255,0.08)';
        cx.lineWidth = sameOwner ? 3 * sc : 1.5 * sc;

        // Dashed for different owners
        if (!sameOwner) cx.setLineDash([4 * sc, 6 * sc]);

        cx.beginPath();
        cx.moveTo(n.x, n.y);
        cx.lineTo(other.x, other.y);
        cx.stroke();
        cx.setLineDash([]);
      }
    }
  }
}

function drawNode(n) {
  const c = COLORS[n.owner];
  const isSelected = selectedNode && selectedNode.idx === n.idx;
  const pulseScale = 1 + Math.sin(n.pulse) * 0.04;
  const r = n.radius * pulseScale;

  // Glow
  cx.globalAlpha = 0.3 + (isSelected ? 0.3 : 0);
  const glowG = cx.createRadialGradient(n.x, n.y, r * 0.3, n.x, n.y, r * 2);
  glowG.addColorStop(0, c.main);
  glowG.addColorStop(1, 'transparent');
  cx.fillStyle = glowG;
  cx.beginPath();
  cx.arc(n.x, n.y, r * 2, 0, Math.PI * 2);
  cx.fill();
  cx.globalAlpha = 1;

  // Outer ring
  cx.strokeStyle = isSelected ? '#FFD700' : c.light;
  cx.lineWidth = isSelected ? 3.5 * sc : 2 * sc;
  cx.beginPath();
  cx.arc(n.x, n.y, r, 0, Math.PI * 2);
  cx.stroke();

  // Fill
  const fillG = cx.createRadialGradient(n.x - r * 0.2, n.y - r * 0.2, 0, n.x, n.y, r);
  fillG.addColorStop(0, c.light);
  fillG.addColorStop(1, c.dark);
  cx.fillStyle = fillG;
  cx.beginPath();
  cx.arc(n.x, n.y, r - 2 * sc, 0, Math.PI * 2);
  cx.fill();

  // Building icon
  if (n.building && IMG[n.building]) {
    const bsz = r * 1.1;
    cx.globalAlpha = 0.7;
    cx.drawImage(IMG[n.building], n.x - bsz / 2, n.y - bsz / 2, bsz, bsz);
    cx.globalAlpha = 1;
  }

  // Troop count
  cx.fillStyle = '#fff';
  cx.font = 'bold ' + (Math.min(14, 11 + n.troops * 0.1) * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  cx.textBaseline = 'middle';
  cx.strokeStyle = 'rgba(0,0,0,0.6)';
  cx.lineWidth = 3;
  cx.strokeText(Math.floor(n.troops), n.x, n.y);
  cx.fillText(Math.floor(n.troops), n.x, n.y);
  cx.textBaseline = 'alphabetic';
  cx.textAlign = 'left';

  // Selection - highlight valid targets
  if (isSelected) {
    for (const ci of n.conns) {
      const target = nodes[ci];
      cx.strokeStyle = 'rgba(255,215,0,0.4)';
      cx.lineWidth = 2 * sc;
      cx.setLineDash([3 * sc, 4 * sc]);
      cx.beginPath();
      cx.arc(target.x, target.y, target.radius + 6 * sc, 0, Math.PI * 2);
      cx.stroke();
      cx.setLineDash([]);
    }
  }
}

function drawNodes() {
  // Draw in order for consistent layering
  for (const n of nodes) {
    drawNode(n);
  }
}

function drawArmies() {
  for (const a of marchingArmies) {
    const c = COLORS[a.owner];
    const sz = 8 * sc + Math.min(12, a.troops * 0.4) * sc;

    // Trail
    cx.globalAlpha = 0.3;
    cx.fillStyle = c.main;
    for (let t = 0; t < 3; t++) {
      const tp = Math.max(0, a.progress - t * 0.04);
      const source = nodes[a.fromIdx];
      const target = nodes[a.toIdx];
      const tx = source.x + (target.x - source.x) * tp;
      const ty = source.y + (target.y - source.y) * tp;
      cx.beginPath();
      cx.arc(tx, ty, sz * (0.4 - t * 0.1), 0, Math.PI * 2);
      cx.fill();
    }
    cx.globalAlpha = 1;

    // Army blob
    cx.fillStyle = c.main;
    cx.beginPath();
    cx.arc(a.x, a.y, sz * 0.55, 0, Math.PI * 2);
    cx.fill();

    // Border
    cx.strokeStyle = c.light;
    cx.lineWidth = 1.5 * sc;
    cx.beginPath();
    cx.arc(a.x, a.y, sz * 0.55, 0, Math.PI * 2);
    cx.stroke();

    // Troop count
    cx.fillStyle = '#fff';
    cx.font = 'bold ' + (9 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    cx.textBaseline = 'middle';
    cx.fillText(a.troops, a.x, a.y);
    cx.textBaseline = 'alphabetic';
    cx.textAlign = 'left';
  }
}

function drawParticles() {
  for (const p of particles) {
    cx.globalAlpha = p.life;
    cx.fillStyle = p.color;
    cx.beginPath();
    cx.arc(p.x, p.y, p.size * p.life * sc, 0, Math.PI * 2);
    cx.fill();
  }
  cx.globalAlpha = 1;
}

function drawFloatTexts() {
  for (const ft of floatTexts) {
    cx.globalAlpha = Math.min(1, ft.life * 2);
    cx.font = 'bold ' + (ft.size * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    cx.strokeStyle = 'rgba(0,0,0,0.6)';
    cx.lineWidth = 3;
    cx.strokeText(ft.text, ft.x, ft.y);
    cx.fillStyle = ft.color;
    cx.fillText(ft.text, ft.x, ft.y);
  }
  cx.globalAlpha = 1;
  cx.textAlign = 'left';
}

function drawHUD() {
  const pc = nodes.filter(n => n.owner === OWNER_PLAYER).length;
  const ec = nodes.filter(n => n.owner === OWNER_ENEMY).length;
  const nc = nodes.filter(n => n.owner === OWNER_NEUTRAL).length;
  const totalP = nodes.filter(n => n.owner === OWNER_PLAYER).reduce((s, n) => s + n.troops, 0);
  const totalE = nodes.filter(n => n.owner === OWNER_ENEMY).reduce((s, n) => s + n.troops, 0);

  // Player panel (left)
  cx.fillStyle = 'rgba(25,118,210,0.3)';
  cx.beginPath();
  cx.roundRect(8, 6, 100 * sc, 50 * sc, 10 * sc);
  cx.fill();

  // Player avatar
  if (IMG.chars) {
    const asz = 30 * sc;
    cx.drawImage(IMG.chars, LULU.x, LULU.y, LULU.w, LULU.h, 12, 10, asz, asz);
  }
  cx.fillStyle = '#42A5F5';
  cx.font = 'bold ' + (12 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText(pc + ' zones', 12 + 34 * sc, 24 * sc);
  cx.fillStyle = '#90CAF9';
  cx.font = (9 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText(Math.floor(totalP) + ' troops', 12 + 34 * sc, 38 * sc);

  // Enemy panel (right)
  cx.fillStyle = 'rgba(198,40,40,0.3)';
  const epX = W - 108 * sc;
  cx.beginPath();
  cx.roundRect(epX, 6, 100 * sc, 50 * sc, 10 * sc);
  cx.fill();

  if (IMG.chars) {
    const asz = 30 * sc;
    cx.drawImage(IMG.chars, BEARON.x, BEARON.y, BEARON.w, BEARON.h, epX + 4, 10, asz, asz);
  }
  cx.fillStyle = '#EF5350';
  cx.font = 'bold ' + (12 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText(ec + ' zones', epX + 38 * sc, 24 * sc);
  cx.fillStyle = '#EF9A9A';
  cx.font = (9 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText(Math.floor(totalE) + ' troops', epX + 38 * sc, 38 * sc);

  // Territory bar (center bottom area)
  const barW = W - 30;
  const barH = 10 * sc;
  const barY = H - 18 * sc;
  const barX = 15;

  cx.fillStyle = 'rgba(0,0,0,0.4)';
  cx.beginPath();
  cx.roundRect(barX, barY, barW, barH, 5 * sc);
  cx.fill();

  const totalNodes = nodes.length;
  const pw = (pc / totalNodes) * barW;
  const ew = (ec / totalNodes) * barW;

  // Player portion
  cx.fillStyle = '#42A5F5';
  cx.beginPath();
  cx.roundRect(barX, barY, pw, barH, [5 * sc, 0, 0, 5 * sc]);
  cx.fill();

  // Enemy portion (from right)
  cx.fillStyle = '#EF5350';
  cx.beginPath();
  cx.roundRect(barX + barW - ew, barY, ew, barH, [0, 5 * sc, 5 * sc, 0]);
  cx.fill();

  // Timer
  const elapsed = Date.now() - startTime;
  const remaining = Math.max(0, 1 - elapsed / MAX_TIME);
  const timerY = H - 36 * sc;
  cx.fillStyle = 'rgba(0,0,0,0.3)';
  cx.beginPath();
  cx.roundRect(barX, timerY, barW, 6 * sc, 3 * sc);
  cx.fill();
  cx.fillStyle = remaining > 0.25 ? '#4CAF50' : '#EF5350';
  cx.beginPath();
  cx.roundRect(barX, timerY, barW * remaining, 6 * sc, 3 * sc);
  cx.fill();

  // Timer text
  const secsLeft = Math.max(0, Math.ceil((MAX_TIME - elapsed) / 1000));
  cx.fillStyle = remaining > 0.25 ? 'rgba(255,255,255,0.5)' : '#EF5350';
  cx.font = (9 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  cx.fillText(secsLeft + 's remaining', W / 2, timerY - 3 * sc);
  cx.textAlign = 'left';
}

function drawTutorial() {
  if (tutStep >= 2 || gameOver) return;

  const alpha = 0.4 + 0.4 * Math.sin(frame * 0.06);
  cx.globalAlpha = alpha;
  cx.fillStyle = '#fff';
  cx.font = 'bold ' + (13 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';

  if (tutStep === 0) {
    cx.fillText('Tap your BLUE territory to select it!', W / 2, H * 0.90);
    // Arrow pointing to player start
    const pn = nodes[12];
    cx.font = (20 * sc) + 'px sans-serif';
    cx.fillText('\\u{1F447}', pn.x, pn.y - pn.radius - 12 * sc);
  } else if (tutStep === 1) {
    cx.fillText('Now tap a connected territory to attack!', W / 2, H * 0.90);
  }

  cx.textAlign = 'left';
  cx.globalAlpha = 1;
}

// ===== RESULT =====
function showResult() {
  const el = document.getElementById('cta');
  const title = document.getElementById('cta-title');
  const sub = document.getElementById('cta-sub');
  const scoreEl = document.getElementById('cta-score');
  const pc = nodes.filter(n => n.owner === OWNER_PLAYER).length;

  if (won) {
    title.textContent = 'CONQUEST COMPLETE!';
    title.style.color = '#FFD700';
    sub.textContent = 'You conquered the realm!';
  } else {
    title.textContent = 'DEFEATED!';
    title.style.color = '#EF5350';
    sub.textContent = 'The enemy was too strong...';
  }
  scoreEl.textContent = pc + '/' + nodes.length + ' territories controlled';
  el.classList.add('show');
}

function restart() { init(); }

// ===== MAIN LOOP =====
function loop() {
  update();

  drawBg();
  drawConnections();
  drawNodes();
  drawArmies();
  drawParticles();
  drawFloatTexts();
  drawHUD();
  drawTutorial();

  requestAnimationFrame(loop);
}

function startApp() {
  init();
  loop();
}
</script>
</body>
</html>`;

const outPath = 'E:/AI/projects/conquest-playable/output/playable.html';
fs.writeFileSync(outPath, html, 'utf8');
const stats = fs.statSync(outPath);
console.log('Written: ' + outPath);
console.log('File size: ' + (stats.size / 1024).toFixed(1) + ' KB (' + stats.size + ' bytes)');
console.log('Under 5MB: ' + (stats.size < 5242880 ? 'YES' : 'NO'));
console.log('Under 2MB: ' + (stats.size < 2097152 ? 'YES' : 'NO'));
