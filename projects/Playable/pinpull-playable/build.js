const fs = require('fs');
const TMP = process.env.TEMP || process.env.TMP || 'C:/Users/user/AppData/Local/Temp';

function b64(name) { return fs.readFileSync(TMP + '/' + name, 'utf8').trim(); }

const A = {
  chars: b64('idle_chars.b64'),
  coin: b64('idle_coin.b64'),
  candies: b64('m3_candies.b64'),
  star: b64('idle_star.b64')
};

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="ad.size" content="width=320,height=480">
<title>Pull the Pin - Save Lulu!</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#F3E5F5;touch-action:none;user-select:none;-webkit-user-select:none}
canvas{display:block;position:absolute;top:0;left:0}
#cta{display:none;position:absolute;top:0;left:0;width:100%;height:100%;background:rgba(60,20,80,0.90);z-index:10;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#cta.show{display:flex}
#cta-title{font-family:'Segoe UI',Arial,sans-serif;font-size:30px;font-weight:bold;margin-bottom:8px;text-shadow:0 3px 15px rgba(255,200,50,0.5)}
#cta-sub{color:#E1BEE7;font-family:'Segoe UI',Arial,sans-serif;font-size:15px;margin-bottom:24px}
#cta-btn{background:linear-gradient(135deg,#FF6B9D,#E040A0);color:#fff;border:none;padding:18px 52px;font-size:22px;font-weight:bold;border-radius:50px;cursor:pointer;animation:pulse 1.4s infinite;font-family:'Segoe UI',Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;box-shadow:0 4px 24px rgba(224,64,160,0.5)}
#cta-btn:active{transform:scale(0.95)}
#cta-retry{color:#CE93D8;font-family:'Segoe UI',Arial,sans-serif;font-size:13px;margin-top:16px;cursor:pointer;text-decoration:underline}
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
let loaded = 0, total = 4;
function ld(k, d) {
  const i = new Image();
  i.onload = i.onerror = () => { IMG[k] = i; loaded++; if (loaded >= total) startApp(); };
  i.src = 'data:image/png;base64,' + d;
}
ld('chars', '${A.chars}');
ld('coin', '${A.coin}');
ld('candies', '${A.candies}');
ld('star', '${A.star}');

const LULU = { x: 30, y: 60, w: 430, h: 480 };
// Candy crops from image261
const CANDY_CROP = [
  { x: 20, y: 120, w: 170, h: 230 },
  { x: 215, y: 120, w: 170, h: 230 },
  { x: 405, y: 115, w: 175, h: 230 },
  { x: 595, y: 120, w: 170, h: 240 },
  { x: 790, y: 140, w: 200, h: 210 }
];

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

// ===== GAME CONSTANTS =====
const GRAVITY = 0.3;
const BOUNCE = 0.35;
const PIN_PULL_SPEED = 8;

// ===== LEVEL DEFINITIONS =====
// Coordinates normalized to puzzle area (0-1)
// walls: {x,y,w,h} - solid boundaries
// pins: {x,y,w, pullDir:'left'|'right'} - draggable pins
// items: {x,y,type:'coin'|'candy'|'bomb', candyIdx} - falling objects
// lulu: {x,y} - character position
// goal: description

