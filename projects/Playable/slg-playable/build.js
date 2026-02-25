const fs = require('fs');
const TMP = process.env.TEMP || process.env.TMP || 'C:/Users/user/AppData/Local/Temp';

function b64(name) { return fs.readFileSync(TMP + '/' + name, 'utf8').trim(); }

const A = {
  tower: b64('slg_tower.b64'),
  archer: b64('slg_archer.b64'),
  arrow: b64('slg_arrow.b64'),
  coin: b64('slg_coin.b64'),
  btn: b64('slg_btn.b64'),
  shadow: b64('slg_shadow.b64'),
  tree: b64('slg_tree.b64'),
  tree2: b64('slg_tree2.b64'),
  bigtree: b64('slg_bigtree.b64'),
  fx: b64('slg_fx.b64')
};

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="ad.size" content="width=320,height=480">
<title>Kingdom Defense - Play Now!</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#1a2a1a;touch-action:none;user-select:none;-webkit-user-select:none}
canvas{display:block;position:absolute;top:0;left:0}
#cta{display:none;position:absolute;top:0;left:0;width:100%;height:100%;background:rgba(10,20,10,0.9);z-index:10;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#cta.show{display:flex}
#cta-title{color:#FFD700;font-family:'Segoe UI',Arial,sans-serif;font-size:30px;font-weight:bold;text-shadow:0 2px 12px rgba(255,215,0,0.5);margin-bottom:8px}
#cta-sub{color:#aed581;font-family:'Segoe UI',Arial,sans-serif;font-size:16px;margin-bottom:24px}
#cta-btn{background:linear-gradient(135deg,#FFD700,#FFA000);color:#3E2723;border:none;padding:18px 48px;font-size:22px;font-weight:bold;border-radius:50px;cursor:pointer;animation:pulse 1.5s infinite;font-family:'Segoe UI',Arial,sans-serif;text-transform:uppercase;letter-spacing:2px;box-shadow:0 4px 24px rgba(255,215,0,0.4)}
#cta-btn:active{transform:scale(0.95)}
#cta-retry{color:#aed581;font-family:'Segoe UI',Arial,sans-serif;font-size:14px;margin-top:16px;cursor:pointer;text-decoration:underline;opacity:0.7}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}
</style>
</head>
<body>
<canvas id="gc"></canvas>
<div id="cta">
  <div id="cta-title"></div>
  <div id="cta-sub"></div>
  <button id="cta-btn" onclick="window.open('https://play.google.com/store','_blank')">INSTALL NOW</button>
  <div id="cta-retry" onclick="restartAll()">Play again</div>
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
const IMG={};
let loaded=0, total=10;
function ld(k,d){const i=new Image();i.onload=i.onerror=()=>{IMG[k]=i;loaded++;if(loaded>=total)startApp();};i.src='data:image/png;base64,'+d;}
ld('tower','${A.tower}');
ld('archer','${A.archer}');
ld('arrow','${A.arrow}');
ld('coin','${A.coin}');
ld('btn','${A.btn}');
ld('shadow','${A.shadow}');
ld('tree','${A.tree}');
ld('tree2','${A.tree2}');
ld('bigtree','${A.bigtree}');
ld('fx','${A.fx}');

// ===== CANVAS =====
const cv=document.getElementById('gc'),cx=cv.getContext('2d');
let W,H,sc;
function resize(){W=cv.width=innerWidth;H=cv.height=innerHeight;sc=Math.min(W/420,H/750);}
resize();addEventListener('resize',resize);

// ===== ISO GRID CONFIG =====
const COLS=7, ROWS=5;
const TW=56, TH=28; // tile width/height in iso
let gridOX, gridOY; // grid origin offset

function calcGrid(){
  gridOX=W/2;
  gridOY=H*0.22;
}

function isoToScreen(col,row){
  const x=gridOX+(col-row)*TW*sc/2;
  const y=gridOY+(col+row)*TH*sc/2;
  return {x,y};
}

function screenToIso(sx,sy){
  const dx=sx-gridOX, dy=sy-gridOY;
  const col=(dx/(TW*sc/2)+dy/(TH*sc/2))/2;
  const row=(dy/(TH*sc/2)-dx/(TW*sc/2))/2;
  return {col:Math.round(col), row:Math.round(row)};
}

