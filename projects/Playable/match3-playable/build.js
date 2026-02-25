const fs = require('fs');
const TMP = process.env.TEMP || process.env.TMP || 'C:/Users/user/AppData/Local/Temp';

function b64(name) { return fs.readFileSync(TMP + '/' + name, 'utf8').trim(); }

const A = {
  candies: b64('m3_candies.b64'),
  coin: b64('m3_coin.b64'),
  star: b64('m3_star.b64')
};

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="ad.size" content="width=320,height=480">
<title>Candy Match - Play Now!</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#2D1B4E;touch-action:none;user-select:none;-webkit-user-select:none}
canvas{display:block;position:absolute;top:0;left:0}
#cta{display:none;position:absolute;top:0;left:0;width:100%;height:100%;background:rgba(30,15,50,0.92);z-index:10;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#cta.show{display:flex}
#cta-title{font-family:'Segoe UI',Arial,sans-serif;font-size:32px;font-weight:bold;margin-bottom:8px;text-shadow:0 3px 15px rgba(255,200,50,0.5)}
#cta-sub{color:#E0C0FF;font-family:'Segoe UI',Arial,sans-serif;font-size:15px;margin-bottom:6px}
#cta-score{color:#FFD700;font-family:'Segoe UI',Arial,sans-serif;font-size:22px;font-weight:bold;margin-bottom:24px}
#cta-btn{background:linear-gradient(135deg,#FF6B9D,#C850C0,#4158D0);color:#fff;border:none;padding:18px 52px;font-size:22px;font-weight:bold;border-radius:50px;cursor:pointer;animation:pulse 1.4s infinite;font-family:'Segoe UI',Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;box-shadow:0 4px 24px rgba(200,80,192,0.5)}
#cta-btn:active{transform:scale(0.95)}
#cta-retry{color:#C0A0E0;font-family:'Segoe UI',Arial,sans-serif;font-size:13px;margin-top:16px;cursor:pointer;text-decoration:underline}
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

// ===== ASSETS =====
const IMG = {};
let loaded = 0, total = 3;
function ld(k, d) {
  const i = new Image();
  i.onload = i.onerror = () => { IMG[k] = i; loaded++; if (loaded >= total) startApp(); };
  i.src = 'data:image/png;base64,' + d;
}
ld('candies', '${A.candies}');
ld('coin', '${A.coin}');
ld('star', '${A.star}');

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

// ===== CANDY SPRITE CROPS (from image261.png 1024x559) =====
const CANDY_CROP = [
  { x: 20,  y: 120, w: 170, h: 230 },  // 0: strawberry (pink)
  { x: 215, y: 120, w: 170, h: 230 },  // 1: clover (green)
  { x: 405, y: 115, w: 175, h: 230 },  // 2: bubble (blue)
  { x: 595, y: 120, w: 170, h: 240 },  // 3: honeydrop (yellow)
  { x: 790, y: 140, w: 200, h: 210 }   // 4: macaron (orange)
];
const CANDY_COLORS = ['#FF6B9D', '#66BB6A', '#42A5F5', '#FFCA28', '#FF8A65'];
const CANDY_NAMES = ['Strawberry', 'Clover', 'Bubble', 'Honey', 'Macaron'];
const NUM_TYPES = 5;

// ===== GRID CONFIG =====
const COLS = 7, ROWS = 8;
let cellSz, gridOX, gridOY;

function calcGrid() {
  cellSz = Math.min((W - 40) / COLS, (H * 0.58) / ROWS) * 0.95;
  gridOX = (W - COLS * cellSz) / 2;
  gridOY = H * 0.18;
}

// ===== GAME STATE =====
let board, score, moves, maxMoves, gameOver, frame;
let selected, swapping, falling, checking;
let particles, floatingTexts;
let combo, tutHint, shakeMag, shakeTimer;
let animQueue; // animation queue

// Board cell: { type, x, y, targetX, targetY, scale, alpha, removing, spawning }