function makeLevels() {
  return [
    // Level 1: Simple - pull pin, coins fall to Lulu
    {
      walls: [
        { x: 0.10, y: 0.15, w: 0.80, h: 0.03 },  // top platform
        { x: 0.08, y: 0.15, w: 0.03, h: 0.55 },   // left wall
        { x: 0.89, y: 0.15, w: 0.03, h: 0.55 },   // right wall
      ],
      pins: [
        { x: 0.20, y: 0.42, w: 0.60, pullDir: 'right', pulled: 0 }
      ],
      items: [
        { x: 0.35, y: 0.22, type: 'coin' },
        { x: 0.50, y: 0.24, type: 'candy', candyIdx: 0 },
        { x: 0.65, y: 0.22, type: 'coin' },
        { x: 0.50, y: 0.32, type: 'candy', candyIdx: 2 },
      ],
      lulu: { x: 0.50, y: 0.72 },
      hint: 'Pull the pin to drop treats to Lulu!'
    },
    // Level 2: Two paths - coins left, bombs right
    {
      walls: [
        { x: 0.05, y: 0.12, w: 0.42, h: 0.03 },  // left platform
        { x: 0.53, y: 0.12, w: 0.42, h: 0.03 },  // right platform
        { x: 0.03, y: 0.12, w: 0.03, h: 0.58 },  // far left wall
        { x: 0.94, y: 0.12, w: 0.03, h: 0.58 },  // far right wall
        { x: 0.47, y: 0.12, w: 0.06, h: 0.30 },  // center divider top
      ],
      pins: [
        { x: 0.10, y: 0.38, w: 0.35, pullDir: 'left', pulled: 0 },
        { x: 0.55, y: 0.38, w: 0.35, pullDir: 'right', pulled: 0 }
      ],
      items: [
        { x: 0.18, y: 0.18, type: 'coin' },
        { x: 0.30, y: 0.20, type: 'candy', candyIdx: 1 },
        { x: 0.24, y: 0.28, type: 'candy', candyIdx: 3 },
        { x: 0.65, y: 0.18, type: 'bomb' },
        { x: 0.78, y: 0.20, type: 'bomb' },
        { x: 0.72, y: 0.28, type: 'bomb' },
      ],
      lulu: { x: 0.50, y: 0.72 },
      hint: 'Pull the LEFT pin for candy! Avoid bombs!'
    },
    // Level 3: Tricky - bomb above, need to pull bottom pin first to drain bomb, then top pin for coins
    {
      walls: [
        { x: 0.10, y: 0.10, w: 0.80, h: 0.03 },  // top
        { x: 0.08, y: 0.10, w: 0.03, h: 0.62 },  // left
        { x: 0.89, y: 0.10, w: 0.03, h: 0.62 },  // right
        { x: 0.42, y: 0.52, w: 0.03, h: 0.20 },  // center bottom divider
        { x: 0.55, y: 0.52, w: 0.03, h: 0.20 },  // center bottom divider R
      ],
      pins: [
        { x: 0.20, y: 0.30, w: 0.60, pullDir: 'right', pulled: 0 },
        { x: 0.20, y: 0.52, w: 0.20, pullDir: 'left', pulled: 0 },
        { x: 0.60, y: 0.52, w: 0.20, pullDir: 'right', pulled: 0 }
      ],
      items: [
        { x: 0.30, y: 0.15, type: 'coin' },
        { x: 0.50, y: 0.15, type: 'candy', candyIdx: 4 },
        { x: 0.70, y: 0.15, type: 'coin' },
        { x: 0.30, y: 0.36, type: 'bomb' },
        { x: 0.50, y: 0.38, type: 'candy', candyIdx: 2 },
        { x: 0.70, y: 0.36, type: 'bomb' },
      ],
      lulu: { x: 0.50, y: 0.76 },
      hint: 'Pull the side pins to drain bombs first!'
    }
  ];
}

// ===== GAME STATE =====
let levels, levelIdx, puzzleX, puzzleY, puzzleW, puzzleH;
let walls, pins, items, luluPos;
let score, gameOver, levelComplete, levelFail;
let particles, floatTexts, frame;
let dragPin, dragStartX;
let transitionTimer, showingResult;
let luluHappy, luluSquash;
let hintAlpha;

function calcPuzzleArea() {
  puzzleW = W * 0.92;
  puzzleH = H * 0.70;
  puzzleX = (W - puzzleW) / 2;
  puzzleY = H * 0.12;
}

