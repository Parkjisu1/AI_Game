# Project hub — Blender 3D 제작 워크플로우

작성일: 2026-09-09. 이 문서의 예산과 합격 기준은 이번 프로젝트의 **제안값**이며 Riot의 실제 내부 규격이 아니다.

## 현재 제공되는 기능과 남은 제작 단계

### 원화 비교 수정 v29 (2026-09-09 저녁)

[실제 비교 화면](https://aimed.tailf6f809.ts.net/asset-studio/style-comparison.html)에 초기 v3와 v4/v8/v17/v21/v26의 Blender 렌더를 보존했다. v26은 TRELLIS.2 1024 형태, 닫힌 QuadriFlow 메시, 4방향 손맵, UV 재배치, 배경색 오염 보정, 32본 리그, 검집·스카프·머리카락 장비를 결합했다. LOD0/1/2는 24,754 / 12,376 / 6,188 triangles, 재질 2개, 몸체 4K와 장비 2K이다. 세 LOD 모두 비정상 면 연결·퇴화면·미할당 웨이트 0, 영향 본 최대 4이다.

GLB는 `KHR_materials_unlit`과 BaseColor 텍스처를 사용해 손맵의 명암을 유지한다. Emission 노드만 연결한 재질이 웹에서 흰색으로 나오는 문제는 RGBA→Material Output으로 고쳤다. FBX 내보내기에만 같은 이미지를 Principled Base Color에 연결한 임시 재질을 쓴다. FBX를 엔진에서 같은 모습으로 보려면 Unlit 셰이더를 지정한다. 독립 검사는 실제 재질 연결, 별도 PNG, 각 LOD 스킨, 3개 클립과 정점 이동까지 확인한다.

**기본 이미지 업로드는 여전히 아래의 TripoSG 초안 경로다.** v26은 Build의 별도 Python 3.11/TRELLIS.2 환경에서 생성하고, 실제 렌더를 비교하면서 이미지 생성 도구로 가이드를 수정하고 Blender 스크립트를 반복 실행한 결과다. 시각 비교·가이드 수정까지 무인 자동화한 기능은 아니다. 최종 .blend는 ProjectHub의 실제 업로드→빌드→다운로드 경로로 처리했다. 버전별 의존 관계는 [STYLE_ITERATIONS.ko.md](STYLE_ITERATIONS.ko.md)에 기록했다.

원화와 남은 차이는 손가락 분리·옆면 얼굴/귀·천 경계와 큰 관절 변형이다. 테스트 동작 3개는 전투 애니메이션 완성품이 아니며 얼굴 리그·IK/FK·엔진 성능 검수와 최종 아트 승인은 미완료다.

새 형태 생성은 [Microsoft TRELLIS.2](https://github.com/microsoft/TRELLIS.2), [Windows fork](https://github.com/IgorAherne/TRELLIS.2-stableprojectorz)를 사용했다. 코드 commit과 모델 revision은 TRELLIS2_MODEL_PROVENANCE.json, 라이선스는 TRELLIS2-LICENSE.txt와 DINOV3-LICENSE.md에 보존한다. Built with DINOv3. 입력 특징은 공개 timm DINOv3 가중치이며 별도의 배경 제거 모델은 사용하지 않는다.

v29에서는 12회 베이크 여백 확장으로 축소 화면의 검은 선을 줄였고, 몸통 3,150정점과 손 575정점의 잘못된 본 영향을 보정했다. v26/v29의 같은 JointTest 렌더를 비교 페이지에 보존한다.

### 기본 이미지 업로드 경로와 공통 제작 기준

웹 표시에는 CSP가 GLB 내장 텍스처의 blob 요청을 막는 문제도 있었다. `/asset-studio/*`에만 `connect-src blob:`를 추가했다. 브라우저 검사는 console 오류와 실제 재질의 texture 로딩까지 확인한다.

현재 워커는 (1) 흰 배경의 정면·후면 A 포즈 이미지 → Mother의 TripoSG 형태 생성, (2) 빌드 PC의 Blender 표면 재구성·감면·UV·2K 색상 및 고폴리 노멀 베이크·자동 FK 리깅, (3) LOD 3단계, (4) FBX·GLB·Blender·텍스처·보고서 패키징을 실행한다. 이미 만들어진 모델을 올리면 기존 UV·재질·리그를 보존해 검사·LOD·패키징한다. 절차형 기술 예제와 별도로 이미지 기반 Wind Ronin 예제가 있다.

**자동 결과는 제작 초안이며 LoL 수준의 최종 리소스가 아니다.** 단독 이미지/다시점 시트는 `needs_modeling`, 정면+후면 이미지와 모델 처리 결과는 `needs_review`로 남긴다. 현재 이미지 예제에는 의상 표면 구멍·측면 투영 흔적·거친 머리/손과 자동 웨이트 한계가 있다. 얼굴/손 조형, 관절에 맞춘 수동 리토폴로지, 재질별 roughness/metallic 페인팅, IK/FK·얼굴 리그, 무기/전투 동작, 엔진 검수가 남는다. 기술 검사 통과로 아트 승인을 대체하지 않는다.

## 3대 컴퓨터의 역할

| 장비 | 역할 | 실제 확인 |
|---|---|---|
| Mother | Project hub 요청·작업 상태·참고 지식 검색·TripoSG 형태 생성·결과 전달 | 기존 Next.js 서비스, RTX 3080 Ti, SSH 연결 |
| 임베딩 컴퓨터 | 출처와 제작 지식의 벡터 검색 | nomic-embed-text 768차원, Qdrant |
| 빌드 컴퓨터 | Blender 실행·LOD·렌더·모델 팩 생성 | RTX 3080 Ti, Samsung SSD, Seagate Expansion HDD |

빌드 컴퓨터 D:는 Seagate Expansion **외장 HDD**, exFAT, 약 1TB이다. 공식 설치 ZIP·레퍼런스·작업·모델 팩은 `D:/ProjectHub3D`에 보관한다. HDD의 다수 소형 파일 압축 해제가 지나치게 느려 실행 파일은 기존 SSD의 `C:/ProjectHub3D/cache/blender-4.5.13-windows-x64/blender.exe`, 임시 작업은 같은 SSD의 cache/temp를 사용한다. D:/ProjectHub3D/Blender.lnk에서 실행한다. Blender 4.5.13 LTS 공식 ZIP의 SHA-256 일치를 확인했으며 `D:/ProjectHub3D/installation.json`에 기록했다.

TripoSG는 [원저자 저장소](https://github.com/VAST-AI-Research/TripoSG)의 MIT 라이선스 모델을 Mother의 별도 ai3d-venv에서 실행한다. 12GB GPU에서 CPU offload와 기존 PyTorch를 사용해 실제 추론을 확인했다. 모델 캐시는 /home/aimed/projecthub-3d/model-cache이다. 흰 배경 입력을 사용하므로 별도 배경 제거 모델은 쓰지 않는다.

Unity 프로세스가 실행 중이면 제작 워커는 대기한다. Blender는 한 번에 한 작업, CPU 8스레드, Cycles GPU를 우선 사용한다. 현재 Unity 검사와 시작 사이의 경쟁 조건까지 통제하는 공통 스케줄러는 없으므로 대규모 동시 빌드 운영 전 기존 빌드 큐와 자원 잠금을 통합해야 한다.

## 1. 레퍼런스와 제작 명세

입력은 목표 엔진·플랫폼, 예상 화면상 캐릭터 높이, 카메라 각도, 기본 자세, 장비 목록, 필요한 애니메이션과 표정이다. 정면·측면·후면은 같은 비율로 맞춘다. 생성 이미지의 앞뒤 불일치도 실제 모델링 전에 수정한다.

야스오 분석에서는 묶은 머리, 비대칭 어깨 덩어리, 검의 곡선, 넓은 천의 흐름, 작은 화면에서 읽히는 명암 구성을 살핀다. Wind Ronin은 이 시각 언어를 참고한 독자 검객이다. AI 레퍼런스 시트와 현재 3D 초안의 아트 완성도는 다르다. 제작 의도 텍스트는 참고 지식 검색과 기록에 사용하며, 현재 형태 생성의 직접 조건은 정면 이미지다. 후면 이미지는 텍스처 투영에 사용한다.

Riot의 캐릭터 아트 설명은 비례·닮음·게임 화면에서의 가독성과 2D→3D 변환을 강조한다. [공식 설명 및 영상 링크](https://www.riotgames.com/en/artedu/character-art), [야스오 공식 레퍼런스](https://www.leagueoflegends.com/en-us/champions/yasuo/).

## 2. 형태와 리토폴로지

큰 덩어리 → 비례/실루엣 → 얼굴/손 → 의상 접힘 → 장비 순서로 작업한다. 256px 높이의 회색 실루엣에서도 얼굴 방향, 머리, 검, 어깨를 식별할 수 있어야 한다. 디테일을 추가하기 전에 정면·측면·후면과 실제 게임 카메라의 형태를 비교한다.

고폴리 조형은 원본으로 보존한다. 게임 메시에는 어깨 회전, 팔꿈치 굽힘, 무릎 굽힘을 따라 연결되는 엣지 루프를 만든다. 얼굴은 눈·입 주변 흐름과 표정 요구를 먼저 정한다. 몸에 붙는 옷과 두꺼운 갑옷은 변형 방식을 구분한다. 손가락·검집·끈을 무작정 합치면 수정과 바인딩이 어려워진다.

Decimate는 주로 LOD 후보를 만드는 수단이다. LOD0의 나쁜 관절 흐름을 고치는 리토폴로지로 취급하지 않는다. 현재 예제는 조립형 절차 메시여서 고급 인체 토폴로지의 대체물이 아니다. [Blender 리토폴로지](https://docs.blender.org/manual/en/4.5/modeling/meshes/retopology.html), [한국어 Decimate 문서](https://docs.blender.org/manual/ko/4.5/modeling/modifiers/generate/decimate.html), [Instant Meshes 원저자 저장소](https://github.com/wjakob/instant-meshes).

## 3. UV·베이크·텍스처

게임용 기본안은 몸/의상 공용 2K atlas 1장, 필요할 때 무기/얼굴을 분리하는 방식이다. 얼굴에 해상도를 더 배분하되 눈에 띄는 텍셀 밀도 차이를 검사한다. 베이크용 UV는 의도하지 않은 겹침이 없어야 한다. 반복되는 장비/천의 공유 UV는 따로 기록한다. 2K에서 16px 여백을 출발값으로 잡고 실제 mipmap 거리에서 번짐을 확인한다.

고폴리→저폴리 베이크는 cage 또는 ray distance를 메시 크기에 맞춘다. 노멀·AO의 이음새, 뒤집힘, 빗나간 광선 흔적을 확인한다. DirectX/OpenGL 노멀 방향은 엔진 설정과 함께 시험한다. 색상은 sRGB, roughness·metallic·normal은 Non-Color로 다룬다. AO를 강하게 그린 BaseColor와 PBR 조명을 함께 써서 이중 음영이 생기지 않게 한다.

LoL 스타일 손맵은 큰 명암 그룹 → 재질별 색 변주 → 주름·엣지 포인트 → 얼굴/손의 집중 디테일 순서로 제작한다. 전체에 같은 크기의 노이즈를 뿌리면 작은 게임 화면에서 읽히지 않는다. 천/피부/금속/가죽은 색상뿐 아니라 roughness와 하이라이트 폭으로 구별한다.

현재 절차형 예제는 공유 UV atlas, 이미지 기반 예제는 정면/후면 색상 투영을 별도 UV에 베이크하고 보존한 고폴리에서 tangent Normal을 베이크한다. 이미지 기반 결과는 균일 roughness .72를 사용하므로 재질별 PBR 페인팅 완료품은 아니다. [Cycles 베이크 공식 문서](https://docs.blender.org/manual/en/4.5/render/cycles/baking.html), [glTF 재질 호환성](https://docs.blender.org/manual/en/4.5/addons/import_export/scene_gltf2.html).

## 4. 리깅·웨이트·동작

Root → Hips → Spine → Chest → Neck → Head, 좌우 쇄골·상완·전완·손·허벅지·정강이·발 계층을 기본으로 한다. 장검/검집은 소켓, 머리/스카프는 보조 본으로 분리한다. 필요한 손가락/표정 본을 명세에 추가한다. 작업용 IK/FK 컨트롤 리그와 내보내기용 deform 본을 구분한다.

자동 웨이트는 초안이다. 합계 1, 미할당 정점 0, 제안 프로필에서 정점당 영향 본 ≤4를 검사한다. 팔 들기 120°, 팔꿈치/무릎 120°, 전완 비틀기 90°, 앉기, 검 뽑기, 머리 회전에서 찢어짐·부피 소실·관통을 확인한다. 필요하면 twist 본·보정 shape key를 추가한다. 애니메이션은 클립별 프레임 범위와 루프 접점을 검사한다.

현재 예제는 기본 FK 리그와 Idle/Walk/JointTest를 제공하며 IK/FK 스위치, 얼굴 리그, 전투 동작 완성품은 아니다. [일본어 스키닝 문서](https://docs.blender.org/manual/ja/4.5/animation/armatures/skinning/parenting.html), [중국어 웨이트 편집 문서](https://docs.blender.org/manual/zh-hans/4.5/sculpt_paint/weight_paint/editing.html).

## 5. 최적화 예산과 검수 기준

| 항목 | PC 제안 | 모바일 제안 | 합격 증거 |
|---|---|---|---|
| LOD0 | ≤30,000 triangles | ≤12,000 triangles | 내보낸 파일 기준 확인 |
| LOD1 / LOD2 | LOD0의 50% / 25% 출발 | 동일 | 실제 화면에서 실루엣 비교 |
| 텍스처 | 2K 공용 atlas 출발 | 1K~2K, 기기 검증 | 압축·mipmap 포함 메모리 실측 |
| 머티리얼 | 1~3 제안 | 1~2 제안 | 엔진 draw call/패스 확인 |
| 웨이트 | 합계 1, ≤4 영향 본 | 동일 | 정점 검사 + 동작 변형 |
| 본 | 필요한 deform 본만 | 필요에 따라 축소 | 애니메이션 CPU 실측 |
| 누락 리소스 | 0 | 0 | 깨끗한 환경에서 재임포트 |

폴리곤 수만으로 최적화가 끝나지 않는다. UV/노멀 이음새는 엔진 정점을 늘릴 수 있다. 머티리얼 패스, 그림자, 투명 헤어/천 overdraw, 스키닝 CPU, 텍스처 메모리를 측정한다. 예를 들어 압축 전 2048² RGBA8 한 장은 약 16MiB, 전체 mip chain은 약 21.3MiB다. 실제 GPU 압축 형식에 따라 달라진다. 성능 목표는 대상 기기·장면 밀도·해상도를 정한 뒤 확정한다.

## 6. 납품 구조

`character.blend`, `character.fbx`, `character_LOD0/1/2.glb`, `textures/*.png`, `preview.png`, `report.json`, `manifest.json`, `README.txt`, `model-pack.zip`을 남긴다. manifest에는 파일 크기와 SHA-256을 저장한다. 원본 입력을 덮어쓰지 않으며 작업 ID별 새 폴더로 실행한다. Blender 원본은 이미지를 pack하고 FBX도 텍스처를 embed한다.

GLB를 새 Blender 세션에서 열어 스킨·텍스처·클립을 점검하고, Unity/Unreal에서는 축/스케일·본 매핑·클립 루프·LOD 전환·재질·프레임 비용을 확인한다. 자동 검사 결과와 아트/엔진 승인 결과는 별도 필드다. 현재 UI는 자동으로 최종 납품 완료 표시를 하지 않는다.

## 조사 범위와 출처 신뢰도

한국·일본·중국·미국 자료와 YouTube·Bilibili·X를 검색했고, **14개 출처 후보의 URL·공개 메타데이터·직접 작성한 요약**을 저장했다. 전체 플랫폼을 전수 수집한 것은 아니다. YouTube 자막/영상 전체, 유료 강의, 로그인 뒤 게시물은 수집하지 않았다. 수집 실패와 robots 제한을 `research-evidence.json`에 기록한다. 접근 실패 자료는 검색/공식 링크에서 확인한 범위만 사용한다. 소스의 언어·지역은 작성자나 사이트 기준이며 Blender 번역 문서를 해당 국가의 독자 제작 기법으로 보지 않는다.

- 미국: [Riot 캐릭터 아트](https://www.riotgames.com/en/artedu/character-art), [공식 YouTube 영상](https://www.youtube.com/watch?v=PfpE5dNTWeI). 공식 설명은 읽었고 영상 전체 전사는 미실시.
- 한국: [게임 테크놀로지 Instant Meshes 영상](https://www.youtube.com/watch?v=H1DZ2hiHbYg). URL과 공개 식별 정보만 확인. 한국어 Blender 문서와 함께 후속 검토용으로 기록.
- 일본: [CGWORLD Blender Fes 제작 세션](https://cgworld.jp/special/blenderfes/vol6/?channel=channel-952). 주최 측 설명에서 2D 실루엣·주름·조형→리토폴로지 주제를 확인. 유료 강의는 미열람.
- 중국: [Hamburn彬仔 리깅·웨이트 튜토리얼](https://www.bilibili.com/video/BV1KM4y167Hi/). 원저자의 공개 설명과 챕터 목록 확인. 영상 전체 미전사.
- X: [Creative Assembly 캐릭터 아트 직무 설명](https://x.com/CAGames/status/1141644725642022912). 검색 색인 발췌만 확인; 직접 페이지 본문은 읽히지 않음. 튜토리얼 근거로 확대 해석하지 않음.

수집 요약은 기존 임베딩 컴퓨터의 nomic-embed-text로 768차원 벡터를 생성해 **별도 `projecthub_3d_knowledge` 컬렉션**에 저장한다. 원문 전수가 아닌 출처가 있는 제작 노트 검색이며, 검색 실패 시 작업에 unavailable을 기록한다. 검색한 내용이 실제 모델링을 자동 수행하는 것은 아니다.

## 재실행

빌드 컴퓨터 설치: `powershell -File tools/asset-studio/remote.ps1 -ScriptPath tools/asset-studio/install-build.ps1`.

Mother 지식 갱신: `python3 /home/aimed/projecthub-3d/collect_knowledge.py --index`.

Mother 워커: `systemctl --user status projecthub-3d-worker`. 로그: `journalctl --user -u projecthub-3d-worker -n 100`.

웹 화면: `/assets-3d`. 모델 업로드는 포장된 .blend 또는 GLB 권장. FBX/OBJ에 외부 텍스처가 빠져 있으면 보고서에서 수정 대상으로 남긴다.
