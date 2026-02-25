const fs = require('fs');
const TMP = process.env.TEMP || process.env.TMP || 'C:/Users/user/AppData/Local/Temp';

function b64(name) { return fs.readFileSync(TMP + '/' + name, 'utf8').trim(); }

const A = {
  chars: b64('idle_chars.b64'),
  coin: b64('idle_coin.b64'),
  tower: b64('idle_tower.b64'),
  tree: b64('idle_tree.b64'),
  bld: b64('idle_bld.b64'),
  castle: b64('idle_castle.b64'),
  star: b64('idle_star.b64')
};

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="ad.size" content="width=320,height=480">
<title>Candy Kingdom - Tap to Build!</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#87CEEB;touch-action:none;user-select:none;-webkit-user-select:none}
canvas{display:block;position:absolute;top:0;left:0}
#cta{display:none;position:absolute;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:10;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#cta.show{display:flex}
#cta-title{font-family:'Segoe UI',Arial,sans-serif;font-size:30px;font-weight:bold;margin-bottom:8px;text-shadow:0 3px 15px rgba(255,200,50,0.5)}
#cta-sub{color:#E0F0FF;font-family:'Segoe UI',Arial,sans-serif;font-size:15px;margin-bottom:6px}
#cta-score{color:#FFD700;font-family:'Segoe UI',Arial,sans-serif;font-size:20px;font-weight:bold;margin-bottom:24px}
#cta-btn{background:linear-gradient(135deg,#FFD700,#FFA000);color:#5D4037;border:none;padding:18px 52px;font-size:22px;font-weight:bold;border-radius:50px;cursor:pointer;animation:pulse 1.4s infinite;font-family:'Segoe UI',Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;box-shadow:0 4px 24px rgba(255,215,0,0.5)}
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
ld('bld', '${A.bld}');
ld('castle', '${A.castle}');
ld('star', '${A.star}');

// Sprite crops from image260.png (1024x559)
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

// ===== NUMBER FORMATTING =====
function fmt(n) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return Math.floor(n).toString();
}

// ===== GAME CONFIG =====
const UPGRADES = [
  { id: 'tap',   name: 'Tap Power',   icon: 'tap',   baseCost: 10,   costMult: 1.8, baseValue: 1,   desc: '+1 per tap' },
  { id: 'auto',  name: 'Auto Miner',  icon: 'auto',  baseCost: 50,   costMult: 2.0, baseValue: 2,   desc: '+2/sec' },
  { id: 'tower', name: 'Guard Tower', icon: 'tower', baseCost: 200,  costMult: 2.2, baseValue: 10,  desc: '+10/sec' },
  { id: 'castle',name: 'Castle',      icon: 'castle',baseCost: 1000, costMult: 2.5, baseValue: 50,  desc: '+50/sec' }
];

const MAX_TIME = 55000; // 55 seconds
const MILESTONES = [100, 500, 2000, 10000, 50000];

// ===== GAME STATE =====
let gold, tapPower, autoGold, totalTapped, frame;
let upgradeLevels, gameOver, startTime;
let particles, flyCoins, floatTexts;
let buildings; // visual buildings on screen
let milestoneIdx, lastMilestone;
let luluBob, luluSquash, luluTapAnim;
let shakeMag;

function init() {
  gold = 0;
  tapPower = 1;
  autoGold = 0;
  totalTapped = 0;
  frame = 0;
  upgradeLevels = [0, 0, 0, 0];
  gameOver = false;
  startTime = Date.now();
  particles = [];
  flyCoins = [];
  floatTexts = [];
  buildings = [];
  milestoneIdx = 0;
  lastMilestone = 0;
  luluBob = 0;
  luluSquash = 1;
  luluTapAnim = 0;
  shakeMag = 0;
  document.getElementById('cta').classList.remove('show');
}

function getUpgradeCost(idx) {
  return Math.floor(UPGRADES[idx].baseCost * Math.pow(UPGRADES[idx].costMult, upgradeLevels[idx]));
}