// ===== GAME STATE =====
const PHASE_DEPLOY=0, PHASE_BATTLE=1, PHASE_RESULT=2;
let phase, budget, units, enemies, arrows, effects, grid;
let battleTimer, deployTimer, resultShown, won;
let dragUnit, dragX, dragY, dragType;
let frame=0, tutorialAlpha=1;

// Unit costs
const UNIT_DEF={
  warrior: {cost:3, hp:120, maxHp:120, atk:18, range:1.2, speed:0.6, atkSpeed:60, label:'Warrior', color:'#4FC3F7'},
  archerTower: {cost:5, hp:90, maxHp:90, atk:12, range:3.5, speed:0, atkSpeed:45, label:'Archer', color:'#81C784'},
  defTower: {cost:4, hp:250, maxHp:250, atk:0, range:0, speed:0, atkSpeed:0, label:'Tower', color:'#90A4AE'}
};

const ENEMY_DEF={
  grunt: {hp:80, maxHp:80, atk:12, range:1.2, speed:0.5, atkSpeed:55, color:'#EF5350'},
  heavy: {hp:180, maxHp:180, atk:22, range:1.2, speed:0.35, atkSpeed:70, color:'#C62828'}
};

function initGame(){
  phase=PHASE_DEPLOY;
  budget=20;
  units=[];
  enemies=[];
  arrows=[];
  effects=[];
  grid=[];
  battleTimer=0;
  deployTimer=0;
  resultShown=false;
  won=false;
  dragUnit=null;
  tutorialAlpha=1;
  calcGrid();

  // Init grid occupancy
  for(let c=0;c<COLS;c++){grid[c]=[];for(let r=0;r<ROWS;r++)grid[c][r]=null;}

  // Pre-place enemies on right side
  spawnEnemy('grunt', 5, 0);
  spawnEnemy('grunt', 5, 2);
  spawnEnemy('grunt', 6, 1);
  spawnEnemy('grunt', 5, 4);
  spawnEnemy('heavy', 6, 3);
  spawnEnemy('grunt', 6, 0);
  spawnEnemy('heavy', 6, 4);

  document.getElementById('cta').classList.remove('show');
}

function spawnEnemy(type, col, row){
  const def=ENEMY_DEF[type];
  const pos=isoToScreen(col,row);
  enemies.push({
    type, col, row,
    x:pos.x, y:pos.y,
    hp:def.hp, maxHp:def.maxHp,
    atk:def.atk, range:def.range,
    speed:def.speed, atkSpeed:def.atkSpeed,
    color:def.color,
    atkTimer:0, dead:false,
    bobPhase:Math.random()*Math.PI*2
  });
}

function placeUnit(type, col, row){
  const def=UNIT_DEF[type];
  if(budget<def.cost)return false;
  if(col<0||col>3||row<0||row>=ROWS)return false;
  if(grid[col][row])return false;
  budget-=def.cost;
  const pos=isoToScreen(col,row);
  const u={
    type, col, row,
    x:pos.x, y:pos.y,
    hp:def.hp, maxHp:def.maxHp,
    atk:def.atk, range:def.range,
    speed:def.speed, atkSpeed:def.atkSpeed,
    color:def.color,
    atkTimer:0, dead:false,
    bobPhase:Math.random()*Math.PI*2,
    label:def.label
  };
  units.push(u);
  grid[col][row]=u;
  return true;
}

// ===== INPUT =====
let touchId=null;

function getPos(e){
  if(e.changedTouches) return {x:e.changedTouches[0].clientX, y:e.changedTouches[0].clientY};
  return {x:e.clientX, y:e.clientY};
}

function onDown(e){
  e.preventDefault();
  const p=getPos(e);

  if(phase===PHASE_DEPLOY){
    // Check if tapping fight button
    const btnArea=getFightBtnArea();
    if(units.length>0 && p.x>=btnArea.x && p.x<=btnArea.x+btnArea.w && p.y>=btnArea.y && p.y<=btnArea.y+btnArea.h){
      startBattle();
      return;
    }
    // Check unit tray
    const tray=getTrayAreas();
    for(const t of tray){
      if(p.x>=t.x && p.x<=t.x+t.w && p.y>=t.y && p.y<=t.y+t.h && budget>=UNIT_DEF[t.type].cost){
        dragType=t.type;
        dragX=p.x; dragY=p.y;
        dragUnit=true;
        tutorialAlpha=0;
        return;
      }
    }
  }
}

