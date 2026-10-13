# Wind Ronin 원화 비교·수정 기록

최신 수정본: v29. 실제 등록 작업: `6aa1374ec1c98766b7b44ece`.
빌드 중간 산출물: `C:/ProjectHub3D/cache/style-iteration`.
최종 팩: `D:/ProjectHub3D/jobs/6aa1374ec1c98766b7b44ece/output`.

| 구간 | 실제 비교에서 찾은 문제 | 수정과 결과 |
|---|---|---|
| v3→v4 | 넓은 몸체, 씻긴 색, 원화와 다른 얼굴 | 비례 조정·원화 색상 투영. 정면 진단값은 개선했지만 옆면은 부족 |
| v5→v8 | 기존 생성 메시의 부서진 표면 | TRELLIS.2 512/1024 비교 후 1024 채택. 실제 네 방향 렌더로 가이드 제작 |
| v9→v13 | 면 연결, 투영 겹침, 허벅지에 손 색이 비침 | 닫힌 voxel→QuadriFlow, 앞/뒤 공간 가중치와 옆면 가시성 사용 |
| v14→v17 | 구운 텍스처의 붉은 삼각형, 빈 UV 공간 | 명시적 UV 래스터 검사. 겹침 173,275→174 픽셀, 점유 7,527,194/16,777,216. 작은 잔여는 래스터 경계 중복 포함 |
| v18→v22 | 장비가 평평함, 머리 위 작은 면이 LOD에서 겹침 | 장비 손맵·명암 베이크, 머리 cap을 중심 fan으로 수정. 32본, 3 LOD 연결 검사 통과 |
| v23 | 무릎·손목·옷 경계의 흰 선 | 픽셀별 전경 마스크와 가까운 내부 색을 사용해 배경 오염 제거 |
| v24/v25 | 손 교체 시 형태·텍스처·면 연결 퇴보 | 채택하지 않음. 실험 파일만 보존 |
| v26 | GLB 웹 재질이 흰색, packed 이미지의 별도 PNG 누락 | unlit 재질 연결·FBX 임시 재질·지연 이미지 로딩 수정. v22 리그에 v23 손맵 결합 |
| v27/v28 | 축소 시 UV 경계에 검은 선 | 베이크 여백을 2회→12회 확장. 같은 웹 카메라에서 선 감소 확인 |
| v29 | 팔·다리·손가락 본이 몸통을 잘못 당김 | 몸통 3,150개·손 575개 정점 보정, 같은 JointTest의 허리 변형 비교 |

## 재현에 필요한 파일

1. `run_style_model.py --1024`: Build의 독립 Python 3.11에서 실행. 생성 결과는 `trellis2/output/wind-ronin-1024`.
2. `preview_native.py -- --1024`: Blender로 pbr-source.blend 생성. `render_texture_views.py`: 원본 네 방향 카메라 렌더.
3. `references/texture-guide-*-v8.png`와 프롬프트 JSON: 위 렌더를 보고 만든 손맵 가이드. 실제 3D 렌더와 구별한다.
4. `retopologize_native.py`: v9/retopo-source.blend. `bake_texture_guides.py -- --retopo --clean --spatial --debug-projection`: v11/projection-debug.blend.
5. `prepare_guide_masks.py`: 별도 Python에서 전경의 최근접 픽셀 인덱스 생성. `bake_uv_explicit.py -- --reunwrap`: v23의 깨끗한 4K 텍스처와 UV.
6. `finish_style_character.py`: 보존된 v19/character.blend를 입력으로 v21 리그·장비 생성. v19는 v17과 같은 UV 배치의 중간 텍스처 버전이다. `repair_export_topology.py`는 v21을 v22로 수정한다.
7. `finalize_style_revision.py`: v22/prepared.blend + v23/Painted_BaseColor_4K.png → v26/prepared.blend. 머리 cap 보정 외의 몸체 UV 배치가 동일한 조합이다.
8. `blender_pipeline.py -- style-v26-job.json`: 팩 생성. `verify_pack.py -- <output>`: 새 Blender 세션에서 독립 검증.

Blender 스크립트는 `--background --disable-autoexec --threads 8 --python-exit-code 1 --python <script> -- <arguments>`로 실행한다. 버전 경로가 지정된 재현용 스크립트들이며 임의 캐릭터용 범용 자동 조형기라고 가정하지 않는다.

## 채택 기준과 남은 차이

웹 뷰어에는 CSP가 GLB 내부 blob 텍스처 요청을 막는 문제도 있었다. 비교 페이지 경로에만 필요한 요청을 허용하고 console 오류와 material texture 로딩을 검사하도록 수정했다. Next 프로덕션 빌드는 Node heap 4GB로 제한해 완료했다.

같은 시점의 원화와 실제 렌더를 비교해 형태·얼굴·재질·실루엣을 먼저 판단하고, LOD·재질 내보내기·동작 검사를 이어서 한다. 정면 픽셀 점수만으로 옆면이나 아트 품질을 승인하지 않는다. 최신 비교 페이지의 정면/사선/후면과 실제 GLB를 함께 확인한다.

손가락이 일부 합쳐진 형태, 옆면 귀·얼굴, 옆구리와 천의 투영 늘어짐, 극단 관절 변형은 남아 있다. IK/FK 조작 리그·얼굴 표정·검 뽑기와 전투 클립, Unity/Unreal 실제 장면의 성능 측정은 미완료다. 기술 통과와 최종 아트 승인을 구별한다.

최신 v29 재현: `bake_uv_explicit.py -- --reunwrap --mip` → v27 텍스처, `finalize_style_revision.py -- --mip` → v28, `refine_style_weights.py` → v29, `blender_pipeline.py -- style-v29-job.json` → 팩.