function loadLevel(idx) {
  calcPuzzleArea();
  const def = levels[idx];

  walls = def.walls.map(w => ({
    x: puzzleX + w.x * puzzleW,
    y: puzzleY + w.y * puzzleH,
    w: w.w * puzzleW,
    h: w.h * puzzleH
  }));

  pins = def.pins.map(p => ({
    x: puzzleX + p.x * puzzleW,
    y: puzzleY + p.y * puzzleH,
    w: p.w * puzzleW,
    h: 10 * sc,
    pullDir: p.pullDir,
    pulled: 0,       // 0 = in place, 1 = fully pulled
    pulling: false,
    handleR: 10 * sc
  }));

  items = def.items.map(it => ({
    x: puzzleX + it.x * puzzleW,
    y: puzzleY + it.y * puzzleH,
    vx: 0, vy: 0,
    type: it.type,
    candyIdx: it.candyIdx || 0,
    radius: it.type === 'bomb' ? 14 * sc : 12 * sc,
    collected: false,
    active: true,
    rotation: 0
  }));

  luluPos = {
    x: puzzleX + def.lulu.x * puzzleW,
    y: puzzleY + def.lulu.y * puzzleH,
    size: 60 * sc
  };

  levelComplete = false;
  levelFail = false;
  transitionTimer = 0;
  dragPin = null;
  luluHappy = 0;
  luluSquash = 1;
  hintAlpha = 1;
}

function init() {
  levels = makeLevels();
  levelIdx = 0;
  score = 0;
  gameOver = false;
  showingResult = false;
  particles = [];
  floatTexts = [];
  frame = 0;
  loadLevel(0);
  document.getElementById('cta').classList.remove('show');
}

// ===== PHYSICS =====
function rectContains(rx, ry, rw, rh, px, py, pr) {
  return px + pr > rx && px - pr < rx + rw && py + pr > ry && py - pr < ry + rh;
}

function resolveCollision(item, rx, ry, rw, rh) {
  const r = item.radius;
  // Find nearest edge and push out
  const cx = Math.max(rx, Math.min(item.x, rx + rw));
  const cy = Math.max(ry, Math.min(item.y, ry + rh));
  const dx = item.x - cx;
  const dy = item.y - cy;
  const dist = Math.sqrt(dx * dx + dy * dy);

  if (dist < r && dist > 0) {
    const nx = dx / dist;
    const ny = dy / dist;
    item.x = cx + nx * r;
    item.y = cy + ny * r;

    // Bounce
    const dot = item.vx * nx + item.vy * ny;
    item.vx -= 2 * dot * nx * BOUNCE;
    item.vy -= 2 * dot * ny * BOUNCE;

    // Friction
    item.vx *= 0.85;
    item.vy *= 0.85;
    return true;
  }
  return false;
}

function updatePhysics() {
  for (const it of items) {
    if (!it.active) continue;

    // Gravity
    it.vy += GRAVITY * sc;
    it.x += it.vx;
    it.y += it.vy;
    it.rotation += it.vx * 0.02;

    // Collision with walls
    for (const w of walls) {
      if (rectContains(w.x, w.y, w.w, w.h, it.x, it.y, it.radius)) {
        resolveCollision(it, w.x, w.y, w.w, w.h);
      }
    }

    // Collision with pins (only if not pulled)
    for (const p of pins) {
      if (p.pulled >= 0.95) continue; // pin removed
      const pinX = p.x + p.pulled * (p.pullDir === 'right' ? p.w : -p.w);
      const pinW = p.w * (1 - p.pulled);
      const actualX = p.pullDir === 'right' ? p.x : pinX;
      if (rectContains(actualX, p.y, pinW, p.h, it.x, it.y, it.radius)) {
        resolveCollision(it, actualX, p.y, pinW, p.h);
      }
    }

    // Screen bounds
    if (it.x - it.radius < puzzleX) { it.x = puzzleX + it.radius; it.vx = Math.abs(it.vx) * BOUNCE; }
    if (it.x + it.radius > puzzleX + puzzleW) { it.x = puzzleX + puzzleW - it.radius; it.vx = -Math.abs(it.vx) * BOUNCE; }

    // Fell off bottom
    if (it.y > puzzleY + puzzleH + 50 * sc) {
      it.active = false;
    }

    // Check Lulu collision
    const dx = it.x - luluPos.x;
    const dy = it.y - (luluPos.y - luluPos.size * 0.3);
    const hitDist = it.radius + luluPos.size * 0.3;
    if (dx * dx + dy * dy < hitDist * hitDist && !it.collected) {
      it.collected = true;
      it.active = false;
      if (it.type === 'bomb') {
        // Fail!
        levelFail = true;
        luluSquash = 0.6;
        spawnBoomEffect(it.x, it.y);
        floatTexts.push({ x: it.x, y: it.y - 20 * sc, text: 'BOOM!', life: 1.5, color: '#EF5350', size: 24 });
      } else {
        // Collect!
        const pts = it.type === 'coin' ? 50 : 30;
        score += pts;
        luluHappy = 1;
        luluSquash = 0.8;
        spawnCollectEffect(it.x, it.y);
        floatTexts.push({ x: it.x, y: it.y - 20 * sc, text: '+' + pts, life: 1, color: '#FFD700', size: 18 });
      }
    }
  }
}