function onMove(e){
  e.preventDefault();
  if(dragUnit){
    const p=getPos(e);
    dragX=p.x; dragY=p.y;
  }
}

function onUp(e){
  e.preventDefault();
  if(dragUnit && dragType){
    const iso=screenToIso(dragX, dragY);
    if(iso.col>=0 && iso.col<=3 && iso.row>=0 && iso.row<ROWS){
      placeUnit(dragType, iso.col, iso.row);
    }
    dragUnit=null; dragType=null;
  }
}

cv.addEventListener('mousedown',onDown);
cv.addEventListener('mousemove',onMove);
cv.addEventListener('mouseup',onUp);
cv.addEventListener('touchstart',onDown,{passive:false});
cv.addEventListener('touchmove',onMove,{passive:false});
cv.addEventListener('touchend',onUp,{passive:false});

// ===== UI AREAS =====
function getTrayAreas(){
  const trayY=H-95*sc;
  const trayW=90*sc, trayH=80*sc, gap=12*sc;
  const totalW=3*trayW+2*gap;
  const startX=(W-totalW)/2;
  const types=['warrior','archerTower','defTower'];
  return types.map((t,i)=>({
    type:t, x:startX+i*(trayW+gap), y:trayY, w:trayW, h:trayH
  }));
}

function getFightBtnArea(){
  return {x:W/2-65*sc, y:H-105*sc-50*sc, w:130*sc, h:40*sc};
}

// ===== BATTLE LOGIC =====
function startBattle(){
  phase=PHASE_BATTLE;
  battleTimer=0;
}

function dist(a,b){
  const dc=a.col-b.col, dr=a.row-b.row;
  return Math.sqrt(dc*dc+dr*dr);
}

function findTarget(unit, targetList){
  let best=null, bestD=999;
  for(const t of targetList){
    if(t.dead)continue;
    const d=dist(unit,t);
    if(d<bestD){bestD=d; best=t;}
  }
  return best ? {target:best, dist:bestD} : null;
}

function fireArrow(from, to){
  const fp=isoToScreen(from.col, from.row);
  const tp=isoToScreen(to.col, to.row);
  arrows.push({
    x:fp.x, y:fp.y-20*sc,
    tx:tp.x, ty:tp.y-15*sc,
    speed:4*sc,
    atk:from.atk,
    target:to,
    life:1
  });
}

function spawnEffect(x,y){
  effects.push({x,y,life:1,size:20*sc});
}

function updateBattle(){
  battleTimer++;

  // Update player units
  for(const u of units){
    if(u.dead)continue;
    const res=findTarget(u, enemies);
    if(!res)continue;

    if(u.speed>0 && res.dist>u.range){
      // Move toward enemy (in grid coords)
      const dx=res.target.col-u.col;
      const dy=res.target.row-u.row;
      const d=Math.sqrt(dx*dx+dy*dy);
      const ncol=u.col+dx/d*u.speed*0.03;
      const nrow=u.row+dy/d*u.speed*0.03;
      u.col=ncol; u.row=nrow;
      const np=isoToScreen(ncol, nrow);
      u.x=np.x; u.y=np.y;
    }

    if(res.dist<=u.range && u.atk>0){
      u.atkTimer++;
      if(u.atkTimer>=u.atkSpeed){
        u.atkTimer=0;
        if(u.range>2){
          fireArrow(u, res.target);
        } else {
          res.target.hp-=u.atk;
          spawnEffect(res.target.x, res.target.y-15*sc);
          if(res.target.hp<=0) res.target.dead=true;
        }
      }
    }
  }

  // Update enemies
  for(const e of enemies){
    if(e.dead)continue;
    const res=findTarget(e, units);
    if(!res)continue;

    if(e.speed>0 && res.dist>e.range){
      const dx=res.target.col-e.col;
      const dy=res.target.row-e.row;
      const d=Math.sqrt(dx*dx+dy*dy);
      e.col+=dx/d*e.speed*0.03;
      e.row+=dy/d*e.speed*0.03;
      const np=isoToScreen(e.col, e.row);
      e.x=np.x; e.y=np.y;
    }

    if(res.dist<=e.range && e.atk>0){
      e.atkTimer++;
      if(e.atkTimer>=e.atkSpeed){
        e.atkTimer=0;
        res.target.hp-=e.atk;
        spawnEffect(res.target.x, res.target.y-15*sc);
        if(res.target.hp<=0) res.target.dead=true;
      }
    }
  }

  // Update arrows
  for(let i=arrows.length-1;i>=0;i--){
    const a=arrows[i];
    const dx=a.tx-a.x, dy=a.ty-a.y;
    const d=Math.sqrt(dx*dx+dy*dy);
    if(d<a.speed||d<2){
      // Hit
      if(a.target && !a.target.dead){
        a.target.hp-=a.atk;
        spawnEffect(a.target.x, a.target.y-15*sc);
        if(a.target.hp<=0) a.target.dead=true;
      }
      arrows.splice(i,1);
    } else {
      a.x+=dx/d*a.speed;
      a.y+=dy/d*a.speed;
    }
  }

  // Update effects
  for(let i=effects.length-1;i>=0;i--){
    effects[i].life-=0.04;
    if(effects[i].life<=0)effects.splice(i,1);
  }

  // Check win/lose
  const aliveUnits=units.filter(u=>!u.dead).length;
  const aliveEnemies=enemies.filter(e=>!e.dead).length;

  if(aliveEnemies===0 && !resultShown){
    won=true; phase=PHASE_RESULT; resultShown=true;
    setTimeout(showCTA, 800);
  } else if(aliveUnits===0 && battleTimer>60 && !resultShown){
    won=false; phase=PHASE_RESULT; resultShown=true;
    setTimeout(showCTA, 800);
  }
}