function buyUpgrade(idx) {
  const cost = getUpgradeCost(idx);
  if (gold < cost) return false;
  gold -= cost;
  upgradeLevels[idx]++;

  if (idx === 0) {
    tapPower = 1 + upgradeLevels[0];
  } else {
    // Recalculate auto gold
    autoGold = 0;
    for (let i = 1; i < UPGRADES.length; i++) {
      autoGold += UPGRADES[i].baseValue * upgradeLevels[i];
    }
  }

  // Add building visual
  if (idx >= 2 && upgradeLevels[idx] <= 5) {
    const bx = 0.15 + Math.random() * 0.7;
    buildings.push({
      type: idx === 2 ? 'tower' : 'castle',
      x: bx,
      scale: 0,
      targetScale: 0.6 + Math.random() * 0.3,
      level: upgradeLevels[idx]
    });
  }

  spawnUpgradeEffect();
  return true;
}

// ===== INPUT =====
function getP(e) {
  if (e.changedTouches) return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY };
  return { x: e.clientX, y: e.clientY };
}

function onTap(e) {
  e.preventDefault();
  if (gameOver) return;
  const p = getP(e);

  // Check upgrade buttons
  const shopY = getShopY();
  if (p.y >= shopY) {
    const btns = getUpgradeButtons();
    for (let i = 0; i < btns.length; i++) {
      const b = btns[i];
      if (p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h) {
        if (buyUpgrade(i)) {
          floatTexts.push({ x: b.x + b.w / 2, y: b.y, text: 'UPGRADED!', life: 1, color: '#4CAF50', size: 14 });
        }
        return;
      }
    }
  }

  // Tap on game area = earn gold
  const earned = tapPower;
  gold += earned;
  totalTapped++;

  // Tap animation
  luluSquash = 0.75;
  luluTapAnim = 1;
  shakeMag = Math.min(3, tapPower * 0.3);

  // Flying coin from tap position
  flyCoins.push({
    x: p.x, y: p.y,
    targetX: 16 + 14 * sc,
    targetY: 14 * sc,
    progress: 0,
    size: 20 + Math.min(10, tapPower) * 2
  });

  // Floating text
  floatTexts.push({ x: p.x, y: p.y - 10, text: '+' + fmt(earned), life: 1, color: '#FFD700', size: 18 + Math.min(8, tapPower) });

  // Tap particles
  for (let i = 0; i < 4 + Math.min(6, tapPower); i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 2 + Math.random() * 3;
    particles.push({
      x: p.x, y: p.y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 2,
      life: 1,
      decay: 0.03 + Math.random() * 0.02,
      size: 2 + Math.random() * 3,
      color: Math.random() > 0.5 ? '#FFD700' : '#FFA000'
    });
  }
}

cv.addEventListener('mousedown', onTap);
cv.addEventListener('touchstart', onTap, { passive: false });
// Prevent scroll
cv.addEventListener('touchmove', e => e.preventDefault(), { passive: false });
cv.addEventListener('mousemove', e => e.preventDefault());
cv.addEventListener('touchend', e => e.preventDefault(), { passive: false });
cv.addEventListener('mouseup', e => e.preventDefault());

// ===== SHOP LAYOUT =====
function getShopY() {
  return H * 0.62;
}

function getUpgradeButtons() {
  const shopY = getShopY();
  const btnH = 52 * sc;
  const gap = 6 * sc;
  const btnW = W - 24;
  const startY = shopY + 32 * sc;

  return UPGRADES.map((u, i) => ({
    x: 12, y: startY + i * (btnH + gap), w: btnW, h: btnH, idx: i
  }));
}

// ===== UPGRADE EFFECT =====
function spawnUpgradeEffect() {
  for (let i = 0; i < 15; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 3 + Math.random() * 4;
    particles.push({
      x: W / 2, y: H * 0.35,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 3,
      life: 1,
      decay: 0.02 + Math.random() * 0.015,
      size: 3 + Math.random() * 5,
      color: ['#FFD700', '#4CAF50', '#42A5F5', '#FF6B9D'][Math.floor(Math.random() * 4)]
    });
  }
}

