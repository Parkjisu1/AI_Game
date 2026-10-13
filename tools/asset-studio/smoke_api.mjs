import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const webRoot='/home/aimed/projecthub-web';
const config=await readFile(webRoot+'/.env.production','utf8');
const keyLine=config.split(/\r?\n/).find(l=>l.startsWith('HERMES_INTERNAL_API_KEY='));
if (!keyLine) throw new Error('Internal authentication key unavailable');
const key=keyLine.slice(keyLine.indexOf('=')+1).replace(/^(["'])(.*)\1$/,'$2');
const base=process.env.ASSET_TEST_BASE || 'http://127.0.0.1:3007';
const headers={'x-hermes-key':key};
const unauth=await fetch(base+'/api/assets-3d',{redirect:'manual'});
assert.ok([401,302,303,307].includes(unauth.status),'Unauthenticated API must be protected');
const list=await fetch(base+'/api/assets-3d',{headers});
assert.equal(list.status,200);
const data=await list.json();
assert.ok(Array.isArray(data.jobs));
const page=await fetch(base+'/assets-3d',{headers});
assert.equal(page.status,200);
assert.ok((await page.text()).includes('3D 모델 제작실'));
const bad=new FormData();bad.set('file',new File(['bad'],'bad.exe'));bad.set('title','invalid');
assert.equal((await fetch(base+'/api/assets-3d',{method:'POST',headers,body:bad})).status,400);
assert.equal((await fetch(base+'/api/assets-3d/000000000000000000000000/files/secret.txt',{headers})).status,404);
console.log('PASS: auth, page, list, invalid upload, file allowlist');
if (process.argv.includes('--create-demo')) {
  const form=new FormData();form.set('mode','demo');form.set('profile','pc');
  form.set('brief','Stylized wind swordsman. Reference: Yasuo. Check silhouette, material atlas, normalized skin weights, LOD, animations and engine import.');
  const response=await fetch(base+'/api/assets-3d',{method:'POST',headers,body:form});
  assert.equal(response.status,201);
  const result=await response.json();
  await writeFile('/home/aimed/projecthub-3d/demo-job.json',JSON.stringify(result,null,2));
  console.log('DEMO_JOB',result.id);
}
if (process.argv.includes('--status')) {
  console.log(JSON.stringify({worker:data.worker,jobs:data.jobs.map(j=>({id:j._id,status:j.status,stage:j.stage,artifacts_ready:j.artifacts_ready,error:j.error,report:j.report}))},null,2));
}