function checkLevelEnd() {
  if (levelComplete || levelFail) return;

  // Fail: bomb collected
  if (levelFail) return;

  // Check if all collectibles are done
  const collectibles = items.filter(it => it.type !== 'bomb');
  const remaining = collectibles.filter(it => it.active && !it.collected);
  const collected = collectibles.filter(it => it.collected);

  if (remaining.length === 0 && collected.length > 0) {
    levelComplete = true;
  }
}

// ===== EFFECTS =====
function spawnCollectEffect(x, y) {
  for (let i = 0; i < 10; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 2 + Math.random() * 3;
    particles.push({
      x, y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 2,
      life: 1, decay: 0.025 + Math.random() * 0.02,
      size: 3 + Math.random() * 4,
      color: ['#FFD700', '#FF6B9D', '#CE93D8', '#81C784'][Math.floor(Math.random() * 4)]
    });
  }
}

function spawnBoomEffect(x, y) {
  for (let i = 0; i < 20; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 3 + Math.random() * 5;
    particles.push({
      x, y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 2,
      life: 1, decay: 0.02 + Math.random() * 0.015,
      size: 3 + Math.random() * 6,
      color: ['#EF5350', '#FF6B00', '#FFD700', '#333'][Math.floor(Math.random() * 4)]
    });
  }
}

// ===== INPUT =====
function getP(e) {
  if (e.changedTouches) return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY };
  return { x: e.clientX, y: e.clientY };
}

function onDown(e) {
  e.preventDefault();
  if (gameOver || levelComplete || levelFail) return;
  const p = getP(e);
  hintAlpha = 0;

  // Check if tapping on a pin handle
  for (const pin of pins) {
    if (pin.pulled >= 0.95) continue;
    // Handle is at the pull end of the pin
    const hx = pin.pullDir === 'right' ? pin.x + pin.w * (1 - pin.pulled) : pin.x + pin.w * pin.pulled;
    const hy = pin.y + pin.h / 2;
    const dx = p.x - hx, dy = p.y - hy;
    if (Math.sqrt(dx * dx + dy * dy) < 35 * sc) {
      dragPin = pin;
      dragStartX = p.x;
      return;
    }
    // Also check tap anywhere on pin body
    const pinLeft = pin.pullDir === 'right' ? pin.x : pin.x + pin.w * pin.pulled;
    const pinWidth = pin.w * (1 - pin.pulled);
    if (p.x >= pinLeft && p.x <= pinLeft + pinWidth && p.y >= pin.y - 15 * sc && p.y <= pin.y + pin.h + 15 * sc) {
      dragPin = pin;
      dragStartX = p.x;
      return;
    }
  }
}

function onMove(e) {
  e.preventDefault();
  if (!dragPin) return;
  const p = getP(e);
  const dx = p.x - dragStartX;

  if (dragPin.pullDir === 'right' && dx > 0) {
    dragPin.pulled = Math.min(1, dx / dragPin.w);
  } else if (dragPin.pullDir === 'left' && dx < 0) {
    dragPin.pulled = Math.min(1, -dx / dragPin.w);
  }
}