function showCTA(){
  const el=document.getElementById('cta');
  document.getElementById('cta-title').textContent=won?'VICTORY!':'DEFEATED!';
  document.getElementById('cta-sub').textContent=won?'You are a master tactician!':'The enemy was too strong...';
  el.classList.add('show');
}

function restartAll(){initGame();}

// ===== DRAW =====
function drawTile(col,row,fill,stroke){
  const p=isoToScreen(col,row);
  const hw=TW*sc/2, hh=TH*sc/2;
  cx.beginPath();
  cx.moveTo(p.x, p.y-hh);
  cx.lineTo(p.x+hw, p.y);
  cx.lineTo(p.x, p.y+hh);
  cx.lineTo(p.x-hw, p.y);
  cx.closePath();
  if(fill){cx.fillStyle=fill;cx.fill();}
  if(stroke){cx.strokeStyle=stroke;cx.lineWidth=1;cx.stroke();}
}

function drawGrid(){
  for(let c=0;c<COLS;c++){
    for(let r=0;r<ROWS;r++){
      const isPlayerZone=c<=3;
      const isEnemyZone=c>=5;
      let fill, stroke;
      if(isPlayerZone){
        fill='rgba(100,180,255,0.12)';
        stroke='rgba(100,180,255,0.3)';
      } else if(isEnemyZone){
        fill='rgba(255,80,80,0.10)';
        stroke='rgba(255,80,80,0.25)';
      } else {
        fill='rgba(255,255,255,0.05)';
        stroke='rgba(255,255,255,0.15)';
      }
      drawTile(c,r,fill,stroke);
    }
  }
}

function drawShadow(x,y,w){
  if(!IMG.shadow)return;
  cx.globalAlpha=0.3;
  cx.drawImage(IMG.shadow, x-w/2, y-w*0.2, w, w*0.4);
  cx.globalAlpha=1;
}

function drawHPBar(x,y,hp,maxHp,color){
  const bw=30*sc, bh=4*sc;
  const bx=x-bw/2, by=y;
  cx.fillStyle='rgba(0,0,0,0.5)';
  cx.fillRect(bx-1,by-1,bw+2,bh+2);
  cx.fillStyle='#333';
  cx.fillRect(bx,by,bw,bh);
  cx.fillStyle=hp/maxHp>0.5?'#66BB6A':hp/maxHp>0.25?'#FFA726':'#EF5350';
  cx.fillRect(bx,by,bw*(hp/maxHp),bh);
}