// ===== UPDATE =====
function update() {
  frame++;

  // Timer
  const elapsed = Date.now() - startTime;
  if (elapsed >= MAX_TIME && !gameOver) {
    gameOver = true;
    setTimeout(showResult, 600);
  }

  // Auto gold (per frame, 60fps assumed)
  if (!gameOver && autoGold > 0) {
    gold += autoGold / 60;
    // Auto income particle (less frequent)
    if (frame % 30 === 0 && autoGold > 0) {
      floatTexts.push({
        x: W / 2 + (Math.random() - 0.5) * 60,
        y: H * 0.45,
        text: '+' + fmt(autoGold / 2),
        life: 0.8,
        color: '#81C784',
        size: 12
      });
    }
  }

  // Milestones
  while (milestoneIdx < MILESTONES.length && gold >= MILESTONES[milestoneIdx]) {
    floatTexts.push({
      x: W / 2, y: H * 0.15,
      text: 'MILESTONE: ' + fmt(MILESTONES[milestoneIdx]) + ' GOLD!',
      life: 2, color: '#FFD700', size: 18
    });
    spawnUpgradeEffect();
    shakeMag = 5;
    milestoneIdx++;
  }

  // Lulu animation
  luluBob += 0.04;
  luluSquash += (1 - luluSquash) * 0.12;
  if (luluTapAnim > 0) luluTapAnim -= 0.05;

  // Building grow animation
  for (const b of buildings) {
    b.scale += (b.targetScale - b.scale) * 0.08;
  }

  // Shake decay
  if (shakeMag > 0) shakeMag *= 0.88;

  // Particles
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx; p.y += p.vy; p.vy += 0.08;
    p.life -= p.decay;
    if (p.life <= 0) particles.splice(i, 1);
  }

  // Flying coins
  for (let i = flyCoins.length - 1; i >= 0; i--) {
    const fc = flyCoins[i];
    fc.progress += 0.04;
    if (fc.progress >= 1) {
      flyCoins.splice(i, 1);
    }
  }

  // Float texts
  for (let i = floatTexts.length - 1; i >= 0; i--) {
    const ft = floatTexts[i];
    ft.y -= 1;
    ft.life -= 0.025;
    if (ft.life <= 0) floatTexts.splice(i, 1);
  }
}

// ===== DRAW =====
function drawSky() {
  const g = cx.createLinearGradient(0, 0, 0, H * 0.65);
  g.addColorStop(0, '#87CEEB');
  g.addColorStop(1, '#E0F7FA');
  cx.fillStyle = g;
  cx.fillRect(0, 0, W, H);
}

function drawGround() {
  const groundY = H * 0.50;
  // Hills
  cx.fillStyle = '#81C784';
  cx.beginPath();
  cx.moveTo(0, groundY + 20 * sc);
  cx.quadraticCurveTo(W * 0.25, groundY - 10 * sc, W * 0.5, groundY + 15 * sc);
  cx.quadraticCurveTo(W * 0.75, groundY + 40 * sc, W, groundY + 10 * sc);
  cx.lineTo(W, H * 0.62);
  cx.lineTo(0, H * 0.62);
  cx.closePath();
  cx.fill();

  // Ground fill
  cx.fillStyle = '#66BB6A';
  cx.fillRect(0, groundY + 20 * sc, W, H * 0.62 - groundY - 20 * sc);

  // Grass edge
  cx.fillStyle = '#A5D660';
  for (let gx = 0; gx < W; gx += 18 * sc) {
    const gy = groundY + 15 * sc + Math.sin(gx * 0.08) * 6 * sc;
    cx.beginPath();
    cx.moveTo(gx - 5 * sc, gy + 5 * sc);
    cx.quadraticCurveTo(gx, gy - 3 * sc, gx + 5 * sc, gy + 5 * sc);
    cx.fill();
  }

  // Flowers
  cx.fillStyle = '#FFE082';
  for (let i = 0; i < 12; i++) {
    const fx = (i * 73 + 20) % W;
    const fy = groundY + 22 * sc + (i * 17) % (20 * sc);
    cx.beginPath();
    cx.arc(fx, fy, 2.5 * sc, 0, Math.PI * 2);
    cx.fill();
  }
}

function drawClouds() {
  cx.fillStyle = 'rgba(255,255,255,0.6)';
  const t = frame * 0.12;
  for (let i = 0; i < 5; i++) {
    const cx_ = ((t * (0.3 + i * 0.1) + i * 180) % (W + 200)) - 80;
    const cy_ = 20 + i * 16 * sc;
    const cw = (50 + i * 12) * sc;
    cx.beginPath();
    cx.ellipse(cx_, cy_, cw * 0.5, 10 * sc, 0, 0, Math.PI * 2);
    cx.fill();
    cx.beginPath();
    cx.ellipse(cx_ - 18 * sc, cy_ - 3 * sc, cw * 0.3, 8 * sc, 0, 0, Math.PI * 2);
    cx.fill();
  }
}