function onUp(e) {
  e.preventDefault();
  if (dragPin) {
    // If pulled more than 40%, snap to fully pulled
    if (dragPin.pulled > 0.4) {
      dragPin.pulled = 1;
    } else {
      dragPin.pulled = 0; // snap back
    }
    dragPin = null;
  }
}

cv.addEventListener('mousedown', onDown);
cv.addEventListener('mousemove', onMove);
cv.addEventListener('mouseup', onUp);
cv.addEventListener('touchstart', onDown, { passive: false });
cv.addEventListener('touchmove', onMove, { passive: false });
cv.addEventListener('touchend', onUp, { passive: false });

// ===== UPDATE =====
function update() {
  frame++;

  if (!levelComplete && !levelFail) {
    updatePhysics();
    checkLevelEnd();
  }

  // Lulu animation
  luluSquash += (1 - luluSquash) * 0.1;
  if (luluHappy > 0) luluHappy -= 0.02;

  // Level transition
  if (levelComplete || levelFail) {
    transitionTimer++;
    if (transitionTimer === 80) {
      if (levelFail) {
        // Retry same level
        loadLevel(levelIdx);
      } else if (levelIdx < levels.length - 1) {
        levelIdx++;
        loadLevel(levelIdx);
      } else {
        // All levels complete!
        gameOver = true;
        if (!showingResult) {
          showingResult = true;
          setTimeout(showResult, 400);
        }
      }
    }
  }

  // Particles
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx; p.y += p.vy; p.vy += 0.08;
    p.life -= p.decay;
    if (p.life <= 0) particles.splice(i, 1);
  }

  // Float texts
  for (let i = floatTexts.length - 1; i >= 0; i--) {
    const ft = floatTexts[i];
    ft.y -= 1; ft.life -= 0.025;
    if (ft.life <= 0) floatTexts.splice(i, 1);
  }
}

// ===== DRAW =====
function drawBg() {
  const g = cx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#F3E5F5');
  g.addColorStop(0.5, '#E1BEE7');
  g.addColorStop(1, '#CE93D8');
  cx.fillStyle = g;
  cx.fillRect(0, 0, W, H);

  // Cute background circles
  cx.globalAlpha = 0.08;
  cx.fillStyle = '#AB47BC';
  for (let i = 0; i < 8; i++) {
    const bx = (i * 137 + frame * 0.1) % (W + 100) - 50;
    const by = (i * 97 + 50) % H;
    cx.beginPath();
    cx.arc(bx, by, 30 + i * 8, 0, Math.PI * 2);
    cx.fill();
  }
  cx.globalAlpha = 1;
}

function drawPuzzleFrame() {
  // Puzzle area background
  const pad = 4 * sc;
  cx.fillStyle = 'rgba(255,255,255,0.4)';
  cx.beginPath();
  cx.roundRect(puzzleX - pad, puzzleY - pad, puzzleW + pad * 2, puzzleH + pad * 2, 16 * sc);
  cx.fill();

  cx.fillStyle = 'rgba(0,0,0,0.06)';
  cx.beginPath();
  cx.roundRect(puzzleX, puzzleY, puzzleW, puzzleH, 14 * sc);
  cx.fill();

  cx.strokeStyle = 'rgba(171,71,188,0.3)';
  cx.lineWidth = 2 * sc;
  cx.beginPath();
  cx.roundRect(puzzleX - pad, puzzleY - pad, puzzleW + pad * 2, puzzleH + pad * 2, 16 * sc);
  cx.stroke();
}

function drawWalls() {
  for (const w of walls) {
    // Rounded kawaii wall
    const g = cx.createLinearGradient(w.x, w.y, w.x, w.y + w.h);
    g.addColorStop(0, '#B39DDB');
    g.addColorStop(1, '#9575CD');
    cx.fillStyle = g;
    cx.beginPath();
    cx.roundRect(w.x, w.y, w.w, w.h, Math.min(w.w, w.h) * 0.3);
    cx.fill();

    // Highlight
    cx.fillStyle = 'rgba(255,255,255,0.2)';
    cx.beginPath();
    cx.roundRect(w.x + 1, w.y + 1, w.w - 2, w.h * 0.4, Math.min(w.w, w.h) * 0.3);
    cx.fill();
  }
}