function drawWarrior(x,y,color,hp,maxHp,isEnemy,bob){
  const sz=18*sc;
  drawShadow(x,y+5*sc,sz*1.8);

  // Body
  cx.fillStyle=color;
  const by=y-sz+Math.sin(bob)*2*sc;

  // Shield (circle)
  cx.beginPath();
  cx.arc(x+(isEnemy?-5:5)*sc, by+sz*0.3, sz*0.3, 0, Math.PI*2);
  cx.fill();

  // Body rectangle
  cx.fillRect(x-sz*0.25, by, sz*0.5, sz*0.7);

  // Head
  cx.fillStyle=isEnemy?'#FFCDD2':'#E1F5FE';
  cx.beginPath();
  cx.arc(x, by, sz*0.3, 0, Math.PI*2);
  cx.fill();

  // Sword / weapon line
  cx.strokeStyle=isEnemy?'#B71C1C':'#0277BD';
  cx.lineWidth=2*sc;
  cx.beginPath();
  cx.moveTo(x+(isEnemy?5:-5)*sc, by+sz*0.2);
  cx.lineTo(x+(isEnemy?14:-14)*sc, by-sz*0.1);
  cx.stroke();

  // Helmet detail
  cx.fillStyle=color;
  cx.fillRect(x-sz*0.35, by-sz*0.35, sz*0.7, sz*0.15);

  drawHPBar(x,by-sz*0.5,hp,maxHp,color);
}

function drawBuildingUnit(x,y,imgKey,hp,maxHp,bob){
  const sz=40*sc;
  drawShadow(x, y+5*sc, sz*1.2);
  if(IMG[imgKey]){
    cx.drawImage(IMG[imgKey], x-sz/2, y-sz+Math.sin(bob)*1.5*sc, sz, sz);
  }
  drawHPBar(x, y-sz-2*sc, hp, maxHp);
}

function drawUnits(){
  // Collect all entities, sort by row for proper depth
  const all=[];
  for(const u of units){
    if(!u.dead) all.push({...u, isEnemy:false});
  }
  for(const e of enemies){
    if(!e.dead) all.push({...e, isEnemy:true});
  }
  // Sort by row (+ col for tie-breaking) for depth order
  all.sort((a,b)=>(a.row+a.col*0.01)-(b.row+b.col*0.01));

  for(const ent of all){
    ent.bobPhase+=0.03;
    if(ent.type==='warrior'||ent.type==='grunt'||ent.type==='heavy'){
      const sz=ent.type==='heavy'?1.3:1;
      cx.save();
      if(sz!==1){cx.translate(ent.x,ent.y);cx.scale(sz,sz);cx.translate(-ent.x,-ent.y);}
      drawWarrior(ent.x, ent.y, ent.color, ent.hp, ent.maxHp, ent.isEnemy, ent.bobPhase);
      cx.restore();
    } else if(ent.type==='archerTower'){
      drawBuildingUnit(ent.x, ent.y, 'archer', ent.hp, ent.maxHp, ent.bobPhase);
    } else if(ent.type==='defTower'){
      drawBuildingUnit(ent.x, ent.y, 'tower', ent.hp, ent.maxHp, ent.bobPhase);
    }
  }
}

function drawArrows(){
  for(const a of arrows){
    if(!IMG.arrow)continue;
    const dx=a.tx-a.x, dy=a.ty-a.y;
    const angle=Math.atan2(dy,dx);
    cx.save();
    cx.translate(a.x,a.y);
    cx.rotate(angle);
    cx.drawImage(IMG.arrow, -15*sc, -7*sc, 30*sc, 14*sc);
    cx.restore();
  }
}

function drawEffects(){
  for(const e of effects){
    if(!IMG.fx)continue;
    cx.globalAlpha=e.life;
    const sz=e.size*e.life;
    cx.drawImage(IMG.fx, e.x-sz/2, e.y-sz/2, sz, sz);
  }
  cx.globalAlpha=1;
}

function drawMapDecor(){
  // Big tree top-right area
  if(IMG.bigtree){
    const sz=80*sc;
    cx.globalAlpha=0.5;
    cx.drawImage(IMG.bigtree, W-sz*1.1, H*0.02, sz, sz);
    cx.globalAlpha=1;
  }
  // Small trees scattered
  if(IMG.tree){
    const tsz=22*sc;
    cx.globalAlpha=0.4;
    cx.drawImage(IMG.tree, W*0.05, gridOY-15*sc, tsz, tsz*1.44);
    cx.drawImage(IMG.tree, W*0.88, gridOY+20*sc, tsz*0.8, tsz*1.15);
    cx.globalAlpha=1;
  }
  if(IMG.tree2){
    const tsz=25*sc;
    cx.globalAlpha=0.45;
    cx.drawImage(IMG.tree2, W*0.02, gridOY+ROWS*TH*sc*0.6, tsz, tsz*1.65);
    cx.globalAlpha=1;
  }
}

