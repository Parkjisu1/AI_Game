const fs = require('fs');

// Read base64 encoded assets
const TMP = process.env.TEMP || process.env.TMP || 'C:/Users/user/AppData/Local/Temp';
const img260 = fs.readFileSync(TMP + '/img260.b64', 'utf8').trim();
const img261 = fs.readFileSync(TMP + '/img261.b64', 'utf8').trim();
const coin = fs.readFileSync(TMP + '/coin.b64', 'utf8').trim();
const tree = fs.readFileSync(TMP + '/tree.b64', 'utf8').trim();
const building = fs.readFileSync(TMP + '/building.b64', 'utf8').trim();
const island = fs.readFileSync(TMP + '/island.b64', 'utf8').trim();

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="ad.size" content="width=320,height=480">
<title>Candy Runner - Play Now!</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#FFF0E0;touch-action:none;user-select:none;-webkit-user-select:none}
canvas{display:block;position:absolute;top:0;left:0}
#cta-overlay{display:none;position:absolute;top:0;left:0;width:100%;height:100%;background:rgba(255,240,224,0.92);z-index:10;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#cta-overlay.show{display:flex}
#cta-title{color:#E06090;font-family:'Segoe UI',Arial,sans-serif;font-size:32px;font-weight:bold;text-shadow:0 2px 8px rgba(224,96,144,0.3);margin-bottom:6px}
#cta-sub{color:#A070C0;font-family:'Segoe UI',Arial,sans-serif;font-size:16px;margin-bottom:6px}
#cta-score{color:#70A050;font-family:'Segoe UI',Arial,sans-serif;font-size:20px;font-weight:bold;margin-bottom:24px}
#cta-btn{background:linear-gradient(135deg,#FF8CAA,#E060A0);color:#fff;border:none;padding:18px 50px;font-size:22px;font-weight:bold;border-radius:50px;cursor:pointer;animation:pulse 1.5s infinite;font-family:'Segoe UI',Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;box-shadow:0 4px 20px rgba(224,96,144,0.4)}
#cta-btn:active{transform:scale(0.95)}
#cta-retry{color:#A070C0;font-family:'Segoe UI',Arial,sans-serif;font-size:14px;margin-top:18px;cursor:pointer;text-decoration:underline;opacity:0.7}
@keyframes pulse{0%,100%{transform:scale(1);box-shadow:0 4px 20px rgba(224,96,144,0.4)}50%{transform:scale(1.06);box-shadow:0 6px 30px rgba(224,96,144,0.6)}}
</style>
</head>
<body>
<canvas id="gc"></canvas>
<div id="cta-overlay">
  <div id="cta-title">CANDY RUNNER</div>
  <div id="cta-sub">Help Lulu collect all the candies!</div>
  <div id="cta-score"></div>
  <button id="cta-btn" onclick="window.open('https://play.google.com/store','_blank')">INSTALL NOW</button>
  <div id="cta-retry" onclick="restartGame()">Tap to retry</div>
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

// ========== ASSET LOADING ==========
const ASSETS = {};
let assetsLoaded = 0;
const TOTAL_ASSETS = 6;

function loadImg(key, src) {
  const img = new Image();
  img.onload = () => { ASSETS[key] = img; assetsLoaded++; if(assetsLoaded >= TOTAL_ASSETS) initGame(); };
  img.onerror = () => { assetsLoaded++; if(assetsLoaded >= TOTAL_ASSETS) initGame(); };
  img.src = src;
}

loadImg('chars', 'data:image/png;base64,${img260}');
loadImg('candies', 'data:image/png;base64,${img261}');
loadImg('coin', 'data:image/png;base64,${coin}');
loadImg('tree', 'data:image/png;base64,${tree}');
loadImg('building', 'data:image/png;base64,${building}');
loadImg('island', 'data:image/png;base64,${island}');