function init() {
  calcGrid();
  score = 0;
  moves = 0;
  maxMoves = 25;
  gameOver = false;
  frame = 0;
  selected = null;
  swapping = null;
  falling = false;
  checking = false;
  combo = 0;
  tutHint = true;
  shakeMag = 0;
  shakeTimer = 0;
  particles = [];
  floatingTexts = [];
  animQueue = [];

  // Init board with no initial matches
  board = [];
  for (let c = 0; c < COLS; c++) {
    board[c] = [];
    for (let r = 0; r < ROWS; r++) {
      let type;
      do {
        type = Math.floor(Math.random() * NUM_TYPES);
      } while (
        (c >= 2 && board[c-1][r] && board[c-2][r] && board[c-1][r].type === type && board[c-2][r].type === type) ||
        (r >= 2 && board[c][r-1] && board[c][r-2] && board[c][r-1].type === type && board[c][r-2].type === type)
      );
      const px = gridOX + c * cellSz + cellSz / 2;
      const py = gridOY + r * cellSz + cellSz / 2;
      board[c][r] = { type, x: px, y: py, targetX: px, targetY: py, scale: 1, alpha: 1, removing: false, spawning: false };
    }
  }
  document.getElementById('cta').classList.remove('show');
}

// ===== INPUT =====
let touchDown = false, touchStartC = -1, touchStartR = -1;

function screenToGrid(sx, sy) {
  const c = Math.floor((sx - gridOX) / cellSz);
  const r = Math.floor((sy - gridOY) / cellSz);
  if (c >= 0 && c < COLS && r >= 0 && r < ROWS) return { c, r };
  return null;
}

function getP(e) {
  if (e.changedTouches) return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY };
  return { x: e.clientX, y: e.clientY };
}

function onDown(e) {
  e.preventDefault();
  if (gameOver || swapping || falling || checking) return;
  const p = getP(e);
  const g = screenToGrid(p.x, p.y);
  if (!g) return;

  tutHint = false;
  touchDown = true;
  touchStartC = g.c;
  touchStartR = g.r;

  if (selected && (selected.c !== g.c || selected.r !== g.r)) {
    // Check if adjacent
    const dc = Math.abs(selected.c - g.c);
    const dr = Math.abs(selected.r - g.r);
    if ((dc === 1 && dr === 0) || (dc === 0 && dr === 1)) {
      trySwap(selected.c, selected.r, g.c, g.r);
      selected = null;
      return;
    }
  }
  selected = { c: g.c, r: g.r };
}

function onMove(e) {
  e.preventDefault();
  if (!touchDown || swapping || falling || checking || gameOver) return;
  const p = getP(e);
  const g = screenToGrid(p.x, p.y);
  if (!g) return;

  // Swipe detection
  const dc = g.c - touchStartC;
  const dr = g.r - touchStartR;
  if (Math.abs(dc) + Math.abs(dr) === 1) {
    trySwap(touchStartC, touchStartR, g.c, g.r);
    selected = null;
    touchDown = false;
  }
}

function onUp(e) {
  e.preventDefault();
  touchDown = false;
}

cv.addEventListener('mousedown', onDown);
cv.addEventListener('mousemove', onMove);
cv.addEventListener('mouseup', onUp);
cv.addEventListener('touchstart', onDown, { passive: false });
cv.addEventListener('touchmove', onMove, { passive: false });
cv.addEventListener('touchend', onUp, { passive: false });

// ===== SWAP LOGIC =====
function trySwap(c1, r1, c2, r2) {
  if (moves >= maxMoves) return;

  // Animate swap
  swapping = { c1, r1, c2, r2, progress: 0, checking: false };
}

function commitSwap(c1, r1, c2, r2) {
  const tmp = board[c1][r1];
  board[c1][r1] = board[c2][r2];
  board[c2][r2] = tmp;
  // Update target positions
  updateTargets();
}

