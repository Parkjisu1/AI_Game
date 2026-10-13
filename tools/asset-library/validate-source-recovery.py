"""Validate all recovered bytes and verify historical copies cannot enter active RAG."""
import hashlib,html,json,pathlib,re,subprocess,time,uuid
import requests
from PIL import Image
ROOT=pathlib.Path('E:/AI/output/asset-library-v2');DATA=ROOT/'data';BASE='http://127.0.0.1:16333'
rows=[json.loads(x) for x in (DATA/'source-recovery.jsonl').open(encoding='utf8')];errors=[];verified=0;previews=0;checks=set();unresolved=[]
for a in rows:
 if a['source_status']=='unavailable':
  assert not a.get('source_path') and not a.get('source_hash')
  info=a['recovery_checks'];name=pathlib.PureWindowsPath(a['legacy_path']).name
  result=subprocess.run(['git','-C',info['git_repository'],'log','--all','--format=','--name-only','--',':(glob)**/'+name],capture_output=True,timeout=45)
  unresolved.append({'id':a['id'],'project':a['project'],'path':a['legacy_path'],'all_git_refs_search_empty':result.returncode==0 and not result.stdout.strip()});continue
 assert a['source_scope']=='historical' and a['source_resolution']=='git_history' and a['eligible'] is False and a['embedding_status']=='excluded_historical'
 raw=pathlib.Path(a['source_path']).read_bytes();g=a['git_source']
 assert hashlib.sha256(raw).hexdigest()==a['source_hash']
 assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==g['blob']
 assert not (pathlib.Path(g['repository'])/g['path']).is_file(),'Restored over current project unexpectedly'
 key=(g['repository'],g['commit'],g['anchor_commit'])
 if key not in checks:
  result=subprocess.run(['git','-C',key[0],'merge-base','--is-ancestor',key[1],key[2]],capture_output=True,timeout=45);assert result.returncode==0;checks.add(key)
 if a.get('preview'):
  with Image.open(ROOT/'previews'/a['preview']) as image:image.verify()
  with Image.open(a['source_path']) as image:assert (image.width,image.height)==(a['width'],a['height'])
  previews+=1
 response=requests.get(BASE+'/library/item/'+a['id'],timeout=30);response.raise_for_status();item=response.json()['item']
 assert item['source_resolution']=='git_history' and item['source_status']=='historical_only'
 response=requests.get(BASE+'/library/file/'+a['id'],timeout=30);response.raise_for_status();assert hashlib.sha256(response.content).hexdigest()==a['source_hash']
 verified+=1
for domain,collection,count in [('code','code_assets',96670),('art','art_assets',38901)]:
 ids=[str(uuid.uuid5(uuid.NAMESPACE_URL,'asset-library:'+x['id'])) for x in rows if x['domain']==domain]
 response=requests.post(BASE+'/collections/'+collection+'/points',json={'ids':ids,'with_payload':False,'with_vector':False},timeout=30);response.raise_for_status();assert response.json()['result']==[],'Historical item found in active vectors'
 response=requests.get(BASE+'/collections/'+collection,timeout=30);response.raise_for_status();assert response.json()['result']['points_count']==count
