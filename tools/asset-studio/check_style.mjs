import { readFile,writeFile } from 'node:fs/promises';
const root='/home/aimed/projecthub-web';
const config=await readFile(root+'/.env.production','utf8');
const line=config.split(/\r?\n/).find(l=>l.startsWith('HERMES_INTERNAL_API_KEY='));
const key=line.slice(line.indexOf('=')+1).replace(/^(["'])(.*)\1$/,'$2');
const headers={'x-hermes-key':key};
const {id}=JSON.parse(await readFile('/home/aimed/projecthub-3d/style-revision-job.json','utf8'));
const base='http://127.0.0.1:3000';
const data=await(await fetch(base+'/api/assets-3d',{headers})).json();
const job=data.jobs.find(j=>j._id===id);
console.log(JSON.stringify({id,worker:data.worker,status:job.status,stage:job.stage,error:job.error,report:job.report},null,2));
if(job.artifacts_ready && process.argv.includes('--download')){
  const files=[];
  for(const file of ['model-pack.zip','preview.png','character_LOD0.glb','report.json','manifest.json','research.json']){
    const response=await fetch(`${base}/api/assets-3d/${id}/files/${file}`,{headers});
    if(!response.ok)throw new Error(`Download failed: ${file}: ${response.status}`);
    const buffer=Buffer.from(await response.arrayBuffer());
    files.push({file,bytes:buffer.length,status:response.status});
  }
  const verification={job_id:id,status:job.status,authenticated_downloads:files,knowledge:job.knowledge?.status,
    technical_pass:job.report.technical_pass,art_approved:false,engine_verified:false,checked_at:new Date().toISOString()};
  await writeFile('/home/aimed/projecthub-3d/STYLE_VALIDATION.json',JSON.stringify(verification,null,2));
  console.log('DOWNLOADS_VERIFIED',JSON.stringify(files));
}