function drawTrees() {
  if (!IMG.tree) return;
  const groundY = H * 0.50;
  const positions = [0.05, 0.88, 0.45, 0.72];
  const sizes = [0.6, 0.5, 0.45, 0.55];
  for (let i = 0; i < positions.length; i++) {
    const tw = 60 * sizes[i] * sc;
    const th = tw * 1.5;
    cx.globalAlpha = 0.7;
    cx.drawImage(IMG.tree, W * positions[i], groundY + 5 * sc - th + Math.sin(frame * 0.015 + i) * 2 * sc, tw, th);
  }
  cx.globalAlpha = 1;
}

function drawBuildings() {
  const groundY = H * 0.50;
  for (const b of buildings) {
    if (b.scale < 0.05) continue;
    const img = b.type === 'tower' ? IMG.tower : IMG.castle;
    if (!img) continue;
    const sz = 55 * b.scale * sc;
    const bx = W * b.x - sz / 2;
    const by = groundY + 10 * sc - sz;

    // Shadow
    cx.globalAlpha = 0.2;
    cx.fillStyle = '#000';
    cx.beginPath();
    cx.ellipse(W * b.x, groundY + 15 * sc, sz * 0.4, 4 * sc, 0, 0, Math.PI * 2);
    cx.fill();
    cx.globalAlpha = 1;

    cx.drawImage(img, bx, by + Math.sin(frame * 0.02 + b.x * 10) * 1.5 * sc, sz, sz);
  }
}

function drawLulu() {
  if (!IMG.chars) return;
  const groundY = H * 0.50;
  const baseX = W * 0.5;
  const baseY = groundY + 8 * sc;
  const sz = 80 * sc;

  // Shadow
  cx.globalAlpha = 0.2;
  cx.fillStyle = '#000';
  cx.beginPath();
  cx.ellipse(baseX, baseY + 2 * sc, sz * 0.3, 5 * sc, 0, 0, Math.PI * 2);
  cx.fill();
  cx.globalAlpha = 1;

  // Lulu with squash & bob
  const bob = Math.sin(luluBob) * 4 * sc;
  const sw = luluSquash;
  const sh = 2 - sw;

  cx.save();
  cx.translate(baseX, baseY + bob);
  cx.scale(sw, sh);

  // Tap glow effect
  if (luluTapAnim > 0) {
    cx.globalAlpha = luluTapAnim * 0.4;
    cx.fillStyle = '#FFD700';
    cx.beginPath();
    cx.arc(0, -sz * 0.5, sz * 0.7 * (1 + luluTapAnim * 0.3), 0, Math.PI * 2);
    cx.fill();
    cx.globalAlpha = 1;
  }

  cx.drawImage(IMG.chars, LULU.x, LULU.y, LULU.w, LULU.h, -sz / 2, -sz, sz, sz);
  cx.restore();

  // "TAP ME" hint when idle
  if (totalTapped < 3) {
    const hintAlpha = 0.4 + 0.4 * Math.sin(frame * 0.08);
    cx.globalAlpha = hintAlpha;
    cx.fillStyle = '#fff';
    cx.font = 'bold ' + (16 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'center';
    cx.fillText('TAP TO EARN!', baseX, groundY - sz - 10 * sc + bob);

    // Bouncing arrow
    const arrowBob = Math.sin(frame * 0.1) * 8 * sc;
    cx.font = (22 * sc) + 'px sans-serif';
    cx.fillText('\\u{1F447}', baseX, groundY - sz + 15 * sc + arrowBob);
    cx.textAlign = 'left';
    cx.globalAlpha = 1;
  }
}

function drawFlyingCoins() {
  if (!IMG.coin) return;
  for (const fc of flyCoins) {
    const t = fc.progress;
    // Bezier curve from tap to HUD
    const mx = (fc.x + fc.targetX) / 2;
    const my = Math.min(fc.y, fc.targetY) - 100 * sc;
    const curX = (1 - t) * (1 - t) * fc.x + 2 * (1 - t) * t * mx + t * t * fc.targetX;
    const curY = (1 - t) * (1 - t) * fc.y + 2 * (1 - t) * t * my + t * t * fc.targetY;
    const sz = fc.size * sc * (1 - t * 0.3);
    cx.globalAlpha = 1 - t * 0.5;
    cx.drawImage(IMG.coin, curX - sz / 2, curY - sz / 2, sz, sz);
  }
  cx.globalAlpha = 1;
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
    cx.strokeStyle = 'rgba(0,0,0,0.5)';
    cx.lineWidth = 3;
    cx.strokeText(ft.text, ft.x, ft.y);
    cx.fillStyle = ft.color;
    cx.fillText(ft.text, ft.x, ft.y);
  }
  cx.globalAlpha = 1;
  cx.textAlign = 'left';
}

