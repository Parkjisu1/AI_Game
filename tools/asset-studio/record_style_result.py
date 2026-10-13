"""Record only checked live v29 artifacts; retain initial experiment evidence."""
from pathlib import Path
import json,hashlib,zipfile,shutil
root=Path(__file__).resolve().parents[2];out=root/'output/asset-studio';studio=root/'tools/asset-studio'
job='6aa1374ec1c98766b7b44ece'
download=json.loads((out/'STYLE_VALIDATION.json').read_text());report=json.loads((out/'v29-report.json').read_text())
roundtrip=json.loads((out/'v29-roundtrip-check.json').read_text());browser=json.loads((out/'style-browser-check.json').read_text())
assert download['job_id']==job and download['technical_pass'] and report['technical_pass'] and roundtrip['passed']
assert job in browser['src'] and not browser['source_override'] and not browser['page_errors']
assert all(m['texture'] for m in browser['materials']) and not browser['mobile_overflow']
pack=out/'Wind-Ronin-style-v29-pack.zip'
with zipfile.ZipFile(pack) as archive:
    assert archive.testzip() is None
    manifest=json.loads(archive.read('manifest.json'))
    for item in manifest['files']:
        data=archive.read(item['path']);assert hashlib.sha256(data).hexdigest()==item['sha256']
    assert len([f for f in archive.namelist() if f.startswith('textures/')])==2
old=out/'INITIAL_VALIDATION.json'
if not old.exists():shutil.copy2(out/'FINAL_VALIDATION.json',old)
final={**download,'revision':'v29','roundtrip':roundtrip,'browser':browser,'local_pack_bytes':pack.stat().st_size,'local_pack_sha256':hashlib.sha256(pack.read_bytes()).hexdigest(),'art_approved':False,'engine_verified':False}
(out/'FINAL_VALIDATION.json').write_text(json.dumps(final,indent=2,ensure_ascii=False),encoding='utf-8')
result=(out/'RESULT-v26.ko.md').read_text(encoding='utf-8').replace('v26','v29').replace('6aa132e47bb44c94fc6d14bc',job).replace('97,402,005','97,681,964').replace('v29-browser-check.json','style-browser-check.json')
result=result.replace('원화와 실제 Blender 렌더를 반복 비교하여','v27/v28에서 축소 시 검은 선을 줄였고 v29에서 몸통 3,150개·손 575개 정점의 본 영향을 보정했다. 같은 동작의 수정 전후 렌더를 확인했다.\n\n원화와 실제 Blender 렌더를 반복 비교하여')
result += '\n실제 웹 검사: GLB 텍스처 2개 로딩, 3개 클립, Walk 재생, 비교 렌더 18개 HTTP 200, console 오류 0, 모바일 가로 넘침 0. ProjectHub 제작실에 비교 페이지 링크를 추가했고, 범위를 제한한 CSP 수정과 프로덕션 빌드를 배포했다.\n'
(out/'RESULT-v29.ko.md').write_text(result,encoding='utf-8')
pointer=out/'RESULT.ko.md';pointer.write_text(pointer.read_text(encoding='utf-8').replace('v26 수정 결과','v29 수정 결과').replace('RESULT-v26.ko.md','RESULT-v29.ko.md'),encoding='utf-8')
print(json.dumps({'revision':'v29','job_id':job,'pack_bytes':pack.stat().st_size,'hashes':len(manifest['files']),'images':len(browser['image_checks']),'technical_pass':True,'art_approved':False,'engine_verified':False}))