function drawTray(){
  if(phase!==PHASE_DEPLOY)return;
  const tray=getTrayAreas();

  // Tray background
  const trayBg=H-110*sc;
  cx.fillStyle='rgba(0,0,0,0.5)';
  cx.beginPath();
  cx.roundRect(10, trayBg, W-20, H-trayBg-5, 12*sc);
  cx.fill();
  cx.strokeStyle='rgba(255,215,0,0.3)';
  cx.lineWidth=1;
  cx.beginPath();
  cx.roundRect(10, trayBg, W-20, H-trayBg-5, 12*sc);
  cx.stroke();

  for(const t of tray){
    const def=UNIT_DEF[t.type];
    const canAfford=budget>=def.cost;

    // Card background
    cx.fillStyle=canAfford?'rgba(255,255,255,0.1)':'rgba(255,255,255,0.03)';
    cx.beginPath();
    cx.roundRect(t.x, t.y, t.w, t.h, 8*sc);
    cx.fill();
    cx.strokeStyle=canAfford?def.color:'rgba(255,255,255,0.1)';
    cx.lineWidth=canAfford?2:1;
    cx.beginPath();
    cx.roundRect(t.x, t.y, t.w, t.h, 8*sc);
    cx.stroke();

    // Icon
    const iconSz=32*sc;
    const iconX=t.x+t.w/2, iconY=t.y+t.h*0.38;
    cx.globalAlpha=canAfford?1:0.3;
    if(t.type==='warrior'){
      drawWarrior(iconX, iconY+10*sc, def.color, def.hp, def.hp, false, frame*0.03);
    } else if(t.type==='archerTower' && IMG.archer){
      cx.drawImage(IMG.archer, iconX-iconSz/2, iconY-iconSz/2, iconSz, iconSz);
    } else if(t.type==='defTower' && IMG.tower){
      cx.drawImage(IMG.tower, iconX-iconSz/2, iconY-iconSz/2, iconSz, iconSz);
    }
    cx.globalAlpha=1;

    // Label
    cx.fillStyle=canAfford?'#fff':'#666';
    cx.font=(10*sc)+'px "Segoe UI",sans-serif';
    cx.textAlign='center';
    cx.fillText(def.label, t.x+t.w/2, t.y+t.h-18*sc);

    // Cost
    if(IMG.coin){
      const coinSz=14*sc;
      cx.drawImage(IMG.coin, t.x+t.w/2-coinSz-2, t.y+t.h-14*sc, coinSz, coinSz);
      cx.fillStyle=canAfford?'#FFD700':'#666';
      cx.font='bold '+(11*sc)+'px "Segoe UI",sans-serif';
      cx.fillText(def.cost, t.x+t.w/2+coinSz/2+2, t.y+t.h-4*sc);
    }
  }
  cx.textAlign='left';

  // Fight button (if units placed)
  if(units.length>0){
    const fb=getFightBtnArea();
    if(IMG.btn){
      cx.drawImage(IMG.btn, fb.x, fb.y, fb.w, fb.h);
    } else {
      cx.fillStyle='#FFA000';
      cx.beginPath();
      cx.roundRect(fb.x, fb.y, fb.w, fb.h, 8*sc);
      cx.fill();
    }
    cx.fillStyle='#3E2723';
    cx.font='bold '+(16*sc)+'px "Segoe UI",sans-serif';
    cx.textAlign='center';
    cx.fillText('FIGHT!', fb.x+fb.w/2, fb.y+fb.h/2+5*sc);
    cx.textAlign='left';
  }
}

function drawHUD(){
  // Budget display
  const hudY=10;
  cx.fillStyle='rgba(0,0,0,0.5)';
  cx.beginPath();
  cx.roundRect(10, hudY, 110*sc, 30*sc, 15*sc);
  cx.fill();
  if(IMG.coin){
    cx.drawImage(IMG.coin, 16, hudY+3, 24*sc, 24*sc);
  }
  cx.fillStyle='#FFD700';
  cx.font='bold '+(16*sc)+'px "Segoe UI",sans-serif';
  cx.fillText(budget, 16+28*sc, hudY+20*sc);

  // Phase label
  cx.fillStyle='rgba(255,255,255,0.6)';
  cx.font=(11*sc)+'px "Segoe UI",sans-serif';
  cx.textAlign='right';
  if(phase===PHASE_DEPLOY){
    cx.fillText('Deploy Phase', W-15, hudY+20*sc);
  } else if(phase===PHASE_BATTLE){
    cx.fillStyle='#EF5350';
    cx.fillText('Battle!', W-15, hudY+20*sc);
  }
  cx.textAlign='left';

  // Unit counts
  if(phase===PHASE_BATTLE){
    const au=units.filter(u=>!u.dead).length;
    const ae=enemies.filter(e=>!e.dead).length;
    cx.fillStyle='#4FC3F7';
    cx.font='bold '+(12*sc)+'px "Segoe UI",sans-serif';
    cx.fillText('Allies: '+au, 15, hudY+50*sc);
    cx.fillStyle='#EF5350';
    cx.fillText('Enemies: '+ae, W/2+10, hudY+50*sc);
  }
}