function updateTargets() {
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      if (!board[c][r]) continue;
      board[c][r].targetX = gridOX + c * cellSz + cellSz / 2;
      board[c][r].targetY = gridOY + r * cellSz + cellSz / 2;
    }
  }
}

// ===== MATCH DETECTION =====
function findMatches() {
  const matched = new Set();

  // Horizontal
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS - 2; c++) {
      if (!board[c][r] || !board[c+1][r] || !board[c+2][r]) continue;
      if (board[c][r].type === board[c+1][r].type && board[c+1][r].type === board[c+2][r].type) {
        matched.add(c + ',' + r);
        matched.add((c+1) + ',' + r);
        matched.add((c+2) + ',' + r);
        // Extend
        let ext = c + 3;
        while (ext < COLS && board[ext][r] && board[ext][r].type === board[c][r].type) {
          matched.add(ext + ',' + r);
          ext++;
        }
      }
    }
  }

  // Vertical
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS - 2; r++) {
      if (!board[c][r] || !board[c][r+1] || !board[c][r+2]) continue;
      if (board[c][r].type === board[c][r+1].type && board[c][r+1].type === board[c][r+2].type) {
        matched.add(c + ',' + r);
        matched.add(c + ',' + (r+1));
        matched.add(c + ',' + (r+2));
        let ext = r + 3;
        while (ext < ROWS && board[c][ext] && board[c][ext].type === board[c][r].type) {
          matched.add(c + ',' + ext);
          ext++;
        }
      }
    }
  }

  return matched;
}

function removeMatches(matched) {
  const pts = matched.size * 10 * (1 + combo * 0.5);
  score += Math.floor(pts);

  for (const key of matched) {
    const [c, r] = key.split(',').map(Number);
    const cell = board[c][r];
    if (cell) {
      // Particles
      spawnMatchParticles(cell.x, cell.y, CANDY_COLORS[cell.type]);
      board[c][r] = null;
    }
  }

  // Floating score text
  if (matched.size > 0) {
    const keys = [...matched];
    const mid = keys[Math.floor(keys.length / 2)].split(',').map(Number);
    const fx = gridOX + mid[0] * cellSz + cellSz / 2;
    const fy = gridOY + mid[1] * cellSz + cellSz / 2;
    const label = combo > 0 ? 'x' + (combo + 1) + ' COMBO!' : '+' + Math.floor(pts);
    const color = combo > 0 ? '#FFD700' : CANDY_COLORS[board[mid[0]] ? 0 : 0];
    floatingTexts.push({ x: fx, y: fy, text: label, life: 1, color: combo > 0 ? '#FFD700' : '#fff', size: combo > 0 ? 20 : 16 });
  }

  if (matched.size >= 4) {
    shakeMag = 4;
    shakeTimer = 12;
  }

  combo++;
}

function applyGravity() {
  let fell = false;
  for (let c = 0; c < COLS; c++) {
    for (let r = ROWS - 1; r >= 0; r--) {
      if (board[c][r] === null) {
        // Find nearest non-null above
        for (let above = r - 1; above >= 0; above--) {
          if (board[c][above] !== null) {
            board[c][r] = board[c][above];
            board[c][above] = null;
            fell = true;
            break;
          }
        }
      }
    }
    // Fill empty spots at top with new candies
    for (let r = 0; r < ROWS; r++) {
      if (board[c][r] === null) {
        const type = Math.floor(Math.random() * NUM_TYPES);
        const px = gridOX + c * cellSz + cellSz / 2;
        const py = gridOY - (ROWS - r) * cellSz; // start above screen
        board[c][r] = { type, x: px, y: py, targetX: px, targetY: 0, scale: 1, alpha: 1, removing: false, spawning: true };
        fell = true;
      }
    }
  }
  updateTargets();
  return fell;
}