// ========== SPRITE CROP DEFINITIONS ==========
// image260: 1024x559 - Lulu (left), Bearon (right)
const SPRITE = {
  lulu:    { x: 30,  y: 60,  w: 430, h: 480 },
  bearon:  { x: 530, y: 20,  w: 470, h: 530 },
  // image261: 1024x559 - 5 candy pieces
  strawberry: { x: 20,  y: 120, w: 170, h: 230 },
  clover:     { x: 215, y: 120, w: 170, h: 230 },
  bubble:     { x: 405, y: 115, w: 175, h: 230 },
  honeydrop:  { x: 595, y: 120, w: 170, h: 240 },
  macaron:    { x: 790, y: 140, w: 200, h: 210 }
};
const CANDY_KEYS = ['strawberry','clover','bubble','honeydrop','macaron'];

// ========== CONFIG ==========
const CFG = {
  gravity: 0.55,
  jumpForce: -11.5,
  groundY: 0.78,
  playerX: 0.16,
  baseSpeed: 3.5,
  maxSpeed: 8,
  speedInc: 0.002,
  obstacleMinGap: 100,
  obstacleMaxGap: 180,
  cloudCount: 6,
  particleCount: 12,
  ctaDelay: 900,
  maxPlayTime: 55000
};

// ========== CANVAS ==========
const canvas = document.getElementById('gc');
const ctx = canvas.getContext('2d');
let W, H, scale, groundLevel;

function resize() {
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
  scale = Math.min(W / 400, H / 700);
  groundLevel = H * CFG.groundY;
}
resize();
window.addEventListener('resize', resize);

// ========== COLORS ==========
const PAL = {
  skyTop: '#FFE8D0',
  skyBot: '#FFF5EA',
  ground: '#8BC34A',
  groundDark: '#6B9B30',
  groundLight: '#A5D660',
  grass: '#4CAF50',
  pink: '#FF8CAA',
  purple: '#B070D0',
  textDark: '#6B4040',
  textLight: '#FFF',
  scoreColor: '#E06090'
};

// ========== GAME STATE ==========
let player, obstacles, particles, clouds, bgTrees, bgIslands;
let speed, score, gameOver, gameStarted, startTime;
let nextObstacleIn, frameCount, highScore = 0;
let groundOffset = 0;

// ========== CLOUDS ==========
function initClouds() {
  clouds = [];
  for (let i = 0; i < CFG.cloudCount; i++) {
    clouds.push({
      x: Math.random() * W * 1.5,
      y: 30 + Math.random() * (groundLevel * 0.35),
      w: 60 + Math.random() * 80,
      h: 25 + Math.random() * 25,
      speed: 0.3 + Math.random() * 0.5,
      alpha: 0.4 + Math.random() * 0.3
    });
  }
}

function initBgElements() {
  bgTrees = [];
  for (let i = 0; i < 5; i++) {
    bgTrees.push({
      x: W * 0.2 + Math.random() * W * 1.2,
      scale: 0.4 + Math.random() * 0.4,
      speed: 0.8 + Math.random() * 0.6
    });
  }
  bgIslands = [];
  for (let i = 0; i < 2; i++) {
    bgIslands.push({
      x: W * 0.5 + Math.random() * W,
      scale: 0.3 + Math.random() * 0.2,
      speed: 0.4 + Math.random() * 0.3
    });
  }
}

// ========== PLAYER ==========
function createPlayer() {
  return {
    x: W * CFG.playerX,
    y: groundLevel - 60 * scale,
    w: 55 * scale,
    h: 60 * scale,
    vy: 0,
    onGround: true,
    jumpCount: 0,
    maxJumps: 2,
    bobPhase: 0,
    squash: 1,
    squashV: 0
  };
}

// ========== INIT ==========
function initGame() {
  player = createPlayer();
  obstacles = [];
  particles = [];
  speed = CFG.baseSpeed;
  score = 0;
  gameOver = false;
  gameStarted = false;
  startTime = 0;
  nextObstacleIn = 80;
  frameCount = 0;
  groundOffset = 0;
  initClouds();
  initBgElements();
  document.getElementById('cta-overlay').classList.remove('show');
  requestAnimationFrame(loop);
}