function drawPins() {
  for (const p of pins) {
    if (p.pulled >= 0.95) continue;

    const visualPulled = p.pulled;
    const pinLeft = p.pullDir === 'right' ? p.x : p.x + p.w * visualPulled;
    const pinWidth = p.w * (1 - visualPulled);

    // Pin body
    const pg = cx.createLinearGradient(pinLeft, p.y, pinLeft, p.y + p.h);
    pg.addColorStop(0, '#FFB74D');
    pg.addColorStop(1, '#FF9800');
    cx.fillStyle = pg;
    cx.beginPath();
    cx.roundRect(pinLeft, p.y, pinWidth, p.h, p.h * 0.4);
    cx.fill();

    // Pin shine
    cx.fillStyle = 'rgba(255,255,255,0.3)';
    cx.beginPath();
    cx.roundRect(pinLeft + 2, p.y + 1, pinWidth - 4, p.h * 0.4, p.h * 0.3);
    cx.fill();

    // Handle (circle at pull end)
    const hx = p.pullDir === 'right' ? pinLeft + pinWidth : pinLeft;
    const hy = p.y + p.h / 2;
    const hr = p.handleR;

    // Handle glow
    const pulse = 0.5 + 0.3 * Math.sin(frame * 0.08);
    cx.globalAlpha = pulse;
    cx.fillStyle = '#FFE082';
    cx.beginPath();
    cx.arc(hx, hy, hr * 1.5, 0, Math.PI * 2);
    cx.fill();
    cx.globalAlpha = 1;

    // Handle
    cx.fillStyle = '#FF6F00';
    cx.beginPath();
    cx.arc(hx, hy, hr, 0, Math.PI * 2);
    cx.fill();

    // Handle highlight
    cx.fillStyle = 'rgba(255,255,255,0.4)';
    cx.beginPath();
    cx.arc(hx - hr * 0.2, hy - hr * 0.2, hr * 0.5, 0, Math.PI * 2);
    cx.fill();

    // Arrow hint on handle
    cx.fillStyle = '#fff';
    cx.font = 'bold ' + (12 * sc) + 'px sans-serif';
    cx.textAlign = 'center';
    cx.textBaseline = 'middle';
    cx.fillText(p.pullDir === 'right' ? '\\u{27A1}' : '\\u{2B05}', hx, hy);
    cx.textBaseline = 'alphabetic';
    cx.textAlign = 'left';
  }
}

