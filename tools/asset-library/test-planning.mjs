import http from 'node:http';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const root='E:/AI/output/asset-library-v2/qa-planning-'+Date.now();
process.env.ASSET_LIBRARY_ROOT=root;
const {library}=await import('../../output/embedding-inspection-20261002/library.mjs');
const server=http.createServer((req,res)=>library(req,res,new URL(req.url,'http://127.0.0.1:16333')));
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const port=server.address().port,base='http://127.0.0.1:'+port;
try{
 const seeded=await (await fetch(base+'/library/planning')).json();assert.equal(seeded.items.length,2);assert(seeded.items.every(x=>x.status==='source_not_imported'));
 const denied=await fetch(base+'/library/planning',{method:'POST',headers:{'Content-Type':'application/json','Origin':'https://outside.invalid'},body:'{}'});assert.equal(denied.status,403);
 const document={title:'한글 기획서 확인',project:'검수 전용',genre:'퍼즐',body:'첫 번째 문장\n두 번째 문장 🎮\n표: 보상, 조건, 비용',url:'https://example.invalid/source'};
 const buffer=Buffer.from(JSON.stringify(document));
 const submitted=await new Promise((resolve,reject)=>{
  const req=http.request({host:'127.0.0.1',port,path:'/library/planning',method:'POST',headers:{'Content-Type':'application/json','Origin':'http://127.0.0.1:16333'}},res=>{const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>resolve({status:res.statusCode,data:JSON.parse(Buffer.concat(chunks))}))});
  req.on('error',reject);for(let i=0;i<buffer.length;i+=2)req.write(buffer.subarray(i,i+2));req.end();
 });
 assert.equal(submitted.status,201);const saved=await (await fetch(base+'/library/planning/'+submitted.data.id)).json();assert.equal(saved.body,document.body);assert.equal(saved.title,document.title);assert.equal(saved.status,'body_registered_not_embedded');
 const snapshot=JSON.parse(fs.readFileSync(root+'/planning-originals/'+saved.id+'.json','utf8'));assert.equal(snapshot.body_hash,createHash('sha256').update(document.body).digest('hex'));
 const report={passed:true,checks:['seed links remain explicitly not imported','cross-origin write rejected','split UTF-8 request preserved exactly','body stored without claiming embedding','source snapshot checksum matched'],fixture_root:root};
 fs.writeFileSync('E:/AI/output/asset-library-v2/data/planning-validation.json',JSON.stringify(report,null,2));console.log('Planning checks PASS (isolated fixture; actual documents untouched)');
}finally{await new Promise(resolve=>server.close(resolve));}
