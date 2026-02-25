'use strict';
const fs = require('fs');

// ==================== LOAD ASSETS ====================
const assetsFile = 'E:/AI/projects/SLG-PinPull-Pro/assets/base64_assets.txt';
const content = fs.readFileSync(assetsFile, 'utf8');
const lines = content.split('\n');
const assets = {};
let i = 0;
while (i < lines.length) {
  const line = lines[i].trim();
  if (line.startsWith('// ')) {
    const name = line.slice(3).trim();
    if (i + 1 < lines.length) {
      assets[name] = lines[i + 1].trim();
    }
    i += 3;
  } else {
    i++;
  }
}

console.log('Assets loaded:');
for (const [k, v] of Object.entries(assets)) {
  console.log(`  ${k}: ${v.length} chars`);
}

// ==================== BUILD HTML ====================
const html = buildHTML(assets);
const outPath = 'E:/AI/projects/SLG-PinPull-Pro/output/playable.html';
fs.writeFileSync(outPath, html, 'utf8');
const size = fs.statSync(outPath).size;
console.log(`\nOutput: ${outPath}`);
console.log(`Size: ${size} bytes (${(size/1024).toFixed(1)} KB / ${(size/1024/1024).toFixed(3)} MB)`);
console.log(`Under 2MB: ${size < 2*1024*1024 ? 'YES' : 'NO'}`);

