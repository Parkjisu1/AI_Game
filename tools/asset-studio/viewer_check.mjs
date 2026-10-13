import { chromium } from './browser/node_modules/playwright-core/index.mjs';
import { execFileSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
// Read only the existing internal key into process memory; never print it or persist it in a browser profile.
const code="from pathlib import Path; p=Path('/home/aimed/projecthub-web/.env.production'); print(next(l.split('=',1)[1].strip().strip(chr(34)).strip(chr(39)) for l in p.read_text().splitlines() if l.startswith('HERMES_INTERNAL_API_KEY=')))";
const remote="python3 -c '"+code.replaceAll("'", "'\"'\"'")+"'";
const key=execFileSync('ssh',['aimed@100.77.190.68',remote],{encoding:'utf8'}).trim();
const browser=await chromium.launch({headless:true,executablePath:'C:/Users/user/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe'});
try {
  const base='http://100.77.190.68:3000';
  const context=await browser.newContext({viewport:{width:1440,height:1080}});
  await context.route(base+'/**',route=>route.continue({headers:{...route.request().headers(),'x-hermes-key':key}}));
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const modelArg=process.argv.indexOf('--model');
  if(modelArg>=0)await page.route('**/character_LOD0.glb',route=>route.fulfill({path:process.argv[modelArg+1],contentType:'model/gltf-binary'}));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(base+'/asset-studio/style-comparison.html',{waitUntil:'networkidle'});
  const imageChecks=await page.evaluate(async()=>{
    const versions=Array.from(document.querySelectorAll('#version option'),o=>o.value);
    return Promise.all(versions.flatMap(v=>['front','three-quarter','back'].map(async view=>{
      const path='/asset-studio/'+v+'-'+view+'.png';const response=await fetch(path);return {path,status:response.status};
    })));
  });
  if(imageChecks.some(r=>r.status!==200))throw new Error(JSON.stringify(imageChecks.filter(r=>r.status!==200)));
  await page.screenshot({path:'output/asset-studio/style-comparison-desktop.png'});
  await page.locator('#model').scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.getElementById('model')?.loaded,undefined,{timeout:60000});
  const info=await page.evaluate(()=>{const model=document.getElementById('model');return {src:model.src,loaded:model.loaded,animations:model.availableAnimations,materials:model.model.materials.map(m=>({name:m.name,texture:!!m.pbrMetallicRoughness.baseColorTexture?.texture}))};});
  await page.waitForTimeout(2000);
  await page.locator('#model').scrollIntoViewIfNeeded();
  await page.screenshot({path:'output/asset-studio/style-viewer-desktop.png'});
  await page.locator('#animation').selectOption({label:'Walk'});await page.locator('#play').click();
  await page.waitForFunction(()=>document.getElementById('model').currentTime>.1);
  const time=await page.evaluate(()=>document.getElementById('model').currentTime);
  await page.screenshot({path:'output/asset-studio/style-viewer-walk.png'});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:'output/asset-studio/style-viewer-mobile.png'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  console.log(JSON.stringify({...info,animation_time:time,page_errors:errors,mobile_overflow:overflow}));
  await import('node:fs/promises').then(fs=>fs.writeFile('output/asset-studio/style-browser-check.json',JSON.stringify({...info,source_override:modelArg>=0?process.argv[modelArg+1]:null,image_checks:imageChecks,animation_time:time,page_errors:errors,mobile_overflow:overflow},null,2)));
  if(errors.length||overflow||!info.animations.includes('Walk')||info.materials.some(m=>!m.texture))process.exitCode=1;
} finally {await browser.close();}