// ===== CHECK FOR POSSIBLE MOVES =====
function hasPossibleMoves() {
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      // Try swap right
      if (c < COLS - 1) {
        swapCells(c, r, c+1, r);
        if (findMatches().size > 0) { swapCells(c, r, c+1, r); return true; }
        swapCells(c, r, c+1, r);
      }
      // Try swap down
      if (r < ROWS - 1) {
        swapCells(c, r, c, r+1);
        if (findMatches().size > 0) { swapCells(c, r, c, r+1); return true; }
        swapCells(c, r, c, r+1);
      }
    }
  }
  return false;
}

function swapCells(c1, r1, c2, r2) {
  const tmp = board[c1][r1];
  board[c1][r1] = board[c2][r2];
  board[c2][r2] = tmp;
}

function shuffleBoard() {
  // Collect all types
  const types = [];
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      if (board[c][r]) types.push(board[c][r].type);
    }
  }
  // Fisher-Yates shuffle
  for (let i = types.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [types[i], types[j]] = [types[j], types[i]];
  }
  let idx = 0;
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      if (board[c][r]) {
        board[c][r].type = types[idx++];
      }
    }
  }
  updateTargets();
  floatingTexts.push({ x: W / 2, y: H / 2, text: 'SHUFFLE!', life: 1.5, color: '#FFD700', size: 28 });
}

// ===== PARTICLES =====
function spawnMatchParticles(x, y, color) {
  for (let i = 0; i < 8; i++) {
    const angle = (Math.PI * 2 / 8) * i + Math.random() * 0.3;
    const speed = 2 + Math.random() * 3;
    particles.push({
      x, y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 1,
      life: 1,
      decay: 0.025 + Math.random() * 0.015,
      size: 3 + Math.random() * 4,
      color,
      type: 'circle'
    });
  }
  // Star particles
  for (let i = 0; i < 3; i++) {
    particles.push({
      x: x + (Math.random() - 0.5) * 20,
      y: y + (Math.random() - 0.5) * 20,
      vx: (Math.random() - 0.5) * 2,
      vy: -1 - Math.random() * 2,
      life: 1,
      decay: 0.02,
      size: 8 + Math.random() * 6,
      color: '#FFD700',
      type: 'star'
    });
  }
}

// ===== ANIMATION UPDATE =====
let stateTimer = 0;
const STATE_IDLE = 0, STATE_SWAPPING = 1, STATE_REMOVING = 2, STATE_FALLING = 3, STATE_CHECKING = 4;
let gameState = STATE_IDLE;