function drawItems() {
  for (const it of items) {
    if (!it.active) continue;
    const sz = it.radius * 2;

    if (it.type === 'bomb') {
      // Kawaii bomb
      cx.save();
      cx.translate(it.x, it.y);
      cx.rotate(it.rotation);

      // Body
      cx.fillStyle = '#424242';
      cx.beginPath();
      cx.arc(0, 0, it.radius, 0, Math.PI * 2);
      cx.fill();

      // Highlight
      cx.fillStyle = 'rgba(255,255,255,0.2)';
      cx.beginPath();
      cx.arc(-it.radius * 0.25, -it.radius * 0.25, it.radius * 0.35, 0, Math.PI * 2);
      cx.fill();

      // Fuse
      cx.strokeStyle = '#FF6F00';
      cx.lineWidth = 3 * sc;
      cx.beginPath();
      cx.moveTo(0, -it.radius);
      cx.quadraticCurveTo(it.radius * 0.5, -it.radius * 1.5, it.radius * 0.3, -it.radius * 1.7);
      cx.stroke();

      // Spark
      const sparkAlpha = 0.5 + 0.5 * Math.sin(frame * 0.15);
      cx.globalAlpha = sparkAlpha;
      cx.fillStyle = '#FFEB3B';
      cx.beginPath();
      cx.arc(it.radius * 0.3, -it.radius * 1.7, 3 * sc, 0, Math.PI * 2);
      cx.fill();
      cx.globalAlpha = 1;

      // Kawaii face (X eyes)
      cx.fillStyle = '#EF5350';
      cx.font = 'bold ' + (it.radius * 0.7) + 'px sans-serif';
      cx.textAlign = 'center';
      cx.textBaseline = 'middle';
      cx.fillText('>.<', 0, it.radius * 0.1);
      cx.textBaseline = 'alphabetic';
      cx.textAlign = 'left';

      cx.restore();
    } else if (it.type === 'coin' && IMG.coin) {
      cx.save();
      cx.translate(it.x, it.y);
      cx.rotate(it.rotation);
      cx.drawImage(IMG.coin, -it.radius, -it.radius, sz, sz);
      cx.restore();
    } else if (it.type === 'candy' && IMG.candies) {
      const crop = CANDY_CROP[it.candyIdx % CANDY_CROP.length];
      cx.save();
      cx.translate(it.x, it.y);
      const bob = Math.sin(frame * 0.05 + it.candyIdx) * 0.05;
      cx.rotate(it.rotation + bob);
      cx.drawImage(IMG.candies, crop.x, crop.y, crop.w, crop.h, -it.radius, -it.radius, sz, sz);
      cx.restore();
    }
  }
}

function drawLulu() {
  if (!IMG.chars) return;
  const lx = luluPos.x;
  const ly = luluPos.y;
  const sz = luluPos.size;

  // Shadow
  cx.globalAlpha = 0.15;
  cx.fillStyle = '#000';
  cx.beginPath();
  cx.ellipse(lx, ly + 5 * sc, sz * 0.35, 5 * sc, 0, 0, Math.PI * 2);
  cx.fill();
  cx.globalAlpha = 1;

  // Happy glow
  if (luluHappy > 0) {
    cx.globalAlpha = luluHappy * 0.3;
    cx.fillStyle = '#FFD700';
    cx.beginPath();
    cx.arc(lx, ly - sz * 0.3, sz * 0.6, 0, Math.PI * 2);
    cx.fill();
    cx.globalAlpha = 1;
  }

  // Lulu
  const sw = luluSquash;
  const sh = 2 - sw;
  cx.save();
  cx.translate(lx, ly);
  cx.scale(sw, sh);
  cx.drawImage(IMG.chars, LULU.x, LULU.y, LULU.w, LULU.h, -sz / 2, -sz, sz, sz);
  cx.restore();

  // Fail indicator
  if (levelFail) {
    cx.fillStyle = '#EF5350';
    cx.font = (30 * sc) + 'px sans-serif';
    cx.textAlign = 'center';
    const bob = Math.sin(frame * 0.1) * 3 * sc;
    cx.fillText('\\u{1F4A5}', lx, ly - sz - 5 * sc + bob);
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
    cx.strokeStyle = 'rgba(0,0,0,0.4)';
    cx.lineWidth = 3;
    cx.strokeText(ft.text, ft.x, ft.y);
    cx.fillStyle = ft.color;
    cx.fillText(ft.text, ft.x, ft.y);
  }
  cx.globalAlpha = 1;
  cx.textAlign = 'left';
}

