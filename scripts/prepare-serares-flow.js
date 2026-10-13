'use strict';
// Source-grounded representative slice; no game code or production DB changes.
const fs=require('fs'),path=require('path');
const {sha256,acceptanceBasis,validateContract}=require('./lib/flow-contract');
const root=path.resolve(__dirname,'..'), project=path.join(root,'projects/SeraresPlayable');
const out=path.join(root,'output/flow-plan-20261006'), designs=path.join(project,'designs');
fs.mkdirSync(designs,{recursive:true});
const contractPath=path.join(designs,'flow-contract.json');
const browserPath=path.join(out,'browser/browser-results.json');
const browser=JSON.parse(fs.readFileSync(browserPath,'utf8'));
if(!browser.passed) throw new Error('Browser checks did not pass; do not promote acceptance');
const pin=p=>({locator:path.relative(designs,p).replaceAll('\\','/'),sha256:sha256(fs.readFileSync(p))});
const source=path.join(project,'build/game.js'),html=path.join(project,'output/playable.html');
const runner=path.join(root,'scripts/verify-serares-flow.py');
if(sha256(fs.readFileSync(runner))!==browser.runner_sha256) throw new Error('Browser evidence runner changed; rerun browser verification');
if(sha256(fs.readFileSync(source))!==browser.source_sha256 || sha256(fs.readFileSync(html))!==browser.build_sha256) throw new Error('Browser evidence is stale');
const goals=[
 ['G1','기존 공격→변신→재입력 구간에서 출처와 실제 브라우저 행동 증거를 연결한다.'],
 ['G2','프로젝트가 선언한 기준으로만 피드백을 만들고 정의·측정 누락을 목표 위반과 구분한다.'],
 ['G3','실제 아트·사용자 경험·시장 검증의 미완료 상태를 코드 검사와 구분한다.']
].map(([id,statement])=>({id,statement}));
const claims=[
 {id:'C1',statement:'로컬 소스 handle(skill)은 공격 피드백을, doMorph는 등급과 전투력 증가를 구현한다. 원본 상용게임의 규칙이라는 주장은 아니다.',basis:'observed',verification:'reproduced',reference_id:'SRC',evidence:[{...pin(source),kind:'source'},{...pin(browserPath),kind:'test'}]},
 {id:'C2',statement:'drawMorphing과 기존 interval은 변신 완료 뒤 다음 변신 입력이 가능한 상태로 돌린다.',basis:'observed',verification:'reproduced',reference_id:'SRC',evidence:[{...pin(source),kind:'source'},{...pin(browserPath),kind:'test'}]},
 {id:'C3',statement:'CTA 클릭은 외부 설치 목적지 호출을 의도한다. 검사는 기존 debug 분기에서 호출을 가로챘으며 자연 완주나 실제 설치를 입증하지 않는다.',basis:'observed',verification:'reproduced',reference_id:'BUILD',evidence:[{...pin(browserPath),kind:'test'}]}
];
const decisions=[
 {id:'D_KEEP',mode:'keep',goal_ids:['G1'],claim_ids:['C1','C2','C3'],rationale:'기존 구현을 변환하거나 재설계하기 전에 행동 기준선을 확보한다.',expected_difference:'게임 기능 변경 없음; 동일한 입력에서 기존에 명시된 출력 검사.'},
 {id:'D_VERIFY',mode:'new',goal_ids:['G1','G2'],claim_ids:[],rationale:'브라우저 및 목표 기준 피드백 증거를 신규 연결한다.',expected_difference:'검증과 추적 정보 추가; 플레이 내용 변경 없음.'},
 {id:'D_SEPARATE',mode:'new',goal_ids:['G3'],claim_ids:[],rationale:'코드 실행 통과와 실제 제작/경험/시장 인수를 분리한다.',expected_difference:'미실행 영역을 명시하고 원본 시장 성과를 전용하지 않는다.'}
];
function req(id,goal,decision,category,scope,ac,statement){return {id,goal_ids:[goal],decision_ids:[decision],category,delivery_scope:scope,acceptance_ids:[ac],statement};}
const requirements=[
 req('R_BEHAVIOR','G1','D_KEEP','behavior','placeholder_functional','A_BEHAVIOR','실제 마우스/터치로 공격→첫 변신→다음 변신 및 별도 CTA 분기를 확인한다.'),
 req('R_RUNTIME','G1','D_VERIFY','technical','placeholder_functional','A_RUNTIME','현 HTML이 현 소스와 일치하고 이미지 디코드·초기화·입력에서 JS 오류와 외부 요청이 없다.'),
 req('R_FEEDBACK','G2','D_VERIFY','technical','placeholder_functional','A_FEEDBACK','시스템이 실제 측정한 hook만 명시 기준과 비교하고 임의 세션 길이/일일보상을 요구하지 않는다.'),
 req('R_ART','G3','D_SEPARATE','art','production_experience','A_ART','타깃 화면·아트 방향이 정해진 뒤 가독성·움직임·일관성을 실제 캡처/기기에서 인수한다.'),
 req('R_EXPERIENCE','G3','D_SEPARATE','experience','production_experience','A_EXPERIENCE','실제 타깃 플레이어의 의도 이해와 행동·피드백 경험을 검증한다.'),
 req('R_MARKET','G3','D_SEPARATE','market','production_experience','A_MARKET','약속·스토어·실제 경험과 유입/성과의 연결을 정의된 표본·비용·귀속 기준으로 검증한다.')
];
function ac(id,kind,scope,method,expected){return {id,kind,scope,method,expected,status:'not_run',evidence:[],input_artifacts:[]};}
const acceptance=[
 ac('A_BEHAVIOR','parity','placeholder_functional','scripts/verify-serares-flow.py; real mouse/touch, seeded RNG, existing build, source-predicted canvas outputs','3 viewport/input scenarios: damage display after clicking (manual/auto attribution not isolated); Lv.60→61→62; next popup available; explicit debug CTA intercepted exactly once. No commercial-original parity claim.'),
 ac('A_RUNTIME','runtime','placeholder_functional','scripts/verify-serares-flow.py','Inspected game.js equals embedded source; all images decode; no page errors or HTTP(S) requests in 3 scenarios.'),
 ac('A_FEEDBACK','structure','placeholder_functional','virtual-player-bridge on browser-derived hook observations','Declared hook comparison within range; no invented targets or player/market success diagnosis.'),
 ac('A_ART','art','production_experience','실제 빌드/자산 버전을 고정하고 합의된 타깃 화면에서 검토','검토 기준·아트 방향과 실제 기기 근거 필요; 현재 브라우저 캡처만으로 최종 품질 인수하지 않음.'),
 ac('A_EXPERIENCE','experience','production_experience','타깃 플레이테스트; 사전 정의한 과업·관찰·분석','실제 플레이어 증거 필요; 자동 입력 성공을 재미/이해도 성공으로 대체하지 않음.'),
 ac('A_MARKET','market','production_experience','승인된 실제 실험의 버전·표본·윈도우·비용·귀속 기록 검토','사업 목표와 실제 데이터 필요; 현재 예산·CPI·성공률을 발명하지 않음.')
];
const contract={version:1,project:'SeraresPlayable',intent:{user_request:'검토·보완 보고서 기반 계획 진행',goals,
 non_goals:['원본 상용게임 역설계 완료 주장','기존 게임 콘텐츠/배포/광고 집행 변경','브라우저 성공을 실제 유저나 시장 성공으로 판정'],
 constraints:['원본 소스와 실행 HTML 보존','외부 네트워크 차단; CTA 호출 가로채기','현재 실행 가능한 로컬 대표 구간에 한정'],
 assumptions:[{statement:'기존 Serares 2D 공격/변신 구간을 대표 검증 대상으로 선택한다.',status:'assumed',basis:'소스와 실행물 존재 및 실제 브라우저 실행 가능',reversible:true},
 {statement:'당시 게임 제작 사용자의 원문 요구는 확인하지 못했다. 기존 코드 주석은 그 사용자 원문으로 취급하지 않는다.',status:'unknown',basis:'현재 확인 가능한 파일 범위',reversible:true}]},
 references:[{id:'SRC',source:pin(source).locator,version:pin(source).sha256},{id:'BUILD',source:pin(html).locator,version:pin(html).sha256}],claims,decisions,requirements,
 work_items:requirements.map((r,i)=>({id:`W${i+1}`,discipline:['development','engineering','engineering','art','design','ua'][i],requirement_ids:[r.id],deliverable:i<2?'projects/SeraresPlayable/output/playable.html':i===2?'output/flow-plan-20261006/vp-feedback.json':`${r.id} independent acceptance evidence pending`})),
 acceptance, virtual_player:{criteria:[{id:'VP_CORE_HOOKS',metric:'engagement_hooks',requirement_ids:['R_FEEDBACK'],acceptance_ids:['A_FEEDBACK'],expected_hooks:['attack_feedback','first_morph','next_morph']}]}};
