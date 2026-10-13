from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[2]
public=root/'tools/projecthub-web/public/asset-studio'
page=public/'style-comparison.html'
text=page.read_text(encoding='utf-8').replace('6aa12c68b4e9da5eb64d439c','6aa132e47bb44c94fc6d14bc')
text=text.replace('<option>v21</option>','<option>v26</option><option>v21</option>')
text=text.replace('· v21','· v26').replace('src="v21-front.png"','src="v26-front.png"')
text=text.replace('24,758','24,754').replace('원본 메시: 열린 경계 0','LOD0/1/2 모두: 열린 경계 0')
text=text.replace('32본 리깅과 장비 제작.','32본 리깅과 장비 제작. 옷 가장자리의 배경색 오염 제거, GLB 색상 및 FBX 텍스처 연결 수정.')
text=text.replace('20deg 83deg 3.1m','20deg 83deg auto').replace('0deg 90deg 3.1m','0deg 90deg auto')
text=text.replace('tone-mapping="neutral"','tone-mapping="linear"')
text=text.replace('</main>','<p class="small">형태 생성: TRELLIS.2 · Built with DINOv3. <a href="third-party-notices.md">사용 도구와 라이선스</a></p></main>')
page.write_text(text,encoding='utf-8')
shutil.copy2(page,public/'style-review.html')
for view in ['front','three-quarter','back']:
    shutil.copy2(root/'output/asset-studio'/('v26-'+view+'.png'),public/('v26-'+view+'.png'))
print('Updated v26 comparison page')