// ========== SPAWN OBSTACLES ==========
function spawnObstacle() {
  const r = Math.random();
  if (r < 0.3) {
    // Bearon obstacle
    obstacles.push({
      type: 'bearon',
      x: W + 30,
      y: groundLevel - 65 * scale,
      w: 55 * scale,
      h: 65 * scale,
      scored: false,
      bobPhase: Math.random() * Math.PI * 2
    });
  } else if (r < 0.5) {
    // Building obstacle
    obstacles.push({
      type: 'building',
      x: W + 30,
      y: groundLevel - 50 * scale,
      w: 50 * scale,
      h: 50 * scale,
      scored: false
    });
  } else if (r < 0.7) {
    // Floating candy (collectible)
    const candyIdx = Math.floor(Math.random() * CANDY_KEYS.length);
    obstacles.push({
      type: 'candy',
      candyKey: CANDY_KEYS[candyIdx],
      x: W + 30,
      y: groundLevel - (80 + Math.random() * 80) * scale,
      w: 35 * scale,
      h: 35 * scale,
      phase: Math.random() * Math.PI * 2,
      collected: false
    });
  } else if (r < 0.85) {
    // Star coin
    obstacles.push({
      type: 'coin',
      x: W + 30,
      y: groundLevel - (60 + Math.random() * 100) * scale,
      w: 30 * scale,
      h: 30 * scale,
      phase: Math.random() * Math.PI * 2,
      collected: false
    });
  } else {
    // Double obstacle - Bearon + floating candy above
    obstacles.push({
      type: 'bearon',
      x: W + 30,
      y: groundLevel - 65 * scale,
      w: 55 * scale,
      h: 65 * scale,
      scored: false,
      bobPhase: Math.random() * Math.PI * 2
    });
    const candyIdx = Math.floor(Math.random() * CANDY_KEYS.length);
    obstacles.push({
      type: 'candy',
      candyKey: CANDY_KEYS[candyIdx],
      x: W + 55,
      y: groundLevel - 150 * scale,
      w: 35 * scale,
      h: 35 * scale,
      phase: Math.random() * Math.PI * 2,
      collected: false
    });
  }
}

// ========== PARTICLES ==========
function emitParticles(x, y, color, count, sizeBase) {
  for (let i = 0; i < count; i++) {
    particles.push({
      x, y,
      vx: (Math.random() - 0.5) * 6,
      vy: (Math.random() - 0.5) * 6 - 2,
      life: 1,
      decay: 0.02 + Math.random() * 0.03,
      size: (sizeBase || 3) + Math.random() * 3,
      color
    });
  }
}

// ========== INPUT ==========
function handleInput() {
  if (gameOver) return;
  if (!gameStarted) {
    gameStarted = true;
    startTime = Date.now();
  }
  if (player.jumpCount < player.maxJumps) {
    player.vy = CFG.jumpForce * scale;
    player.onGround = false;
    player.jumpCount++;
    player.squash = 0.7;
    player.squashV = 0;
    emitParticles(player.x + player.w/2, player.y + player.h, '#A5D660', 5, 2);
  }
}

canvas.addEventListener('mousedown', e => { e.preventDefault(); handleInput(); });
canvas.addEventListener('touchstart', e => { e.preventDefault(); handleInput(); }, {passive:false});

// ========== COLLISION ==========
function hitTest(a, b) {
  const s = 6 * scale;
  return a.x+s < b.x+b.w-s && a.x+a.w-s > b.x+s && a.y+s < b.y+b.h-s && a.y+a.h-s > b.y+s;
}

