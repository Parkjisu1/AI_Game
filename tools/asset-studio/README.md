# ProjectHub 3D 제작실

운영 화면: https://aimed.tailf6f809.ts.net/assets-3d (기존 ProjectHub 로그인).

제작 기준·출처·품질 한계: [WORKFLOW.ko.md](WORKFLOW.ko.md).

최신 v29은 [원화 비교·실제 3D 화면](https://aimed.tailf6f809.ts.net/asset-studio/style-comparison.html)과 [반복 수정 기록](STYLE_ITERATIONS.ko.md)에서 확인한다. 24,754 triangles, 32본, 4K/2K 손맵과 3 LOD를 제공한다. 기본 TripoSG 업로드 초안과 별도로 Build TRELLIS.2 + 네 방향 손맵을 반복 수정한 .blend를 실제 큐로 패키징했다. 자동 기술 검사는 통과했으며 아트·엔진 승인은 남아 있다.

## 입력과 결과

- 정면과 후면: 흰 배경, 전신, 같은 A 포즈. 모델링·UV·텍스처 및 노멀 베이크·FK 자동 웨이트·LOD·팩 생성이 실행된다. 현재 인체형 초안용이며 얼굴/손/의상/관절의 아트 품질은 보장하지 않는다.
- 단독 이미지 또는 복수 뷰가 한 장에 들어간 시트: 참고 자료로 저장되며 자동 실행하지 않는다.
- .blend/.glb/.fbx/.obj: 기존 모델·리그·재질 보존, 검사·LOD·패키징. 외부 텍스처는 packed .blend 또는 embedded GLB 권장. 리그가 없는 임의 모델에 자동으로 올바른 본을 붙인다고 가정하지 않는다.
- 제작 의도는 기록과 지식 검색에 사용한다. 현재 3D 생성 모델은 정면 이미지를 조건으로 사용하며 텍스트 지시를 직접 수행하지 않는다.
- 결과: Blender 원본, FBX, LOD0/1/2 GLB, PNG 텍스처, 렌더, 검사 보고서, SHA-256 manifest, ZIP. `needs_review`는 최종 납품 승인이 아니다.

## 운영 위치

| 위치 | 내용 |
|---|---|
| Mother /home/aimed/projecthub-web | 기존 웹 서비스와 data/asset-studio 작업 기록 |
| Mother /home/aimed/projecthub-3d | worker.mjs, TripoSG, 별도 ai3d-venv, 모델 캐시 |
| 임베딩 PC Ollama | nomic-embed-text 768차원 생성 |
| Mother Qdrant projecthub_3d_knowledge | 출처가 있는 제작 노트 검색 |
| Build D:/ProjectHub3D | 설치 ZIP, pipeline, references, jobs, 모델 팩 |
| Build C:/ProjectHub3D/cache | Blender 4.5.13 LTS 실행 파일과 임시 파일 |

Mother 서비스: `systemctl --user status projecthub-web projecthub-3d-worker`.
워커 로그: `journalctl --user -u projecthub-3d-worker -n 100`.
빌드 로그: `D:/ProjectHub3D/jobs/<id>/blender.log`, `blender-error.log`.

## 설치/코드 동기화

`install-build.ps1`은 공식 ZIP과 SHA-256을 대조하고 SSD에서 Blender를 실행한다. 원격 실행은 `remote.ps1 -ScriptPath install-build.ps1`. 기존 Seagate Expansion D:를 확인하며 포맷하지 않는다.

Build pipeline 폴더에 `blender_pipeline.py`, `prepare_generated.py`, `run-job.ps1`, `rig-template.blend`, `verify_pack.py`를 둔다. rig-template은 이 작업에서 직접 만든 31본 FK와 Idle/Walk/JointTest 클립이며 외부 게임 파일에서 추출하지 않았다.

Mother에는 `worker.mjs`, `image_to_shape.py`, `collect_knowledge.py`, `sources.json`을 동기화한다. TripoSG의 설치 commit과 패키지 버전은 MODEL_PROVENANCE.json, 라이선스는 TRIPOSG-LICENSE.txt에 기록했다. `setup_ai3d.py`는 Mother의 기존 QLoRA Python 3.11 환경을 읽어 사용하는 별도 venv를 만든다. 기존 torch 패키지는 수정하지 않는다.

웹 변경은 운영 소스로 만든 별도 web-stage에 필요한 파일만 overlay하여 `next build --webpack`으로 검증했다. 배포 전 파일과 빌드 산출물은 `/home/aimed/projecthub-3d/backups`에 남는다. 로컬 저장소의 다른 미배포 변경은 함께 배포하지 않는다.

## 검증과 남은 일

`smoke_api.mjs`: 인증, 목록/페이지, 잘못된 업로드, 파일 허용 목록 검사.
`ui_check.mjs`: Chromium 데스크톱/모바일 렌더, JS 오류와 가로 넘침 검사.
`verify_pack.py`: ZIP 해시, GLB 삼각형·내장 이미지·클립, 각 LOD 스키닝 재임포트, 실제 정점 움직임, FBX 재임포트. Blender 별도 세션에서 실행한다.

실제 정면/후면 이미지 업로드 → Mother 형태 생성 → Build Blender 처리 → 다운로드 경로를 시험했다. 모델의 자동 검사 결과는 report.json에 그대로 표시한다. 의상 구멍·옆면 텍스처 투영·머리/손·웨이트 변형과 무기·전투 동작 제작, 대상 엔진 성능 검증이 남아 있다. 사용자가 요청한 최종 고품질 캐릭터 팩은 아직 완성되지 않았다.

기존 빌드 시스템과 GPU 자원 잠금을 공유하지 않으므로 Unity 실행 여부 검사만으로 동시 실행 경쟁 조건을 완전히 제거하지는 않는다. 생성 작업은 한 번에 하나이며 중단된 작업은 interrupted로 기록한다.
