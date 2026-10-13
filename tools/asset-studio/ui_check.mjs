import { chromium } from './browser/node_modules/playwright-core/index.mjs';
import { execFileSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
// Read only the existing internal key into process memory; never print it or persist it in a browser profile.
const code="from pathlib import Path; p=Path('/home/aimed/projecthub-web/.env.production'); print(next(l.split('=',1)[1].strip().strip(chr(34)).strip(chr(39)) for l in p.read_text().splitlines() if l.startswith('HERMES_INTERNAL_API_KEY=')))";
const remote="python3 -c '"+code.replaceAll("'", "'\"'\"'")+"'";
const key=execFileSync('ssh',['aimed@100.77.190.68',remote],{encoding:'utf8'}).trim();
const browser=await chromium.launch({headless:true,executablePath:'C:/Users/user/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe'});
try {
  const context=await browser.newContext({extraHTTPHeaders:{'x-hermes-key':key},viewport:{width:1440,height:1080}});
  const page=await context.newPage();
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://100.77.190.68:3000/assets-3d',{waitUntil:'networkidle'});
  await page.getByRole('heading',{name:'3D 모델 제작실'}).waitFor();
  await mkdir('output/asset-studio',{recursive:true});
  await page.screenshot({path:'output/asset-studio/projecthub-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'output/asset-studio/projecthub-mobile.png',fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  console.log(JSON.stringify({page_errors:errors,mobile_overflow:overflow,title:await page.title()}));
  if(errors.length||overflow)process.exitCode=1;
} finally {await browser.close();}