// ==================== VERIFICATION ====================
const src = fs.readFileSync(outPath, 'utf8');
console.log('\n=== Self-Verification ===');
const checks = [
  ['1. No external HTTP requests', !/(fetch|XMLHttpRequest|src\s*=\s*["']https?:\/\/)/i.test(src)],
  ['2. Touch event handlers', /touchstart/i.test(src) && /touchend/i.test(src)],
  ['3. Mouse event handlers', /mousedown/i.test(src) && /mouseup/i.test(src)],
  ['4. CTA button with onclick', /id="cta-btn"/.test(src) && /onclick/.test(src)],
  ['5. File size < 2MB', size < 2*1024*1024],
  ['6. requestAnimationFrame used', /requestAnimationFrame/i.test(src)],
  ['7. devicePixelRatio handled', /devicePixelRatio/i.test(src)],
  ['8. MRAID ready check', /mraid\.isReady\(\)/.test(src)],
  ['9. WebAudio sounds defined', /AudioContext|webkitAudioContext/i.test(src)],
  ['10. Object pool for particles', /pPool|particlePool|lPool/.test(src)],
  ['11. Screen shake implemented', /triggerShake/.test(src)],
];
let allPass = true;
for (const [label, pass] of checks) {
  console.log(`  ${pass ? 'PASS' : 'FAIL'} ${label}`);
  if (!pass) allPass = false;
}
console.log(`\nAll checks passed: ${allPass ? 'YES' : 'NO'}`);

// ==================== HTML BUILDER ====================
function buildHTML(a) {
  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>SLG Pin Pull Pro - Playable Ad</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#000;display:flex;align-items:center;justify-content:center;width:100vw;height:100vh;overflow:hidden;font-family:'Arial Black',Arial,sans-serif;}
#wrap{position:relative;width:540px;height:960px;overflow:hidden;transform-origin:top left;}
#game{position:absolute;top:0;left:0;display:block;cursor:pointer;}
#cta-overlay{position:absolute;top:0;left:0;width:100%;height:100%;display:none;flex-direction:column;align-items:center;justify-content:center;background:rgba(0,0,0,0);z-index:100;transition:background 0.5s;}
#cta-overlay.show{display:flex;background:rgba(0,0,0,0.75);}
.cta-inner{display:flex;flex-direction:column;align-items:center;padding:44px 36px;background:linear-gradient(160deg,#12163a 0%,#0d2458 60%,#1a0a2e 100%);border-radius:28px;border:3px solid #FFD700;box-shadow:0 0 50px rgba(255,215,0,0.4),0 0 100px rgba(255,100,0,0.2);max-width:440px;width:88%;animation:ctaIn 0.6s cubic-bezier(0.175,0.885,0.32,1.275) both;}
@keyframes ctaIn{from{transform:scale(0.3) rotate(-5deg);opacity:0;}to{transform:scale(1) rotate(0);opacity:1;}}
.cta-game-title{font-size:34px;font-weight:900;color:#FFD700;text-shadow:0 0 20px rgba(255,215,0,0.9),0 2px 0 #8B6914;margin-bottom:10px;text-align:center;letter-spacing:3px;}
.cta-stars{font-size:32px;margin-bottom:10px;letter-spacing:4px;}
.cta-title{font-size:28px;font-weight:900;color:#fff;margin-bottom:8px;text-align:center;line-height:1.2;text-shadow:0 2px 8px rgba(0,0,0,0.8);}
.cta-subtitle{font-size:16px;color:#99bbff;margin-bottom:30px;text-align:center;line-height:1.5;}
.cta-btn{background:linear-gradient(135deg,#FF8C00 0%,#FF3D00 50%,#CC0000 100%);color:#fff;border:none;border-radius:50px;padding:22px 64px;font-size:26px;font-weight:900;cursor:pointer;letter-spacing:2px;box-shadow:0 8px 32px rgba(255,80,0,0.7),0 2px 0 rgba(255,255,255,0.2) inset;transition:transform 0.1s,box-shadow 0.1s;text-transform:uppercase;outline:none;-webkit-tap-highlight-color:transparent;text-shadow:0 2px 4px rgba(0,0,0,0.5);}
.cta-btn:hover{box-shadow:0 12px 40px rgba(255,80,0,0.9);}
.cta-btn:active{transform:scale(0.95) !important;box-shadow:0 4px 16px rgba(255,80,0,0.6);}
#loading{position:absolute;top:0;left:0;width:100%;height:100%;background:radial-gradient(ellipse at 50% 40%,#1a2c6e 0%,#0a0f28 100%);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:200;}
.load-logo{font-size:48px;font-weight:900;color:#FFD700;text-shadow:0 0 30px rgba(255,215,0,0.6),0 4px 0 #8B6914;letter-spacing:4px;margin-bottom:8px;}
.load-sub{font-size:22px;color:#FF6B00;font-weight:700;letter-spacing:2px;margin-bottom:32px;}
.load-bar-wrap{width:300px;height:10px;background:rgba(255,255,255,0.1);border-radius:5px;overflow:hidden;box-shadow:0 0 10px rgba(255,200,0,0.2);}
.load-bar{height:100%;background:linear-gradient(90deg,#FF6B00,#FFD700);border-radius:5px;width:0%;transition:width 0.2s;}
.load-text{font-size:14px;color:#667;margin-top:12px;letter-spacing:1px;}
</style>
</head>
<body>
<div id="wrap">
  <canvas id="game"></canvas>
  <div id="loading">
    <div class="load-logo">PIN PULL</div>
    <div class="load-sub">PRO</div>
    <div class="load-bar-wrap"><div class="load-bar" id="load-bar"></div></div>
    <div class="load-text">LOADING...</div>
  </div>
  <div id="cta-overlay">
    <div class="cta-inner">
      <div class="cta-game-title">PIN PULL PRO</div>
      <div class="cta-stars" id="cta-stars">★★★</div>
      <div class="cta-title" id="cta-title">CAN YOU SOLVE IT?</div>
      <div class="cta-subtitle" id="cta-subtitle">Download now and prove your skills!</div>
      <button class="cta-btn" id="cta-btn" onclick="window.__openStore()">INSTALL NOW</button>
    </div>
  </div>
</div>
<script>
(function(){"use strict";

// ==================== MRAID 2.0 ====================
var mraidReady=false;
function onMraidReady(){
  mraidReady=true;
  if(typeof mraid!=='undefined'){
    mraid.addEventListener('viewableChange',function(v){
      if(v&&gameState==='title'){}
    });
    var st=mraid.getState();
    if(st==='hidden')return;
  }
}
if(typeof mraid!=='undefined'){
  if(mraid.isReady())onMraidReady();
  else mraid.addEventListener('ready',onMraidReady);
}

// ==================== STORE URL ====================
window.__openStore=function(){
  SFX.buttonClick();
  var ua=navigator.userAgent.toLowerCase();
  var url=(ua.indexOf('iphone')>-1||ua.indexOf('ipad')>-1||ua.indexOf('ipod')>-1)
    ?'https://apps.apple.com'
    :'https://play.google.com/store';
  if(typeof mraid!=='undefined'){mraid.open(url);}
  else{window.open(url,'_blank');}
};

// ==================== ASSETS ====================
var ASSETS={
  map_bg:  {src:'${a['Map_2048']}',img:null},
  hero:    {src:'${a['NPC_Summon_001_D']}',img:null},
  enemy:   {src:'${a['MOB_Cactus01_red_D']}',img:null},
  boss:    {src:'${a['MOB_Boss_Cactus_Crown_D']}',img:null},
  tower:   {src:'${a['TowerA']}',img:null},
  wall_tex:{src:'${a['WallA']}',img:null},
  arrow:   {src:'${a['Arrow']}',img:null},
  coin:    {src:'${a['Coin']}',img:null},
  button:  {src:'${a['Button']}',img:null},
  star:    {src:'${a['Effect_Star_1']}',img:null},
  shadow:  {src:'${a['Shadow']}',img:null}
};

function loadAssets(cb){
  var keys=Object.keys(ASSETS),loaded=0,bar=document.getElementById('load-bar');
  keys.forEach(function(k){
    var img=new Image();
    img.onload=img.onerror=function(){
      loaded++;
      if(bar)bar.style.width=Math.round(loaded/keys.length*100)+'%';
      if(loaded===keys.length)cb();
    };
    img.src=ASSETS[k].src;
    ASSETS[k].img=img;
  });
}

// ==================== CANVAS ====================
var wrap=document.getElementById('wrap');
var canvas=document.getElementById('game');
var ctx=canvas.getContext('2d');
var DPR=window.devicePixelRatio||1;
var W=540,H=960;
canvas.width=W*DPR; canvas.height=H*DPR;
canvas.style.width=W+'px'; canvas.style.height=H+'px';
ctx.scale(DPR,DPR);

function resize(){
  var vw=window.innerWidth,vh=window.innerHeight;
  var sc=Math.min(vw/W,vh/H);
  wrap.style.transform='scale('+sc+')';
  wrap.style.transformOrigin='top left';
  wrap.style.left=((vw-W*sc)/2)+'px';
  wrap.style.top=((vh-H*sc)/2)+'px';
}
resize();
window.addEventListener('resize',resize);

// ==================== AUDIO ====================
var audioCtx=null;
function getAC(){
  if(!audioCtx)audioCtx=new(window.AudioContext||window.webkitAudioContext)();
  if(audioCtx.state==='suspended')audioCtx.resume();
  return audioCtx;
}
var SFX={
  pinPull:function(){
    var ac=getAC(),o=ac.createOscillator(),g=ac.createGain();
    o.type='sawtooth';o.connect(g);g.connect(ac.destination);
    o.frequency.setValueAtTime(800,ac.currentTime);
    o.frequency.exponentialRampToValueAtTime(200,ac.currentTime+0.3);
    g.gain.setValueAtTime(0.28,ac.currentTime);
    g.gain.linearRampToValueAtTime(0,ac.currentTime+0.3);
    o.start();o.stop(ac.currentTime+0.3);
  },
  lavaFlow:function(){
    var ac=getAC(),n=ac.sampleRate*0.9,b=ac.createBuffer(1,n,ac.sampleRate);
    var d=b.getChannelData(0);for(var i=0;i<n;i++)d[i]=(Math.random()*2-1)*0.4;
    var s=ac.createBufferSource();s.buffer=b;
    var f=ac.createBiquadFilter();f.type='lowpass';f.frequency.value=180;
    var g=ac.createGain();
    g.gain.setValueAtTime(0.35,ac.currentTime);
    g.gain.linearRampToValueAtTime(0,ac.currentTime+0.9);
    s.connect(f);f.connect(g);g.connect(ac.destination);
    s.start();s.stop(ac.currentTime+0.9);
  },
  enemyDeath:function(){
    var ac=getAC(),n=ac.sampleRate*0.2,b=ac.createBuffer(1,n,ac.sampleRate);
    var d=b.getChannelData(0);for(var i=0;i<n;i++)d[i]=(Math.random()*2-1);
    var s=ac.createBufferSource();s.buffer=b;
    var o=ac.createOscillator();o.type='square';o.frequency.value=180;
    var g=ac.createGain();
    g.gain.setValueAtTime(0.45,ac.currentTime);
    g.gain.linearRampToValueAtTime(0,ac.currentTime+0.22);
    s.connect(g);o.connect(g);g.connect(ac.destination);
    s.start();s.stop(ac.currentTime+0.2);
    o.start();o.stop(ac.currentTime+0.22);
  },
  heroSave:function(){
    var ac=getAC(),[523,659,784].forEach(function(f,i){
      var o=ac.createOscillator(),g=ac.createGain();
      o.type='sine';o.frequency.value=f;
      var t=ac.currentTime+i*0.12;
      g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(0.38,t+0.05);
      g.gain.linearRampToValueAtTime(0,t+0.18);
      o.connect(g);g.connect(ac.destination);o.start(t);o.stop(t+0.2);
    });
  },
  coinCollect:function(){
    var ac=getAC(),o=ac.createOscillator(),g=ac.createGain();
    o.type='sine';o.frequency.value=1200;
    g.gain.setValueAtTime(0.28,ac.currentTime);
    g.gain.linearRampToValueAtTime(0,ac.currentTime+0.12);
    o.connect(g);g.connect(ac.destination);o.start();o.stop(ac.currentTime+0.12);
  },
  buttonClick:function(){
    var ac=getAC(),o=ac.createOscillator(),g=ac.createGain();
    o.type='square';o.frequency.value=600;
    g.gain.setValueAtTime(0.18,ac.currentTime);
    g.gain.linearRampToValueAtTime(0,ac.currentTime+0.06);
    o.connect(g);g.connect(ac.destination);o.start();o.stop(ac.currentTime+0.06);
  },
  shake:function(){
    var ac=getAC(),o=ac.createOscillator(),g=ac.createGain();
    o.type='sine';o.frequency.value=150;
    g.gain.setValueAtTime(0.22,ac.currentTime);
    g.gain.linearRampToValueAtTime(0,ac.currentTime+0.2);
    o.connect(g);g.connect(ac.destination);o.start();o.stop(ac.currentTime+0.2);
  },
  fail:function(){
    var ac=getAC(),o=ac.createOscillator(),g=ac.createGain();
    o.type='sawtooth';
    o.frequency.setValueAtTime(380,ac.currentTime);
    o.frequency.exponentialRampToValueAtTime(95,ac.currentTime+0.5);
    g.gain.setValueAtTime(0.32,ac.currentTime);
    g.gain.linearRampToValueAtTime(0,ac.currentTime+0.5);
    o.connect(g);g.connect(ac.destination);o.start();o.stop(ac.currentTime+0.5);
  },
  levelClear:function(){
    var ac=getAC(),[523,659,784,1047].forEach(function(f,i){
      var o=ac.createOscillator(),g=ac.createGain();
      o.type='sine';o.frequency.value=f;
      var t=ac.currentTime+i*0.14;
      g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(0.32,t+0.05);
      g.gain.linearRampToValueAtTime(0,t+0.22);
      o.connect(g);g.connect(ac.destination);o.start(t);o.stop(t+0.25);
    });
  }
};

// ==================== TWEEN ENGINE ====================
var tweens=[];
var Ease={
  linear:function(t){return t;},
  easeInOut:function(t){return t<0.5?2*t*t:-1+(4-2*t)*t;},
  easeOutElastic:function(t){
    if(t<=0)return 0;if(t>=1)return 1;
    var p=0.3;return Math.pow(2,-10*t)*Math.sin((t-p/4)*(2*Math.PI)/p)+1;
  },
  easeOutBounce:function(t){
    if(t<1/2.75)return 7.5625*t*t;
    if(t<2/2.75){t-=1.5/2.75;return 7.5625*t*t+0.75;}
    if(t<2.5/2.75){t-=2.25/2.75;return 7.5625*t*t+0.9375;}
    t-=2.625/2.75;return 7.5625*t*t+0.984375;
  },
  easeOutBack:function(t){var s=1.70158;t=t-1;return t*t*((s+1)*t+s)+1;}
};
function tween(obj,prop,fr,to,dur,ease,done){
  tweens.push({obj:obj,prop:prop,fr:fr,to:to,dur:dur,ease:ease||'linear',done:done||null,el:0,fin:false});
}
function updateTweens(dt){
  for(var i=tweens.length-1;i>=0;i--){
    var tw=tweens[i];
    if(tw.fin){tweens.splice(i,1);continue;}
    tw.el+=dt;
    var t=Math.min(tw.el/tw.dur,1);
    var et=Ease[tw.ease]?Ease[tw.ease](t):t;
    tw.obj[tw.prop]=tw.fr+(tw.to-tw.fr)*et;
    if(t>=1){tw.obj[tw.prop]=tw.to;tw.fin=true;if(tw.done)tw.done();}
  }
}

// ==================== SCREEN SHAKE ====================
var shakeX=0,shakeY=0,shakeInt=0,shakeDur=0,shakeEl=0;
function triggerShake(intensity,duration){
  shakeInt=intensity;shakeDur=duration/1000;shakeEl=0;
  try{SFX.shake();}catch(e){}
}
function updateShake(dt){
  if(shakeEl<shakeDur){
    shakeEl+=dt;
    var decay=1-(shakeEl/shakeDur);
    var ii=shakeInt*decay;
    shakeX=(Math.random()*2-1)*ii;shakeY=(Math.random()*2-1)*ii;
  }else{shakeX=0;shakeY=0;}
}

// ==================== PARTICLE POOL ====================
var POOL=200;
var pPool=[];
for(var _pi=0;_pi<POOL;_pi++)pPool.push({active:false,x:0,y:0,vx:0,vy:0,r:5,color:'#FF4400',alpha:1,life:0,maxLife:1});

function getPart(){
  for(var i=0;i<POOL;i++)if(!pPool[i].active)return pPool[i];
  return null;
}
function spawnExplosion(x,y,big){
  var colors=['#FF4400','#FF8800','#FFCC00','#FF2200','#FFEE00'];
  var count=big?18:12;
  for(var i=0;i<count;i++){
    var p=getPart();if(!p)continue;
    var angle=(i/count)*Math.PI*2;
    var spd=(big?120:80)+Math.random()*140;
    p.active=true;p.x=x;p.y=y;
    p.vx=Math.cos(angle)*spd;p.vy=Math.sin(angle)*spd;
    p.r=(big?5:4)+Math.random()*8;
    p.color=colors[Math.floor(Math.random()*colors.length)];
    p.alpha=1;p.life=0;p.maxLife=0.5+Math.random()*0.35;
  }
}
function spawnCoinBurst(x,y){
  var colors=['#FFD700','#FFA500','#FFEC00'];
  for(var i=0;i<8;i++){
    var p=getPart();if(!p)continue;
    var angle=-Math.PI/2+(Math.random()-0.5)*Math.PI*1.2;
    var spd=100+Math.random()*120;
    p.active=true;p.x=x;p.y=y;
    p.vx=Math.cos(angle)*spd;p.vy=Math.sin(angle)*spd-60;
    p.r=4+Math.random()*4;
    p.color=colors[Math.floor(Math.random()*colors.length)];
    p.alpha=1;p.life=0;p.maxLife=0.4+Math.random()*0.25;
  }
}
function spawnStarShower(cx,cy,w,h){
  var colors=['#FFD700','#FFFFFF','#FF69B4','#00FFFF','#88FF44'];
  for(var i=0;i<22;i++){
    var p=getPart();if(!p)continue;
    p.active=true;
    p.x=cx+(Math.random()-0.5)*w;p.y=cy+(Math.random()-0.5)*h;
    p.vx=(Math.random()-0.5)*80;p.vy=-100-Math.random()*100;
    p.r=3+Math.random()*8;
    p.color=colors[Math.floor(Math.random()*colors.length)];
    p.alpha=1;p.life=0;p.maxLife=0.8+Math.random()*0.5;
  }
}
function updateParticles(dt){
  for(var i=0;i<POOL;i++){
    var p=pPool[i];if(!p.active)continue;
    p.life+=dt;
    if(p.life>=p.maxLife){p.active=false;continue;}
    p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=220*dt;
    p.alpha=1-(p.life/p.maxLife);
  }
}
function drawParticles(){
  for(var i=0;i<POOL;i++){
    var p=pPool[i];if(!p.active)continue;
    ctx.save();ctx.globalAlpha=p.alpha;
    ctx.fillStyle=p.color;
    ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill();
    ctx.restore();
  }
}

// ==================== LAVA PARTICLE POOL ====================
var LPOOL=80;
var lPool=[];
for(var _li=0;_li<LPOOL;_li++)lPool.push({active:false,x:0,y:0,vx:0,vy:0,r:6,color:'#FF3300',alpha:1,life:0,maxLife:1});

function getLPart(){
  for(var i=0;i<LPOOL;i++)if(!lPool[i].active)return lPool[i];
  return null;
}
function spawnLavaDrip(x,y,count){
  var colors=['#FF2200','#FF5500','#FF7700','#FF3300'];
  var n=count||3;
  for(var i=0;i<n;i++){
    var p=getLPart();if(!p)continue;
    p.active=true;
    p.x=x+(Math.random()-0.5)*20;p.y=y;
    p.vx=(Math.random()-0.5)*25;p.vy=50+Math.random()*70;
    p.r=4+Math.random()*5;
    p.color=colors[Math.floor(Math.random()*colors.length)];
    p.alpha=1;p.life=0;p.maxLife=0.5+Math.random()*0.4;
  }
}
function spawnLavaFlow(sx,sy,dx,dy,count){
  var colors=['#FF2200','#FF5500','#FF7700'];
  var n=count||5;
  for(var i=0;i<n;i++){
    var p=getLPart();if(!p)continue;
    p.active=true;p.x=sx+(Math.random()-0.5)*30;p.y=sy;
    var ex=dx-sx,ey=dy-sy;
    var spd=100+Math.random()*60;
    var len=Math.sqrt(ex*ex+ey*ey)||1;
    p.vx=(ex/len)*spd+(Math.random()-0.5)*40;
    p.vy=(ey/len)*spd+(Math.random()-0.5)*40;
    p.r=5+Math.random()*5;
    p.color=colors[Math.floor(Math.random()*colors.length)];
    p.alpha=1;p.life=0;p.maxLife=0.55+Math.random()*0.4;
  }
}
function updateLava(dt){
  for(var i=0;i<LPOOL;i++){
    var p=lPool[i];if(!p.active)continue;
    p.life+=dt;
    if(p.life>=p.maxLife){p.active=false;continue;}
    p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=130*dt;
    p.alpha=Math.max(0,1-p.life/p.maxLife);
  }
}
function drawLava(){
  for(var i=0;i<LPOOL;i++){
    var p=lPool[i];if(!p.active)continue;
    ctx.save();ctx.globalAlpha=p.alpha*0.88;
    var g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,p.r);
    g.addColorStop(0,'#FFEE00');g.addColorStop(0.5,p.color);g.addColorStop(1,'rgba(180,0,0,0)');
    ctx.fillStyle=g;
    ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill();
    ctx.restore();
  }
}

// ==================== FLOAT TEXTS ====================
var floatTexts=[];
function addFloat(x,y,text,color,sz){
  floatTexts.push({x:x,y:y,text:text,color:color||'#FFD700',alpha:1,vy:-65,life:0,maxLife:1.3,sz:sz||28});
}
function updateFloats(dt){
  for(var i=floatTexts.length-1;i>=0;i--){
    var t=floatTexts[i];
    t.life+=dt;t.y+=t.vy*dt;
    t.alpha=Math.max(0,1-t.life/t.maxLife);
    if(t.life>=t.maxLife)floatTexts.splice(i,1);
  }
}
function drawFloats(){
  floatTexts.forEach(function(t){
    ctx.save();ctx.globalAlpha=t.alpha;
    ctx.fillStyle=t.color;
    ctx.font='bold '+t.sz+'px Arial';
    ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.shadowColor='rgba(0,0,0,0.9)';ctx.shadowBlur=8;
    ctx.fillText(t.text,t.x,t.y);
    ctx.restore();
  });
}

// ==================== GAME STATE ====================
var gameState='loading';
var currentLevel=0;
var failCount=0;
var score=0;
var stateTimer=0;
var resultType='win';
var resultText='';
var resultSubText='';
var stars=[false,false,false];
var starScales=[0,0,0];
var coinsCollected=0;
var globalTimer=0;
var MAX_TIME=35;
var level=null;
var draggedPin=null;
var dragStartX=0,dragStartY=0;
var DRAG_THRESH=18;
var handAlpha=0;
var handPinRef=null;
var levelFailed=false;

// ==================== LEVEL DATA ====================
var LEVEL_DEFS=[
  {// Level 1 - Tutorial (guaranteed win)
    name:'Tutorial',
    lava:{x:170,y:240,w:110,h:85},
    walls:[
      {x:100,y:375,w:340,h:24},
      {x:100,y:220,w:22,h:178},
      {x:418,y:220,w:22,h:178}
    ],
    pins:[
      {id:'pin1',x:270,y:387,w:100,h:20,dir:'right',removed:false,alpha:1,dragX:0,dragY:0,dragging:false,vertical:false}
    ],
    hero:{x:270,y:700,saved:false,hitAnim:0,jumpY:0},
    enemies:[
      {x:270,y:290,type:'regular',alive:true,deathAnim:0}
    ],
    lavaFlowing:false,firstPinRemoved:null
  },
  {// Level 2 - Challenge (order puzzle)
    name:'Challenge',
    lava:{x:185,y:200,w:150,h:100},
    walls:[
      {x:100,y:348,w:340,h:24},
      {x:100,y:465,w:340,h:24}
    ],
    pins:[
      {id:'pin1',x:168,y:360,w:100,h:20,dir:'left',removed:false,alpha:1,dragX:0,dragY:0,dragging:false,vertical:false,wrongFirst:true},
      {id:'pin2',x:340,y:477,w:100,h:20,dir:'right',removed:false,alpha:1,dragX:0,dragY:0,dragging:false,vertical:false,correctFirst:true}
    ],
    hero:{x:340,y:700,saved:false,hitAnim:0,jumpY:0},
    enemies:[
      {x:155,y:270,type:'regular',alive:true,deathAnim:0},
      {x:300,y:255,type:'regular',alive:true,deathAnim:0}
    ],
    lavaFlowing:false,firstPinRemoved:null
  },
  {// Level 3 - Fail Bait (boss + complexity)
    name:'Impossible',
    lava:{x:145,y:155,w:200,h:115},
    walls:[
      {x:100,y:305,w:340,h:24},
      {x:100,y:405,w:200,h:24},
      {x:328,y:405,w:112,h:24},
      {x:100,y:505,w:340,h:24}
    ],
    pins:[
      {id:'pin1',x:128,y:317,w:100,h:20,dir:'left',removed:false,alpha:1,dragX:0,dragY:0,dragging:false,vertical:false},
      {id:'pin2',x:301,y:417,w:20,h:80,dir:'down',removed:false,alpha:1,dragX:0,dragY:0,dragging:false,vertical:true},
      {id:'pin3',x:220,y:517,w:100,h:20,dir:'right',removed:false,alpha:1,dragX:0,dragY:0,dragging:false,vertical:false}
    ],
    hero:{x:340,y:720,saved:false,hitAnim:0,jumpY:0},
    enemies:[
      {x:195,y:205,type:'regular',alive:true,deathAnim:0},
      {x:355,y:225,type:'regular',alive:true,deathAnim:0},
      {x:265,y:165,type:'boss',alive:true,deathAnim:0}
    ],
    lavaFlowing:false,firstPinRemoved:null
  }
];

// ==================== INPUT ====================
function getPos(clientX,clientY){
  var rect=canvas.getBoundingClientRect();
  return{x:(clientX-rect.left)*(W/rect.width),y:(clientY-rect.top)*(H/rect.height)};
}
function onDown(cx,cy){
  getAC();
  if(gameState==='title'){SFX.buttonClick();startLevel(0);return;}
  if(gameState==='result'){
    SFX.buttonClick();
    if(resultType==='fail'||levelFailed){showCTA();}
    else{var nx=currentLevel+1;if(nx<LEVEL_DEFS.length)startLevel(nx);else showCTA();}
    return;
  }
  if(gameState==='playing')tryGrab(cx,cy);
}
function onMove(cx,cy){
  if(gameState!=='playing'||!draggedPin)return;
  var dx=cx-dragStartX,dy=cy-dragStartY;
  if(!draggedPin.vertical)draggedPin.dragX=dx;
  else draggedPin.dragY=dy;
}
function onUp(cx,cy){
  if(gameState==='playing'&&draggedPin)releaseDrag(cx,cy);
  draggedPin=null;
}
canvas.addEventListener('mousedown',function(e){e.preventDefault();var p=getPos(e.clientX,e.clientY);onDown(p.x,p.y);},{passive:false});
canvas.addEventListener('mousemove',function(e){e.preventDefault();var p=getPos(e.clientX,e.clientY);onMove(p.x,p.y);},{passive:false});
canvas.addEventListener('mouseup',function(e){e.preventDefault();var p=getPos(e.clientX,e.clientY);onUp(p.x,p.y);},{passive:false});
canvas.addEventListener('touchstart',function(e){e.preventDefault();var t=e.touches[0];var p=getPos(t.clientX,t.clientY);onDown(p.x,p.y);},{passive:false});
canvas.addEventListener('touchmove',function(e){e.preventDefault();var t=e.touches[0];var p=getPos(t.clientX,t.clientY);onMove(p.x,p.y);},{passive:false});
canvas.addEventListener('touchend',function(e){e.preventDefault();var t=e.changedTouches[0];var p=getPos(t.clientX,t.clientY);onUp(p.x,p.y);},{passive:false});

function tryGrab(cx,cy){
  if(!level||!level.pins)return;
  for(var i=0;i<level.pins.length;i++){
    var pin=level.pins[i];
    if(pin.removed)continue;
    var hw=(pin.w||100)/2+14,hh=(pin.h||20)/2+14;
    if(cx>=pin.x-hw&&cx<=pin.x+hw&&cy>=pin.y-hh&&cy<=pin.y+hh){
      draggedPin=pin;dragStartX=cx;dragStartY=cy;
      pin.dragging=true;pin.dragX=0;pin.dragY=0;
      return;
    }
  }
}
function releaseDrag(cx,cy){
  if(!draggedPin)return;
  var pin=draggedPin;
  pin.dragging=false;
  var dx=cx-dragStartX,dy=cy-dragStartY;
  var removed=false;
  if(!pin.vertical){
    removed=(pin.dir==='right'&&dx>DRAG_THRESH)||(pin.dir==='left'&&dx<-DRAG_THRESH)||Math.abs(dx)>DRAG_THRESH*2;
  }else{
    removed=(pin.dir==='down'&&dy>DRAG_THRESH)||Math.abs(dy)>DRAG_THRESH*2;
  }
  if(removed){removePin(pin);}
  else{
    tween(pin,'dragX',pin.dragX,0,0.18,'easeOutBack');
    tween(pin,'dragY',pin.dragY||0,0,0.18,'easeOutBack');
  }
  draggedPin=null;
}

// ==================== GAME LOGIC ====================
function removePin(pin){
  SFX.pinPull();
  pin.removed=true;pin.dragging=false;
  tween(pin,'alpha',1,0,0.22,'linear');
  if(currentLevel===0)handleL1(pin);
  else if(currentLevel===1)handleL2(pin);
  else if(currentLevel===2)handleL3(pin);
}

function handleL1(pin){
  level.lavaFlowing=true;SFX.lavaFlow();
  spawnLavaFlow(level.lava.x+level.lava.w/2,level.lava.y+level.lava.h,level.enemies[0].x,level.enemies[0].y,10);
  setTimeout(function(){killEnemy(0);},800);
  setTimeout(function(){onWin();},1600);
}

function handleL2(pin){
  level.lavaFlowing=true;SFX.lavaFlow();
  if(!level.firstPinRemoved){
    level.firstPinRemoved=pin.id;
    if(pin.wrongFirst){
      // Wrong order - lava to hero
      addFloat(W/2,380,'WRONG!','#FF4444');
      spawnLavaFlow(level.lava.x+level.lava.w/2,level.lava.y+level.lava.h,level.hero.x,level.hero.y,12);
      setTimeout(function(){
        triggerShake(12,400);
        spawnExplosion(level.hero.x,level.hero.y,false);
        level.hero.hitAnim=1;
        tween(level.hero,'hitAnim',1,0,0.7,'linear');
        SFX.fail();
        setTimeout(function(){onFail('WRONG ORDER!');},700);
      },900);
    }else{
      // Correct first pin (pin2)
      addFloat(W/2,480,'GOOD!','#00FF88');
    }
  }else{
    // Second pin
    if(level.firstPinRemoved==='pin2'&&pin.wrongFirst){
      // Correct sequence: pin2 -> pin1 => enemies die
      spawnLavaFlow(level.lava.x+level.lava.w/2,level.lava.y+level.lava.h,level.enemies[0].x,level.enemies[0].y,8);
      spawnLavaFlow(level.lava.x+level.lava.w/2,level.lava.y+level.lava.h,level.enemies[1].x,level.enemies[1].y,8);
      setTimeout(function(){killEnemy(0);},700);
      setTimeout(function(){killEnemy(1);},950);
      setTimeout(function(){onWin();},1700);
    }else if(level.firstPinRemoved==='pin1'){
      // Already triggered fail from wrong first
    }
  }
}

function handleL3(pin){
  level.lavaFlowing=true;SFX.lavaFlow();
  var removedCount=level.pins.filter(function(p){return p.removed;}).length;
  if(removedCount===1){
    triggerShake(6,500);
    spawnLavaFlow(level.lava.x+level.lava.w/2,level.lava.y+level.lava.h,level.enemies[2].x,level.enemies[2].y,6);
    addFloat(level.enemies[2].x,level.enemies[2].y-50,'BOSS AWAKES!','#FF4400',22);
  }else if(removedCount===2){
    spawnLavaFlow(level.lava.x+level.lava.w/2,level.lava.y+level.lava.h,W/2,550,8);
    triggerShake(8,300);
    addFloat(W/2,420,'DANGER!','#FF6600');
  }else if(removedCount>=3){
    // Fail bait: lava floods to hero
    spawnLavaFlow(level.lava.x+level.lava.w/2,level.lava.y+level.lava.h,level.hero.x,level.hero.y,15);
    setTimeout(function(){
      triggerShake(12,450);
      spawnExplosion(level.hero.x,level.hero.y,true);
      level.hero.hitAnim=1;
      tween(level.hero,'hitAnim',1,0,0.7,'linear');
      SFX.fail();
      // Kill enemies too for drama
      setTimeout(function(){killEnemy(0);},200);
      setTimeout(function(){killEnemy(1);},400);
      setTimeout(function(){onFail('YOU NEED MORE POWER!');},900);
    },700);
  }
}

function killEnemy(idx){
  var e=level.enemies[idx];
  if(!e||!e.alive)return;
  e.alive=false;
  spawnExplosion(e.x,e.y,e.type==='boss');
  triggerShake(e.type==='boss'?10:8,350);
  SFX.enemyDeath();
  addFloat(e.x,e.y-30,e.type==='boss'?'BOSS SLAIN!':'ELIMINATED!','#FF4400',24);
  score+=e.type==='boss'?200:100;
}

function onWin(){
  if(gameState!=='playing')return;
  SFX.levelClear();SFX.heroSave();
  level.hero.saved=true;
  tween(level.hero,'jumpY',0,-50,0.3,'easeOutBack',function(){
    tween(level.hero,'jumpY',-50,0,0.4,'easeOutBounce');
  });
  level.enemies.forEach(function(e,i){
    if(e.alive)setTimeout(function(){killEnemy(i);},i*220);
  });
  spawnCoinBurst(level.hero.x,level.hero.y-60);
  spawnStarShower(W/2,320,420,300);
  SFX.coinCollect();
  var coinAmt=[50,100,200][currentLevel]||50;
  coinsCollected+=coinAmt;
  stars=[true,true,true];
  starScales=[0,0,0];
  for(var i=0;i<3;i++){
    (function(ii){
      setTimeout(function(){
        tween(starScales,ii+'',0,1,0.45,'easeOutElastic');
      },180+ii*160);
    })(i);
  }
  var wt=['GREAT!','AWESOME!','AMAZING!'][currentLevel]||'GREAT!';
  addFloat(W/2,420,wt,'#FFD700',44);
  setTimeout(function(){
    gameState='result';resultType='win';
    resultText=wt;resultSubText='Level '+(currentLevel+1)+' Complete!';
    stateTimer=0;levelFailed=false;
  },2000);
}

function onFail(msg){
  if(levelFailed)return;
  levelFailed=true;
  failCount++;
  gameState='result';resultType='fail';
  resultText=msg||'FAILED!';
  resultSubText='Can you do better?';
  stateTimer=0;
  setTimeout(function(){showCTA();},1800);
}

function showCTA(){
  gameState='cta';
  var overlay=document.getElementById('cta-overlay');
  overlay.classList.add('show');
  document.getElementById('cta-title').textContent=resultType==='fail'?(resultText||'CAN YOU DO BETTER?'):'YOU ARE A CHAMPION!';
  document.getElementById('cta-subtitle').textContent=resultType==='fail'
    ?'Get the full game for the real challenge!'
    :'Download now and unlock all levels!';
  document.getElementById('cta-stars').textContent=stars.map(function(s){return s?'★':'☆';}).join('');
  // Pulse animation
  var btn=document.getElementById('cta-btn');
  var pv=1,pd=1;
  (function pulse(){
    if(gameState!=='cta')return;
    pv+=pd*0.009;
    if(pv>1.09)pd=-1;if(pv<0.94)pd=1;
    btn.style.transform='scale('+pv+')';
    requestAnimationFrame(pulse);
  })();
}

// ==================== LEVEL MANAGEMENT ====================
var lavaDripInt=null;
function startLevel(idx){
  currentLevel=idx;
  level=JSON.parse(JSON.stringify(LEVEL_DEFS[idx]));
  stars=[false,false,false];starScales=[0,0,0];
  floatTexts=[];levelFailed=false;draggedPin=null;
  for(var i=0;i<POOL;i++)pPool[i].active=false;
  for(var j=0;j<LPOOL;j++)lPool[j].active=false;
  gameState='intro';stateTimer=0;
  handAlpha=idx===0?1:0;
  if(lavaDripInt)clearInterval(lavaDripInt);
  setTimeout(function(){
    gameState='playing';stateTimer=0;
    // Ambient lava drip
    lavaDripInt=setInterval(function(){
      if(gameState!=='playing'||!level)return;
      var lv=level.lava;
      spawnLavaDrip(lv.x+lv.w/2+(Math.random()-0.5)*lv.w*0.6,lv.y+lv.h-4,2);
    },100);
  },950);
}

// ==================== RENDER ====================
function drawBg(){
  var img=ASSETS.map_bg.img;
  if(img&&img.complete&&img.naturalWidth>0){
    var iw=img.naturalWidth,ih=img.naturalHeight;
    var sc=Math.max(W/iw,H/ih);
    var sw=W/sc,sh=H/sc,sx=(iw-sw)/2,sy=(ih-sh)/2;
    ctx.drawImage(img,sx,sy,sw,sh,0,0,W,H);
    ctx.fillStyle='rgba(0,0,20,0.38)';ctx.fillRect(0,0,W,H);
  }else{
    var g=ctx.createLinearGradient(0,0,0,H);
    g.addColorStop(0,'#1a2c5e');g.addColorStop(0.5,'#0d1a3d');g.addColorStop(1,'#0a1228');
    ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
  }
}

function drawWalls(){
  if(!level)return;
  level.walls.forEach(function(wall){
    ctx.save();
    // Stone fill
    ctx.fillStyle='#3d4a6b';
    ctx.fillRect(wall.x,wall.y,wall.w,wall.h);
    // Texture lines
    ctx.strokeStyle='rgba(100,130,180,0.25)';ctx.lineWidth=1;
    for(var xx=wall.x;xx<wall.x+wall.w;xx+=18){
      ctx.beginPath();ctx.moveTo(xx,wall.y);ctx.lineTo(xx,wall.y+wall.h);ctx.stroke();
    }
    // Top highlight
    ctx.fillStyle='rgba(180,200,255,0.12)';
    ctx.fillRect(wall.x,wall.y,wall.w,4);
    // Border
    ctx.strokeStyle='#5a6a8a';ctx.lineWidth=2;
    ctx.strokeRect(wall.x,wall.y,wall.w,wall.h);
    // Lava glow if flowing
    if(level.lavaFlowing){
      ctx.strokeStyle='rgba(255,80,0,0.3)';ctx.lineWidth=3;
      ctx.strokeRect(wall.x-1,wall.y-1,wall.w+2,wall.h+2);
    }
    ctx.restore();
  });
}

function drawReservoir(){
  if(!level)return;
  var lv=level.lava,tt=Date.now()/1000;
  ctx.save();
  // Outer glow
  ctx.shadowColor='#FF4400';ctx.shadowBlur=25;
  var g=ctx.createLinearGradient(lv.x,lv.y,lv.x,lv.y+lv.h);
  g.addColorStop(0,'#FF5500');g.addColorStop(0.4,'#FF3300');g.addColorStop(1,'#CC1100');
  ctx.fillStyle=g;ctx.fillRect(lv.x,lv.y,lv.w,lv.h);
  ctx.shadowBlur=0;
  // Animated bubbles
  ctx.fillStyle='rgba(255,200,0,0.45)';
  for(var i=0;i<4;i++){
    var bx=lv.x+lv.w*0.15+i*(lv.w*0.22);
    var by=lv.y+6+Math.sin(tt*2.5+i*1.2)*4;
    ctx.beginPath();ctx.arc(bx,by,lv.w/11,0,Math.PI,true);ctx.fill();
  }
  // Border glow
  ctx.strokeStyle='#FF8800';ctx.lineWidth=3;
  ctx.strokeRect(lv.x,lv.y,lv.w,lv.h);
  // Dripping edge
  if(level.lavaFlowing){
    ctx.fillStyle='rgba(255,80,0,0.6)';
    ctx.fillRect(lv.x,lv.y+lv.h,lv.w,4);
  }
  ctx.restore();
}

function drawPins(){
  if(!level)return;
  level.pins.forEach(function(pin){
    if(pin.removed&&pin.alpha<=0.02)return;
    ctx.save();ctx.globalAlpha=pin.alpha;
    var px=pin.x+(pin.dragX||0),py=pin.y+(pin.dragY||0);
    var pw=pin.w||100,ph=pin.h||20;
    // Shadow
    ctx.fillStyle='rgba(0,0,0,0.45)';
    ctx.beginPath();ctx.roundRect(px-pw/2+4,py-ph/2+4,pw,ph,ph/2);ctx.fill();
    // Body gradient
    var grad=ctx.createLinearGradient(px-pw/2,py-ph/2,px-pw/2,py+ph/2);
    grad.addColorStop(0,'#e0e0e8');
    grad.addColorStop(0.25,'#b0b0c0');
    grad.addColorStop(0.75,'#888898');
    grad.addColorStop(1,'#606068');
    ctx.fillStyle=grad;
    ctx.beginPath();ctx.roundRect(px-pw/2,py-ph/2,pw,ph,ph/2);ctx.fill();
    // Highlight
    ctx.fillStyle='rgba(255,255,255,0.55)';
    ctx.beginPath();ctx.roundRect(px-pw/2+5,py-ph/2+3,pw-10,ph/3,ph/4);ctx.fill();
    // Rivets
    var rv1x=pin.dir==='right'?px-pw/2+10:px+pw/2-10;
    var rv2x=pin.dir==='right'?px-pw/2+20:px+pw/2-20;
    [rv1x,rv2x].forEach(function(rvx){
      ctx.fillStyle='#999';
      ctx.beginPath();ctx.arc(rvx,py,ph/4,0,Math.PI*2);ctx.fill();
      ctx.fillStyle='rgba(255,255,255,0.4)';
      ctx.beginPath();ctx.arc(rvx-1,py-1,ph/6,0,Math.PI*2);ctx.fill();
    });
    // Handle knob
    var hx=(pin.dir==='right'||pin.dir==='down')?px+pw/2:px-pw/2;
    if(pin.vertical)hx=px;
    var hy=pin.vertical?py+ph/2:py;
    if(!pin.vertical)hy=py;
    var hg=ctx.createRadialGradient(hx-2,hy-2,0,hx,hy,ph/2+5);
    hg.addColorStop(0,'#FFE066');hg.addColorStop(0.5,'#FFB800');hg.addColorStop(1,'#CC8800');
    ctx.fillStyle=hg;
    ctx.beginPath();ctx.arc(hx,hy,ph/2+4,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='#FF8C00';ctx.lineWidth=2;ctx.stroke();
    // Direction arrow hint
    if(!pin.removed&&pin.alpha>0.5){
      var tt=Date.now()/1000;
      var bounce=Math.sin(tt*3)*3;
      ctx.fillStyle='rgba(255,230,0,0.9)';
      ctx.font='bold 18px Arial';ctx.textAlign='center';ctx.textBaseline='middle';
      var arrowCh=pin.dir==='right'?'→':pin.dir==='left'?'←':pin.dir==='down'?'↓':'↑';
      var ax=pin.dir==='right'?px+pw/2+18+bounce:pin.dir==='left'?px-pw/2-18-bounce:px;
      var ay=pin.dir==='down'?py+ph/2+18+bounce:py;
      ctx.fillText(arrowCh,ax,ay);
    }
    ctx.restore();
  });
}

function drawShadow(x,y){
  var sh=ASSETS.shadow.img;
  ctx.save();ctx.globalAlpha=0.35;
  if(sh&&sh.complete&&sh.naturalWidth>0){
    ctx.drawImage(sh,x-32,y-6,64,14);
  }else{
    ctx.fillStyle='#000';ctx.beginPath();ctx.ellipse(x,y+5,26,8,0,0,Math.PI*2);ctx.fill();
  }
  ctx.restore();
}

function drawSprite(img,x,y,size,alpha){
  if(!img||!img.complete||!img.naturalWidth)return;
  ctx.save();if(alpha!==undefined)ctx.globalAlpha=alpha;
  ctx.drawImage(img,x-size/2,y-size/2,size,size);
  ctx.restore();
}

function drawHero(){
  if(!level)return;
  var h=level.hero,img=ASSETS.hero.img;
  var y=h.y+(h.jumpY||0);
  drawShadow(h.x,h.y+30);
  if(h.hitAnim>0.05){
    ctx.save();
    ctx.globalAlpha=h.hitAnim*0.7;
    var rg=ctx.createRadialGradient(h.x,y,0,h.x,y,42);
    rg.addColorStop(0,'rgba(255,0,0,0.8)');rg.addColorStop(1,'rgba(255,0,0,0)');
    ctx.fillStyle=rg;ctx.beginPath();ctx.arc(h.x,y,42,0,Math.PI*2);ctx.fill();
    ctx.restore();
  }
  if(h.saved){
    ctx.save();ctx.shadowColor='#FFD700';ctx.shadowBlur=35;
    drawSprite(img,h.x,y,85);ctx.restore();
  }else{
    drawSprite(img,h.x,y,74);
  }
  if(!h.saved&&h.hitAnim<0.05){
    var tt=Date.now()/1000;
    ctx.save();ctx.fillStyle='#FF0000';
    ctx.font='bold 22px Arial';ctx.textAlign='center';
    ctx.fillText('!',h.x,y-46+Math.sin(tt*5)*3);ctx.restore();
  }
}

function drawEnemies(){
  if(!level)return;
  level.enemies.forEach(function(e){
    if(!e.alive)return;
    var img=e.type==='boss'?ASSETS.boss.img:ASSETS.enemy.img;
    var sz=e.type==='boss'?92:68;
    var tt=Date.now()/1000;
    var wb=Math.sin(tt*2.8+e.x*0.05)*3;
    drawShadow(e.x,e.y+sz/2-8);
    if(e.type==='boss'){
      ctx.save();ctx.shadowColor='#FF2200';ctx.shadowBlur=20;
      drawSprite(img,e.x,e.y+wb,sz);ctx.restore();
      // Boss HP bar
      ctx.save();
      ctx.fillStyle='rgba(0,0,0,0.6)';ctx.beginPath();ctx.roundRect(e.x-38,e.y-58,76,10,3);ctx.fill();
      ctx.fillStyle='#FF2200';ctx.beginPath();ctx.roundRect(e.x-38,e.y-58,76,10,3);ctx.fill();
      ctx.strokeStyle='rgba(255,100,0,0.8)';ctx.lineWidth=1.5;ctx.strokeRect(e.x-38,e.y-58,76,10);
      ctx.fillStyle='#FF5500';ctx.font='bold 11px Arial';ctx.textAlign='center';
      ctx.fillText('BOSS',e.x,e.y-68);ctx.restore();
    }else{
      drawSprite(img,e.x,e.y+wb,sz);
    }
  });
}

function drawTutHand(){
  if(currentLevel!==0||handAlpha<=0||gameState!=='playing')return;
  var pin0=level&&level.pins?level.pins[0]:null;
  if(!pin0||pin0.removed)return;
  var tt=Date.now()/1000;
  var cyc=(tt*0.75)%1;
  var hx=pin0.x+10+(pin0.w||100)*0.7*cyc;
  var hy=pin0.y;
  var sc=1+Math.sin(tt*4)*0.08;
  ctx.save();
  ctx.globalAlpha=handAlpha*(0.75+Math.sin(tt*3)*0.25);
  ctx.translate(hx,hy);ctx.scale(sc,sc);
  // Outer ring
  ctx.strokeStyle='rgba(255,230,0,0.5)';ctx.lineWidth=3;
  ctx.beginPath();ctx.arc(0,0,24,0,Math.PI*2);ctx.stroke();
  // Hand circle
  ctx.fillStyle='rgba(255,255,255,0.92)';
  ctx.beginPath();ctx.arc(0,4,16,0,Math.PI*2);ctx.fill();
  ctx.strokeStyle='rgba(0,0,0,0.4)';ctx.lineWidth=1.5;ctx.stroke();
  // Finger
  ctx.fillStyle='rgba(255,255,255,0.92)';
  ctx.fillRect(-5,-18,10,20);
  ctx.restore();
  // PULL label
  ctx.save();
  ctx.globalAlpha=handAlpha*(0.6+Math.sin(tt*2)*0.4);
  ctx.fillStyle='#FFD700';ctx.font='bold 20px Arial';ctx.textAlign='center';
  ctx.shadowColor='rgba(0,0,0,0.9)';ctx.shadowBlur=6;
  ctx.fillText('PULL!',pin0.x+(pin0.w||100)*0.35,pin0.y-36);
  ctx.restore();
}

function drawUI(){
  if(gameState!=='playing'&&gameState!=='result')return;
  // Score badge
  ctx.save();
  ctx.fillStyle='rgba(0,0,0,0.55)';ctx.beginPath();ctx.roundRect(12,12,155,42,8);ctx.fill();
  ctx.fillStyle='#FFD700';ctx.font='bold 17px Arial';ctx.textAlign='left';
  ctx.fillText('SCORE: '+score,24,36);ctx.restore();
  // Level badge
  ctx.save();
  ctx.fillStyle='rgba(0,0,0,0.55)';ctx.beginPath();ctx.roundRect(W/2-58,12,116,42,8);ctx.fill();
  ctx.fillStyle='#fff';ctx.font='bold 20px Arial';ctx.textAlign='center';
  ctx.fillText('LEVEL '+(currentLevel+1),W/2,36);ctx.restore();
  // Coins
  ctx.save();
  ctx.fillStyle='rgba(0,0,0,0.55)';ctx.beginPath();ctx.roundRect(W-162,12,150,42,8);ctx.fill();
  var ci=ASSETS.coin.img;
  if(ci&&ci.complete)ctx.drawImage(ci,W-152,16,30,30);
  ctx.fillStyle='#FFD700';ctx.font='bold 17px Arial';ctx.textAlign='right';
  ctx.fillText(coinsCollected,W-18,36);ctx.restore();
  // Timer bar
  var tp=Math.max(0,1-globalTimer/MAX_TIME);
  ctx.save();
  ctx.fillStyle='rgba(0,0,0,0.5)';ctx.fillRect(0,H-10,W,10);
  ctx.fillStyle=tp>0.4?'#00CC66':tp>0.2?'#FFAA00':'#FF3300';
  ctx.fillRect(0,H-10,W*tp,10);ctx.restore();
}

function drawStarDisplay(){
  if(!stars[0]&&!stars[1]&&!stars[2])return;
  var si=ASSETS.star.img;
  var pos=[W/2-68,W/2,W/2+68];
  for(var i=0;i<3;i++){
    if(!stars[i]||starScales[i]<0.01)continue;
    ctx.save();
    ctx.translate(pos[i],H-115);ctx.scale(starScales[i],starScales[i]);
    if(si&&si.complete&&si.naturalWidth>0){
      ctx.drawImage(si,-26,-26,52,52);
    }else{
      ctx.fillStyle='#FFD700';ctx.font='42px Arial';
      ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('★',0,0);
    }
    ctx.restore();
  }
}

function drawIntroOverlay(){
  var p=Math.min(stateTimer/0.95,1);
  ctx.fillStyle='rgba(0,0,0,'+(p*0.72)+')';ctx.fillRect(0,0,W,H);
  var sc=0.4+p*0.6;
  ctx.save();ctx.globalAlpha=p;ctx.translate(W/2,H/2);ctx.scale(sc,sc);
  ctx.fillStyle='#FFD700';ctx.font='bold 62px Arial';
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.shadowColor='#FF8800';ctx.shadowBlur=22;
  ctx.fillText('LEVEL '+(currentLevel+1),0,-22);ctx.shadowBlur=0;
  ctx.fillStyle='#fff';ctx.font='bold 30px Arial';
  ctx.fillText(LEVEL_DEFS[currentLevel].name,0,34);
  ctx.restore();
}

function drawResultOverlay(){
  var p=Math.min(stateTimer/0.55,1);
  ctx.fillStyle='rgba(0,0,0,'+(p*0.65)+')';ctx.fillRect(0,0,W,H);
  ctx.save();ctx.translate(W/2,H/2-50);ctx.scale(0.4+p*0.6,0.4+p*0.6);ctx.globalAlpha=p;
  var col=resultType==='win'?'#FFD700':'#FF4444';
  ctx.fillStyle=col;ctx.font='bold 58px Arial';
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.shadowColor=col;ctx.shadowBlur=22;ctx.fillText(resultText,0,0);ctx.shadowBlur=0;
  ctx.fillStyle='#fff';ctx.font='bold 26px Arial';ctx.fillText(resultSubText,0,58);
  if(p>0.85){
    ctx.fillStyle='rgba(255,255,255,0.7)';ctx.font='20px Arial';
    ctx.fillText('Tap to continue',0,100);
  }
  ctx.restore();
}

// ==================== MAIN LOOP ====================
var lastT=0;
function loop(ts){
  var dt=Math.min((ts-lastT)/1000,0.05);lastT=ts;
  if(gameState!=='cta'){
    updateShake(dt);updateTweens(dt);updateParticles(dt);updateLava(dt);updateFloats(dt);
    if(gameState==='playing'){
      globalTimer+=dt;stateTimer+=dt;
      if(globalTimer>=MAX_TIME&&!levelFailed)showCTA();
    }
    if(gameState==='intro')stateTimer+=dt;
    if(gameState==='result')stateTimer+=dt;
  }
  ctx.save();ctx.translate(shakeX,shakeY);
  drawBg();
  if(gameState==='title'){
    drawTitleScreen();
  }else if(gameState==='intro'){
    drawWalls();drawReservoir();drawPins();drawEnemies();drawHero();drawIntroOverlay();
  }else if(gameState==='playing'||gameState==='result'){
    drawWalls();drawReservoir();drawLava();drawPins();drawEnemies();drawHero();
    drawParticles();drawStarDisplay();drawUI();drawTutHand();drawFloats();
    if(gameState==='result')drawResultOverlay();
  }
  ctx.restore();
  requestAnimationFrame(loop);
}

function drawTitleScreen(){
  ctx.fillStyle='rgba(0,0,18,0.88)';ctx.fillRect(0,0,W,H);
  var tt=Date.now()/1000,pulse=1+Math.sin(tt*1.8)*0.025;
  ctx.save();ctx.translate(W/2,H/2-70);ctx.scale(pulse,pulse);
  ctx.fillStyle='rgba(0,0,0,0.65)';ctx.beginPath();ctx.roundRect(-210,-90,420,180,24);ctx.fill();
  ctx.fillStyle='#FFD700';ctx.font='bold 58px Arial';
  ctx.textAlign='center';ctx.textBaseline='middle';
  ctx.shadowColor='rgba(255,200,0,0.85)';ctx.shadowBlur=32;
  ctx.fillText('PIN PULL',0,-26);ctx.shadowBlur=0;
  ctx.fillStyle='#FF6B00';ctx.font='bold 44px Arial';ctx.fillText('PRO',0,34);
  ctx.restore();
  // Tagline
  ctx.save();ctx.fillStyle='rgba(180,200,255,0.8)';ctx.font='18px Arial';
  ctx.textAlign='center';ctx.fillText('Save the hero - pull the pins!',W/2,H/2+75);ctx.restore();
  // Tap to start
  if(Math.sin(tt*2.8)>0){
    ctx.save();ctx.fillStyle='#fff';ctx.font='bold 28px Arial';ctx.textAlign='center';
    ctx.fillText('TAP TO START',W/2,H/2+120);ctx.restore();
  }
  // Pin demo animation
  var pa=(Math.sin(tt*1.8)+1)/2;
  ctx.save();ctx.translate(W/2,H/2+200);
  ctx.fillStyle='#aaa';ctx.beginPath();ctx.roundRect(-55+pa*40,-10,110,20,10);ctx.fill();
  ctx.fillStyle='#FFD700';ctx.beginPath();ctx.arc(55+pa*40,0,12,0,Math.PI*2);ctx.fill();
  ctx.fillStyle='rgba(255,220,0,0.9)';ctx.font='bold 22px Arial';ctx.textAlign='center';
  ctx.fillText('→',95+pa*30,4);ctx.restore();
  // Decorative towers
  var ti=ASSETS.tower.img;
  if(ti&&ti.complete){
    ctx.save();ctx.globalAlpha=0.5;
    ctx.drawImage(ti,20,H-200,80,160);ctx.drawImage(ti,W-100,H-200,80,160);ctx.restore();
  }
}

// ==================== INIT ====================
loadAssets(function(){
  document.getElementById('loading').style.display='none';
  gameState='title';lastT=performance.now();
  requestAnimationFrame(loop);
});

})();
</script>
</body>
</html>`;
}
