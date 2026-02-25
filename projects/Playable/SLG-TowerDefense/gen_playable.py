#!/usr/bin/env python3
"""HTML5 Playable Ad Generator - SLG Tower Defense"""
import base64, os, sys

ASSETS_DIR = r"E:\AI\projects\SLG-TowerDefense\assets"
OUTPUT_FILE = r"E:\AI\projects\SLG-TowerDefense\output\playable.html"

def b64(filename):
    path = os.path.join(ASSETS_DIR, filename)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")

print("Encoding assets...")
MAP      = b64("Map_2048.png")
NPC      = b64("NPC_Summon_001_D.png")
MOB      = b64("MOB_Cactus01_red_D.png")
BOSS_TEX = b64("MOB_Boss_Cactus_Crown_D.png")
ARROW    = b64("Arrow.png")
BUTTON   = b64("Button.png")
COIN     = b64("Coin.png")
STAR     = b64("Effect_Star_1.png")
HP       = b64("HPSlider.png")
SHADOW   = b64("Shadow.png")
TOWER    = b64("TowerA.png")
VPAD     = b64("VirtualPad.png")
VPADBACK = b64("VirtualPadBack.png")
WALL     = b64("WallA.png")
print("Assets encoded. Building HTML...")

HTML = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>SLG Tower Defense - Playable Ad</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#000;display:flex;justify-content:center;align-items:center;width:100vw;height:100vh;overflow:hidden;}}
canvas{{display:block;touch-action:none;}}
#cta-overlay{{
  display:none;position:fixed;top:0;left:0;width:100%;height:100%;
  background:rgba(0,0,0,0.88);
  justify-content:center;align-items:center;flex-direction:column;
  z-index:100;
}}
#cta-overlay.show{{display:flex;}}
.cta-box{{
  background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);
  border:3px solid #ffd700;border-radius:20px;padding:30px 40px;
  text-align:center;max-width:320px;width:80%;
  box-shadow:0 0 40px rgba(255,215,0,0.4);
}}
.cta-title{{color:#ffd700;font-family:Arial Black,Impact,sans-serif;font-size:22px;font-weight:900;letter-spacing:1px;margin-bottom:8px;text-shadow:0 0 10px rgba(255,215,0,0.8);}}
.cta-subtitle{{color:#ccc;font-family:Arial,sans-serif;font-size:13px;margin-bottom:22px;line-height:1.5;}}
.cta-btn{{
  background:linear-gradient(180deg,#ff4444,#cc0000);
  color:#ffd700;font-family:Arial Black,Impact,sans-serif;
  font-size:20px;font-weight:900;letter-spacing:2px;
  border:3px solid #ffd700;border-radius:12px;
  padding:16px 40px;cursor:pointer;width:100%;
  text-shadow:0 1px 2px rgba(0,0,0,0.5);
  box-shadow:0 0 20px rgba(255,68,68,0.6);
  animation:pulse 1.2s ease-in-out infinite;
}}
.cta-btn:hover{{transform:scale(1.05);}}
@keyframes pulse{{
  0%,100%{{box-shadow:0 0 20px rgba(255,215,0,0.6);transform:scale(1);}}
  50%{{box-shadow:0 0 40px rgba(255,215,0,1);transform:scale(1.04);}}
}}
.wave-stars{{color:#ffd700;font-size:28px;margin-bottom:10px;}}
</style>
</head>
<body>
<canvas id="game"></canvas>
<div id="cta-overlay">
  <div class="cta-box">
    <div class="wave-stars" id="cta-stars">&#9733;&#9733;&#9733;</div>
    <div class="cta-title">CAN YOU SURVIVE ALL WAVES?</div>
    <div class="cta-subtitle">Build your fortress &amp; command your hero!<br>Download now and play for FREE!</div>
    <button class="cta-btn" onclick="openCTA()">INSTALL NOW</button>
  </div>
</div>
<script>
(function(){{
"use strict";

// ─── CTA URL ───
const CTA_URL = "https://example.com";
function openCTA(){{
  if(typeof mraid !== 'undefined'){{ mraid.open(CTA_URL); }}
  else{{ window.open(CTA_URL,'_blank'); }}
}}
window.openCTA = openCTA;

// ─── Canvas Setup ───
const DESIGN_W = 540, DESIGN_H = 960;
const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
canvas.width = DESIGN_W; canvas.height = DESIGN_H;

function resize(){{
  const scaleX = window.innerWidth / DESIGN_W;
  const scaleY = window.innerHeight / DESIGN_H;
  const scale = Math.min(scaleX, scaleY);
  canvas.style.width  = DESIGN_W * scale + 'px';
  canvas.style.height = DESIGN_H * scale + 'px';
}}
window.addEventListener('resize', resize); resize();

// ─── Asset Images ───
function loadImg(b64){{
  const img = new Image();
  img.src = 'data:image/png;base64,' + b64;
  return img;
}}
const IMG = {{
  map:      loadImg("{MAP}"),
  npc:      loadImg("{NPC}"),
  mob:      loadImg("{MOB}"),
  boss_tex: loadImg("{BOSS_TEX}"),
  arrow:    loadImg("{ARROW}"),
  button:   loadImg("{BUTTON}"),
  coin:     loadImg("{COIN}"),
  star:     loadImg("{STAR}"),
  hp:       loadImg("{HP}"),
  shadow:   loadImg("{SHADOW}"),
  tower:    loadImg("{TOWER}"),
  vpad:     loadImg("{VPAD}"),
  vpadback: loadImg("{VPADBACK}"),
  wall:     loadImg("{WALL}"),
}};

// ─── Config ───
const CFG = {{
  heroR: 22, // hero radius
  heroHp: 100, heroAtk: 15, heroSpeed: 120,
  autoRange: 150, attackCd: 0.5,
  projSpeed: 300, projR: 6,
  joystickBaseR: 60, joystickKnobR: 28,
  joystickX: 110, joystickY: 820,
  wallY: 95,
  bgScrollSpeed: 20,
}};

// ─── Game State ───
let state = 'title'; // title | wave_playing | upgrade_select | victory | cta
let wave = 0;
let timer = 0;
let totalTimer = 0;
let titleTimer = 0;
let victoryTimer = 0;
let ctaShown = false;

// ─── Hero ───
let hero = {{
  x: DESIGN_W/2, y: DESIGN_H * 0.55,
  hp: CFG.heroHp, maxHp: CFG.heroHp,
  atk: CFG.heroAtk, speed: CFG.heroSpeed,
  attackCd: 0, spinAttack: false,
  flashTimer: 0,
}};

// ─── Enemies ───
let enemies = [];
let spawnQueue = [];
let spawnTimer = 0;

// ─── Projectiles ───
let projectiles = [];
for(let i=0;i<40;i++) projectiles.push({{active:false,x:0,y:0,dx:0,dy:0,life:0}});

// ─── Particles ───
let particles = [];

// ─── Coins ───
let coins = [];

// ─── Joystick ───
let joy = {{
  active: false, id: -1,
  bx: CFG.joystickX, by: CFG.joystickY,
  kx: CFG.joystickX, ky: CFG.joystickY,
  dx: 0, dy: 0,
}};

// ─── Upgrade state ───
let upgradeCards = [];
let upgradeAnim = 0;

// ─── Victory stars ───
let victoryStars = [
  {{shown:false,x:DESIGN_W/2-90,y:DESIGN_H/2-30,scale:0,delay:0.3}},
  {{shown:false,x:DESIGN_W/2,    y:DESIGN_H/2-70,scale:0,delay:0.6}},
  {{shown:false,x:DESIGN_W/2+90,y:DESIGN_H/2-30,scale:0,delay:0.9}},
];

// ─── Tutorial hand ───
let handAnim = 0;
let showHand = true;

// ─── Background scroll ───
let bgY = 0;

// ─── Wave definitions ───
const WAVE_DATA = [
  {{ // wave 1
    enemies:[
      {{type:'orc',hp:30,atk:5,speed:40,spawn:0}},
      {{type:'orc',hp:30,atk:5,speed:40,spawn:1.0}},
      {{type:'orc',hp:30,atk:5,speed:40,spawn:2.0}},
    ]
  }},
  {{ // wave 2
    enemies:[
      {{type:'orc', hp:50,atk:8,speed:40,spawn:0}},
      {{type:'zombie',hp:30,atk:6,speed:70,spawn:0.4}},
      {{type:'orc', hp:50,atk:8,speed:40,spawn:0.8}},
      {{type:'zombie',hp:30,atk:6,speed:70,spawn:1.2}},
      {{type:'orc', hp:50,atk:8,speed:40,spawn:1.6}},
    ]
  }},
  {{ // wave 3
    enemies:[
      {{type:'boss',hp:200,atk:15,speed:25,spawn:0}},
      {{type:'orc', hp:40,atk:6,speed:45,spawn:2.0}},
      {{type:'orc', hp:40,atk:6,speed:45,spawn:2.5}},
      {{type:'zombie',hp:25,atk:5,speed:75,spawn:4.0}},
      {{type:'zombie',hp:25,atk:5,speed:75,spawn:4.5}},
    ]
  }},
];

const UPGRADE_CARDS = [
  [
    {{id:'atk',   icon:'⚔',  title:'ATK UP',     desc:'+10 Attack Power', color:'#e74c3c'}},
    {{id:'hp',    icon:'❤',  title:'HP UP',       desc:'+50 Max HP',        color:'#2ecc71'}},
  ],
  [
    {{id:'spin',  icon:'🌀', title:'SPIN ATTACK', desc:'8-Direction Shots', color:'#9b59b6'}},
    {{id:'speed', icon:'💨', title:'SPEED UP',    desc:'+50% Move Speed',   color:'#3498db'}},
  ],
];

// ─── Enemy type specs ───
const ENEMY_SPEC = {{
  orc:    {{r:18, color:'#4a7c35', stroke:'#2a5010', label:'ORC', labelColor:'#fff', labelSize:9}},
  zombie: {{r:14, color:'#cc3333', stroke:'#880000', label:'Z',   labelColor:'#fff', labelSize:11}},
  boss:   {{r:34, color:'#7b0000', stroke:'#ff5500', label:'BOSS',labelColor:'#ff8c00',labelSize:11, glow:true}},
}};

// ─── Helpers ───
function dist2(ax,ay,bx,by){{ return (ax-bx)**2+(ay-by)**2; }}
function dist(ax,ay,bx,by){{ return Math.sqrt(dist2(ax,ay,bx,by)); }}
function clamp(v,lo,hi){{ return Math.max(lo,Math.min(hi,v)); }}
function randRange(a,b){{ return a + Math.random()*(b-a); }}
function spawnParticles(x,y,color,n){{
  for(let i=0;i<n;i++){{
    const angle=Math.random()*Math.PI*2;
    const speed=randRange(80,200);
    particles.push({{x,y,dx:Math.cos(angle)*speed,dy:Math.sin(angle)*speed,
      life:1,maxLife:1,r:randRange(3,7),color}});
  }}
}}
function spawnCoin(x,y){{
  coins.push({{x,y,vy:-180,life:1.2,maxLife:1.2,scale:0,targetScale:1}});
}}
function getProj(){{
  for(let p of projectiles){{ if(!p.active) return p; }}
  return null;
}}
function fireAt(tx,ty,extra){{
  const dx0 = tx - hero.x, dy0 = ty - hero.y;
  const d = Math.sqrt(dx0*dx0+dy0*dy0)||1;
  const nx = dx0/d, ny = dy0/d;
  const p = getProj(); if(!p) return;
  p.active=true; p.x=hero.x; p.y=hero.y;
  p.dx=nx*CFG.projSpeed; p.dy=ny*CFG.projSpeed;
  p.life=2.0;
  if(extra){{
    // fire in all 8 directions for spin attack
    const angles=[0,45,90,135,180,225,270,315];
    for(let ang of angles){{
      const rp=getProj(); if(!rp) continue;
      const rad=ang*Math.PI/180;
      rp.active=true; rp.x=hero.x; rp.y=hero.y;
      rp.dx=Math.cos(rad)*CFG.projSpeed; rp.dy=Math.sin(rad)*CFG.projSpeed;
      rp.life=2.0;
    }}
  }}
}}

// ─── Wave start ───
function startWave(wIdx){{
  wave = wIdx;
  enemies = [];
  const data = WAVE_DATA[wIdx];
  spawnQueue = data.enemies.map(e=>Object.assign({{}},e));
  spawnTimer = 0;
  timer = 0;
  for(let p of projectiles) p.active=false;
  particles=[];
  coins=[];
  state='wave_playing';
  showHand = (wIdx===0);
  handAnim = 0;
}}

function spawnEnemy(spec){{
  const side = Math.random()<0.7 ? 'top' : (Math.random()<0.5?'left':'right');
  let ex,ey;
  if(side==='top'){{ ex=randRange(80,DESIGN_W-80); ey=150; }}
  else if(side==='left'){{ ex=30; ey=randRange(150,400); }}
  else{{ ex=DESIGN_W-30; ey=randRange(150,400); }}
  if(spec.type==='boss'){{ ex=DESIGN_W/2; ey=160; }}
  enemies.push({{
    type:spec.type,
    x:ex, y:ey,
    hp:spec.hp, maxHp:spec.hp,
    atk:spec.atk, speed:spec.speed,
    r:ENEMY_SPEC[spec.type].r,
    flashTimer:0,
    deadTimer:-1,
  }});
}}

// ─── Upgrade apply ───
function applyUpgrade(id){{
  if(id==='atk')   {{ hero.atk+=10; }}
  if(id==='hp')    {{ hero.maxHp+=50; hero.hp=Math.min(hero.hp+50,hero.maxHp); }}
  if(id==='spin')  {{ hero.spinAttack=true; }}
  if(id==='speed') {{ hero.speed*=1.5; }}
  // next wave
  const nextWave = wave+1;
  if(nextWave < WAVE_DATA.length) startWave(nextWave);
  else showVictory();
}}

function showVictory(){{
  state='victory';
  victoryTimer=0;
  for(let s of victoryStars){{ s.shown=false; s.scale=0; }}
}}

function showCTA(){{
  if(ctaShown) return;
  ctaShown=true;
  state='cta';
  document.getElementById('cta-overlay').classList.add('show');
}}

// ─── Input ───
function getCanvasPos(clientX,clientY){{
  const rect = canvas.getBoundingClientRect();
  const scaleX = DESIGN_W / rect.width;
  const scaleY = DESIGN_H / rect.height;
  return {{ x:(clientX-rect.left)*scaleX, y:(clientY-rect.top)*scaleY }};
}}
function onPointerDown(cx,cy,id){{
  if(state==='title'){{ state='wave_playing'; startWave(0); return; }}
  if(state==='wave_playing'){{
    showHand=false;
    const d = dist(cx,cy,CFG.joystickX,CFG.joystickY);
    if(d < CFG.joystickBaseR*2.5 || cy > DESIGN_H*0.65){{
      joy.active=true; joy.id=id;
      joy.bx=cx; joy.by=cy;
      joy.kx=cx; joy.ky=cy;
      joy.dx=0; joy.dy=0;
    }}
  }}
  if(state==='upgrade_select'){{
    // check card clicks
    const cardW=200,cardH=240;
    const gap=20;
    const totalW=cardW*2+gap;
    const startX=(DESIGN_W-totalW)/2;
    const startY=DESIGN_H/2-cardH/2+20;
    for(let i=0;i<upgradeCards.length;i++){{
      const cx0=startX+i*(cardW+gap);
      const cy0=startY;
      if(cx>=cx0&&cx<=cx0+cardW&&cy>=cy0&&cy<=cy0+cardH){{
        applyUpgrade(upgradeCards[i].id);
        upgradeCards=[];
        return;
      }}
    }}
  }}
}}
function onPointerMove(cx,cy,id){{
  if(joy.active && joy.id===id){{
    const maxR=CFG.joystickBaseR;
    let dx=cx-joy.bx, dy=cy-joy.by;
    const mag=Math.sqrt(dx*dx+dy*dy);
    if(mag>maxR){{ dx=dx/mag*maxR; dy=dy/mag*maxR; }}
    joy.kx=joy.bx+dx; joy.ky=joy.by+dy;
    const deadzone=10;
    if(mag>deadzone){{ joy.dx=dx/maxR; joy.dy=dy/maxR; }}
    else {{ joy.dx=0; joy.dy=0; }}
  }}
}}
function onPointerUp(id){{
  if(joy.id===id){{ joy.active=false; joy.dx=0; joy.dy=0; joy.kx=CFG.joystickX; joy.ky=CFG.joystickY; }}
}}

canvas.addEventListener('touchstart',e=>{{
  e.preventDefault();
  for(let t of e.changedTouches){{
    const p=getCanvasPos(t.clientX,t.clientY);
    onPointerDown(p.x,p.y,t.identifier);
  }}
}},{{passive:false}});
canvas.addEventListener('touchmove',e=>{{
  e.preventDefault();
  for(let t of e.changedTouches){{
    const p=getCanvasPos(t.clientX,t.clientY);
    onPointerMove(p.x,p.y,t.identifier);
  }}
}},{{passive:false}});
canvas.addEventListener('touchend',e=>{{
  e.preventDefault();
  for(let t of e.changedTouches) onPointerUp(t.identifier);
}},{{passive:false}});
canvas.addEventListener('mousedown',e=>{{
  const p=getCanvasPos(e.clientX,e.clientY);
  onPointerDown(p.x,p.y,-1);
}});
canvas.addEventListener('mousemove',e=>{{
  if(e.buttons) {{ const p=getCanvasPos(e.clientX,e.clientY); onPointerMove(p.x,p.y,-1); }}
}});
canvas.addEventListener('mouseup',()=>onPointerUp(-1));

// ─── Clip image as circle ───
function drawCircleImage(img,cx,cy,r,ready){{
  if(!ready || !img.complete || img.naturalWidth===0){{
    return false;
  }}
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx,cy,r,0,Math.PI*2);
  ctx.clip();
  ctx.drawImage(img,cx-r,cy-r,r*2,r*2);
  ctx.restore();
  return true;
}}

// ─── Draw functions ───
function drawBackground(dt_val){{
  // Scrolling map texture - bgY updated here with actual dt
  if(IMG.map.complete && IMG.map.naturalWidth>0){{
    const mapAspect = IMG.map.naturalWidth / IMG.map.naturalHeight;
    const drawW = DESIGN_W;
    const drawH = Math.max(DESIGN_H, drawW / mapAspect);
    if(dt_val) bgY = (bgY + CFG.bgScrollSpeed * dt_val) % drawH;
    // Draw two tiles to cover screen during scroll
    const offsetY = bgY % drawH;
    ctx.drawImage(IMG.map, 0, offsetY - drawH, drawW, drawH);
    ctx.drawImage(IMG.map, 0, offsetY, drawW, drawH);
  }} else {{
    // Fallback gradient
    const grd = ctx.createLinearGradient(0,0,0,DESIGN_H);
    grd.addColorStop(0,'#2d5a1b'); grd.addColorStop(0.5,'#4a7c3f'); grd.addColorStop(1,'#3d6b34');
    ctx.fillStyle=grd; ctx.fillRect(0,0,DESIGN_W,DESIGN_H);
  }}
  // Dark vignette top/bottom
  const topGrad=ctx.createLinearGradient(0,0,0,140);
  topGrad.addColorStop(0,'rgba(0,0,0,0.7)');topGrad.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle=topGrad; ctx.fillRect(0,0,DESIGN_W,140);
  const botGrad=ctx.createLinearGradient(0,DESIGN_H-160,0,DESIGN_H);
  botGrad.addColorStop(0,'rgba(0,0,0,0)');botGrad.addColorStop(1,'rgba(0,0,0,0.6)');
  ctx.fillStyle=botGrad; ctx.fillRect(0,DESIGN_H-160,DESIGN_W,160);
}}

function drawWall(){{
  const wy = CFG.wallY;
  // Draw wall texture sprite sheet
  if(IMG.wall.complete && IMG.wall.naturalWidth>0){{
    // stretch wall across top
    ctx.drawImage(IMG.wall,0,wy-30,DESIGN_W,80);
    // overlay dark tint
    ctx.fillStyle='rgba(0,0,0,0.2)';
    ctx.fillRect(0,wy-30,DESIGN_W,80);
  }} else {{
    // Fallback blocks
    ctx.fillStyle='#8b7355';
    for(let i=0;i<11;i++){{ ctx.fillRect(i*50,wy,45,40); }}
    ctx.strokeStyle='#5a4a2a'; ctx.lineWidth=1;
    for(let i=0;i<11;i++){{ ctx.strokeRect(i*50,wy,45,40); }}
  }}
  // Tower sprites
  if(IMG.tower.complete && IMG.tower.naturalWidth>0){{
    ctx.drawImage(IMG.tower, 30, wy-50, 60, 80);
    ctx.drawImage(IMG.tower, DESIGN_W-90, wy-50, 60, 80);
  }}
  // Torches
  drawTorch(60, wy-5);
  drawTorch(DESIGN_W-60, wy-5);
}}

function drawTorch(x,y){{
  const flicker = 0.7+Math.random()*0.3;
  ctx.save();
  ctx.shadowBlur=15*flicker; ctx.shadowColor='#ff8c00';
  ctx.fillStyle=`rgba(255,140,0,${{flicker}})`;
  ctx.beginPath(); ctx.arc(x,y,5,0,Math.PI*2); ctx.fill();
  ctx.restore();
}}

function drawShadow(x,y,r){{
  if(IMG.shadow.complete && IMG.shadow.naturalWidth>0){{
    ctx.globalAlpha=0.35;
    ctx.drawImage(IMG.shadow, x-r*0.9, y-r*0.35, r*1.8, r*0.7);
    ctx.globalAlpha=1;
  }} else {{
    ctx.save(); ctx.globalAlpha=0.3;
    ctx.fillStyle='#000';
    ctx.beginPath(); ctx.ellipse(x,y,r*0.9,r*0.35,0,0,Math.PI*2); ctx.fill();
    ctx.restore();
  }}
}}

function drawHero(){{
  drawShadow(hero.x, hero.y+CFG.heroR*0.8, CFG.heroR);
  const r=CFG.heroR;
  // Try draw UV texture clipped to circle, fallback to shape
  const drawn = drawCircleImage(IMG.npc, hero.x, hero.y, r, true);
  if(!drawn){{
    // Fallback: styled circle
    ctx.save();
    if(hero.flashTimer>0){{ ctx.globalAlpha=0.5; }}
    ctx.shadowBlur=12; ctx.shadowColor='#ffd700';
    ctx.fillStyle='#3a6ebf';
    ctx.beginPath(); ctx.arc(hero.x,hero.y,r,0,Math.PI*2); ctx.fill();
    ctx.strokeStyle='#ffd700'; ctx.lineWidth=3;
    ctx.stroke();
    ctx.fillStyle='white'; ctx.font='bold 12px Arial';
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText('H',hero.x,hero.y);
    ctx.restore();
  }} else {{
    // Gold ring
    ctx.save();
    ctx.strokeStyle=hero.flashTimer>0?'rgba(255,255,255,0.9)':'#ffd700';
    ctx.lineWidth=3;
    ctx.shadowBlur=8; ctx.shadowColor='#ffd700';
    ctx.beginPath(); ctx.arc(hero.x,hero.y,r,0,Math.PI*2); ctx.stroke();
    ctx.restore();
  }}
  // HP bar
  drawHpBar(hero.x, hero.y-r-12, 50, 7, hero.hp/hero.maxHp, '#2ecc71','#e74c3c');
}}

function drawEnemy(e){{
  const spec=ENEMY_SPEC[e.type];
  drawShadow(e.x, e.y+e.r*0.8, e.r);
  let drawn=false;
  if(e.type==='boss'){{
    drawn=drawCircleImage(IMG.boss_tex, e.x, e.y, e.r, true);
  }} else if(e.type==='orc'){{
    drawn=drawCircleImage(IMG.mob, e.x, e.y, e.r, true);
  }} else {{
    // zombie – tint the mob texture red
    drawn=false;
  }}
  if(!drawn){{
    ctx.save();
    if(e.flashTimer>0) ctx.globalAlpha=0.5;
    if(spec.glow){{ ctx.shadowBlur=20; ctx.shadowColor=spec.stroke; }}
    ctx.fillStyle=spec.color;
    ctx.beginPath(); ctx.arc(e.x,e.y,e.r,0,Math.PI*2); ctx.fill();
    ctx.strokeStyle=spec.stroke; ctx.lineWidth=spec.glow?4:2; ctx.stroke();
    ctx.fillStyle=spec.labelColor; ctx.font=`bold ${{spec.labelSize}}px Arial`;
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(spec.label,e.x,e.y);
    ctx.restore();
  }} else {{
    ctx.save();
    if(e.flashTimer>0){{ ctx.globalAlpha=0.4; ctx.fillStyle='white'; ctx.beginPath(); ctx.arc(e.x,e.y,e.r,0,Math.PI*2); ctx.fill(); ctx.globalAlpha=1; }}
    ctx.strokeStyle=spec.glow?'#ff5500':'#000';
    ctx.lineWidth=spec.glow?4:2;
    if(spec.glow){{ctx.shadowBlur=15; ctx.shadowColor='#ff5500';}}
    ctx.beginPath(); ctx.arc(e.x,e.y,e.r,0,Math.PI*2); ctx.stroke();
    if(e.type==='zombie'){{
      ctx.globalAlpha=0.5; ctx.fillStyle='#cc0000';
      ctx.beginPath(); ctx.arc(e.x,e.y,e.r,0,Math.PI*2); ctx.fill();
    }}
    ctx.restore();
  }}
  // HP bar (only if damaged)
  if(e.hp < e.maxHp){{
    drawHpBar(e.x, e.y-e.r-10, e.r*2.2, 5, e.hp/e.maxHp, '#e74c3c','#555');
  }}
  // Boss HP bar bigger
  if(e.type==='boss'){{
    drawHpBar(e.x, e.y-e.r-14, e.r*3, 8, e.hp/e.maxHp,'#e74c3c','#333');
    ctx.fillStyle='#ff8c00'; ctx.font='bold 9px Arial';
    ctx.textAlign='center'; ctx.textBaseline='bottom';
    ctx.fillText('BOSS',e.x,e.y-e.r-14);
  }}
}}

function drawHpBar(cx,cy,w,h,pct,col,bg){{
  const x=cx-w/2;
  ctx.fillStyle=bg; ctx.fillRect(x,cy,w,h);
  ctx.fillStyle=col; ctx.fillRect(x,cy,w*pct,h);
  ctx.strokeStyle='rgba(0,0,0,0.5)'; ctx.lineWidth=1; ctx.strokeRect(x,cy,w,h);
}}

function drawProjectile(p){{
  ctx.save();
  ctx.shadowBlur=8; ctx.shadowColor='rgba(255,255,100,0.8)';
  if(IMG.arrow.complete && IMG.arrow.naturalWidth>0){{
    const angle=Math.atan2(p.dy,p.dx);
    ctx.translate(p.x,p.y); ctx.rotate(angle);
    ctx.drawImage(IMG.arrow,-12,-6,24,12);
  }} else {{
    ctx.fillStyle='#ffff44';
    ctx.beginPath(); ctx.arc(p.x,p.y,CFG.projR,0,Math.PI*2); ctx.fill();
  }}
  ctx.restore();
}}

function drawParticle(p){{
  ctx.save();
  ctx.globalAlpha=p.life/p.maxLife;
  ctx.fillStyle=p.color;
  ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2); ctx.fill();
  ctx.restore();
}}

function drawCoin(c){{
  if(IMG.coin.complete && IMG.coin.naturalWidth>0){{
    const s=28*c.scale;
    ctx.save(); ctx.globalAlpha=c.life/c.maxLife;
    ctx.drawImage(IMG.coin,c.x-s/2,c.y-s/2,s,s);
    ctx.restore();
  }}
}}

function drawJoystick(){{
  const bx=joy.bx, by=joy.by;
  const kx=joy.active?joy.kx:CFG.joystickX, ky=joy.active?joy.ky:CFG.joystickY;
  // base
  if(IMG.vpadback.complete && IMG.vpadback.naturalWidth>0){{
    ctx.save(); ctx.globalAlpha=0.55;
    ctx.drawImage(IMG.vpadback, bx-CFG.joystickBaseR, by-CFG.joystickBaseR, CFG.joystickBaseR*2, CFG.joystickBaseR*2);
    ctx.restore();
  }} else {{
    ctx.save(); ctx.globalAlpha=0.35;
    ctx.strokeStyle='rgba(255,255,255,0.6)'; ctx.lineWidth=2;
    ctx.beginPath(); ctx.arc(bx,by,CFG.joystickBaseR,0,Math.PI*2); ctx.stroke();
    ctx.restore();
  }}
  // knob
  if(IMG.vpad.complete && IMG.vpad.naturalWidth>0){{
    ctx.save(); ctx.globalAlpha=0.8;
    ctx.drawImage(IMG.vpad, kx-CFG.joystickKnobR, ky-CFG.joystickKnobR, CFG.joystickKnobR*2, CFG.joystickKnobR*2);
    ctx.restore();
  }} else {{
    ctx.save(); ctx.globalAlpha=0.7;
    ctx.fillStyle='rgba(255,255,255,0.7)';
    ctx.beginPath(); ctx.arc(kx,ky,CFG.joystickKnobR,0,Math.PI*2); ctx.fill();
    ctx.restore();
  }}
}}

function drawHUD(){{
  // HP bar (hero) top
  ctx.fillStyle='rgba(0,0,0,0.5)'; ctx.fillRect(10,14,200,22); ctx.strokeStyle='#ffd700'; ctx.lineWidth=1.5; ctx.strokeRect(10,14,200,22);
  const hpPct=hero.hp/hero.maxHp;
  const hpColor = hpPct>0.5?'#2ecc71':(hpPct>0.25?'#f39c12':'#e74c3c');
  ctx.fillStyle=hpColor; ctx.fillRect(12,16,196*hpPct,18);
  if(IMG.hp.complete&&IMG.hp.naturalWidth>0){{ ctx.drawImage(IMG.hp,12,13,24,24); }}
  ctx.fillStyle='white'; ctx.font='bold 11px Arial'; ctx.textAlign='left'; ctx.textBaseline='middle';
  ctx.fillText(`HP ${{hero.hp}}/${{hero.maxHp}}`,40,25);
  // Wave indicator
  ctx.fillStyle='rgba(0,0,0,0.55)'; ctx.fillRect(DESIGN_W/2-70,8,140,32); ctx.strokeStyle='#ffd700'; ctx.lineWidth=1.5; ctx.strokeRect(DESIGN_W/2-70,8,140,32);
  ctx.fillStyle='#ffd700'; ctx.font='bold 14px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText(`WAVE ${{wave+1}} / 3`, DESIGN_W/2, 24);
  // Upgrade indicators top right
  if(hero.spinAttack){{
    ctx.fillStyle='rgba(155,89,182,0.8)'; ctx.fillRect(DESIGN_W-70,8,60,28);
    ctx.fillStyle='white'; ctx.font='10px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText('SPIN',DESIGN_W-40,22);
  }}
}}

function drawTutorialHand(){{
  if(!showHand) return;
  const hx=CFG.joystickX+50+Math.sin(handAnim*3)*15;
  const hy=CFG.joystickY+50+Math.cos(handAnim*2)*8;
  // Simple hand icon
  ctx.save();
  ctx.globalAlpha=0.85+Math.sin(handAnim*4)*0.15;
  ctx.fillStyle='rgba(255,255,255,0.9)';
  ctx.font='36px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText('👆',hx,hy);
  ctx.restore();
  // "DRAG TO MOVE" label
  ctx.save();
  ctx.fillStyle='rgba(0,0,0,0.6)'; ctx.fillRect(hx-70,hy+24,140,26);
  ctx.fillStyle='#ffd700'; ctx.font='bold 13px Arial';
  ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText('DRAG TO MOVE!',hx,hy+37);
  ctx.restore();
}}

function drawWaveLabel(txt,subTxt){{
  ctx.save();
  ctx.fillStyle='rgba(0,0,0,0.6)'; ctx.fillRect(DESIGN_W/2-120,DESIGN_H/2-35,240,70);
  ctx.strokeStyle='#ffd700'; ctx.lineWidth=2; ctx.strokeRect(DESIGN_W/2-120,DESIGN_H/2-35,240,70);
  ctx.fillStyle='#ffd700'; ctx.font='bold 26px Arial Black,Impact,sans-serif'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText(txt,DESIGN_W/2,DESIGN_H/2-10);
  if(subTxt){{
    ctx.fillStyle='white'; ctx.font='14px Arial'; ctx.fillText(subTxt,DESIGN_W/2,DESIGN_H/2+18);
  }}
  ctx.restore();
}}

// ─── Title state ───
function drawTitle(dt_val){{
  drawBackground(dt_val);
  drawWall();
  // Title box
  ctx.save();
  const pulse=1+Math.sin(titleTimer*2)*0.02;
  ctx.translate(DESIGN_W/2,DESIGN_H*0.32); ctx.scale(pulse,pulse);
  ctx.fillStyle='rgba(0,0,0,0.75)'; ctx.fillRect(-170,-55,340,110);
  ctx.strokeStyle='#ffd700'; ctx.lineWidth=3; ctx.strokeRect(-170,-55,340,110);
  ctx.shadowBlur=20; ctx.shadowColor='#ffd700';
  ctx.fillStyle='#ffd700'; ctx.font='bold 30px Arial Black,Impact,sans-serif';
  ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillText('DEFEND THE',0,-25);
  ctx.fillStyle='#ff4444'; ctx.font='bold 38px Arial Black,Impact,sans-serif';
  ctx.fillText('FORTRESS!',0,18);
  ctx.restore();
  // Subtitle
  ctx.fillStyle='rgba(0,0,0,0.5)'; ctx.fillRect(DESIGN_W/2-110,DESIGN_H*0.52,220,36);
  ctx.fillStyle='white'; ctx.font='14px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText('TAP TO START',DESIGN_W/2,DESIGN_H*0.52+18);
  // Bouncing hand
  const bounce=Math.sin(titleTimer*4)*12;
  ctx.font='40px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText('👆',DESIGN_W/2,DESIGN_H*0.65+bounce);
  ctx.fillStyle='rgba(0,0,0,0.5)'; ctx.fillRect(DESIGN_W/2-80,DESIGN_H*0.73,160,26);
  ctx.fillStyle='#ffd700'; ctx.font='bold 13px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText('DRAG TO MOVE!',DESIGN_W/2,DESIGN_H*0.73+13);
}}

// ─── Upgrade cards ───
function drawUpgradeSelect(dt_val){{
  drawBackground(dt_val);
  drawWall();
  // dim overlay
  ctx.fillStyle='rgba(0,0,0,0.45)'; ctx.fillRect(0,0,DESIGN_W,DESIGN_H);
  // WAVE CLEAR banner
  ctx.save();
  const sc=1+Math.sin(upgradeAnim*3)*0.03;
  ctx.translate(DESIGN_W/2,DESIGN_H*0.25); ctx.scale(sc,sc);
  ctx.fillStyle='rgba(0,0,0,0.7)'; ctx.fillRect(-130,-35,260,70);
  ctx.strokeStyle='#ffd700'; ctx.lineWidth=2.5; ctx.strokeRect(-130,-35,260,70);
  ctx.fillStyle='#ffd700'; ctx.font='bold 28px Arial Black,Impact,sans-serif';
  ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.shadowBlur=15; ctx.shadowColor='#ffd700';
  ctx.fillText(`WAVE ${{wave+1}} CLEAR!`,0,-8);
  ctx.fillStyle='white'; ctx.font='14px Arial';
  ctx.shadowBlur=0;
  ctx.fillText('Choose an upgrade',0,18);
  ctx.restore();
  // Cards
  const cardW=200, cardH=240, gap=20;
  const startX=(DESIGN_W-(cardW*2+gap))/2;
  const startY=DESIGN_H/2-cardH/2+30;
  for(let i=0;i<upgradeCards.length;i++){{
    const card=upgradeCards[i];
    const cx=startX+i*(cardW+gap);
    const hover=1+Math.sin(upgradeAnim*3+i*1.5)*0.015;
    ctx.save(); ctx.translate(cx+cardW/2,startY+cardH/2); ctx.scale(hover,hover); ctx.translate(-cardW/2,-cardH/2);
    // card bg
    ctx.fillStyle=`rgba(10,10,30,0.9)`; ctx.fillRect(0,0,cardW,cardH);
    ctx.strokeStyle=card.color; ctx.lineWidth=3;
    ctx.shadowBlur=12; ctx.shadowColor=card.color;
    ctx.strokeRect(0,0,cardW,cardH);
    // icon
    ctx.font='54px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.shadowBlur=0;
    ctx.fillText(card.icon,cardW/2,70);
    // title
    ctx.fillStyle=card.color; ctx.font='bold 18px Arial Black,sans-serif';
    ctx.fillText(card.title,cardW/2,130);
    // desc
    ctx.fillStyle='#ccc'; ctx.font='13px Arial';
    ctx.fillText(card.desc,cardW/2,160);
    // button
    ctx.fillStyle=card.color; ctx.fillRect(20,cardH-55,cardW-40,36);
    ctx.fillStyle='white'; ctx.font='bold 14px Arial';
    ctx.fillText('SELECT',cardW/2,cardH-37);
    ctx.restore();
  }}
}}

// ─── Victory screen ───
function drawVictory(dt_val){{
  drawBackground(dt_val);
  drawWall();
  ctx.fillStyle='rgba(0,0,0,0.5)'; ctx.fillRect(0,0,DESIGN_W,DESIGN_H);
  // VICTORY text scale-in
  const maxScale=1.0;
  const scale=Math.min(1.0, victoryTimer*3);
  ctx.save();
  ctx.translate(DESIGN_W/2, DESIGN_H*0.38);
  ctx.scale(scale,scale);
  ctx.shadowBlur=30; ctx.shadowColor='#ffd700';
  ctx.fillStyle='#ffd700'; ctx.font='bold 56px Arial Black,Impact,sans-serif';
  ctx.textAlign='center'; ctx.textBaseline='middle';
  ctx.fillText('VICTORY!',0,0);
  ctx.restore();
  // Stars
  for(let i=0;i<victoryStars.length;i++){{
    const s=victoryStars[i];
    const elapsed = victoryTimer - s.delay;
    if(elapsed>0){{
      s.scale = Math.min(1.0, elapsed*3);
      ctx.save();
      ctx.translate(s.x, s.y); ctx.scale(s.scale, s.scale);
      if(IMG.star.complete&&IMG.star.naturalWidth>0){{
        ctx.drawImage(IMG.star,-22,-22,44,44);
      }} else {{
        ctx.fillStyle='#ffd700'; ctx.font='40px Arial';
        ctx.textAlign='center'; ctx.textBaseline='middle';
        ctx.fillText('★',0,0);
      }}
      ctx.restore();
    }}
  }}
  // Subtitle
  if(victoryTimer>1.2){{
    ctx.save();
    ctx.globalAlpha=Math.min(1,(victoryTimer-1.2)*2);
    ctx.fillStyle='white'; ctx.font='18px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText('Download the full game!',DESIGN_W/2,DESIGN_H*0.55);
    ctx.restore();
  }}
}}

// ─── Update ───
function updateWave(dt){{
  handAnim+=dt;
  // Spawn queue
  spawnTimer+=dt;
  while(spawnQueue.length>0 && spawnTimer >= spawnQueue[0].spawn){{
    spawnEnemy(spawnQueue[0]);
    spawnQueue.shift();
  }}
  // Hero movement
  if(Math.abs(joy.dx)>0.01 || Math.abs(joy.dy)>0.01){{
    hero.x = clamp(hero.x+joy.dx*hero.speed*dt, CFG.heroR, DESIGN_W-CFG.heroR);
    hero.y = clamp(hero.y+joy.dy*hero.speed*dt, CFG.wallY+60+CFG.heroR, DESIGN_H-100-CFG.heroR);
  }}
  // Hero flash
  if(hero.flashTimer>0) hero.flashTimer-=dt;
  // Auto attack
  hero.attackCd-=dt;
  if(hero.attackCd<=0 && enemies.length>0){{
    // Find nearest in range
    let closest=null, closestD=Infinity;
    for(let e of enemies){{
      const d=dist(hero.x,hero.y,e.x,e.y);
      if(d<CFG.autoRange && d<closestD){{ closestD=d; closest=e; }}
    }}
    if(closest){{
      hero.attackCd=CFG.attackCd;
      fireAt(closest.x, closest.y, hero.spinAttack);
    }} else if(hero.spinAttack && joy.dx===0 && joy.dy===0){{
      // Spin attack idle fire
      hero.attackCd=CFG.attackCd;
      const p=getProj(); if(p){{
        const angle=performance.now()*0.002;
        p.active=true; p.x=hero.x; p.y=hero.y;
        p.dx=Math.cos(angle)*CFG.projSpeed; p.dy=Math.sin(angle)*CFG.projSpeed; p.life=2;
      }}
    }}
  }}
  // Projectile update + collision
  for(let p of projectiles){{
    if(!p.active) continue;
    p.x+=p.dx*dt; p.y+=p.dy*dt; p.life-=dt;
    if(p.life<=0||p.x<0||p.x>DESIGN_W||p.y<0||p.y>DESIGN_H){{ p.active=false; continue; }}
    for(let i=enemies.length-1;i>=0;i--){{
      const e=enemies[i];
      if(dist(p.x,p.y,e.x,e.y)<e.r+CFG.projR){{
        e.hp-=hero.atk;
        e.flashTimer=0.12;
        spawnParticles(e.x,e.y,'#ffcc00',4);
        p.active=false;
        if(e.hp<=0){{
          spawnParticles(e.x,e.y,'#ff4444',12);
          spawnCoin(e.x,e.y);
          enemies.splice(i,1);
        }}
        break;
      }}
    }}
  }}
  // Enemy movement + hero damage
  for(let e of enemies){{
    const dx=hero.x-e.x, dy=hero.y-e.y;
    const d=Math.sqrt(dx*dx+dy*dy)||1;
    const nx=dx/d, ny=dy/d;
    e.x+=nx*e.speed*dt; e.y+=ny*e.speed*dt;
    if(e.flashTimer>0) e.flashTimer-=dt;
    // Attack hero on contact
    if(d<CFG.heroR+e.r){{
      hero.hp-=e.atk*dt;
      hero.flashTimer=0.1;
      if(hero.hp<=0){{ hero.hp=0; showCTA(); return; }}
    }}
  }}
  // Particles
  for(let i=particles.length-1;i>=0;i--){{
    const p=particles[i];
    p.x+=p.dx*dt; p.y+=p.dy*dt; p.dy+=300*dt;
    p.life-=dt; if(p.life<=0) particles.splice(i,1);
  }}
  // Coins
  for(let i=coins.length-1;i>=0;i--){{
    const c=coins[i];
    c.y+=c.vy*dt; c.vy+=200*dt;
    c.scale=Math.min(1,c.scale+dt*4);
    c.life-=dt; if(c.life<=0) coins.splice(i,1);
  }}
  // Check win condition
  const waveData=WAVE_DATA[wave];
  const allSpawned=spawnQueue.length===0;
  const allDead=enemies.length===0;
  if(allSpawned && allDead){{
    // Wave clear
    if(wave<2){{
      // Show upgrade select
      state='upgrade_select';
      upgradeCards=UPGRADE_CARDS[wave];
      upgradeAnim=0;
    }} else {{
      showVictory();
    }}
  }}
}}

// ─── Main loop ───
let lastTime=0;
function loop(ts){{
  const dt=Math.min((ts-lastTime)/1000,0.05);
  lastTime=ts;
  totalTimer+=dt;
  // Global CTA timer
  if(totalTimer>=30 && state!='cta' && !ctaShown){{ showCTA(); }}

  ctx.clearRect(0,0,DESIGN_W,DESIGN_H);

  if(state==='title'){{
    titleTimer+=dt;
    drawTitle(dt);
    if(titleTimer>2){{ startWave(0); }}
  }} else if(state==='wave_playing'){{
    updateWave(dt);
    drawBackground(dt);
    drawWall();
    // draw entities
    for(let c of coins) drawCoin(c);
    for(let p of particles) drawParticle(p);
    for(let p of projectiles){{ if(p.active) drawProjectile(p); }}
    for(let e of enemies) drawEnemy(e);
    drawHero();
    drawJoystick();
    drawHUD();
    drawTutorialHand();
    // Spawn indicator
    if(spawnQueue.length>0 && enemies.length===0){{
      ctx.save();
      ctx.globalAlpha=0.7+Math.sin(timer*5)*0.3;
      ctx.fillStyle='#ffd700'; ctx.font='bold 14px Arial'; ctx.textAlign='center'; ctx.textBaseline='middle';
      ctx.fillText('⚠ INCOMING!',DESIGN_W/2,180);
      ctx.restore();
    }}
  }} else if(state==='upgrade_select'){{
    upgradeAnim+=dt;
    drawUpgradeSelect(dt);
  }} else if(state==='victory'){{
    victoryTimer+=dt;
    drawVictory(dt);
    if(victoryTimer>3.5) showCTA();
  }}

  timer+=dt;
  requestAnimationFrame(loop);
}}

requestAnimationFrame(loop);

}})();
</script>
</body>
</html>"""

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(HTML)
print(f"Written: {OUTPUT_FILE}")
print(f"Size: {os.path.getsize(OUTPUT_FILE)/1024:.1f} KB")
