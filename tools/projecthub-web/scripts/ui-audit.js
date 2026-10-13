// v4 — v3 + 그라디언트 배경을 색 정지점으로 근사(가장 나쁜 정지점 기준).
const { chromium } = require("/home/aimed/.hermes/hermes-agent/node_modules/playwright");
const fs = require("fs");
const KEY = fs.readFileSync("/home/aimed/.hermes/watcher/.env","utf8").split("\n")
  .find(l=>l.startsWith("HERMES_INTERNAL_API_KEY=")).split("=").slice(1).join("=").trim().replace(/^"|"$/g,"");
const PAGES = process.argv.slice(2);

const AUDIT = () => {
  const cv=document.createElement("canvas"); cv.width=cv.height=1;
  const ctx=cv.getContext("2d",{willReadFrequently:true}); const cache=new Map();
  const parse=(s)=>{ if(!s) return null; if(cache.has(s)) return cache.get(s);
    ctx.clearRect(0,0,1,1); try{ ctx.fillStyle="rgba(0,0,0,0)"; ctx.fillStyle=s; }catch{ cache.set(s,null); return null; }
    ctx.fillRect(0,0,1,1); const d=ctx.getImageData(0,0,1,1).data;
    const v={r:d[0],g:d[1],b:d[2],a:d[3]/255}; cache.set(s,v); return v; };
  const lum=(c)=>{const f=(v)=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);};
    return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b);};
  const ratio=(a,b)=>{const l1=lum(a),l2=lum(b),hi=Math.max(l1,l2),lo=Math.min(l1,l2);return (hi+0.05)/(lo+0.05);};
  const over=(f,b)=>({r:f.r*f.a+b.r*(1-f.a),g:f.g*f.a+b.g*(1-f.a),b:f.b*f.a+b.b*(1-f.a),a:1});
  const hex=(c)=>"#"+[c.r,c.g,c.b].map(v=>Math.round(v).toString(16).padStart(2,"0")).join("");
  const path=(el)=>{const o=[];let n=el,d=0;while(n&&n.nodeType===1&&d<3){let s=n.tagName.toLowerCase();
    const c=(n.getAttribute("class")||"").trim().split(/\s+/).filter(Boolean).slice(0,6).join(".");
    if(c)s+="."+c;o.unshift(s);n=n.parentElement;d++;}return o.join(" > ");};
  const stops=(bgi)=>{ // 그라디언트 문자열에서 색 토큰만 뽑는다
    const out=[]; const re=/(rgba?\([^)]*\)|#[0-9a-f]{3,8}|\b(?:lab|lch|oklab|oklch|color)\([^)]*\))/gi; let m;
    while((m=re.exec(bgi))) out.push(m[1]); return out; };

  const effBg=(el)=>{
    const layers=[]; let n=el, grad=null;
    while(n&&n.nodeType===1){ const s=getComputedStyle(n);
      const bi=s.backgroundImage;
      if(bi&&bi!=="none"&&/gradient/.test(bi)){ grad={el:n, stops:stops(bi)}; break; }
      if(bi&&bi!=="none"&&/url\(/.test(bi)){ grad={el:n, stops:[]}; break; }
      const c=parse(s.backgroundColor);
      if(c&&c.a>0.004){ layers.push({c,el:n}); if(c.a>=0.995) break; }
      n=n.parentElement; }
    let below={r:255,g:255,b:255,a:1};
    if(grad){ // 그라디언트 아래의 면부터 구한다
      let p=grad.el.parentElement, sub=[];
      while(p&&p.nodeType===1){ const s=getComputedStyle(p); const c=parse(s.backgroundColor);
        if(c&&c.a>0.004){ sub.push(c); if(c.a>=0.995) break; } p=p.parentElement; }
      for(let i=sub.length-1;i>=0;i--) below=over(sub[i],below);
    }
    let acc={r:255,g:255,b:255,a:1};
    for(let i=layers.length-1;i>=0;i--) acc=over(layers[i].c,acc);
    if(grad){
      const cs=grad.stops.map(parse).filter(Boolean).map(c=>c.a<1?over(c,below):c);
      const chain=(base)=>{ let x=base; for(let i=layers.length-1;i>=0;i--) x=over(layers[i].c,x); return x; };
      return { grad:true, el:grad.el, cands: cs.length? cs.map(chain) : [chain(below)] };
    }
    return { grad:false, color:acc, el: layers.length?layers[0].el:document.body, cands:[acc] };
  };

  const out={contrast:[],overflow:[],noBg:0};
  for(const el of Array.from(document.querySelectorAll("body *"))){
    const cs=getComputedStyle(el);
    if(cs.display==="none"||cs.visibility==="hidden"||parseFloat(cs.opacity)<0.05) continue;
    const rect=el.getBoundingClientRect(); if(rect.width<1||rect.height<1) continue;
    const own=Array.from(el.childNodes).filter(n=>n.nodeType===3&&n.textContent.trim()).map(n=>n.textContent.trim()).join(" ").slice(0,50);
    if(own){
      const fgRaw=parse(cs.color); const b=effBg(el);
      if(fgRaw&&fgRaw.a>0.05&&b.cands.length){
        let worst=null;
        for(const bgc of b.cands){ const fg=fgRaw.a<1?over(fgRaw,bgc):fgRaw; const cr=ratio(fg,bgc);
          if(!worst||cr<worst.cr) worst={cr,fg,bg:bgc}; }
        const size=parseFloat(cs.fontSize), bold=parseInt(cs.fontWeight,10)>=700;
        const need=(size>=24||(size>=18.66&&bold))?3:4.5;
        if(worst.cr<need) out.contrast.push({cr:+worst.cr.toFixed(2),need,fg:hex(worst.fg),bg:hex(worst.bg),
          grad:b.grad,size,text:own,sel:path(el),bgSel:path(b.el)});
      }
    }
    const bgc=parse(cs.backgroundColor)||{a:0};
    const boxed=(parseFloat(cs.borderTopWidth)>0&&cs.borderTopStyle!=="none")||bgc.a>0.05;
    if(boxed&&(el.textContent||"").trim()){
      if(cs.overflowX==="visible"&&el.clientWidth>0&&el.scrollWidth-el.clientWidth>2)
        out.overflow.push({type:"self-x",d:el.scrollWidth-el.clientWidth,sel:path(el),text:(el.textContent||"").trim().slice(0,50)});
      if(cs.overflowY==="visible"&&el.clientHeight>0&&el.scrollHeight-el.clientHeight>2)
        out.overflow.push({type:"self-y",d:el.scrollHeight-el.clientHeight,sel:path(el),text:(el.textContent||"").trim().slice(0,50)});
      if(cs.overflow==="visible") for(const ch of Array.from(el.children)){
        const cst=getComputedStyle(ch);
        if(cst.position==="absolute"||cst.position==="fixed"||cst.display==="none") continue;
        if(!(ch.textContent||"").trim()) continue;
        const r2=ch.getBoundingClientRect(); if(r2.width<1) continue;
        const dx=Math.max(r2.right-rect.right,rect.left-r2.left), dy=Math.max(r2.bottom-rect.bottom,rect.top-r2.top);
        if(dx>4||dy>4) out.overflow.push({type:"child",dx:Math.round(dx),dy:Math.round(dy),sel:path(ch),parent:path(el),text:(ch.textContent||"").trim().slice(0,50)});
      }
    }
  }
  return out;
};

(async()=>{
  const browser=await chromium.launch();
  const ctx=await browser.newContext({viewport:{width:1440,height:1000},extraHTTPHeaders:{"x-hermes-key":KEY}});
  const page=await ctx.newPage(); const all={};
  for(const p of PAGES){
    try{ await page.goto(`http://127.0.0.1:3000${p}`,{waitUntil:"networkidle",timeout:45000}); }catch{}
    await page.waitForTimeout(2500);
    let r; try{ r=await page.evaluate(AUDIT); }catch(e){ r={error:String(e),contrast:[],overflow:[]}; }
    all[p]=r;
    console.log(`### ${p}  대비=${r.contrast.length}(심각<3:${r.contrast.filter(x=>x.cr<3).length}) 넘침=${r.overflow.length}${r.error?" ERR "+r.error:""}`);
  }
  fs.writeFileSync(process.env.OUT||"/tmp/audit4.json",JSON.stringify(all,null,1));
  await browser.close();
})();