function update() {
  frame++;

  // Animate board cells toward targets
  let allSettled = true;
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      const cell = board[c][r];
      if (!cell) continue;
      const dx = cell.targetX - cell.x;
      const dy = cell.targetY - cell.y;
      if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) {
        cell.x += dx * 0.2;
        cell.y += dy * 0.2;
        allSettled = false;
      } else {
        cell.x = cell.targetX;
        cell.y = cell.targetY;
      }
      if (cell.spawning) {
        cell.scale += (1 - cell.scale) * 0.15;
        if (Math.abs(cell.scale - 1) < 0.02) { cell.scale = 1; cell.spawning = false; }
      }
    }
  }

  // Swap animation
  if (swapping) {
    const sw = swapping;
    sw.progress += 0.08;
    if (sw.progress >= 1) {
      sw.progress = 1;
      if (!sw.checking) {
        commitSwap(sw.c1, sw.r1, sw.c2, sw.r2);
        const matches = findMatches();
        if (matches.size > 0) {
          moves++;
          combo = 0;
          removeMatches(matches);
          swapping = null;
          stateTimer = 15;
          gameState = STATE_REMOVING;
        } else {
          // Swap back
          sw.checking = true;
          sw.progress = 0;
          commitSwap(sw.c1, sw.r1, sw.c2, sw.r2); // swap back
        }
      } else {
        swapping = null;
        gameState = STATE_IDLE;
      }
    } else {
      // Animate positions during swap
      const a = board[sw.c1][sw.r1];
      const b = board[sw.c2][sw.r2];
      if (a && b) {
        const t = sw.checking ? 1 - sw.progress : sw.progress;
        const ax = gridOX + sw.c1 * cellSz + cellSz / 2;
        const ay = gridOY + sw.r1 * cellSz + cellSz / 2;
        const bx = gridOX + sw.c2 * cellSz + cellSz / 2;
        const by = gridOY + sw.r2 * cellSz + cellSz / 2;
        a.x = ax + (bx - ax) * t;
        a.y = ay + (by - ay) * t;
        b.x = bx + (ax - bx) * t;
        b.y = by + (ay - by) * t;
      }
    }
    return;
  }

  // State machine for cascades
  if (gameState === STATE_REMOVING) {
    stateTimer--;
    if (stateTimer <= 0) {
      applyGravity();
      gameState = STATE_FALLING;
      stateTimer = 20;
    }
  } else if (gameState === STATE_FALLING) {
    stateTimer--;
    if (stateTimer <= 0 && allSettled) {
      const matches = findMatches();
      if (matches.size > 0) {
        removeMatches(matches);
        stateTimer = 15;
        gameState = STATE_REMOVING;
      } else {
        combo = 0;
        gameState = STATE_IDLE;
        // Check game over
        if (moves >= maxMoves) {
          gameOver = true;
          setTimeout(showResult, 800);
        } else if (!hasPossibleMoves()) {
          shuffleBoard();
        }
      }
    }
  }

  // Particles
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx;
    p.y += p.vy;
    p.vy += 0.06;
    p.life -= p.decay;
    if (p.life <= 0) particles.splice(i, 1);
  }

  // Floating texts
  for (let i = floatingTexts.length - 1; i >= 0; i--) {
    const ft = floatingTexts[i];
    ft.y -= 1.2;
    ft.life -= 0.02;
    if (ft.life <= 0) floatingTexts.splice(i, 1);
  }

  // Screen shake
  if (shakeTimer > 0) {
    shakeTimer--;
    shakeMag *= 0.85;
  }
}

// ===== DRAW =====
function drawBg() {
  const g = cx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#1A0A30');
  g.addColorStop(0.4, '#2D1B4E');
  g.addColorStop(1, '#1A1040');
  cx.fillStyle = g;
  cx.fillRect(0, 0, W, H);

  // Subtle stars
  cx.fillStyle = 'rgba(255,255,255,0.3)';
  for (let i = 0; i < 30; i++) {
    const sx = (i * 137.5 + frame * 0.05) % W;
    const sy = (i * 97.3 + Math.sin(frame * 0.01 + i) * 3) % (H * 0.3);
    const ss = 1 + Math.sin(frame * 0.03 + i * 2) * 0.5;
    cx.beginPath();
    cx.arc(sx, sy, ss, 0, Math.PI * 2);
    cx.fill();
  }
}

function drawGridBg() {
  // Grid panel
  const pad = 6 * sc;
  cx.fillStyle = 'rgba(255,255,255,0.06)';
  cx.beginPath();
  cx.roundRect(gridOX - pad, gridOY - pad, COLS * cellSz + pad * 2, ROWS * cellSz + pad * 2, 12 * sc);
  cx.fill();
  cx.strokeStyle = 'rgba(255,255,255,0.12)';
  cx.lineWidth = 1.5;
  cx.beginPath();
  cx.roundRect(gridOX - pad, gridOY - pad, COLS * cellSz + pad * 2, ROWS * cellSz + pad * 2, 12 * sc);
  cx.stroke();

  // Cell backgrounds
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      const x = gridOX + c * cellSz;
      const y = gridOY + r * cellSz;
      const isLight = (c + r) % 2 === 0;
      cx.fillStyle = isLight ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)';
      cx.fillRect(x + 1, y + 1, cellSz - 2, cellSz - 2);
    }
  }

  // Selected highlight
  if (selected && gameState === STATE_IDLE && !swapping) {
    const sx = gridOX + selected.c * cellSz;
    const sy = gridOY + selected.r * cellSz;
    const pulse = 0.3 + 0.15 * Math.sin(frame * 0.1);
    cx.strokeStyle = 'rgba(255,215,0,' + pulse + ')';
    cx.lineWidth = 3 * sc;
    cx.beginPath();
    cx.roundRect(sx + 2, sy + 2, cellSz - 4, cellSz - 4, 6 * sc);
    cx.stroke();
  }
}