// ========== UPDATE ==========
function update() {
  frameCount++;
  if (!gameStarted) return;

  if (Date.now() - startTime > CFG.maxPlayTime) { triggerGameOver(); return; }

  if (speed < CFG.maxSpeed) speed += CFG.speedInc;

  // Player physics
  player.vy += CFG.gravity * scale;
  player.y += player.vy;
  player.bobPhase += 0.06;

  // Squash & stretch
  player.squash += (1 - player.squash) * 0.15;

  if (player.y >= groundLevel - player.h) {
    if (!player.onGround && player.vy > 3) {
      player.squash = 1.3; // squash on land
      emitParticles(player.x + player.w/2, groundLevel, '#A5D660', 4, 2);
    }
    player.y = groundLevel - player.h;
    player.vy = 0;
    player.onGround = true;
    player.jumpCount = 0;
  }

  // Ground scroll
  groundOffset = (groundOffset + speed * scale) % (30 * scale);

  // Clouds
  clouds.forEach(c => {
    c.x -= c.speed * (speed / CFG.baseSpeed);
    if (c.x + c.w < -20) { c.x = W + 50 + Math.random()*100; c.y = 30+Math.random()*(groundLevel*0.35); }
  });

  // Background trees
  bgTrees.forEach(t => {
    t.x -= t.speed * (speed / CFG.baseSpeed);
    if (t.x < -100) { t.x = W + 50 + Math.random()*200; }
  });
  bgIslands.forEach(t => {
    t.x -= t.speed * (speed / CFG.baseSpeed);
    if (t.x < -200) { t.x = W + 100 + Math.random()*300; }
  });

  // Spawn
  nextObstacleIn--;
  if (nextObstacleIn <= 0) {
    spawnObstacle();
    nextObstacleIn = (CFG.obstacleMinGap + Math.random()*(CFG.obstacleMaxGap - CFG.obstacleMinGap)) / (speed/CFG.baseSpeed);
  }

  // Update obstacles
  for (let i = obstacles.length-1; i >= 0; i--) {
    const o = obstacles[i];
    o.x -= speed * scale;

    if (o.type === 'candy' && !o.collected) {
      o.phase += 0.04;
      o.y += Math.sin(o.phase) * 0.5;
    }
    if (o.type === 'coin' && !o.collected) {
      o.phase += 0.06;
    }
    if (o.type === 'bearon') {
      o.bobPhase += 0.03;
    }

    if (o.x + o.w < -50) { obstacles.splice(i, 1); continue; }

    // Collect candy
    if (o.type === 'candy' && !o.collected && hitTest(player, o)) {
      o.collected = true;
      score += 30;
      emitParticles(o.x+o.w/2, o.y+o.h/2, '#FFD700', 8, 3);
      emitParticles(o.x+o.w/2, o.y+o.h/2, '#FF8CAA', 5, 2);
      obstacles.splice(i, 1);
      continue;
    }

    // Collect coin
    if (o.type === 'coin' && !o.collected && hitTest(player, o)) {
      o.collected = true;
      score += 50;
      emitParticles(o.x+o.w/2, o.y+o.h/2, '#FFD700', 10, 4);
      obstacles.splice(i, 1);
      continue;
    }

    // Score for passing hazards
    if ((o.type === 'bearon' || o.type === 'building') && !o.scored && o.x+o.w < player.x) {
      o.scored = true;
      score += 10;
    }

    // Collision with hazards
    if ((o.type === 'bearon' || o.type === 'building') && hitTest(player, o)) {
      triggerGameOver();
      return;
    }
  }

  // Particles
  for (let i = particles.length-1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx; p.y += p.vy; p.vy += 0.1;
    p.life -= p.decay;
    if (p.life <= 0) particles.splice(i, 1);
  }
}

// ========== GAME OVER ==========
function triggerGameOver() {
  gameOver = true;
  if (score > highScore) highScore = score;
  emitParticles(player.x+player.w/2, player.y+player.h/2, '#FF8CAA', CFG.particleCount, 4);
  emitParticles(player.x+player.w/2, player.y+player.h/2, '#FFD700', CFG.particleCount, 3);
  setTimeout(() => {
    const ov = document.getElementById('cta-overlay');
    document.getElementById('cta-score').textContent = 'Score: ' + score + (highScore > score ? '  |  Best: ' + highScore : '  ★ NEW BEST!');
    ov.classList.add('show');
  }, CFG.ctaDelay);
}

function restartGame() {
  player = createPlayer();
  obstacles = [];
  particles = [];
  speed = CFG.baseSpeed;
  score = 0;
  gameOver = false;
  gameStarted = true;
  startTime = Date.now();
  nextObstacleIn = 80;
  groundOffset = 0;
  document.getElementById('cta-overlay').classList.remove('show');
}

// ========== DRAW HELPERS ==========
function drawSprite(imgKey, sprDef, dx, dy, dw, dh) {
  const img = ASSETS[imgKey];
  if (!img) return;
  ctx.drawImage(img, sprDef.x, sprDef.y, sprDef.w, sprDef.h, dx, dy, dw, dh);
}