function drawHUD() {
  // Level indicator
  cx.fillStyle = 'rgba(171,71,188,0.3)';
  cx.beginPath();
  cx.roundRect(W / 2 - 55 * sc, 6, 110 * sc, 28 * sc, 14 * sc);
  cx.fill();
  cx.fillStyle = '#7B1FA2';
  cx.font = 'bold ' + (14 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  cx.fillText('Level ' + (levelIdx + 1) + '/' + levels.length, W / 2, 25 * sc);
  cx.textAlign = 'left';

  // Score
  cx.fillStyle = 'rgba(255,255,255,0.6)';
  cx.beginPath();
  cx.roundRect(8, 6, 90 * sc, 28 * sc, 14 * sc);
  cx.fill();
  if (IMG.coin) cx.drawImage(IMG.coin, 12, 9, 20 * sc, 20 * sc);
  cx.fillStyle = '#FF6F00';
  cx.font = 'bold ' + (14 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText(score, 12 + 24 * sc, 25 * sc);

  // Level dots
  const dotY = 40 * sc;
  for (let i = 0; i < levels.length; i++) {
    const dx = W / 2 + (i - 1) * 20 * sc;
    cx.fillStyle = i < levelIdx ? '#4CAF50' : i === levelIdx ? '#FF6B9D' : 'rgba(0,0,0,0.15)';
    cx.beginPath();
    cx.arc(dx, dotY, 5 * sc, 0, Math.PI * 2);
    cx.fill();
  }

  // Hint text
  if (hintAlpha > 0 && levels[levelIdx]) {
    const pulse = 0.5 + 0.4 * Math.sin(frame * 0.06);
    cx.globalAlpha = hintAlpha * pulse;
    cx.fillStyle = '#7B1FA2';
    cx.font = 'bold ' + (12 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    cx.fillText(levels[levelIdx].hint, W / 2, puzzleY + puzzleH + 24 * sc);
    cx.textAlign = 'left';
    cx.globalAlpha = 1;
  }

  // Level complete/fail banner
  if (levelComplete && transitionTimer < 80) {
    const alpha = Math.min(1, transitionTimer / 20);
    cx.globalAlpha = alpha;
    cx.fillStyle = 'rgba(76,175,80,0.8)';
    cx.beginPath();
    cx.roundRect(W * 0.1, H * 0.4, W * 0.8, 60 * sc, 16 * sc);
    cx.fill();
    cx.fillStyle = '#fff';
    cx.font = 'bold ' + (22 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    cx.fillText(levelIdx < levels.length - 1 ? 'SWEET!' : 'ALL CLEAR!', W / 2, H * 0.4 + 38 * sc);
    cx.textAlign = 'left';
    cx.globalAlpha = 1;
  }

  if (levelFail && transitionTimer < 80) {
    const alpha = Math.min(1, transitionTimer / 20);
    cx.globalAlpha = alpha;
    cx.fillStyle = 'rgba(239,83,80,0.8)';
    cx.beginPath();
    cx.roundRect(W * 0.1, H * 0.4, W * 0.8, 60 * sc, 16 * sc);
    cx.fill();
    cx.fillStyle = '#fff';
    cx.font = 'bold ' + (22 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    cx.fillText('TRY AGAIN!', W / 2, H * 0.4 + 38 * sc);
    cx.textAlign = 'left';
    cx.globalAlpha = 1;
  }
}

// ===== RESULT =====
function showResult() {
  const el = document.getElementById('cta');
  document.getElementById('cta-title').textContent = 'YOU DID IT!';
  document.getElementById('cta-title').style.color = '#FFD700';
  document.getElementById('cta-sub').textContent = '3 puzzles solved! Score: ' + score + '\\nCan you solve 100+ more levels?';
  el.classList.add('show');
}

function restart() { init(); }

// ===== MAIN LOOP =====
function loop() {
  update();
  drawBg();
  drawPuzzleFrame();
  drawWalls();
  drawPins();
  drawItems();
  drawLulu();
  drawParticles();
  drawFloatTexts();
  drawHUD();
  requestAnimationFrame(loop);
}

function startApp() {
  init();
  loop();
}
</script>
</body>
</html>`;

const outPath = 'E:/AI/projects/pinpull-playable/output/playable.html';
fs.writeFileSync(outPath, html, 'utf8');
const stats = fs.statSync(outPath);
console.log('Written: ' + outPath);
console.log('File size: ' + (stats.size / 1024).toFixed(1) + ' KB (' + stats.size + ' bytes)');
console.log('Under 5MB: ' + (stats.size < 5242880 ? 'YES' : 'NO'));
console.log('Under 2MB: ' + (stats.size < 2097152 ? 'YES' : 'NO'));