for(const id of ['A_BEHAVIOR','A_RUNTIME']){
 const item=acceptance.find(x=>x.id===id);item.status='passed';item.evidence=[{...pin(browserPath),kind:'test'}];
 item.input_artifacts=[source,html,runner].map(pin);
 item.basis_hash=acceptanceBasis(contract,item);
}
const validate=validateContract(contract,{stage:'handoff',baseDir:designs});if(!validate.ok)throw new Error(JSON.stringify(validate.errors));
// Never overwrite another project's contract: this script's explicit project/scope is fixed.
if(fs.existsSync(contractPath)){
 const old=JSON.parse(fs.readFileSync(contractPath,'utf8').replace(/^\uFEFF/,''));
 const protectedScope = c => JSON.stringify({project:c.project,intent:c.intent,requirements:c.requirements,decisions:c.decisions,work_items:c.work_items,virtual_player:c.virtual_player,
   acceptance:c.acceptance.map(({id,kind,scope,method,expected})=>({id,kind,scope,method,expected}))});
 if(protectedScope(old)!==protectedScope(contract)) throw new Error('Existing pilot goals/criteria differ; preserve them and reconcile scope before regeneration');
 for(const item of contract.acceptance){
   if(!['A_BEHAVIOR','A_RUNTIME'].includes(item.id)){
     const previous=old.acceptance.find(a=>a.id===item.id);
     Object.assign(item,previous);
     if(item.status==='passed' && item.basis_hash!==acceptanceBasis(contract,item)) item.status='stale';
   }
 }
}
fs.writeFileSync(contractPath,JSON.stringify(contract,null,2));
const vp={project:'SeraresPlayable',evidence_type:'automated_browser_scenarios',not_human_players:true,
 source:{path:path.relative(out,browserPath),sha256:sha256(fs.readFileSync(browserPath))},
 sessions:{engagement_hooks:['attack_feedback','first_morph','next_morph']},
 observations:browser.scenarios.map(s=>({scenario:s.id,status:s.status,input_mode:s.input_mode,viewport:s.viewport})),
 metric_definitions:{engagement_hooks:'Intersection of tested interaction milestones passed by all three automated scenarios; not player retention or session analytics.'}};
fs.writeFileSync(path.join(out,'vp-input.json'),JSON.stringify(vp,null,2));
console.log(JSON.stringify({contract:contractPath,handoff:validate.verdict,browser_acceptance:['A_BEHAVIOR','A_RUNTIME'],pending:contract.acceptance.filter(a=>a.status!=='passed').map(a=>a.id)}));