function drawFullImg(imgKey, dx, dy, dw, dh) {
  const img = ASSETS[imgKey];
  if (!img) return;
  ctx.drawImage(img, dx, dy, dw, dh);
}

// ========== DRAW ==========
function drawSky() {
  const grad = ctx.createLinearGradient(0, 0, 0, groundLevel);
  grad.addColorStop(0, PAL.skyTop);
  grad.addColorStop(1, PAL.skyBot);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, groundLevel);
}

function drawClouds() {
  clouds.forEach(c => {
    ctx.globalAlpha = c.alpha;
    ctx.fillStyle = '#fff';
    // Fluffy cloud shape
    const cx = c.x + c.w/2, cy = c.y + c.h/2;
    ctx.beginPath();
    ctx.ellipse(cx, cy, c.w/2, c.h/2, 0, 0, Math.PI*2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(cx - c.w*0.25, cy - c.h*0.15, c.w*0.3, c.h*0.4, 0, 0, Math.PI*2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(cx + c.w*0.2, cy - c.h*0.1, c.w*0.25, c.h*0.35, 0, 0, Math.PI*2);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
}

function drawBgElements() {
  // Islands (far background)
  bgIslands.forEach(t => {
    const iw = 512 * t.scale * scale;
    const ih = 322 * t.scale * scale;
    ctx.globalAlpha = 0.5;
    drawFullImg('island', t.x, groundLevel - ih * 0.6, iw, ih);
  });
  ctx.globalAlpha = 1;

  // Trees (mid background)
  bgTrees.forEach(t => {
    const tw = 128 * t.scale * scale;
    const th = 184 * t.scale * scale;
    ctx.globalAlpha = 0.7;
    drawFullImg('tree', t.x, groundLevel - th + 5, tw, th);
  });
  ctx.globalAlpha = 1;
}

function drawGround() {
  // Main ground
  ctx.fillStyle = PAL.ground;
  ctx.fillRect(0, groundLevel, W, H - groundLevel);

  // Top edge highlight
  ctx.fillStyle = PAL.groundLight;
  ctx.fillRect(0, groundLevel, W, 4 * scale);

  // Grass tufts
  ctx.fillStyle = PAL.grass;
  const grassStep = 25 * scale;
  for (let gx = -groundOffset; gx < W + grassStep; gx += grassStep) {
    const gh = 6 + Math.sin(gx * 0.1) * 3;
    ctx.beginPath();
    ctx.moveTo(gx - 4*scale, groundLevel);
    ctx.quadraticCurveTo(gx, groundLevel - gh*scale, gx + 4*scale, groundLevel);
    ctx.fill();
  }

  // Ground pattern dots (flowers)
  const dotStep = 50 * scale;
  for (let dx = -groundOffset*0.7; dx < W + dotStep; dx += dotStep) {
    for (let dy = groundLevel + 15*scale; dy < H; dy += 30*scale) {
      const flowerX = dx + Math.sin(dy*0.3) * 10;
      ctx.globalAlpha = 0.3;
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      ctx.arc(flowerX, dy, 2*scale, 0, Math.PI*2);
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;

  // Darker bottom
  const gGrad = ctx.createLinearGradient(0, groundLevel, 0, H);
  gGrad.addColorStop(0, 'rgba(0,0,0,0)');
  gGrad.addColorStop(1, 'rgba(0,0,0,0.15)');
  ctx.fillStyle = gGrad;
  ctx.fillRect(0, groundLevel, W, H - groundLevel);
}

function drawPlayer() {
  if (!ASSETS.chars) return;
  const p = player;
  const cx = p.x + p.w/2;
  const cy = p.y + p.h/2;

  // Shadow
  ctx.globalAlpha = 0.2;
  ctx.fillStyle = '#000';
  const shadowY = groundLevel - 2;
  const shadowScale = 1 - Math.min(0.5, (shadowY - (p.y+p.h)) / (H*0.3));
  ctx.beginPath();
  ctx.ellipse(cx, shadowY, p.w*0.4*shadowScale, 4*scale*shadowScale, 0, 0, Math.PI*2);
  ctx.fill();
  ctx.globalAlpha = 1;

  // Squash & stretch + bob
  const bob = player.onGround ? Math.sin(player.bobPhase) * 3 * scale : 0;
  const sw = player.squash;
  const sh = 2 - sw; // inverse for stretch

  ctx.save();
  ctx.translate(cx, p.y + p.h + bob);
  ctx.scale(sw, sh);
  drawSprite('chars', SPRITE.lulu, -p.w/2, -p.h, p.w, p.h);
  ctx.restore();
}

function drawObstacles() {
  obstacles.forEach(o => {
    if (o.type === 'bearon') {
      // Shadow
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = '#000';
      ctx.beginPath();
      ctx.ellipse(o.x+o.w/2, groundLevel-1, o.w*0.35, 3*scale, 0, 0, Math.PI*2);
      ctx.fill();
      ctx.globalAlpha = 1;

      // Bearon with slight bob
      const bob = Math.sin(o.bobPhase) * 2 * scale;
      if (ASSETS.chars) {
        drawSprite('chars', SPRITE.bearon, o.x - 5*scale, o.y + bob - 5*scale, o.w + 10*scale, o.h + 10*scale);
      }
    }
    else if (o.type === 'building') {
      // Shadow
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = '#000';
      ctx.beginPath();
      ctx.ellipse(o.x+o.w/2, groundLevel-1, o.w*0.4, 3*scale, 0, 0, Math.PI*2);
      ctx.fill();
      ctx.globalAlpha = 1;
      drawFullImg('building', o.x, o.y, o.w, o.h);
    }
    else if (o.type === 'candy' && !o.collected) {
      const cx = o.x + o.w/2, cy = o.y + o.h/2;
      // Glow
      ctx.globalAlpha = 0.25;
      ctx.fillStyle = '#FFD700';
      ctx.beginPath();
      ctx.arc(cx, cy, o.w*0.7, 0, Math.PI*2);
      ctx.fill();
      ctx.globalAlpha = 1;
      // Candy sprite with gentle scale pulse
      const pulseS = 1 + Math.sin(o.phase) * 0.08;
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(pulseS, pulseS);
      const spr = SPRITE[o.candyKey];
      if (ASSETS.candies && spr) {
        drawSprite('candies', spr, -o.w/2, -o.h/2, o.w, o.h);
      }
      ctx.restore();
    }
    else if (o.type === 'coin' && !o.collected) {
      const cx = o.x + o.w/2, cy = o.y + o.h/2;
      // Glow
      ctx.globalAlpha = 0.2;
      ctx.fillStyle = '#FFD700';
      ctx.beginPath();
      ctx.arc(cx, cy, o.w*0.8, 0, Math.PI*2);
      ctx.fill();
      ctx.globalAlpha = 1;
      // Coin with spin illusion (scale x)
      const scX = Math.abs(Math.cos(o.phase));
      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(scX, 1);
      drawFullImg('coin', -o.w/2, -o.h/2, o.w, o.h);
      ctx.restore();
    }
  });
}

function drawParticles() {
  particles.forEach(p => {
    ctx.globalAlpha = p.life;
    ctx.fillStyle = p.color;
    ctx.beginPath();
    // Star-shaped particles
    const r = p.size * p.life;
    ctx.arc(p.x, p.y, r, 0, Math.PI*2);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
}

function drawHUD() {
  // Score badge
  const badgeW = 140 * scale;
  const badgeH = 34 * scale;
  const badgeX = 10, badgeY = 10;

  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.beginPath();
  ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 17*scale);
  ctx.fill();

  ctx.fillStyle = PAL.scoreColor;
  ctx.font = 'bold ' + (16*scale) + 'px "Segoe UI",Arial,sans-serif';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  // Draw mini coin icon
  if (ASSETS.coin) {
    drawFullImg('coin', badgeX + 6, badgeY + 3, badgeH - 6, badgeH - 6);
  }
  ctx.fillText('' + score, badgeX + badgeH + 4, badgeY + badgeH/2 + 1);

  // Speed bar
  const speedPct = (speed - CFG.baseSpeed) / (CFG.maxSpeed - CFG.baseSpeed);
  const barW = 80 * scale;
  const barX = W - barW - 15, barY = 18;
  ctx.fillStyle = 'rgba(255,255,255,0.5)';
  ctx.beginPath();
  ctx.roundRect(barX, barY, barW, 8*scale, 4*scale);
  ctx.fill();
  ctx.fillStyle = PAL.pink;
  ctx.beginPath();
  ctx.roundRect(barX, barY, barW * speedPct, 8*scale, 4*scale);
  ctx.fill();
  ctx.fillStyle = PAL.textDark;
  ctx.font = (9*scale) + 'px "Segoe UI",Arial,sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('SPEED', barX + barW/2, barY - 4);

  // Timer
  if (gameStarted && !gameOver) {
    const elapsed = Date.now() - startTime;
    const remaining = Math.max(0, 1 - elapsed / CFG.maxPlayTime);
    const tBarW = W - 30;
    const tBarY = badgeY + badgeH + 8;
    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.beginPath();
    ctx.roundRect(15, tBarY, tBarW, 4*scale, 2*scale);
    ctx.fill();
    ctx.fillStyle = remaining > 0.3 ? PAL.purple : '#F44';
    ctx.beginPath();
    ctx.roundRect(15, tBarY, tBarW * remaining, 4*scale, 2*scale);
    ctx.fill();
  }

  // Double jump hint
  if (!player.onGround && player.jumpCount < player.maxJumps) {
    ctx.fillStyle = 'rgba(176,112,208,0.6)';
    ctx.font = (11*scale) + 'px "Segoe UI",Arial,sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('TAP FOR DOUBLE JUMP!', W/2, H * 0.12);
  }
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
}

function drawStartScreen() {
  // Title
  ctx.fillStyle = PAL.pink;
  ctx.font = 'bold ' + (34*scale) + 'px "Segoe UI",Arial,sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('CANDY RUNNER', W/2, H * 0.22);

  // Subtitle
  ctx.fillStyle = PAL.purple;
  ctx.font = (15*scale) + 'px "Segoe UI",Arial,sans-serif';
  ctx.fillText('Help Lulu collect candies!', W/2, H * 0.28);

  // Lulu preview
  if (ASSETS.chars) {
    const prevW = 90 * scale, prevH = 100 * scale;
    const bob = Math.sin(frameCount * 0.04) * 5 * scale;
    drawSprite('chars', SPRITE.lulu, W/2 - prevW/2, H*0.33 + bob, prevW, prevH);
  }

  // Tap to start
  ctx.globalAlpha = 0.5 + 0.5 * Math.sin(frameCount * 0.06);
  ctx.fillStyle = PAL.textDark;
  ctx.font = 'bold ' + (18*scale) + 'px "Segoe UI",Arial,sans-serif';
  ctx.fillText('TAP TO START', W/2, H * 0.56);
  ctx.globalAlpha = 1;

  // Controls
  ctx.fillStyle = 'rgba(107,64,64,0.5)';
  ctx.font = (11*scale) + 'px "Segoe UI",Arial,sans-serif';
  ctx.fillText('Tap to jump  |  Double tap for double jump', W/2, H * 0.62);
  ctx.textAlign = 'left';
}

// ========== MAIN DRAW ==========
function draw() {
  drawSky();
  drawClouds();
  drawBgElements();
  drawGround();
  drawObstacles();
  drawParticles();
  if (!gameOver) drawPlayer();
  if (gameStarted && !gameOver) drawHUD();
  if (!gameStarted) drawStartScreen();
}

// ========== LOOP ==========
function loop() {
  update();
  draw();
  requestAnimationFrame(loop);
}
</script>
</body>
</html>`;

const outPath = 'E:/AI/projects/scifi-runner-playable/output/playable.html';
fs.writeFileSync(outPath, html, 'utf8');

const stats = fs.statSync(outPath);
console.log('Written: ' + outPath);
console.log('File size: ' + (stats.size / 1024).toFixed(1) + ' KB (' + stats.size + ' bytes)');
console.log('Under 5MB: ' + (stats.size < 5242880 ? 'YES' : 'NO'));