function drawHUD() {
  // Gold display
  cx.fillStyle = 'rgba(62,39,35,0.8)';
  cx.beginPath();
  cx.roundRect(8, 6, 150 * sc, 34 * sc, 17 * sc);
  cx.fill();
  if (IMG.coin) cx.drawImage(IMG.coin, 14, 9, 26 * sc, 26 * sc);
  cx.fillStyle = '#FFD700';
  cx.font = 'bold ' + (17 * sc) + 'px "Segoe UI",sans-serif';
  cx.fillText(fmt(gold), 14 + 30 * sc, 30 * sc);

  // Per-second indicator
  if (autoGold > 0) {
    cx.fillStyle = '#81C784';
    cx.font = (10 * sc) + 'px "Segoe UI",sans-serif';
    cx.fillText('+' + fmt(autoGold) + '/s', 14 + 30 * sc, 42 * sc);
  }

  // Timer bar
  const elapsed = Date.now() - startTime;
  const remaining = Math.max(0, 1 - elapsed / MAX_TIME);
  const barW = W - 24;
  const barY = 48 * sc;
  cx.fillStyle = 'rgba(0,0,0,0.3)';
  cx.beginPath();
  cx.roundRect(12, barY, barW, 6 * sc, 3 * sc);
  cx.fill();
  cx.fillStyle = remaining > 0.25 ? '#4CAF50' : '#EF5350';
  cx.beginPath();
  cx.roundRect(12, barY, barW * remaining, 6 * sc, 3 * sc);
  cx.fill();

  // Timer text
  const secsLeft = Math.ceil((MAX_TIME - elapsed) / 1000);
  if (secsLeft > 0 && secsLeft <= 10) {
    cx.fillStyle = '#EF5350';
    cx.font = 'bold ' + (12 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'right';
    cx.fillText(secsLeft + 's', W - 14, barY - 2);
    cx.textAlign = 'left';
  }

  // Tap power indicator
  cx.fillStyle = 'rgba(255,255,255,0.6)';
  cx.font = (10 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'right';
  cx.fillText('Tap: +' + fmt(tapPower), W - 14, 28 * sc);
  cx.textAlign = 'left';
}

function drawShop() {
  const shopY = getShopY();

  // Shop background
  const shopG = cx.createLinearGradient(0, shopY, 0, H);
  shopG.addColorStop(0, '#3E2723');
  shopG.addColorStop(1, '#2A1A16');
  cx.fillStyle = shopG;
  cx.beginPath();
  cx.roundRect(0, shopY, W, H - shopY, [16 * sc, 16 * sc, 0, 0]);
  cx.fill();

  // Shop header
  cx.fillStyle = 'rgba(255,215,0,0.15)';
  cx.fillRect(0, shopY, W, 28 * sc);
  cx.fillStyle = '#FFD700';
  cx.font = 'bold ' + (13 * sc) + 'px "Segoe UI",sans-serif';
  cx.textAlign = 'center';
  cx.fillText('UPGRADES', W / 2, shopY + 19 * sc);
  cx.textAlign = 'left';

  // Upgrade buttons
  const btns = getUpgradeButtons();
  for (let i = 0; i < btns.length; i++) {
    const b = btns[i];
    const u = UPGRADES[i];
    const cost = getUpgradeCost(i);
    const canAfford = gold >= cost;
    const level = upgradeLevels[i];

    // Button bg
    cx.fillStyle = canAfford ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.03)';
    cx.beginPath();
    cx.roundRect(b.x, b.y, b.w, b.h, 10 * sc);
    cx.fill();
    cx.strokeStyle = canAfford ? 'rgba(255,215,0,0.4)' : 'rgba(255,255,255,0.08)';
    cx.lineWidth = canAfford ? 2 : 1;
    cx.beginPath();
    cx.roundRect(b.x, b.y, b.w, b.h, 10 * sc);
    cx.stroke();

    // Icon
    const iconSz = 32 * sc;
    const iconX = b.x + 10;
    const iconY = b.y + (b.h - iconSz) / 2;
    cx.globalAlpha = canAfford ? 1 : 0.4;
    if (u.icon === 'tap') {
      // Draw hand icon
      cx.fillStyle = '#FFD700';
      cx.font = (20 * sc) + 'px sans-serif';
      cx.fillText('\\u{1F44A}', iconX + 2, iconY + iconSz * 0.75);
    } else if (u.icon === 'auto') {
      // Draw pickaxe icon
      cx.fillStyle = '#81C784';
      cx.font = (20 * sc) + 'px sans-serif';
      cx.fillText('\\u26CF', iconX + 2, iconY + iconSz * 0.75);
    } else if (u.icon === 'tower' && IMG.tower) {
      cx.drawImage(IMG.tower, iconX, iconY, iconSz, iconSz);
    } else if (u.icon === 'castle' && IMG.castle) {
      cx.drawImage(IMG.castle, iconX, iconY, iconSz, iconSz);
    }
    cx.globalAlpha = 1;

    // Name + Level
    const textX = b.x + 12 + iconSz + 8;
    cx.fillStyle = canAfford ? '#fff' : '#888';
    cx.font = 'bold ' + (12 * sc) + 'px "Segoe UI",sans-serif';
    cx.fillText(u.name + (level > 0 ? ' Lv.' + level : ''), textX, b.y + 20 * sc);

    // Description
    cx.fillStyle = canAfford ? '#B0B0B0' : '#666';
    cx.font = (9 * sc) + 'px "Segoe UI",sans-serif';
    cx.fillText(u.desc, textX, b.y + 34 * sc);

    // Cost
    const costX = b.x + b.w - 10;
    if (IMG.coin) {
      const csz = 16 * sc;
      cx.globalAlpha = canAfford ? 1 : 0.4;
      cx.drawImage(IMG.coin, costX - 55 * sc, b.y + 12 * sc, csz, csz);
      cx.globalAlpha = 1;
    }
    cx.fillStyle = canAfford ? '#FFD700' : '#666';
    cx.font = 'bold ' + (13 * sc) + 'px "Segoe UI",sans-serif';
    cx.textAlign = 'right';
    cx.fillText(fmt(cost), costX - 6, b.y + 26 * sc);

    // Affordable glow
    if (canAfford) {
      const glowAlpha = 0.1 + 0.05 * Math.sin(frame * 0.06 + i);
      cx.fillStyle = 'rgba(255,215,0,' + glowAlpha + ')';
      cx.beginPath();
      cx.roundRect(b.x, b.y, b.w, b.h, 10 * sc);
      cx.fill();
    }

    cx.textAlign = 'left';
  }
}

// ===== RESULT =====
function showResult() {
  const el = document.getElementById('cta');
  document.getElementById('cta-title').textContent = 'KINGDOM BUILT!';
  document.getElementById('cta-title').style.color = '#FFD700';
  document.getElementById('cta-sub').textContent = 'You earned ' + fmt(gold) + ' gold in 55 seconds!';
  document.getElementById('cta-score').textContent = totalTapped + ' taps | ' + buildings.length + ' buildings';
  el.classList.add('show');
}

function restart() { init(); }

// ===== MAIN LOOP =====
function loop() {
  update();

  cx.save();
  if (shakeMag > 0.1) {
    cx.translate(
      (Math.random() - 0.5) * shakeMag * sc,
      (Math.random() - 0.5) * shakeMag * sc
    );
  }

  drawSky();
  drawClouds();
  drawGround();
  drawTrees();
  drawBuildings();
  drawLulu();
  drawFlyingCoins();
  drawParticles();
  drawFloatTexts();
  drawHUD();
  drawShop();

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

const outPath = 'E:/AI/projects/idle-playable/output/playable.html';
fs.writeFileSync(outPath, html, 'utf8');
const stats = fs.statSync(outPath);
console.log('Written: ' + outPath);
console.log('File size: ' + (stats.size / 1024).toFixed(1) + ' KB (' + stats.size + ' bytes)');
console.log('Under 5MB: ' + (stats.size < 5242880 ? 'YES' : 'NO'));
console.log('Under 2MB: ' + (stats.size < 2097152 ? 'YES' : 'NO'));
