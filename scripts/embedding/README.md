# 지식베이스 임베딩 스크립트 (프로젝트 증분 갱신)

2026-10-09 MergeDrop 작업 때 세션 스크래치에서 만든 범용 스크립트를 2026-10-12 에 여기로 옮겼다.
워크스테이션(Windows)에서 만들고, 임베딩컴(`ssh aimed@100.87.87.59`)에서 Qdrant 에 넣는다.
Qdrant(:6333)는 워크스테이션에서 직접 닿지 않으니 Qdrant 작업은 항상 ssh 로 한다.

## 어디에 들어가나

| 저장소 | 위치 | 넣는 도구 | 키 |
|---|---|---|---|
| `gf_code_chunks_m3` (bge-m3 1024d, .cs 원문 조각) — hermes 라이브 코드 검색 | 임베딩컴 Qdrant | `chunks.js` → `host/qdrant_delta.py` | uuid5(NS,"proj\|path\|chunk\|piece"), path 단위 fileSha 비교 |
| `art_vectors` (CLIP ViT-B-32 512d) | 임베딩컴 Qdrant | `art_index.js` → `clip_embed.py` → `host/artload_file.py` | uuid5(NS,"proj\|path") |
| `code_base` (클래스 계약·메타) | Mongo `aigame` | `scripts/parser.js` | fileId(클래스명)+project |
| `unity_configs` (씬·프리팹 구조) | Mongo `aigame` | `scripts/unity-config-parser.js` | configId = `proj__prefab__파일이름` |
| `art_assets` (에셋 메타) | Mongo `aigame` | `art_index.js` | assetId = sha1("proj\|path")[:16] |

NS = `6ba7b810-9dad-11d1-80b4-00c04fd430c8`. `code_assets_v2_*`(Roslyn 라이브러리)는 증분 불가라 여기서 다루지 않는다.
project 이름은 레지스트리 `hermes_projects.graph.embed_project` 와 같게 쓴다(예: ColorSort, Buddyflow).

## 파일

워크스테이션: `chunks.js`, `art_index.js`, `manifest_todo.js`, `kb_status.js`, `clip_embed.py`(CLIP venv 전용),
`code_base_stale_embeddings.js`(낡은 OpenAI embedding 무효화), `embed_missing_status.js`, `twin_check.py`, `code_base_changed.js`(진단), `code_base_ghosts.js`·`art_assets_delete.js`(승인된 삭제)
임베딩컴(`host/` → `~/` 로 scp): `qdrant_delta.py`, `artload_file.py`, `kb_qdrant.py`

```bash
scp scripts/embedding/host/*.py aimed@100.87.87.59:~/      # 바뀌었을 때만
```

## 순서 (프로젝트 하나)

변수: `P`=project, `W`=작업 폴더(스크래치), 임베딩컴 작업 폴더 `~/kb_delta`.