h=requests.get(BASE+'/dashboard/',timeout=10).text
assert 'function sourceInfo(a)' in h and 'historical_source_recovered' in h
js=re.search(r'<script>(.*?)</script>',h,re.S).group(1);script=ROOT/'source-recovery-ui-check.js';script.write_text(js,encoding='utf8');subprocess.run(['C:/Program Files/nodejs/node.exe','--check',str(script)],check=True)
report={'at':time.time(),'passed':True,'target_records':len(rows),'verified_historical_files':verified,'verified_previews':previews,'verified_source_downloads':verified,'unresolved':unresolved,'active_vector_counts_unchanged':True,'historical_records_in_active_vectors':0,'page_script_syntax':'passed','visual_browser_inspection':False,'errors':errors}
(DATA/'source-recovery-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
remaining=''.join('<li>'+html.escape(x['project']+' / '+x['path'])+'</li>' for x in unresolved)
page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>원본 연결 복구 결과</title><style>body{font:15px/1.8 "Malgun Gothic",sans-serif;max-width:950px;margin:35px auto;padding:0 18px;color:#183044}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #d4dfe8;text-align:left}.note{background:#fff2dc;padding:18px}a{color:#147b83}pre{white-space:pre-wrap;background:#f0f4f7;padding:16px}</style><h1>원본 연결 복구 결과 · 2026-10-05</h1><a href="/dashboard/#/collections">자료실로 돌아가기</a><p>legacy_id는 과거 등록 번호입니다. 파일이 삭제되더라도 DB 등록 번호는 남습니다. 이전 조회 화면은 이 상태를 단순 missing으로 보여줘 등록·파일·임베딩의 차이를 알아보기 어려웠습니다.</p><table><tr><th>필드</th><th>의미</th></tr><tr><td>legacy_id</td><td>이전 DB의 등록 번호. 파일 존재나 내용 일치의 증거가 아닙니다.</td></tr><tr><td>legacy_path</td><td>예전에 등록됐던 파일 경로</td></tr><tr><td>source_path</td><td>현재 실제로 읽을 수 있는 파일 위치. 과거 보관본이면 별도 표시합니다.</td></tr><tr><td>source_resolution</td><td>원본을 찾은 방식. git_history는 Git 과거 이력에서 복구했다는 뜻입니다.</td></tr><tr><td>image_dimensions / width·height</td><td>이미지의 실제 픽셀 크기. 기존 resolution은 이 해상도를 뜻하지 않습니다.</td></tr><tr><td>status / source_status</td><td>파일 검수 상태 / 현재 원본인지 과거 보관본인지 구분하는 상태</td></tr></table><h2>처리 결과</h2><ul><li>누락 상태 114개를 점검했습니다. 아트 92개, 코드 20개의 과거 파일을 복구했습니다.</li><li>Git 저장소·커밋·파일 경로·blob ID와 원본 SHA-256을 기록했습니다. 과거 파일은 별도 보관했으며 게임 저장소에는 되살리지 않았습니다.</li><li>상태 필터에서 <b>과거 원본 복구 · 현재 프로젝트에 없음</b>을 선택하면 확인할 수 있습니다. 상세 화면에서 원문·미리보기·다운로드를 제공합니다.</li><li>현행 AI 검색에는 복구 자료를 추가하지 않았습니다. 코드 96,670건, 아트 38,901건의 활성 벡터 수는 그대로입니다.</li></ul><div class="note">Git에서 읽은 파일 자체의 무결성은 검증했습니다. 예전 등록 당시의 내용 해시가 없어, 모든 보관본이 최초 임베딩 당시의 바이트와 동일하다고 단정할 수는 없습니다. Git 삭제 이력이 현재 프로젝트에서 삭제된 이유나 재사용 적합성을 설명해 주는 것도 아닙니다.</div><h2>남은 원본 2개</h2><ul>__REMAINING__</ul><p>현재 파일과 로컬 Git의 모든 참조 이력에서 찾지 못했습니다. 등록 번호만으로 내용을 재생성하지 않았습니다. 원래 작업 PC나 별도 백업에서 원본을 확보해야 합니다.</p><h2>검증 결과</h2><pre>__RESULT__</pre></html>'''
page=page.replace('__REMAINING__',remaining).replace('__RESULT__',html.escape(json.dumps(report,ensure_ascii=False,indent=2)));(ROOT/'SOURCE-RECOVERY.html').write_text(page,encoding='utf8')
print('RECOVERY VALIDATION PASS:',verified,'historical files;',previews,'previews;',len(unresolved),'unresolved; active vectors unchanged')