function drawCandy(cell) {
  if (!cell || !IMG.candies) return;
  const crop = CANDY_CROP[cell.type];
  const sz = cellSz * 0.82 * cell.scale;

  cx.globalAlpha = cell.alpha;
  cx.drawImage(IMG.candies, crop.x, crop.y, crop.w, crop.h, cell.x - sz / 2, cell.y - sz / 2, sz, sz);
  cx.globalAlpha = 1;
}

function drawBoard() {
  // Draw all cells sorted by row for proper layering
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      drawCandy(board[c][r]);
    }
  }
}

function drawParticles() {
  for (const p of particles) {
    cx.globalAlpha = p.life;
    if (p.type === 'star' && IMG.star) {
      const sz = p.size * p.life * sc;
      cx.drawImage(IMG.star, p.x - sz / 2, p.y - sz / 2, sz, sz);
    } else {
      cx.fillStyle = p.color;
      cx.beginPath();
      cx.arc(p.x, p.y, p.size * p.life * sc, 0, Math.PI * 2);
      cx.fill();
    }
  }
  cx.globalAlpha = 1;
}

function drawFloatingTexts() {
  for (const ft of floatingTexts) {
    cx.globalAlpha = Math.min(1, ft.life * 2);
    cx.fillStyle = ft.color;
    cx.font = 'bold ' + (ft.size * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    cx.strokeStyle = 'rgba(0,0,0,0.5)';
    cx.lineWidth = 3;
    cx.strokeText(ft.text, ft.x, ft.y);
    cx.fillText(ft.text, ft.x, ft.y);
  }
  cx.globalAlpha = 1;
  cx.textAlign = 'left';
}

function drawHUD() {
  // Score panel
  cx.fillStyle = 'rgba(0,0,0,0.4)';
  cx.beginPath();
  cx.roundRect(10, 8, 130 * sc, 32 * sc, 16 * sc);
  cx.fill();
  if (IMG.coin) cx.drawImage(IMG.coin, 16, 11, 24 * sc, 24 * sc);
  cx.fillStyle = '#FFD700';
  cx.font = 'bold ' + (16 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText(score, 16 + 28 * sc, 28 * sc);

  // Moves panel
  cx.fillStyle = 'rgba(0,0,0,0.4)';
  const mvX = W - 120 * sc;
  cx.beginPath();
  cx.roundRect(mvX, 8, 112 * sc, 32 * sc, 16 * sc);
  cx.fill();
  cx.fillStyle = moves >= maxMoves - 3 ? '#EF5350' : '#E0C0FF';
  cx.font = 'bold ' + (14 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'right';
  cx.fillText((maxMoves - moves) + ' moves', W - 16, 28 * sc);
  cx.textAlign = 'left';

  // Title
  cx.fillStyle = '#E0C0FF';
  cx.font = 'bold ' + (11 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  cx.fillText('CANDY MATCH', W / 2, 28 * sc);
  cx.textAlign = 'left';

  // Moves bar
  const barW = COLS * cellSz;
  const barX = gridOX;
  const barY = gridOY - 14 * sc;
  cx.fillStyle = 'rgba(255,255,255,0.1)';
  cx.beginPath();
  cx.roundRect(barX, barY, barW, 6 * sc, 3 * sc);
  cx.fill();
  const pct = Math.max(0, 1 - moves / maxMoves);
  const barColor = pct > 0.3 ? '#C850C0' : '#EF5350';
  cx.fillStyle = barColor;
  cx.beginPath();
  cx.roundRect(barX, barY, barW * pct, 6 * sc, 3 * sc);
  cx.fill();
}

function drawTutorial() {
  if (!tutHint || moves > 0) return;
  cx.globalAlpha = 0.4 + 0.4 * Math.sin(frame * 0.06);
  cx.fillStyle = '#fff';
  cx.font = 'bold ' + (14 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  cx.fillText('Swipe to match 3+ candies!', W / 2, gridOY + ROWS * cellSz + 28 * sc);

  // Hand icon hint - point to a random cell
  const hx = gridOX + 3 * cellSz + cellSz / 2;
  const hy = gridOY + 3 * cellSz + cellSz / 2;
  const offX = Math.sin(frame * 0.05) * 15 * sc;
  cx.font = (24 * sc) + 'px sans-serif';
  cx.fillText('\\u{1F449}', hx + offX, hy + 5 * sc);
  cx.textAlign = 'left';
  cx.globalAlpha = 1;
}

function drawBottomDecor() {
  // Decorative bottom panel
  const panelY = gridOY + ROWS * cellSz + 10 * sc;
  const panelH = H - panelY;
  if (panelH <= 0) return;

  const g = cx.createLinearGradient(0, panelY, 0, H);
  g.addColorStop(0, 'rgba(200,80,192,0.15)');
  g.addColorStop(1, 'rgba(65,88,208,0.1)');
  cx.fillStyle = g;
  cx.fillRect(0, panelY, W, panelH);

  // Tip text
  if (!gameOver) {
    cx.fillStyle = 'rgba(224,192,255,0.5)';
    cx.font = (10 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    if (combo > 1) {
      cx.fillStyle = '#FFD700';
      cx.font = 'bold ' + (14 * sc) + 'px "Segoe UI",sans-serif';
      cx.fillText(combo + 'x COMBO!', W / 2, panelY + 30 * sc);
    } else {
      cx.fillText('Match 4+ for bonus points!', W / 2, panelY + 30 * sc);
    }
    cx.textAlign = 'left';
  }
}

// ===== RESULT =====
function showResult() {
  const el = document.getElementById('cta');
  const title = document.getElementById('cta-title');
  const sub = document.getElementById('cta-sub');
  const scoreEl = document.getElementById('cta-score');

  if (score >= 300) {
    title.textContent = 'SWEET VICTORY!';
    title.style.color = '#FFD700';
    sub.textContent = 'You\\'re a candy master!';
  } else {
    title.textContent = 'TIME\\'S UP!';
    title.style.color = '#FF6B9D';
    sub.textContent = 'Can you beat your score?';
  }
  scoreEl.textContent = 'Score: ' + score;
  el.classList.add('show');
}

function restart() { init(); }

// ===== MAIN LOOP =====
function loop() {
  update();

  cx.save();
  // Screen shake
  if (shakeTimer > 0) {
    cx.translate(
      (Math.random() - 0.5) * shakeMag * sc,
      (Math.random() - 0.5) * shakeMag * sc
    );
  }

  drawBg();
  drawGridBg();
  drawBoard();
  drawParticles();
  drawFloatingTexts();
  drawHUD();
  drawTutorial();
  drawBottomDecor();

  cx.restore();
  requestAnimationFrame(loop);
}

function startApp() {
  init();
  loop();
}
</script>
</body>
</html>`;

const outPath = 'E:/AI/projects/match3-playable/output/playable.html';
fs.writeFileSync(outPath, html, 'utf8');
const stats = fs.statSync(outPath);
console.log('Written: ' + outPath);
console.log('File size: ' + (stats.size / 1024).toFixed(1) + ' KB (' + stats.size + ' bytes)');
console.log('Under 5MB: ' + (stats.size < 5242880 ? 'YES' : 'NO'));
console.log('Under 2MB: ' + (stats.size < 2097152 ? 'YES' : 'NO'));
