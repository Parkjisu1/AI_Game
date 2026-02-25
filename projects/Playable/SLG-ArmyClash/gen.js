const fs = require('fs');
const dir = 'E:/AI/projects/Playable/SLG-ArmyClash/assets/';
const outPath = 'E:/AI/projects/Playable/SLG-ArmyClash/output/playable.html';

function b64(name) {
  return fs.readFileSync(dir + name).toString('base64');
}

const A = {
  map:    b64('Map_2048.png'),
  player: b64('NPC_Summon_001_D.png'),
  tower:  b64('TowerA.png'),
  enemy:  b64('MOB_Cactus01_red_D.png'),
  boss:   b64('MOB_Boss_Cactus_Crown_D.png'),
  wall:   b64('WallA.png'),
  arrow:  b64('Arrow.png'),
  coin:   b64('Coin.png'),
  shadow: b64('Shadow.png'),
  star:   b64('Effect_Star_1.png'),
};

console.log('Assets loaded. Generating HTML...');

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Army Clash: Kingdom War - Playable Ad</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
body{background:#000;display:flex;justify-content:center;align-items:center;width:100vw;height:100vh;overflow:hidden;position:fixed;top:0;left:0;}
#wrapper{position:absolute;width:540px;height:960px;}
canvas{display:block;position:absolute;top:0;left:0;width:540px;height:960px;touch-action:none;}
#cta-overlay{display:none;position:absolute;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.88);flex-direction:column;justify-content:center;align-items:center;z-index:10;}
#cta-overlay.visible{display:flex;}
.cta-logo{font-family:"Arial Black",Arial,sans-serif;font-size:38px;font-weight:900;color:#ffd700;text-shadow:0 0 20px #ff8800,2px 2px 0 #8b0000;letter-spacing:2px;text-align:center;margin-bottom:8px;padding:0 20px;}
.cta-sub{font-family:Arial,sans-serif;font-size:19px;color:#fff;text-align:center;margin-bottom:36px;text-shadow:1px 1px 3px #000;padding:0 20px;}
.cta-btn{font-family:"Arial Black",Arial,sans-serif;font-size:26px;font-weight:900;color:#fff;background:linear-gradient(180deg,#ff4400 0%,#cc0000 100%);border:3px solid #ffd700;border-radius:12px;padding:16px 48px;cursor:pointer;letter-spacing:1px;box-shadow:0 6px 20px rgba(0,0,0,0.6);animation:ctaPulse 1.2s ease-in-out infinite;text-shadow:1px 1px 3px #000;}
@keyframes ctaPulse{0%,100%{transform:scale(1);box-shadow:0 6px 20px rgba(0,0,0,0.6),0 0 0 0 rgba(255,215,0,0.5);}50%{transform:scale(1.07);box-shadow:0 10px 28px rgba(0,0,0,0.7),0 0 0 14px rgba(255,215,0,0);}}
.cta-stars{font-size:48px;margin-bottom:14px;}
.cta-result{font-family:Arial,sans-serif;font-size:24px;margin-bottom:18px;font-weight:bold;}
</style>
</head>
<body>
<div id="wrapper">
<canvas id="game" width="540" height="960"></canvas>
<div id="cta-overlay">
  <div class="cta-stars">&#11088;&#11088;&#11088;</div>
  <div class="cta-result" id="cta-result-text" style="color:#ffd700">VICTORY!</div>
  <div class="cta-logo">BUILD YOUR ARMY!</div>
  <div class="cta-sub">Recruit heroes &amp; conquer kingdoms!</div>
  <button class="cta-btn" onclick="(function(){try{if(typeof mraid!=='undefined'&&mraid.open){mraid.open('https://play.google.com/store');}else{window.open('https://play.google.com/store','_blank');}}catch(e){window.open('https://play.google.com/store','_blank');}})()">INSTALL NOW</button>
</div>
</div>
<script>
(function(){
'use strict';
var ASSETS={
  map:    'data:image/png;base64,${A.map}',
  player: 'data:image/png;base64,${A.player}',
  tower:  'data:image/png;base64,${A.tower}',
  enemy:  'data:image/png;base64,${A.enemy}',
  boss:   'data:image/png;base64,${A.boss}',
  wall:   'data:image/png;base64,${A.wall}',
  arrow:  'data:image/png;base64,${A.arrow}',
  coin:   'data:image/png;base64,${A.coin}',
  shadow: 'data:image/png;base64,${A.shadow}',
  star:   'data:image/png;base64,${A.star}'
};
var W=540,H=960,LANE_YS=[250,450,650],PBX=45,EBX=495,BF_TOP=60,BF_BOT=800,CP_Y=812,CW=92,CH=112,MAX_T=45;
var UDEFS={
  swordsman:{hp:60,atk:12,spd:50,range:32,ranged:false,ikey:'player',col:'#3a6ebf',sz:44},
  archer:   {hp:35,atk:18,spd:35,range:155,ranged:true,ikey:'tower',col:'#2a8f2f',sz:40},
  soldier:  {hp:40,atk:8,spd:45,range:32,ranged:false,ikey:'enemy',col:'#cc4444',sz:40},
  elite:    {hp:80,atk:15,spd:35,range:32,ranged:false,ikey:'enemy',col:'#8b0000',sz:50},
  boss:     {hp:300,atk:25,spd:20,range:42,ranged:false,ikey:'boss',col:'#660066',sz:72}
};
var LEVELS=[
  {gs:30,bg:0,ebhp:100,alock:true,sp:[{t:'soldier',n:3,hp:40,a:8,s:45,iv:2.0,d:0.5}]},
  {gs:0,bg:20,ebhp:150,alock:false,sp:[{t:'soldier',n:4,hp:50,a:10,s:45,iv:1.5,d:0.5},{t:'elite',n:1,hp:80,a:15,s:35,iv:99,d:4.5}]},
  {gs:0,bg:30,ebhp:200,alock:false,sp:[{t:'soldier',n:3,hp:50,a:10,s:50,iv:1.0,d:0.3},{t:'elite',n:2,hp:80,a:15,s:40,iv:2.0,d:3.0},{t:'boss',n:1,hp:300,a:25,s:20,iv:99,d:7.0}]}
];
var CARDS=[{type:'swordsman',x:140,y:832,cost:10,locked:false},{type:'archer',x:310,y:832,cost:20,locked:true}];
var imgs={},loaded=0,total=Object.keys(ASSETS).length;
var state='loading',stT=0,lvl=0,gold=30;
var pbhp=200,pbmax=200,ebhp=100,ebmax=100;
var pu=[],eu=[],projs=[],spawns=[],drag=null,uid=0;
var gTimer=0,wTimer=0,victory=false,tutDone=false,nuTimer=0,lt=0;
var parts=[];for(var i=0;i<150;i++)parts.push({a:false,x:0,y:0,vx:0,vy:0,life:0,ml:1,col:'#fff',sz:3});
var cv=document.getElementById('game'),cx=cv.getContext('2d');
function scale(){var s=Math.min(window.innerWidth/W,window.innerHeight/H),wr=document.getElementById('wrapper');wr.style.transform='scale('+s+')';wr.style.transformOrigin='top left';wr.style.left=Math.round((window.innerWidth-W*s)/2)+'px';wr.style.top=Math.round((window.innerHeight-H*s)/2)+'px';}
scale();window.addEventListener('resize',scale,{passive:true});
var ac=null;
function gAC(){if(!ac){try{ac=new(window.AudioContext||window.webkitAudioContext)();}catch(e){}}return ac;}
function tn(f,d,t,v){var a=gAC();if(!a)return;try{var o=a.createOscillator(),g=a.createGain();o.connect(g);g.connect(a.destination);o.type=t||'square';o.frequency.value=f;g.gain.setValueAtTime(v||0.15,a.currentTime);g.gain.exponentialRampToValueAtTime(0.001,a.currentTime+d);o.start();o.stop(a.currentTime+d+0.06);}catch(e){}}
function ns(d,v){var a=gAC();if(!a)return;try{var b=a.createBuffer(1,Math.ceil(a.sampleRate*d),a.sampleRate),dd=b.getChannelData(0);for(var i=0;i<dd.length;i++)dd[i]=(Math.random()*2-1);var s=a.createBufferSource(),g=a.createGain();s.buffer=b;s.connect(g);g.connect(a.destination);g.gain.setValueAtTime(v||0.1,a.currentTime);g.gain.exponentialRampToValueAtTime(0.001,a.currentTime+d);s.start();s.stop(a.currentTime+d+0.06);}catch(e){}}
function sDep(){tn(220,0.15,'square',0.18);}function sHit(){ns(0.07,0.08);}function sDeath(){ns(0.12,0.12);tn(140,0.1,'sawtooth',0.1);}function sCoin(){tn(660,0.07,'sine',0.12);setTimeout(function(){tn(880,0.08,'sine',0.1);},80);}function sArr(){tn(880,0.09,'sine',0.08);}function sBase(){tn(60,0.18,'sawtooth',0.18);}function sWC(){[523,659,784].forEach(function(f,i){setTimeout(function(){tn(f,0.2,'sine',0.15);},i*110);});}function sVic(){[523,659,784,1047].forEach(function(f,i){setTimeout(function(){tn(f,0.25,'sine',0.18);},i*130);});}
function loadAssets(){Object.keys(ASSETS).forEach(function(k){var img=new Image();img.onload=function(){imgs[k]=img;loaded++;if(loaded>=total)onLoaded();};img.onerror=function(){imgs[k]=null;loaded++;if(loaded>=total)onLoaded();};img.src=ASSETS[k];});}
function onLoaded(){state='title';stT=0;}
function sp(x,y,vx,vy,life,col,sz){for(var i=0;i<parts.length;i++){var p=parts[i];if(!p.a){p.a=true;p.x=x;p.y=y;p.vx=vx;p.vy=vy;p.life=life;p.ml=life;p.col=col;p.sz=sz;return;}}}
function sparks(x,y,col,n,spd){n=n||5;spd=spd||80;for(var i=0;i<n;i++){var a=Math.random()*Math.PI*2;sp(x,y,Math.cos(a)*spd*(0.5+Math.random()),Math.sin(a)*spd*(0.5+Math.random()),0.2+Math.random()*0.2,col,2+Math.random()*4);}}
function burst(x,y,col,n){sparks(x,y,col,n||10,130);}
function coinFX(x,y){sp(x,y,0,-65,0.6,'#ffd700',11);}
function baseBlast(x,y){var c=['#ff4400','#ff8800','#ffcc00'];for(var i=0;i<22;i++){var a=Math.random()*Math.PI*2,s=90+Math.random()*160;sp(x,y,Math.cos(a)*s,Math.sin(a)*s,0.6+Math.random()*0.4,c[i%3],5+Math.random()*10);}}
function updParts(dt){for(var i=0;i<parts.length;i++){var p=parts[i];if(!p.a)continue;p.life-=dt;if(p.life<=0){p.a=false;continue;}p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=110*dt;}}
function mkU(type,x,y,ohp,oa,os){var d=UDEFS[type];return{id:uid++,type:type,x:x,y:y,hp:ohp||d.hp,maxHp:ohp||d.hp,atk:oa||d.atk,spd:os||d.spd,range:d.range,ranged:d.ranged,ikey:d.ikey,col:d.col,sz:d.sz,acd:0,ar:1.0,af:0,isP:true};}
function laneOf(y){return LANE_YS.reduce(function(b,ly,i){return Math.abs(ly-y)<Math.abs(LANE_YS[b]-y)?i:b;},0);}
function initWave(i){var lv=LEVELS[i];if(i===0){gold=lv.gs;pbhp=200;pbmax=200;}else{gold+=lv.bg;pbhp=Math.min(pbmax,pbhp+20);}ebhp=lv.ebhp;ebmax=lv.ebhp;CARDS[1].locked=lv.alock;pu=[];eu=[];projs=[];gTimer=0;wTimer=0;tutDone=false;nuTimer=(i===1)?3.5:0;spawns=lv.sp.map(function(s){return{type:s.t,rem:s.n,timer:s.d,iv:s.iv,hp:s.hp,atk:s.a,spd:s.s};});}
function toCV(cx2,cy2){var r=cv.getBoundingClientRect();return{x:(cx2-r.left)*(W/r.width),y:(cy2-r.top)*(H/r.height)};}
function onDown(cx2,cy2){var p=toCV(cx2,cy2);if(state==='title'){state='wave_intro';stT=0;initWave(0);return;}if(state!=='playing')return;for(var i=0;i<CARDS.length;i++){var c=CARDS[i];if(c.locked)continue;if(p.x>=c.x&&p.x<=c.x+CW&&p.y>=c.y&&p.y<=c.y+CH&&gold>=c.cost){drag={type:c.type,gx:p.x,gy:p.y};return;}}}
function onMove(cx2,cy2){if(!drag)return;var p=toCV(cx2,cy2);drag.gx=p.x;drag.gy=p.y;}
function onUp(cx2,cy2){if(!drag)return;var p=toCV(cx2,cy2);var cc=CARDS.find(function(c){return c.type===drag.type;});var inBF=p.y>=BF_TOP&&p.y<=BF_BOT&&p.x>=80&&p.x<=EBX-50;if(inBF&&gold>=cc.cost){var ly=LANE_YS[laneOf(p.y)];var u=mkU(drag.type,85+Math.random()*30,ly,null,null,null);u.isP=true;pu.push(u);gold-=cc.cost;sDep();tutDone=true;}drag=null;}
cv.addEventListener('touchstart',function(e){e.preventDefault();var t=e.changedTouches[0];onDown(t.clientX,t.clientY);},{passive:false});
cv.addEventListener('touchmove',function(e){e.preventDefault();var t=e.changedTouches[0];onMove(t.clientX,t.clientY);},{passive:false});
cv.addEventListener('touchend',function(e){e.preventDefault();var t=e.changedTouches[0];onUp(t.clientX,t.clientY);},{passive:false});
cv.addEventListener('mousedown',function(e){onDown(e.clientX,e.clientY);});
cv.addEventListener('mousemove',function(e){onMove(e.clientX,e.clientY);});
cv.addEventListener('mouseup',function(e){onUp(e.clientX,e.clientY);});
function spawnEnemies(dt){for(var i=0;i<spawns.length;i++){var q=spawns[i];if(q.rem<=0)continue;q.timer-=dt;if(q.timer<=0){q.rem--;q.timer=q.iv;var ly=LANE_YS[Math.floor(Math.random()*3)];var u=mkU(q.type,EBX-25-Math.random()*15,ly,q.hp,q.atk,q.spd);u.isP=false;eu.push(u);}}}
function updBattle(dt){
  for(var i=0;i<pu.length;i++){var u=pu[i];if(u.acd>0)u.acd-=dt;if(u.af>0)u.af-=dt;var ml=laneOf(u.y),best=null,bd=9999;for(var j=0;j<eu.length;j++){var e=eu[j];if(laneOf(e.y)===ml){var d=e.x-u.x;if(d>-25&&d<bd){bd=d;best=e;}}}if(best&&bd<=u.range+8){if(u.acd<=0){u.acd=u.ar;u.af=0.15;if(u.ranged){projs.push({x:u.x,y:u.y,tx:best.x,ty:best.y,tid:best.id,atk:u.atk,spd:280,alive:true});sArr();}else{best.hp-=u.atk;sHit();sparks(best.x,best.y,'#ffff44',5,90);}}}else if(best)u.x+=u.spd*dt;else{if(u.x<EBX-52)u.x+=u.spd*dt;else if(u.acd<=0){u.acd=u.ar;u.af=0.15;ebhp=Math.max(0,ebhp-u.atk);sBase();sparks(EBX,u.y,'#ff4444',4,60);}}u.x=Math.min(u.x,EBX-15);}
  for(var i=0;i<eu.length;i++){var u=eu[i];if(u.acd>0)u.acd-=dt;if(u.af>0)u.af-=dt;var ml=laneOf(u.y),best=null,bd=9999;for(var j=0;j<pu.length;j++){var p2=pu[j];if(laneOf(p2.y)===ml){var d=u.x-p2.x;if(d>-25&&d<bd){bd=d;best=p2;}}}if(best&&bd<=u.range+8){if(u.acd<=0){u.acd=u.ar;u.af=0.15;best.hp-=u.atk;sHit();sparks(best.x,best.y,'#aaaaff',5,90);}}else if(best)u.x-=u.spd*dt;else{if(u.x>PBX+52)u.x-=u.spd*dt;else if(u.acd<=0){u.acd=u.ar;u.af=0.15;pbhp=Math.max(0,pbhp-u.atk);sBase();sparks(PBX,u.y,'#4488ff',4,60);}}u.x=Math.max(u.x,PBX+15);}
  for(var i=projs.length-1;i>=0;i--){var p=projs[i];if(!p.alive)continue;var tgt=null;for(var j=0;j<eu.length;j++)if(eu[j].id===p.tid){tgt=eu[j];p.tx=tgt.x;p.ty=tgt.y;break;}var dx=p.tx-p.x,dy=p.ty-p.y,dist=Math.sqrt(dx*dx+dy*dy);if(dist<10){if(tgt){tgt.hp-=p.atk;sHit();sparks(tgt.x,tgt.y,'#ffff44',4,70);}p.alive=false;}else{var s=p.spd*dt/dist;p.x+=dx*s;p.y+=dy*s;}}
  projs=projs.filter(function(p){return p.alive;});
  for(var i=eu.length-1;i>=0;i--)if(eu[i].hp<=0){burst(eu[i].x,eu[i].y,'#ff6600',10);coinFX(eu[i].x,eu[i].y-30);gold+=10;sDeath();sCoin();eu.splice(i,1);}
  for(var i=pu.length-1;i>=0;i--)if(pu[i].hp<=0){burst(pu[i].x,pu[i].y,'#4488ff',8);sDeath();pu.splice(i,1);}
}
function showCTA(win){state='cta';var el=document.getElementById('cta-result-text');if(win){el.textContent='VICTORY!';el.style.color='#ffd700';sVic();}else{el.textContent='DEFEATED!';el.style.color='#ff4444';sDeath();}document.getElementById('cta-overlay').classList.add('visible');}
function hpBar(x,y,w,hp,mhp,col){var p=Math.max(0,hp/mhp);cx.fillStyle='rgba(0,0,0,0.55)';cx.fillRect(x,y,w,7);cx.fillStyle=col;cx.fillRect(x,y,w*p,7);cx.strokeStyle='rgba(0,0,0,0.4)';cx.lineWidth=1;cx.strokeRect(x,y,w,7);}
function rr(x,y,w,h,r,fill,stroke,sw){cx.beginPath();cx.moveTo(x+r,y);cx.lineTo(x+w-r,y);cx.quadraticCurveTo(x+w,y,x+w,y+r);cx.lineTo(x+w,y+h-r);cx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);cx.lineTo(x+r,y+h);cx.quadraticCurveTo(x,y+h,x,y+h-r);cx.lineTo(x,y+r);cx.quadraticCurveTo(x,y,x+r,y);cx.closePath();if(fill){cx.fillStyle=fill;cx.fill();}if(stroke){cx.strokeStyle=stroke;cx.lineWidth=sw||2;cx.stroke();}}
function drawBG(){if(imgs.map){cx.drawImage(imgs.map,0,0,W,H);return;}var g=cx.createLinearGradient(0,0,0,H);g.addColorStop(0,'#87CEEB');g.addColorStop(0.52,'#7bbde8');g.addColorStop(0.52,'#4a7c3f');g.addColorStop(1,'#2d5a1f');cx.fillStyle=g;cx.fillRect(0,0,W,H);}
function drawUnit(u,isP){var sz=u.sz,img=imgs[u.ikey];if(imgs.shadow){cx.save();cx.globalAlpha=0.36;cx.drawImage(imgs.shadow,u.x-sz*0.5,u.y+sz*0.28,sz,sz*0.28);cx.restore();}var alp=u.af>0?(0.55+Math.random()*0.5):1;cx.save();cx.globalAlpha=alp;if(img){if(!isP){cx.translate(u.x,u.y);cx.scale(-1,1);cx.drawImage(img,-sz/2,-sz/2,sz,sz);cx.setTransform(1,0,0,1,0,0);}else cx.drawImage(img,u.x-sz/2,u.y-sz/2,sz,sz);}else{cx.fillStyle=u.col;cx.beginPath();cx.arc(u.x,u.y,sz/2,0,Math.PI*2);cx.fill();}cx.restore();if(u.hp<u.maxHp){var bw=sz+6;hpBar(u.x-bw/2,u.y-sz/2-11,bw,u.hp,u.maxHp,isP?'#00cc44':'#ff4444');}if(u.type==='boss'){cx.font='bold 12px Arial';cx.fillStyle='#ff00ff';cx.textAlign='center';cx.shadowColor='#000';cx.shadowBlur=4;cx.fillText('BOSS',u.x,u.y-sz/2-15);cx.shadowBlur=0;}}
function drawBase(x,hp,mhp,isP){var my=LANE_YS[1],bw=55,bh=80,img=imgs.wall;cx.save();if(img){if(!isP){cx.translate(x,my);cx.scale(-1,1);cx.drawImage(img,-bw/2,-bh/2,bw,bh);}else cx.drawImage(img,x-bw/2,my-bh/2,bw,bh);}else{cx.fillStyle=isP?'#3a6ebf':'#cc4444';cx.fillRect(x-bw/2,my-bh/2,bw,bh);}cx.restore();hpBar(x-45,my-bh/2-14,90,hp,mhp,isP?'#00cc44':'#ff4444');cx.font='bold 10px Arial';cx.fillStyle=isP?'#aaffaa':'#ffaaaa';cx.textAlign='center';cx.fillText(isP?'YOUR BASE':'ENEMY BASE',x,my-bh/2-20);}
function drawProjs(){for(var i=0;i<projs.length;i++){var p=projs[i];if(!p.alive)continue;var ang=Math.atan2(p.ty-p.y,p.tx-p.x);cx.save();cx.translate(p.x,p.y);cx.rotate(ang);if(imgs.arrow)cx.drawImage(imgs.arrow,-12,-5,24,10);else{cx.fillStyle='#8b4513';cx.fillRect(-10,-2,20,4);}cx.restore();}}
function drawParts(){for(var i=0;i<parts.length;i++){var p=parts[i];if(!p.a)continue;cx.save();cx.globalAlpha=p.life/p.ml;cx.fillStyle=p.col;cx.beginPath();cx.arc(p.x,p.y,p.sz/2,0,Math.PI*2);cx.fill();cx.restore();}}
function drawHUD(){cx.fillStyle='rgba(0,0,0,0.68)';cx.fillRect(0,0,W,58);if(imgs.coin)cx.drawImage(imgs.coin,10,7,32,32);else{cx.fillStyle='#ffd700';cx.beginPath();cx.arc(26,23,14,0,Math.PI*2);cx.fill();}cx.font='bold 22px Arial';cx.fillStyle='#ffd700';cx.textAlign='left';cx.fillText(gold,50,33);cx.font='bold 20px Arial';cx.fillStyle='#fff';cx.textAlign='center';cx.fillText('WAVE '+(lvl+1)+' / 3',W/2,33);var ratio=Math.max(0,(MAX_T-gTimer)/MAX_T);cx.fillStyle='rgba(0,0,0,0.45)';cx.fillRect(0,54,W,5);cx.fillStyle=ratio>0.4?'#ff6600':'#ff2200';cx.fillRect(0,54,W*ratio,5);}
function drawCards(){cx.fillStyle='rgba(18,10,4,0.90)';cx.fillRect(0,CP_Y,W,H-CP_Y);cx.strokeStyle='#8b7355';cx.lineWidth=2;cx.beginPath();cx.moveTo(0,CP_Y);cx.lineTo(W,CP_Y);cx.stroke();for(var i=0;i<CARDS.length;i++){var c=CARDS[i],x=c.x,y=c.y,w=CW,h=CH;var aff=!c.locked&&gold>=c.cost;rr(x,y,w,h,8,c.locked?'rgba(25,15,8,0.6)':aff?'rgba(60,40,20,0.95)':'rgba(38,24,12,0.8)',c.locked?'#443322':aff?'#c8a050':'#554433',2);var ik=c.type==='swordsman'?'player':'tower',ui=imgs[ik];if(ui){cx.save();cx.globalAlpha=c.locked?0.3:1;cx.drawImage(ui,x+CW/2-24,y+30,48,48);cx.restore();}cx.font='bold 11px Arial';cx.textAlign='center';cx.fillStyle=c.locked?'#665544':aff?'#ffd700':'#aa8844';cx.fillText(c.type==='swordsman'?'Swordsman':'Archer',x+CW/2,y+86);if(imgs.coin){cx.save();cx.globalAlpha=c.locked?0.3:1;cx.drawImage(imgs.coin,x+12,y+h-28,20,20);cx.restore();}cx.font='bold 14px Arial';cx.fillStyle=c.locked?'#555':aff?'#ffd700':'#ff5533';cx.fillText(c.cost,x+CW/2+8,y+h-12);if(c.locked){cx.font='bold 12px Arial';cx.fillStyle='rgba(255,255,255,0.45)';cx.fillText('LOCKED',x+CW/2,y+106);}if(drag&&drag.type===c.type)rr(x-1,y-1,CW+2,CH+2,9,null,'rgba(80,255,80,0.7)',3);}}
function drawGhost(){if(!drag)return;var inBF=drag.gy>=BF_TOP&&drag.gy<=BF_BOT&&drag.gx>=80&&drag.gx<=EBX-50;cx.fillStyle=inBF?'rgba(0,220,0,0.10)':'rgba(255,0,0,0.08)';cx.fillRect(80,BF_TOP,EBX-130,BF_BOT-BF_TOP);var ik=drag.type==='swordsman'?'player':'tower',img=imgs[ik];cx.save();cx.globalAlpha=0.6;if(img)cx.drawImage(img,drag.gx-24,drag.gy-24,48,48);else{cx.fillStyle='#ffd700';cx.beginPath();cx.arc(drag.gx,drag.gy,22,0,Math.PI*2);cx.fill();}cx.restore();var sl=LANE_YS[laneOf(drag.gy)];cx.strokeStyle='rgba(0,255,100,0.4)';cx.lineWidth=2;cx.setLineDash([8,8]);cx.beginPath();cx.moveTo(80,sl);cx.lineTo(EBX-50,sl);cx.stroke();cx.setLineDash([]);}
function drawTutorial(wt){if(tutDone||wt>7)return;var pr=((Date.now()/1000)%1.4)/1.4;var sx=195,sy=876,ex=265,ey=582;var hx=sx+(ex-sx)*pr,hy=sy+(ey-sy)*pr;cx.save();cx.font='bold 14px Arial';cx.fillStyle='rgba(255,255,100,0.95)';cx.textAlign='center';cx.shadowColor='#000';cx.shadowBlur=6;cx.fillText('DRAG TROOP TO BATTLEFIELD!',W/2,90);cx.shadowBlur=0;cx.strokeStyle='rgba(255,255,100,0.55)';cx.lineWidth=2;cx.setLineDash([7,7]);cx.beginPath();cx.moveTo(sx,sy-20);cx.lineTo(hx,hy);cx.stroke();cx.setLineDash([]);cx.font='26px serif';cx.fillText('\u261D',hx,hy+4);cx.restore();}
function drawTitle(){drawBG();cx.fillStyle='rgba(0,0,0,0.50)';cx.fillRect(0,0,W,H);cx.font='bold 58px "Arial Black",Arial';cx.fillStyle='#ffd700';cx.textAlign='center';cx.shadowColor='#ff8800';cx.shadowBlur=28;cx.fillText('ARMY CLASH',W/2,300);cx.shadowBlur=0;cx.font='bold 28px Arial';cx.fillStyle='#fff';cx.fillText('Kingdom War',W/2,352);cx.font='20px Arial';cx.fillStyle='rgba(255,255,255,0.88)';cx.fillText('Drag troops to battle!',W/2,402);var t=((Date.now()/900)%1);var cX=175,cY=545,bX=295,bY=430,hx=cX+(bX-cX)*t,hy=cY+(bY-cY)*t;rr(cX-5,cY-15,62,72,6,'rgba(60,40,20,0.92)','#c8a050',2);if(imgs.player)cx.drawImage(imgs.player,cX,cY-10,42,42);cx.font='10px Arial';cx.fillStyle='#ffd700';cx.textAlign='center';cx.fillText('Swordsman',cX+26,cY+38);cx.fillText('10',cX+26,cY+52);cx.strokeStyle='rgba(255,215,0,0.6)';cx.lineWidth=3;cx.setLineDash([10,8]);cx.beginPath();cx.moveTo(cX+26,cY+20);cx.lineTo(hx,hy);cx.stroke();cx.setLineDash([]);cx.font='30px serif';cx.fillStyle='#fff';cx.textAlign='left';cx.fillText('\u261D',hx-6,hy+8);var ps=18+Math.sin(stT*3.5)*5;cx.strokeStyle='rgba(255,255,255,0.65)';cx.lineWidth=2.5;cx.beginPath();cx.arc(W/2,730,ps,0,Math.PI*2);cx.stroke();cx.font='17px Arial';cx.fillStyle='rgba(255,255,255,0.9)';cx.textAlign='center';cx.fillText('TAP TO START',W/2,780);}
function drawWaveIntro(w){drawBG();cx.fillStyle='rgba(0,0,0,0.55)';cx.fillRect(0,0,W,H);var sc=1+Math.sin(stT*Math.PI*2)*0.04;cx.save();cx.translate(W/2,H/2);cx.scale(sc,sc);cx.font='bold 52px "Arial Black",Arial';cx.fillStyle='#ffd700';cx.textAlign='center';cx.shadowColor='#ff8800';cx.shadowBlur=22;cx.fillText(w===3?'BOSS BATTLE!':'WAVE '+w,0,-30);cx.shadowBlur=0;cx.font='bold 22px Arial';cx.fillStyle='#fff';cx.fillText(w===1?'Deploy your troops!':w===2?'ARCHER UNLOCKED!':'Defeat the Boss!',0,22);cx.restore();}
function drawWaveClear(w){var sc=Math.min(1.0,0.6+stT*0.8);cx.save();cx.translate(W/2,H/2-60);cx.scale(sc,sc);cx.font='bold 56px "Arial Black",Arial';cx.fillStyle='#ffd700';cx.textAlign='center';cx.shadowColor='#ffaa00';cx.shadowBlur=24;cx.fillText('WAVE '+w+' CLEAR!',0,0);cx.shadowBlur=0;cx.font='bold 24px Arial';cx.fillStyle='rgba(255,255,255,0.85)';cx.fillText('+20 GOLD BONUS!',0,50);cx.restore();}
function drawResult(){cx.fillStyle='rgba(0,0,0,0.62)';cx.fillRect(0,0,W,H);var sc=Math.min(1.0,0.4+stT/0.5*0.6);cx.save();cx.translate(W/2,H/2);cx.scale(sc,sc);if(victory){cx.font='bold 68px "Arial Black",Arial';cx.fillStyle='#ffd700';cx.textAlign='center';cx.shadowColor='#ffaa00';cx.shadowBlur=32;cx.fillText('VICTORY!',0,-40);cx.shadowBlur=0;cx.font='60px serif';cx.fillText('\u2B50\u2B50\u2B50',0,40);}else{cx.font='bold 60px "Arial Black",Arial';cx.fillStyle='#ff4444';cx.textAlign='center';cx.shadowColor='#ff0000';cx.shadowBlur=20;cx.fillText('DEFEATED!',0,-30);cx.shadowBlur=0;cx.font='22px Arial';cx.fillStyle='#fff';cx.fillText('Can you conquer the kingdom?',0,30);}cx.restore();}
function drawLoading(){cx.fillStyle='#16213e';cx.fillRect(0,0,W,H);var pct=total>0?loaded/total:0;cx.font='bold 32px Arial';cx.fillStyle='#ffd700';cx.textAlign='center';cx.shadowColor='#ff8800';cx.shadowBlur=15;cx.fillText('ARMY CLASH',W/2,H/2-80);cx.shadowBlur=0;cx.fillStyle='rgba(255,255,255,0.2)';cx.fillRect(W/2-120,H/2-15,240,30);cx.fillStyle='#ffd700';cx.fillRect(W/2-120,H/2-15,240*pct,30);cx.font='16px Arial';cx.fillStyle='#fff';cx.fillText('Loading... '+Math.round(pct*100)+'%',W/2,H/2+50);}
function update(dt){switch(state){case 'loading':break;case 'title':stT+=dt;if(stT>=2.8){state='wave_intro';stT=0;initWave(0);}break;case 'wave_intro':stT+=dt;if(stT>=1.5){state='playing';stT=0;}break;case 'playing':gTimer+=dt;wTimer+=dt;stT+=dt;if(nuTimer>0)nuTimer-=dt;spawnEnemies(dt);updBattle(dt);updParts(dt);if(ebhp<=0){baseBlast(EBX,LANE_YS[1]);if(lvl<2){state='wave_clear';stT=0;sWC();}else{state='result';stT=0;victory=true;}}if(pbhp<=0){baseBlast(PBX,LANE_YS[1]);state='result';stT=0;victory=false;}if(gTimer>=MAX_T){state='result';stT=0;victory=false;}break;case 'wave_clear':stT+=dt;updParts(dt);if(stT>=1.9){lvl++;state='wave_intro';stT=0;initWave(lvl);}break;case 'result':stT+=dt;updParts(dt);if(stT>=2.3)showCTA(victory);break;case 'cta':break;}}
function render(){cx.clearRect(0,0,W,H);switch(state){case 'loading':drawLoading();break;case 'title':drawTitle();break;case 'wave_intro':drawBG();drawBase(PBX,pbhp,pbmax,true);drawBase(EBX,ebhp,ebmax,false);drawParts();drawWaveIntro(lvl+1);break;case 'playing':drawBG();for(var li=0;li<3;li++){cx.save();cx.strokeStyle='rgba(255,255,255,0.07)';cx.lineWidth=1;cx.setLineDash([10,14]);cx.beginPath();cx.moveTo(0,LANE_YS[li]);cx.lineTo(W,LANE_YS[li]);cx.stroke();cx.setLineDash([]);cx.restore();}drawBase(PBX,pbhp,pbmax,true);drawBase(EBX,ebhp,ebmax,false);for(var i=0;i<pu.length;i++)drawUnit(pu[i],true);for(var i=0;i<eu.length;i++)drawUnit(eu[i],false);drawProjs();drawParts();drawGhost();drawHUD();drawCards();drawTutorial(stT);if(nuTimer>0){cx.font='bold 17px Arial';cx.fillStyle='#00ff88';cx.textAlign='center';cx.shadowColor='#00cc44';cx.shadowBlur=10;cx.fillText('NEW! ARCHER UNLOCKED!',W/2,88);cx.shadowBlur=0;}break;case 'wave_clear':drawBG();drawBase(PBX,pbhp,pbmax,true);drawBase(EBX,0,ebmax,false);for(var i=0;i<pu.length;i++)drawUnit(pu[i],true);drawParts();drawHUD();drawCards();drawWaveClear(lvl+1);break;case 'result':drawBG();drawBase(PBX,pbhp,pbmax,true);drawBase(EBX,ebhp,ebmax,false);for(var i=0;i<pu.length;i++)drawUnit(pu[i],true);for(var i=0;i<eu.length;i++)drawUnit(eu[i],false);drawParts();drawResult();break;case 'cta':break;}}
function loop(ts){var dt=Math.min((ts-lt)/1000,0.05);lt=ts;update(dt);render();requestAnimationFrame(loop);}
loadAssets();requestAnimationFrame(loop);
})();
</script>
</body>
</html>`;

fs.writeFileSync(outPath, html, 'utf8');
const stat = fs.statSync(outPath);
console.log('SUCCESS!');
console.log('Output:', outPath);
console.log('Size:', Math.round(stat.size/1024), 'KB (' + stat.size + ' bytes)');
console.log('Within 5MB limit:', stat.size < 5*1024*1024 ? 'YES' : 'NO - EXCEEDS LIMIT');
