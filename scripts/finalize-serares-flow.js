'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {sha256,acceptanceBasis,validateContract}=require('./lib/flow-contract');
const root=path.resolve(__dirname,'..'),out=path.join(root,'output/flow-plan-20261006');
const cp=path.join(root,'projects/SeraresPlayable/designs/flow-contract.json'),base=path.dirname(cp);
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const pin=p=>({locator:path.relative(base,p).replaceAll('\\','/'),sha256:sha256(fs.readFileSync(p))});
const c=read(cp),vpPath=path.join(out,'vp-feedback.json'),vp=read(vpPath),input=path.join(out,'vp-input.json'),browser=path.join(out,'browser/browser-results.json');
assert.equal(c.project,'SeraresPlayable');assert.equal(vp.project,c.project);
assert.equal(vp.contract_trace.sha256,sha256(fs.readFileSync(cp)),'Feedback used another contract revision');
assert.equal(vp.input_snapshot.sha256,sha256(fs.readFileSync(input)),'Feedback input changed');
assert.equal(read(input).source.sha256,sha256(fs.readFileSync(browser)),'Browser-derived input stale');
assert.equal(vp.comparisons.length,c.virtual_player.criteria.length);
assert.ok(vp.comparisons.every(x=>x.status==='within_declared_range'));
const a=c.acceptance.find(x=>x.id==='A_FEEDBACK');
a.status='passed';a.evidence=[{...pin(vpPath),kind:'test'}];
a.input_artifacts=[input,browser,path.join(root,'scripts/virtual-player-bridge.js'),path.join(root,'scripts/lib/flow-contract.js')].map(pin);
a.basis_hash=acceptanceBasis(c,a);
const gates={};for(const scope of ['technical','behavior','art','experience','market']) gates[scope]=validateContract(c,{stage:'acceptance',scope,baseDir:base});
assert.ok(gates.technical.ok && gates.behavior.ok);
assert.ok(!gates.art.ok && !gates.experience.ok && !gates.market.ok);
fs.writeFileSync(path.join(out,'contract-at-feedback.json'),fs.readFileSync(cp));
fs.writeFileSync(cp,JSON.stringify(c,null,2));
fs.writeFileSync(path.join(out,'acceptance-results.json'),JSON.stringify(gates,null,2));
// Exercise the actual normalized import boundary, not only a raw JSON archive.
const exported=read(path.join(out,'observations/export/base/rpg/ingame/files/serares_flow_slice.json'));
const agg=read(path.join(out,'observations/aggregated.json'));
const converted=require('./design-parser').convertJson(exported,{project:'SeraresPlayable',genre:'rpg',source:'observed'});
assert.equal(converted.length,1);
const detail=converted[0].detailFile;
for(const id of Object.keys(agg)) for(const field of ['observations','selected_observation_id','alternative_values','dissenting_observation_ids','selection_metadata']){
 assert.deepEqual(detail.content.parameters[id][field],agg[id][field],`${id}.${field}`);
}
fs.writeFileSync(path.join(out,'observations/reimported.json'),JSON.stringify(detail,null,2));
fs.writeFileSync(path.join(out,'observations/roundtrip-result.json'),JSON.stringify({passed:true,parameters:Object.keys(agg).length,raw_observations:Object.values(agg).reduce((n,x)=>n+x.observations.length,0),checks:['raw records','selected observation links','alternative values','dissent links','selection policy'],scope:'Local audit export and normalized in-memory import; production DB untouched'},null,2));
console.log(JSON.stringify({acceptance:Object.fromEntries(Object.entries(gates).map(([k,v])=>[k,v.verdict])),provenance_roundtrip:'PASS'}));