```bash
# 0) 현황(전)
node scripts/embedding/kb_status.js $P
ssh aimed@100.87.87.59 "python3 ~/kb_qdrant.py counts $P"

# 1) 코드 청크 → gf_code_chunks_m3   (*.local.cs·시크릿 패턴 파일은 자동 제외)
node scripts/embedding/chunks.js $P <base> <dir1,dir2> $W/chunks.jsonl
scp $W/chunks.jsonl aimed@100.87.87.59:~/kb_delta/
ssh aimed@100.87.87.59 "python3 ~/qdrant_delta.py ~/kb_delta/chunks.jsonl --dry-run"   # 변경/신규/잔존 확인
ssh aimed@100.87.87.59 "cd ~/kb_delta && nohup bash -c 'python3 ~/qdrant_delta.py ~/kb_delta/chunks.jsonl --missing-out=missing.txt; echo DONE_MARK' > delta.log 2>&1 < /dev/null &"
#   끝났는지는 delta.log 의 DONE_MARK 로 본다(pgrep -f 대기 루프는 자기 명령줄과 매치돼 끝나지 않는다).
#   --delete-missing 은 사람이 삭제를 결정했을 때만.

# 2) 아트 메타 → art_assets, 그리고 CLIP 대상 계산
node scripts/embedding/art_index.js $P <root1,root2> --manifest=$W/full.jsonl --delta-manifest=$W/delta.jsonl --missing-out=$W/art_assets_missing.txt   # 먼저 --dry-run 권장
ssh aimed@100.87.87.59 "python3 ~/kb_qdrant.py paths art_vectors $P" > $W/vpaths.txt
node scripts/embedding/manifest_todo.js $W/full.jsonl $W/delta.jsonl $W/vpaths.txt $W/todo.jsonl --stale-out=$W/art_vectors_stale.txt

# 3) CLIP → art_vectors   (CPU 약 13~27장/s. 다른 무거운 작업과 겹치면 --threads 4)
C:/Users/user/clipenv/Scripts/python.exe scripts/embedding/clip_embed.py $W/todo.jsonl $W/art_vectors.jsonl --threads 4
scp $W/art_vectors.jsonl aimed@100.87.87.59:~/kb_delta/
ssh aimed@100.87.87.59 "python3 ~/artload_file.py ~/kb_delta/art_vectors.jsonl"

# 4) code_base (스크립트 폴더 통째로 — 파일 간 의존 해석 때문에 부분 실행하지 않는다. upsert)
#    ★ parser.js 는 $set 업서트라 내용이 바뀌어도 기존 OpenAI embedding 을 그대로 남긴다(2026-10-13 감사:
#      Buddyflow 193/299 가 09-07 벡터를 10-08 내용에 붙인 채였다. 같은 텍스트의 ColorSort 쌍과 코사인 최저 0.752).
#      embed_collection.py 는 embedding 이 "없는" 문서만 채우므로, parser.js 뒤에는 반드시 4b 를 돌린다.
node scripts/parser.js <Assets/Scripts 폴더> <Genre> --project $P --mongo
# 4b) 낡은 embedding 무효화 → 재임베딩 (필수. 규칙: embedded_at < updatedAt 이면 비운다. 내용이 같아도 parser 가
#     updatedAt 을 갱신하므로 넓게 잡히지만 수백 건에 몇 초라 안전한 쪽을 택한다)
node scripts/embedding/code_base_stale_embeddings.js --project=$P --log=$W/cb_stale_ids.jsonl --unset
C:/Users/user/AppData/Local/Programs/Python/Python313/python.exe scripts/embed_collection.py code_base   # embedding 없는 문서만
node scripts/embedding/code_base_stale_embeddings.js            # stale_total 0 이어야 한다(전 프로젝트)
node scripts/embedding/embed_missing_status.js code_base        # missing_embedding 0
#    포크 쌍이 있으면 확인: python scripts/embedding/twin_check.py Buddyflow ColorSort  (같은 텍스트 쌍 전부 ≥0.99)
#    (code_base_changed.js snapshot/diff 는 "무엇이 바뀌었나" 진단용으로만 남긴다. usedBy 등을 빼고 비교해서
#     4b 보다 좁게 잡으므로 무효화 수단으로 쓰지 않는다.)

# 5) unity_configs
node scripts/unity-config-parser.js <Unity 루트 또는 바뀐 프리팹이 든 폴더> <Genre> --project $P --mongo

# 6) 현황(후) + 검색 확인
ssh aimed@100.87.87.59 "python3 ~/kb_qdrant.py counts $P; python3 ~/kb_qdrant.py art <이미지이름.png> $P; python3 ~/kb_qdrant.py code '<한국어 질의>' $P"
```

## 잔존 삭제 (사람이 승인했을 때만)

업서트 스크립트에는 삭제 기능이 없다. 따로 둔 두 도구를 쓰며, 둘 다 `--apply` 없이는 조회만 한다.

```bash
# 목록 재계산(위 2단계) → 디스크 부재 재확인 → dry-run → 목록 보관 → --apply
scp $W/art_vectors_stale.txt aimed@100.87.87.59:~/kb_delta/
ssh aimed@100.87.87.59 "python3 ~/kb_delete.py art_vectors $P ~/kb_delta/art_vectors_stale.txt --ids-out=\$HOME/kb_delta/ids.txt [--apply]"
node scripts/embedding/art_assets_delete.js $P $W/art_assets_missing.txt scripts/embedding/deleted/<이름>_docs.json [--apply]
```
지운 목록·덤프는 `deleted/` 에 둔다(2026-10-12 Buddyflow: 벡터 104, art_assets 166).
gf_code_chunks_m3 는 `qdrant_delta.py --delete-missing` (git 삭제 확인 후).

## code_base OpenAI 임베딩 필드

