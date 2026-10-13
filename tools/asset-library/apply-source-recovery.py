"""Apply a backed-up catalog overlay and make source status explicit in the viewer."""
import collections,json,pathlib,sqlite3,subprocess,sys
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data'
rows=[json.loads(x) for x in (data/'source-recovery.jsonl').open(encoding='utf8')]
backup=data/'catalog-before-source-recovery-20261005.jsonl'
if not backup.exists():
 db=sqlite3.connect('file:'+str(root/'catalog.sqlite')+'?mode=ro',uri=True)
 with backup.open('w',encoding='utf8') as f:
  for x in rows:
   old=db.execute('SELECT data FROM assets WHERE id=?',(x['id'],)).fetchone();f.write(json.dumps({'id':x['id'],'previous':json.loads(old[0]) if old else None},ensure_ascii=False)+'\n')
 db.close()
subprocess.run([sys.executable,str(pathlib.Path(__file__).parent/'catalog.py')],check=True)
for x in rows:
 if x['source_status']=='unavailable':print('Unresolved:',x['project'],x['legacy_path'],x.get('recovery_reason'))
print('Identity evidence:',collections.Counter((x.get('legacy_identity_check',{}).get('same_guid'),x.get('legacy_identity_check',{}).get('same_size')) for x in rows))
p=root.parent/'embedding-inspection-20261002/library.html';s=p.read_text(encoding='utf8')
if 'function sourceInfo(a)' not in s:
 s=s.replace('<button id="issuesButton">검수 이슈</button>','<button id="issuesButton">검수 이슈</button><a href="/library/recovery-report" target="_blank" rel="noopener">원본 복구 결과</a>')
 s=s.replace("let tab='code'", "Object.assign(labels,{historical_source_recovered:'과거 원본 복구 · 현재 프로젝트에 없음',source_recovered_pending_index:'현재 파일 복구 · 재임베딩 대기'});\nlet tab='code'")
 source_info='''function sourceInfo(a){
const historical=a.source_scope==='historical',missing=a.source_status==='unavailable'||a.status==='source_missing';
const methods={git_history:'Git 과거 이력에서 복구',unity_guid:'Unity GUID로 현재 파일 확인',original_path:'등록 경로에서 확인',project_relative_path:'프로젝트 상대 경로로 확인',unique_filename_in_project:'프로젝트 안의 고유 파일명으로 확인',source_archive:'해시가 기록된 원본 보관본',missing:'현재 파일을 찾지 못함',unresolved:'현재 파일을 찾지 못함'};
return (historical?'<div class="notice"><b>과거 원본 보관본입니다.</b> 현재 프로젝트에는 이 파일이 없습니다. 미리보기와 다운로드는 가능하지만 활성 AI 검색에서는 제외했습니다. 복구 커밋: <code>'+esc(a.git_source?.commit)+'</code></div>':missing?'<div class="notice"><b>등록 정보만 있고 원본은 아직 확보하지 못했습니다.</b> legacy_id는 파일 존재나 복구 가능 여부를 보장하지 않습니다.</div>':'')+'<dl><dt>등록 번호 (legacy_id)</dt><dd>'+esc(a.legacy_id||'원본에서 파생된 자료')+'</dd><dt>파일 연결 방식 (source_resolution)</dt><dd>'+esc(methods[a.source_resolution]||a.source_resolution||'미기록')+'</dd><dt>이미지 해상도</dt><dd>'+(a.image_dimensions?esc(a.image_dimensions.width)+' × '+esc(a.image_dimensions.height)+' px':'미확인 또는 이미지가 아닌 자료')+'</dd>'+(a.legacy_path?'<dt>과거 등록 경로</dt><dd>'+esc(a.legacy_path)+'</dd>':'')+'</dl><p class="muted">기존 resolution 필드는 파일을 찾은 방식입니다. 픽셀 크기는 image_dimensions 또는 width·height로 구분합니다.</p>';
}
'''
 s=s.replace('async function detail(id){',source_info+'async function detail(id){')
 s=s.replace("document.querySelectorAll('[data-related]').forEach", "$('detailBody').insertAdjacentHTML('afterbegin',sourceInfo(a));document.querySelectorAll('[data-related]').forEach")
 s=s.replace('<dt>원본 위치</dt>','<dt>확인된 파일 위치 / 과거 등록 경로</dt>')
 s=s.replace('/missing|failed|ambiguous|error|unverified|requires/', '/missing|failed|ambiguous|error|unverified|requires|historical|pending/')
 p.write_text(s,encoding='utf8',newline='')
schema=root/'SCHEMA.json';v=json.loads(schema.read_text(encoding='utf8'));v['source_identity_fields']={'legacy_id':'Registration ID, not content identity or proof of file presence.','source_path':'Actual readable file, including explicitly marked historical archives.','source_resolution':'How the source was found; replaces ambiguous legacy resolution field.','image_dimensions':'Decoded image width/height in pixels; unrelated to source resolution.','source_scope':'historical files are excluded from active RAG.','git_source':'Repository/commit/path/blob provenance; does not prove equality to original ingestion bytes without a stored hash.'};schema.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
print('Catalog overlay and source-status UI applied')
