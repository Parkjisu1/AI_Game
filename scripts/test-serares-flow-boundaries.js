'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.resolve(__dirname,'..');
const script=path.join(__dirname,'prepare-serares-flow.js');
const cp=path.join(root,'projects/SeraresPlayable/designs/flow-contract.json');
const bp=path.join(root,'output/flow-plan-20261006/browser/browser-results.json');
function invoke(overrides){
 let writes=0;
 const fake={...fs,mkdirSync:()=>{},readFileSync:(file,...args)=>{
   const value=overrides[path.resolve(file)];
   return value===undefined?fs.readFileSync(file,...args):args.length?value:Buffer.from(value);
 },writeFileSync:()=>{writes++;throw new Error('Unexpected write before guard');}};
 let error;
 try{vm.runInNewContext(fs.readFileSync(script,'utf8'),{require:name=>name==='fs'?fake:name==='./lib/flow-contract'?require('./lib/flow-contract'):require(name),__dirname,console:{log:()=>{}}},{filename:script,timeout:5000});}
 catch(e){error=e;}
 return {writes,error};
}
test('pilot regeneration refuses user-modified goals before any write',()=>{
 const contract=JSON.parse(fs.readFileSync(cp,'utf8'));contract.intent.goals[0].statement='User changed the intended outcome';
 const r=invoke({[cp]:JSON.stringify(contract)});assert.match(r.error?.message||'',/Existing pilot goals\/criteria differ/);assert.equal(r.writes,0);
});
test('pilot refuses browser evidence from a different verifier revision before any write',()=>{
 const browser=JSON.parse(fs.readFileSync(bp,'utf8'));browser.runner_sha256='0'.repeat(64);
 const r=invoke({[bp]:JSON.stringify(browser)});assert.match(r.error?.message||'',/runner changed/);assert.equal(r.writes,0);
});