4b 단계가 채운다(`E:/AI/.env` 의 `OPENAI_API_KEY` 사용, 키 값은 출력·기록 금지). `embed_collection.py` 는 embedding 없는 문서만 처리하고 프로젝트 필터가 없다 —
그래서 parser.js 로 내용이 바뀐 문서는 `code_base_stale_embeddings.js --unset` 으로 먼저 비워야 한다. 지운 _id 기록: `deleted/code_base_stale_embeddings_20261013.jsonl`(279건, 첫 교정).
누락 현황: `node scripts/embedding/embed_missing_status.js`. 로컬 Mongo 는 `$vectorSearch` 를 지원하지 않는다(Atlas 전용).

code_base 유령(소스 파일·클래스가 사라진 문서): `node scripts/embedding/code_base_ghosts.js <project> <scripts_root> [--include=fileId] [--dump=f] [--apply]`.

## 함정

- **unity-config-parser 는 주어진 루트 아래를 전부 훑는다.** 안에 다른 Unity 프로젝트가 있으면(예: `D:/MergeDrop/Reconstruction/UnityProject`) 그 프리팹까지 같은 project 로 들어간다. 2026-10-09 에 4,564건을 지워 교정했다. 서브 프로젝트가 있는 루트에는 `Assets/` 만 주거나, 바뀐 프리팹이 든 **좁은 폴더**만 준다(configId 는 파일 이름 기반, filePath 는 절대경로라 좁은 폴더로 돌려도 같은 문서에 upsert 된다). 신규만 넣을 때는 `--resume`(기존 configId 건너뜀).
- unity_configs·code_base 는 이름 기반 키라 같은 이름 파일이 합쳐진다(프리팹 144→135, partial class 120→80). 정상.
- **art_index 의 root 는 기존 문서 path 접두와 대소문자까지 같아야 한다.** 다르면 assetId 가 바뀌어 중복이 생긴다. Buddyflow = `E:/Buddyflow/Buddyflow/Assets`(소문자 f).
- art_assets 변경 판정은 바이트 크기만 본다(원래 동작). 같은 크기로 바뀐 이미지는 못 잡는다.
- 디스크에서 사라진 항목은 자동 삭제하지 않는다. `--missing-out`/`--stale-out` 목록을 사람에게 보여 주고 결정을 받는다.
- bash heredoc(`<<EOF`)에 JS 정규식 백슬래시를 넣으면 사라진다 → 파일은 에디터/Write 로 쓴다.
- code_base 의 `embedding` 필드(text-embedding-3-small)는 parser.js 가 갱신하지 않는다 → 4b 를 빼먹으면 내용과 다른 낡은 벡터가 남는다(검사: `code_base_stale_embeddings.js`, `twin_check.py`).

## 프로젝트별 실제 인자 (2026-10-12 기준)

| project | chunks.js `<base> <dirs>` | art_index roots | parser.js | unity-config-parser |
|---|---|---|---|---|
| MergeDrop | `D:/MergeDrop Assets/MergeDrop/Scripts` | `D:/MergeDrop/Assets` | `D:/MergeDrop/Assets/MergeDrop/Scripts Merge` | `D:/MergeDrop/Assets Merge` (루트 금지) |
| MergeDrop_Reconstruction | `D:/MergeDrop/Reconstruction/UnityProject Assets/ReferenceTools` | `D:/MergeDrop/Reconstruction/UnityProject/Assets` | `.../UnityProject/Assets/ReferenceTools Merge` | `D:/MergeDrop/Reconstruction/UnityProject Merge` (프리팹 4,718개 — 바뀐 폴더만 권장) |
| Buddyflow | `E:/Buddyflow/Buddyflow/Assets/1.Scripts .` | `E:/Buddyflow/Buddyflow/Assets` | `E:/BuddyFlow/Buddyflow/Assets/1.Scripts Puzzle` | `E:/BuddyFlow/Buddyflow Puzzle` |
| ColorSort | `E:/ColorSort/ColorSort/Assets/1.Scripts .` | `E:/ColorSort/ColorSort/Assets` | `E:/ColorSort/ColorSort/Assets/1.Scripts Puzzle` | `E:/ColorSort/ColorSort Puzzle` |

MergeDrop 제외 범위: `Reconstruction/Export*/ExportedProject`(AssetRipper 덤프), `Tools/`(SpineRuntime·UIEffect), `Backups/`, `Builds/*/Captures`, `Documentation/Screenshots` — 위 루트를 쓰면 자연히 빠진다.