function drawTutorial(){
  if(phase!==PHASE_DEPLOY||tutorialAlpha<=0||units.length>0)return;
  tutorialAlpha=0.5+0.5*Math.sin(frame*0.05);
  cx.globalAlpha=tutorialAlpha;
  cx.fillStyle='#fff';
  cx.font='bold '+(14*sc)+'px "Segoe UI",sans-serif';
  cx.textAlign='center';
  cx.fillText('Drag units to the blue zone!', W/2, gridOY-18*sc);

  // Arrow pointing down to tray
  cx.fillText('\\u2B07', W/2, H-115*sc);
  cx.textAlign='left';
  cx.globalAlpha=1;
}

function drawDragPreview(){
  if(!dragUnit||!dragType)return;
  const iso=screenToIso(dragX, dragY);
  const valid=iso.col>=0 && iso.col<=3 && iso.row>=0 && iso.row<ROWS && !grid[iso.col]?.[iso.row];

  // Highlight target tile
  if(valid){
    drawTile(iso.col, iso.row, 'rgba(100,255,100,0.3)', 'rgba(100,255,100,0.7)');
  }

  // Draw unit at drag position
  cx.globalAlpha=0.7;
  const def=UNIT_DEF[dragType];
  if(dragType==='warrior'){
    drawWarrior(dragX, dragY, def.color, def.hp, def.hp, false, frame*0.05);
  } else if(dragType==='archerTower' && IMG.archer){
    const sz=40*sc;
    cx.drawImage(IMG.archer, dragX-sz/2, dragY-sz, sz, sz);
  } else if(dragType==='defTower' && IMG.tower){
    const sz=40*sc;
    cx.drawImage(IMG.tower, dragX-sz/2, dragY-sz, sz, sz);
  }
  cx.globalAlpha=1;
}

function drawBackground(){
  // Sky gradient
  const grad=cx.createLinearGradient(0,0,0,H);
  grad.addColorStop(0,'#1a2a3a');
  grad.addColorStop(0.5,'#2a3a2a');
  grad.addColorStop(1,'#1a2a1a');
  cx.fillStyle=grad;
  cx.fillRect(0,0,W,H);

  // Subtle ground plane below grid
  const groundY=gridOY+ROWS*TH*sc/2+20*sc;
  const gGrad=cx.createLinearGradient(0,groundY-30*sc,0,H);
  gGrad.addColorStop(0,'rgba(60,100,40,0.2)');
  gGrad.addColorStop(1,'rgba(30,60,20,0.3)');
  cx.fillStyle=gGrad;
  cx.fillRect(0,groundY-30*sc,W,H);
}

// ===== MAIN LOOP =====
function loop(){
  frame++;
  calcGrid();

  if(phase===PHASE_BATTLE) updateBattle();

  drawBackground();
  drawMapDecor();
  drawGrid();
  drawUnits();
  drawArrows();
  drawEffects();
  drawDragPreview();
  drawHUD();
  drawTray();
  drawTutorial();

  requestAnimationFrame(loop);
}

function startApp(){
  initGame();
  loop();
}
</script>
</body>
</html>`;

const outPath = 'E:/AI/projects/slg-playable/output/playable.html';
fs.writeFileSync(outPath, html, 'utf8');
const stats = fs.statSync(outPath);
console.log('Written: ' + outPath);
console.log('File size: ' + (stats.size / 1024).toFixed(1) + ' KB (' + stats.size + ' bytes)');
console.log('Under 5MB: ' + (stats.size < 5242880 ? 'YES' : 'NO'));
console.log('Under 2MB: ' + (stats.size < 2097152 ? 'YES' : 'NO'));
