#!/usr/bin/env node
/**
 * Generate Hermes scoped memory bundles for BalloonFlow:
 *   - puzzle/_shared/dev/   — Unity code architecture overview (class roster, recipes, anti-patterns)
 *   - puzzle/_shared/art/   — Art asset conventions (folder structure, naming, atlas/animation list)
 *
 * Output: writes 2 markdown files to E:/AI/hermes/memories/teams/puzzle/_shared/{dev,art}/
 * (then SCP to Mother manually).
 */
const fs = require('fs');
const path = require('path');
const { MongoClient } = require('mongodb');

const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const OUT_BASE = 'E:/AI/hermes/memories/teams/puzzle/_shared';

async function main() {
  const client = new MongoClient(env.MONGO_URI);
  await client.connect();
  const db = client.db('aigame');

  // ---- DEV summary ----
  const codeDocs = await db.collection('code_base').find({ project: 'BalloonFlow' }).toArray();
  const byRole = {};
  const byRecipe = {};
  const byLayer = {};
  const byFolder = {};
  let antiNewGo = 0, antiFind = 0;
  const managerClasses = [];
  const viewClasses = [];
  const componentClasses = [];

  for (const d of codeDocs) {
    byRole[d.role] = (byRole[d.role] || 0) + 1;
    byRecipe[d.recipe] = (byRecipe[d.recipe] || 0) + 1;
    byLayer[d.layer] = (byLayer[d.layer] || 0) + 1;
    const folder = (d.file_path || '').split('/').slice(-2, -1)[0] || '?';
    byFolder[folder] = (byFolder[folder] || 0) + 1;
    if (d.anti_patterns?.new_gameobject) antiNewGo++;
    if (d.anti_patterns?.find_calls) antiFind++;
    if (d.role === 'Manager') managerClasses.push(d.className);
    if (d.role === 'View') viewClasses.push(d.className);
    if (d.role === 'Component') componentClasses.push(d.className);
  }

  const sceneDocs = await db.collection('unity_configs').find({ project: 'BalloonFlow', kind: 'scene' }).toArray();
  const prefabDocs = await db.collection('unity_configs').find({ project: 'BalloonFlow', kind: 'prefab' }).toArray();

  const devMd = `# BalloonFlow Unity Dev Context

> Auto-generated from Atlas \`code_base\` + \`unity_configs\` (project=BalloonFlow).
> Source path: \`E:/Balloonflow/BallonFlow_Git/BalloonFlow/Assets/1.Scripts/\`

## 프로젝트 개요
- **장르**: Puzzle (Balloon flow / queue mechanic)
- **C# 스크립트**: ${codeDocs.length}개 (137 game + 4 PixelArtConverter tool)
- **씬**: ${sceneDocs.length} (${sceneDocs.map(s => s.file_name || s.name).join(', ')})
- **프리팹**: ${prefabDocs.length} (parsed of 71 total — Library 잠금 등으로 일부 미파싱)

## Layer 분포
${Object.entries(byLayer).sort((a,b) => b[1] - a[1]).map(([k,v]) => `- ${k}: ${v}`).join('\n')}

## Role 분포
${Object.entries(byRole).sort((a,b) => b[1] - a[1]).map(([k,v]) => `- ${k}: ${v}`).join('\n')}

## Recipe 분포 (코드 패턴)
${Object.entries(byRecipe).sort((a,b) => b[1] - a[1]).map(([k,v]) => `- ${k}: ${v}`).join('\n')}

## 폴더 구조 (Assets/1.Scripts/)
${Object.entries(byFolder).sort((a,b) => b[1] - a[1]).map(([k,v]) => `- ${k}: ${v} files`).join('\n')}

## Manager 클래스 목록 (${managerClasses.length}개)
${managerClasses.sort().map(c => `- ${c}`).join('\n')}

## View 클래스 목록 (${viewClasses.length}개)
${viewClasses.sort().map(c => `- ${c}`).join('\n')}

## Component 클래스 목록 (${componentClasses.length}개)
${componentClasses.sort().map(c => `- ${c}`).join('\n')}

## 알려진 안티패턴 (수정 시 주의)
- \`new GameObject()\`: ${antiNewGo} files — Runtime 코드에서 금지. Resources.Load/ObjectPool 사용.
- \`Find()\` / \`FindObjectOfType()\`: ${antiFind} files — \`[SerializeField]\` 또는 캐시된 참조 사용.

## 검색 지원
Atlas \`code_base\` 컬렉션에 모든 ${codeDocs.length}개 스크립트가 \`text-embedding-3-small\` 1536d 임베딩으로 인덱스됨.
Vector search query: \`db.code_base.aggregate([{$vectorSearch: {index: 'vector_index', path: 'embedding', queryVector: ..., limit: 5, filter: {project: 'BalloonFlow'}}}])\`

## 관련 메모리
- \`_shared/design/BalloonFlow_*.md\` — 16개 기획 디렉션 문서
- \`_shared/conventions.md\` — 장르 공통 코딩 컨벤션
- \`_shared/design/parameters.yaml\` — 파라미터 표준
`;

  // ---- ART summary ----
  const artDocs = await db.collection('art_assets').find({ project: 'BalloonFlow' }).toArray();
  const byKind = {};
  const byFolderArt = {};
  const byTag = {};
  let totalBytes = 0;
  for (const d of artDocs) {
    byKind[d.kind] = (byKind[d.kind] || 0) + 1;
    const folder = (d.folder || '').split('/').slice(2, 5).join('/');
    byFolderArt[folder] = (byFolderArt[folder] || 0) + 1;
    for (const t of d.tags || []) byTag[t] = (byTag[t] || 0) + 1;
    totalBytes += d.size_bytes || 0;
  }

  const animations = artDocs.filter(d => d.kind === 'animation').map(d => d.file_name);
  const fonts = artDocs.filter(d => d.kind === 'font').map(d => d.file_name);
  const audios = artDocs.filter(d => /audio/.test(d.kind)).map(d => d.file_name);
  const atlasFiles = artDocs.filter(d => d.kind === 'spriteatlas').map(d => d.file_name);

  const artMd = `# BalloonFlow Art Asset Context

> Auto-generated from Atlas \`art_assets\` (project=BalloonFlow).
> Source paths: \`Assets/2.Sprite\`, \`3.Material\`, \`4.Atlas\`, \`5.Fonts\`, \`6.Sound\` + History backups.

## 자산 요약
- **총 자산**: ${artDocs.length}개 (${(totalBytes / 1024 / 1024).toFixed(2)} MB)

## Kind 분포
${Object.entries(byKind).sort((a,b) => b[1] - a[1]).map(([k,v]) => `- ${k}: ${v}`).join('\n')}

## 폴더 분포 (top 15)
${Object.entries(byFolderArt).sort((a,b) => b[1] - a[1]).slice(0, 15).map(([k,v]) => `- ${k}: ${v}`).join('\n')}

## 태그 분포 (top 15)
${Object.entries(byTag).sort((a,b) => b[1] - a[1]).slice(0, 15).map(([k,v]) => `- ${k}: ${v}`).join('\n')}

## SpriteAtlas (${atlasFiles.length})
${atlasFiles.map(f => `- ${f}`).join('\n')}

## Animation Clips (${animations.length})
${animations.map(f => `- ${f}`).join('\n')}

## Audio (${audios.length})
${audios.map(f => `- ${f}`).join('\n')}

## Fonts (${fonts.length})
${fonts.map(f => `- ${f}`).join('\n')}

## 폴더 컨벤션
- \`Assets/2.Sprite/UI/\` — UI 스프라이트 (HUD, 버튼, 팝업, 아이콘)
- \`Assets/2.Sprite/TS/\` — TileSet / 게임 보드 요소 (Balloon, Dart, Rail)
- \`Assets/3.Material/\` — Material assets (.mat)
- \`Assets/4.Atlas/\` — SpriteAtlas
- \`Assets/5.Fonts/\` — TTF/OTF
- \`Assets/6.Sound/BGM\` — 배경 음악
- \`Assets/6.Sound/Effect\` — SFX

## 작업 시 주의
- 새 스프라이트는 적절한 SpriteAtlas에 등록해야 batching 효율 유지.
- pivot/anchor은 \`design/parameters.yaml\` 기준 (1080×1920, UI 용도별 anchor 규칙).
- 머티리얼은 기존 \`3.Material/\` 의 것을 우선 재사용 (불필요한 신규 머티리얼 생성 금지).
- 임시 자산 (placeholder)은 \`BalloonFlow_BackUpThisFolder_ButDontShipItWithYourGame/\` 활용 가능.

## 검색 지원
Atlas \`art_assets\` 컬렉션에 모든 ${artDocs.length}개 자산이 임베딩됨 (file_name + folder + tags + kind).
조건 검색 권장: \`{project: 'BalloonFlow', kind: 'image', tags: 'balloon'}\` 등.

## 관련 메모리
- \`_shared/design/BalloonFlow_픽셀아트_레벨변환_워크플로우.md\` — 픽셀아트→레벨 변환 절차
- \`_shared/design/BalloonFlow_기믹명세.md\` — 기믹별 비주얼 명세
- \`_shared/design/BalloonFlow_인게임아이템_UX명세.md\` — 부스터/아이템 비주얼
`;

  if (!fs.existsSync(`${OUT_BASE}/dev`)) fs.mkdirSync(`${OUT_BASE}/dev`, { recursive: true });
  if (!fs.existsSync(`${OUT_BASE}/art`)) fs.mkdirSync(`${OUT_BASE}/art`, { recursive: true });
  fs.writeFileSync(`${OUT_BASE}/dev/BalloonFlow_Dev_Context.md`, devMd);
  fs.writeFileSync(`${OUT_BASE}/art/BalloonFlow_Art_Context.md`, artMd);
  console.log(`✓ wrote ${OUT_BASE}/dev/BalloonFlow_Dev_Context.md (${devMd.length} chars)`);
  console.log(`✓ wrote ${OUT_BASE}/art/BalloonFlow_Art_Context.md (${artMd.length} chars)`);

  await client.close();
}

main().catch(e => { console.error(e); process.exit(1); });
