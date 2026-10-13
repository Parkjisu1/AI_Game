"""Publish the accepted visual revision; keep earlier renders and audit records."""
from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[2];public=root/'tools/projecthub-web/public/asset-studio';studio=root/'tools/asset-studio';out=root/'output/asset-studio'
page=public/'style-comparison.html';text=page.read_text(encoding='utf-8')
text=text.replace('6aa132e47bb44c94fc6d14bc','6aa1374ec1c98766b7b44ece')
text=text.replace('<option>v26</option>','<option>v29</option><option>v26</option>')
text=text.replace('· v26','· v29').replace('src="v26-front.png"','src="v29-front.png"')
text=text.replace('초기 3D · v3','초기 3D · v3 정면')
text=text.replace('다운로드할 모델 직접 확인','최신 v29 모델 직접 확인')
text=text.replace('GLB 색상 및 FBX 텍스처 연결 수정.','GLB 색상 및 FBX 텍스처 연결 수정. 축소 시 검은 선을 줄이고 몸통 3,150개·손 575개 정점의 웨이트를 보정.')
motion='<details><summary>같은 동작으로 웨이트 수정 전후 비교</summary><div class="grid" style="grid-template-columns:repeat(2,minmax(0,1fr))"><section class="card"><h2>v26 · 보정 전</h2><img src="v26-JointTest.png" alt="보정 전 몸통과 허리의 변형"></section><section class="card"><h2>v29 · 보정 후</h2><img src="v29-JointTest.png" alt="같은 관절 동작의 웨이트 보정 후"></section></div><p>같은 카메라와 JointTest 13프레임을 렌더했습니다. 허리를 팔·다리 본이 당기던 문제를 줄였습니다. 손가락 형태와 천의 큰 변형은 추가 수정 대상입니다.</p></details>'
if 'v29-JointTest.png' not in text:text=text.replace('<details><summary>전체 제작 레퍼런스</summary>',motion+'<details><summary>전체 제작 레퍼런스</summary>')
page.write_text(text,encoding='utf-8');shutil.copy2(page,public/'style-review.html')
for name in ['v29-front.png','v29-three-quarter.png','v29-back.png','v29-JointTest.png','v26-JointTest.png']:
    shutil.copy2(out/name,public/name)
for name in ['README.md','WORKFLOW.ko.md']:
    path=studio/name;text=path.read_text(encoding='utf-8')
    text=text.replace('최신 v26','최신 v29').replace('원화 비교 수정 v26 (','원화 비교 수정 v29 (')
    path.write_text(text,encoding='utf-8')
workflow=studio/'WORKFLOW.ko.md';text=workflow.read_text(encoding='utf-8')
text=text.replace('### 기본 이미지 업로드 경로와 공통 제작 기준','v29에서는 12회 베이크 여백 확장으로 축소 화면의 검은 선을 줄였고, 몸통 3,150정점과 손 575정점의 잘못된 본 영향을 보정했다. v26/v29의 같은 JointTest 렌더를 비교 페이지에 보존한다.\n\n### 기본 이미지 업로드 경로와 공통 제작 기준')
workflow.write_text(text,encoding='utf-8')
history=studio/'STYLE_ITERATIONS.ko.md';text=history.read_text(encoding='utf-8').replace('최신 수정본: v26.','최신 수정본: v29.').replace('6aa132e47bb44c94fc6d14bc','6aa1374ec1c98766b7b44ece')
text=text.replace('## 재현에 필요한 파일','| v27/v28 | 축소 시 UV 경계에 검은 선 | 베이크 여백을 2회→12회 확장. 같은 웹 카메라에서 선 감소 확인 |\n| v29 | 팔·다리·손가락 본이 몸통을 잘못 당김 | 몸통 3,150개·손 575개 정점 보정, 같은 JointTest의 허리 변형 비교 |\n\n## 재현에 필요한 파일')
text += '\n최신 v29 재현: `bake_uv_explicit.py -- --reunwrap --mip` → v27 텍스처, `finalize_style_revision.py -- --mip` → v28, `refine_style_weights.py` → v29, `blender_pipeline.py -- style-v29-job.json` → 팩.\n'
history.write_text(text,encoding='utf-8')
for source,target in [(workflow,public/'workflow.md'),(history,public/'STYLE_ITERATIONS.ko.md')]:shutil.copy2(source,target)
print('v29 publication files ready')
