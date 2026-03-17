#!/usr/bin/env node
/**
 * Unity Config Parser v1.0
 * .unity (scene) 및 .prefab 파일에서 프로젝트 구성 정보를 추출
 *
 * 추출 대상:
 *   - RectTransform (Pivot, Anchor, SizeDelta)
 *   - CanvasScaler 설정
 *   - GameObject 계층구조
 *   - 컴포넌트 바인딩 (MonoBehaviour + SerializeField 참조)
 *   - Camera, EventSystem 설정
 *
 * 출력: JSON 파일 (로컬) + MongoDB unity_configs collection (옵션)
 *
 * Usage:
 *   node unity-config-parser.js <project_path> <genre> [options]
 *   --project <name>   프로젝트명
 *   --db <path>        로컬 DB 경로
 *   --mongo            MongoDB 동시 저장
 */

const fs = require('fs');
const path = require('path');

// ============================================================
// Unity YAML Block Parser
// ============================================================

/**
 * Unity YAML은 표준 YAML이 아님 (--- !u!classId &fileId 형식)
 * 블록 단위로 파싱하여 오브젝트 맵 생성
 */
function parseUnityYAML(content) {
    const objects = {};
    const blocks = content.split(/^--- !u!(\d+) &(\d+)/m);

    // blocks[0] = header, then [classId, fileId, body, classId, fileId, body, ...]
    for (let i = 1; i + 2 < blocks.length; i += 3) {
        const classId = blocks[i];
        const fileId = blocks[i + 1];
        const body = blocks[i + 2];

        const obj = {
            classId,
            fileId,
            type: getUnityTypeName(classId),
            data: parseYAMLBlock(body)
        };

        objects[fileId] = obj;
    }

    return objects;
}

/**
 * Unity class ID → type name mapping (주요 타입만)
 */
function getUnityTypeName(classId) {
    const typeMap = {
        '1': 'GameObject',
        '4': 'Transform',
        '20': 'Camera',
        '23': 'MeshRenderer',
        '33': 'MeshFilter',
        '54': 'Rigidbody',
        '61': 'BoxCollider',
        '65': 'BoxCollider2D',
        '82': 'AudioSource',
        '95': 'Animator',
        '104': 'RenderSettings',
        '114': 'MonoBehaviour',
        '124': 'Behaviour',
        '157': 'LightmapSettings',
        '196': 'NavMeshSettings',
        '212': 'SpriteRenderer',
        '222': 'CanvasRenderer',
        '223': 'Canvas',
        '224': 'RectTransform',
        '225': 'CanvasGroup',
    };
    return typeMap[classId] || `UnityType_${classId}`;
}

/**
 * 단순 YAML 블록 파싱 (중첩 지원, Unity 전용)
 */
function parseYAMLBlock(text) {
    const result = {};
    const lines = text.split('\n');

    for (const line of lines) {
        const trimmed = line.trimStart();
        if (!trimmed || trimmed.startsWith('#')) continue;

        // key: value 패턴
        const kvMatch = trimmed.match(/^(\w[\w.]*)\s*:\s*(.*)$/);
        if (kvMatch) {
            const key = kvMatch[1];
            let val = kvMatch[2].trim();

            // {x: 0, y: 0} 인라인 오브젝트
            if (val.startsWith('{') && val.endsWith('}')) {
                result[key] = parseInlineObject(val);
            }
            // {fileID: 123} 참조
            else if (val.startsWith('{fileID:')) {
                const fidMatch = val.match(/fileID:\s*(\d+)/);
                result[key] = fidMatch ? { fileID: fidMatch[1] } : val;
            }
            // 숫자
            else if (/^-?\d+\.?\d*$/.test(val)) {
                result[key] = parseFloat(val);
            }
            // 빈 배열/리스트 시작
            else if (val === '' || val === '[]') {
                result[key] = val === '[]' ? [] : val;
            }
            else {
                result[key] = val;
            }
        }
    }

    return result;
}

function parseInlineObject(str) {
    const result = {};
    // {x: 0.5, y: 1, z: 0, w: 0}
    const inner = str.slice(1, -1);
    const parts = inner.split(',');
    for (const part of parts) {
        const kv = part.split(':');
        if (kv.length >= 2) {
            const k = kv[0].trim();
            const v = kv.slice(1).join(':').trim();
            result[k] = /^-?\d+\.?\d*$/.test(v) ? parseFloat(v) : v;
        }
    }
    return result;
}

// ============================================================
// Extractors
// ============================================================

/**
 * RectTransform 추출
 */
function extractRectTransforms(objects, gameObjects) {
    const rects = [];

    for (const [fid, obj] of Object.entries(objects)) {
        if (obj.type !== 'RectTransform') continue;

        const d = obj.data;
        const goRef = d.m_GameObject;
        const goName = goRef?.fileID ? getGameObjectName(objects, goRef.fileID) : 'unknown';

        // 부모 찾기
        const parentRef = d.m_Father;
        const parentName = parentRef?.fileID && parentRef.fileID !== '0'
            ? getGameObjectName(objects, findGameObjectByTransform(objects, parentRef.fileID))
            : null;

        // 자식 수
        let childCount = 0;
        if (d.m_Children && Array.isArray(d.m_Children)) {
            childCount = d.m_Children.length;
        } else {
            // m_Children이 YAML 리스트로 파싱 안 된 경우 카운트
            childCount = Object.keys(d).filter(k => k.startsWith('m_Children')).length > 0 ? -1 : 0;
        }

        rects.push({
            fileId: fid,
            gameObject: goName,
            parent: parentName,
            anchorMin: d.m_AnchorMin || { x: 0, y: 0 },
            anchorMax: d.m_AnchorMax || { x: 0, y: 0 },
            pivot: d.m_Pivot || { x: 0.5, y: 0.5 },
            sizeDelta: d.m_SizeDelta || { x: 0, y: 0 },
            anchoredPosition: d.m_AnchoredPosition || { x: 0, y: 0 },
            localScale: d.m_LocalScale || { x: 1, y: 1, z: 1 },
            childCount
        });
    }

    return rects;
}

function getGameObjectName(objects, fileId) {
    if (!fileId || fileId === '0') return 'unknown';
    const go = objects[fileId];
    if (!go) return `ref_${fileId}`;
    if (go.type === 'GameObject') return go.data.m_Name || `GO_${fileId}`;
    // If it's a transform, find the parent GO
    if (go.data?.m_GameObject?.fileID) {
        const parentGO = objects[go.data.m_GameObject.fileID];
        return parentGO?.data?.m_Name || `GO_${fileId}`;
    }
    return `ref_${fileId}`;
}

function findGameObjectByTransform(objects, transformFileId) {
    const transform = objects[transformFileId];
    if (!transform) return null;
    return transform.data?.m_GameObject?.fileID || null;
}

/**
 * CanvasScaler 설정 추출
 */
function extractCanvasScalers(objects) {
    const scalers = [];

    for (const [fid, obj] of Object.entries(objects)) {
        if (obj.type !== 'MonoBehaviour') continue;
        const d = obj.data;
        if (!d.m_EditorClassIdentifier || !d.m_EditorClassIdentifier.includes('CanvasScaler')) continue;

        scalers.push({
            fileId: fid,
            uiScaleMode: d.m_UiScaleMode,  // 0=ConstantPixelSize, 1=ScaleWithScreenSize, 2=ConstantPhysicalSize
            referenceResolution: d.m_ReferenceResolution || { x: 1080, y: 1920 },
            screenMatchMode: d.m_ScreenMatchMode,
            matchWidthOrHeight: d.m_MatchWidthOrHeight,
            referencePixelsPerUnit: d.m_ReferencePixelsPerUnit
        });
    }

    return scalers;
}

/**
 * Canvas 설정 추출
 */
function extractCanvases(objects) {
    const canvases = [];

    for (const [fid, obj] of Object.entries(objects)) {
        if (obj.type !== 'Canvas') continue;
        const d = obj.data;
        const goName = d.m_GameObject?.fileID ? getGameObjectName(objects, d.m_GameObject.fileID) : 'unknown';

        canvases.push({
            fileId: fid,
            gameObject: goName,
            renderMode: d.m_RenderMode,  // 0=ScreenSpace-Overlay, 1=ScreenSpace-Camera, 2=WorldSpace
            sortingOrder: d.m_SortingOrder || 0,
            pixelPerfect: d.m_PixelPerfect || 0
        });
    }

    return canvases;
}

/**
 * MonoBehaviour (커스텀 스크립트) 추출
 */
function extractMonoBehaviours(objects) {
    const scripts = [];

    for (const [fid, obj] of Object.entries(objects)) {
        if (obj.type !== 'MonoBehaviour') continue;
        const d = obj.data;

        // Unity 내장 컴포넌트 스킵
        if (d.m_EditorClassIdentifier && (
            d.m_EditorClassIdentifier.includes('UnityEngine.UI') ||
            d.m_EditorClassIdentifier.includes('UnityEngine.EventSystems') ||
            d.m_EditorClassIdentifier.includes('TMPro')
        )) continue;

        const scriptRef = d.m_Script;
        const goRef = d.m_GameObject;
        const goName = goRef?.fileID ? getGameObjectName(objects, goRef.fileID) : 'unknown';

        // SerializeField 참조 추출 (fileID가 있는 필드들)
        const serializedRefs = [];
        for (const [key, val] of Object.entries(d)) {
            if (key.startsWith('m_') || key === 'serializedVersion') continue;
            if (val && typeof val === 'object' && val.fileID && val.fileID !== '0') {
                const refName = getGameObjectName(objects, val.fileID);
                serializedRefs.push({ field: key, ref: refName, fileID: val.fileID });
            }
        }

        // 클래스명 추출
        let className = 'unknown';
        if (d.m_EditorClassIdentifier) {
            const parts = d.m_EditorClassIdentifier.split('::');
            className = parts[parts.length - 1] || 'unknown';
        }

        if (className === 'unknown' && serializedRefs.length === 0) continue;

        scripts.push({
            fileId: fid,
            gameObject: goName,
            className,
            scriptGuid: scriptRef?.guid || null,
            serializedRefs
        });
    }

    return scripts;
}

/**
 * GameObject 계층구조 추출
 */
function extractHierarchy(objects) {
    const gameObjects = [];

    for (const [fid, obj] of Object.entries(objects)) {
        if (obj.type !== 'GameObject') continue;
        const d = obj.data;

        const components = [];
        if (d.m_Component) {
            // m_Component는 Unity 특수 형식이라 직접 파싱 안 될 수 있음
            // 대신 objects를 순회하며 m_GameObject가 이 GO를 가리키는 것 찾기
        }

        // 이 GO에 붙은 컴포넌트 찾기
        for (const [cid, cobj] of Object.entries(objects)) {
            if (cobj.data?.m_GameObject?.fileID === fid) {
                components.push({
                    type: cobj.type,
                    fileId: cid
                });
            }
        }

        gameObjects.push({
            fileId: fid,
            name: d.m_Name || `GO_${fid}`,
            tag: d.m_TagString || 'Untagged',
            layer: d.m_Layer || 0,
            isActive: d.m_IsActive !== undefined ? d.m_IsActive : 1,
            components: components.map(c => c.type)
        });
    }

    return gameObjects;
}

// ============================================================
// File Scanner
// ============================================================

function findUnityFiles(projectPath) {
    const result = { scenes: [], prefabs: [] };

    function walk(dir) {
        let entries;
        try { entries = fs.readdirSync(dir); } catch { return; }

        for (const entry of entries) {
            const full = path.join(dir, entry);
            try {
                const stat = fs.statSync(full);
                if (stat.isDirectory()) {
                    // Skip Library, Temp, obj, Packages
                    if (['Library', 'Temp', 'obj', 'Packages', '.git', 'Logs'].includes(entry)) continue;
                    walk(full);
                } else if (entry.endsWith('.unity')) {
                    result.scenes.push(full);
                } else if (entry.endsWith('.prefab')) {
                    result.prefabs.push(full);
                }
            } catch { continue; }
        }
    }

    walk(projectPath);
    return result;
}

// ============================================================
// Main Parser
// ============================================================

function parseUnityFile(filePath, projectName, genre) {
    const content = fs.readFileSync(filePath, 'utf-8');
    const isScene = filePath.endsWith('.unity');
    const fileName = path.basename(filePath);
    const relativePath = filePath; // keep absolute for reference

    const objects = parseUnityYAML(content);
    const objectCount = Object.keys(objects).length;

    if (objectCount === 0) return null;

    const rectTransforms = extractRectTransforms(objects);
    const canvasScalers = extractCanvasScalers(objects);
    const canvases = extractCanvases(objects);
    const monoBehaviours = extractMonoBehaviours(objects);
    const hierarchy = extractHierarchy(objects);

    // UI 레이아웃 요약
    const uiSummary = rectTransforms
        .filter(r => r.gameObject !== 'unknown' && r.gameObject !== 'Canvas')
        .map(r => ({
            name: r.gameObject,
            parent: r.parent,
            anchor: `(${r.anchorMin.x},${r.anchorMin.y})-(${r.anchorMax.x},${r.anchorMax.y})`,
            pivot: `(${r.pivot.x},${r.pivot.y})`,
            size: `${r.sizeDelta.x}x${r.sizeDelta.y}`
        }));

    return {
        configId: `${projectName}__${isScene ? 'scene' : 'prefab'}__${path.parse(fileName).name}`,
        project: projectName,
        genre,
        type: isScene ? 'scene' : 'prefab',
        fileName,
        filePath: relativePath,
        objectCount,
        parsedAt: new Date().toISOString(),

        canvas: {
            count: canvases.length,
            configs: canvases,
            scalers: canvasScalers
        },

        rectTransforms: {
            count: rectTransforms.length,
            items: rectTransforms
        },

        scripts: {
            count: monoBehaviours.length,
            items: monoBehaviours
        },

        hierarchy: {
            gameObjectCount: hierarchy.length,
            items: hierarchy.slice(0, 100),  // 대형 씬은 100개로 제한
            tags: [...new Set(hierarchy.map(h => h.tag).filter(t => t !== 'Untagged'))]
        },

        ui_layout_summary: uiSummary
    };
}

// ============================================================
// Database Manager
// ============================================================

function saveToLocal(data, dbPath) {
    const dir = path.join(dbPath, 'unity_configs', data.project.toLowerCase(), data.type);
    const filesDir = path.join(dir, 'files');

    if (!fs.existsSync(filesDir)) {
        fs.mkdirSync(filesDir, { recursive: true });
    }

    // Save detail file
    const filePath = path.join(filesDir, `${data.configId.replace(/[^a-zA-Z0-9_-]/g, '_')}.json`);
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');

    // Update index
    const indexPath = path.join(dir, 'index.json');
    let index = [];
    if (fs.existsSync(indexPath)) {
        try { index = JSON.parse(fs.readFileSync(indexPath, 'utf-8')); } catch { index = []; }
    }

    index = index.filter(e => e.configId !== data.configId);
    index.push({
        configId: data.configId,
        project: data.project,
        genre: data.genre,
        type: data.type,
        fileName: data.fileName,
        objectCount: data.objectCount,
        canvasCount: data.canvas.count,
        rectTransformCount: data.rectTransforms.count,
        scriptCount: data.scripts.count,
        gameObjectCount: data.hierarchy.gameObjectCount,
        canvasScaler: data.canvas.scalers.length > 0 ? data.canvas.scalers[0] : null
    });

    fs.writeFileSync(indexPath, JSON.stringify(index, null, 2), 'utf-8');
}

async function saveToMongo(data) {
    try {
        const dbClient = require('./lib/db-client');
        await dbClient.connect();
        const col = await dbClient.getCollection('unity_configs');
        await col.updateOne(
            { configId: data.configId },
            { $set: { ...data, updatedAt: new Date() } },
            { upsert: true }
        );
    } catch (e) {
        console.error(`  MongoDB save failed: ${e.message}`);
    }
}

// ============================================================
// Main
// ============================================================

async function main() {
    const args = process.argv.slice(2);

    if (args.length < 2) {
        console.log(`
Usage: node unity-config-parser.js <project_path> <genre> [options]

Arguments:
  project_path   Unity project root (contains Assets/)
  genre          RPG, Idle, Puzzle, Casual, etc.

Options:
  --project <name>   Project name (default: folder name)
  --db <path>        Local DB path (default: E:/AI/db)
  --mongo            Enable MongoDB storage
  --scenes-only      Parse only .unity scene files
  --prefabs-only     Parse only .prefab files
  --max-prefabs <n>  Limit prefab parsing (for large projects)

Examples:
  node unity-config-parser.js "E:/AI_WORK_FLOW_TEST/DropCat" Puzzle --project DropCat --mongo
  node unity-config-parser.js "E:/AIMED/Luffy_Modify/Project" Idle --project IdleMoney --max-prefabs 50
`);
        process.exit(1);
    }

    const projectPath = args[0];
    const genre = args[1];
    let projectName = path.basename(projectPath);
    let dbPath = 'E:/AI/db';
    let mongoEnabled = false;
    let scenesOnly = false;
    let prefabsOnly = false;
    let maxPrefabs = Infinity;
    let resumeMode = false;

    for (let i = 2; i < args.length; i++) {
        if (args[i] === '--project' && args[i + 1]) { projectName = args[++i]; }
        else if (args[i] === '--db' && args[i + 1]) { dbPath = args[++i]; }
        else if (args[i] === '--mongo') { mongoEnabled = true; }
        else if (args[i] === '--scenes-only') { scenesOnly = true; }
        else if (args[i] === '--prefabs-only') { prefabsOnly = true; }
        else if (args[i] === '--max-prefabs' && args[i + 1]) { maxPrefabs = parseInt(args[++i]); }
        else if (args[i] === '--resume') { resumeMode = true; }
    }

    // In resume mode, load existing configIds from MongoDB to skip already-parsed files
    let existingIds = new Set();
    if (resumeMode && mongoEnabled) {
        try {
            const dbClient = require('./lib/db-client');
            await dbClient.connect();
            const col = await dbClient.getCollection('unity_configs');
            const docs = await col.find({ project: projectName }, { projection: { configId: 1 } }).toArray();
            existingIds = new Set(docs.map(d => d.configId));
            console.log(`Resume mode: ${existingIds.size} entries already in MongoDB, will skip them`);
        } catch (e) {
            console.error(`Resume mode init failed: ${e.message}`);
        }
    }

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Unity Config Parser v1.0`);
    console.log(`${'='.repeat(60)}`);
    console.log(`Project:  ${projectName} (${genre})`);
    console.log(`Path:     ${projectPath}`);
    console.log(`DB:       ${dbPath}`);
    console.log(`MongoDB:  ${mongoEnabled ? 'enabled' : 'disabled'}`);
    console.log(`${'='.repeat(60)}\n`);

    // Find files
    const files = findUnityFiles(projectPath);
    console.log(`Found: ${files.scenes.length} scenes, ${files.prefabs.length} prefabs`);

    const stats = {
        scenes: { total: 0, parsed: 0, failed: 0 },
        prefabs: { total: 0, parsed: 0, failed: 0 },
        totalRectTransforms: 0,
        totalScripts: 0,
        totalCanvases: 0
    };

    // Parse scenes
    if (!prefabsOnly) {
        console.log(`\n--- Parsing Scenes ---`);
        for (const scenePath of files.scenes) {
            stats.scenes.total++;
            const fileName = path.basename(scenePath);
            process.stdout.write(`  ${fileName}... `);

            try {
                const result = parseUnityFile(scenePath, projectName, genre);
                if (result) {
                    saveToLocal(result, dbPath);
                    if (mongoEnabled) await saveToMongo(result);
                    stats.scenes.parsed++;
                    stats.totalRectTransforms += result.rectTransforms.count;
                    stats.totalScripts += result.scripts.count;
                    stats.totalCanvases += result.canvas.count;
                    console.log(`OK (${result.objectCount} objects, ${result.rectTransforms.count} UI, ${result.scripts.count} scripts)`);
                } else {
                    stats.scenes.failed++;
                    console.log('SKIP (empty)');
                }
            } catch (e) {
                stats.scenes.failed++;
                console.log(`FAIL: ${e.message}`);
            }
        }
    }

    // Parse prefabs
    if (!scenesOnly) {
        const prefabsToParse = files.prefabs.slice(0, maxPrefabs);
        console.log(`\n--- Parsing Prefabs (${prefabsToParse.length}/${files.prefabs.length}) ---`);

        let skippedCount = 0;
        for (const prefabPath of prefabsToParse) {
            stats.prefabs.total++;
            const fileName = path.basename(prefabPath);

            // Resume mode: skip already-parsed files
            if (resumeMode) {
                const candidateId = `${projectName}__prefab__${path.parse(fileName).name}`;
                if (existingIds.has(candidateId)) {
                    skippedCount++;
                    if (skippedCount % 5000 === 0) console.log(`  Skipped: ${skippedCount} already-parsed prefabs...`);
                    continue;
                }
            }

            try {
                const result = parseUnityFile(prefabPath, projectName, genre);
                if (result) {
                    saveToLocal(result, dbPath);
                    if (mongoEnabled) await saveToMongo(result);
                    stats.prefabs.parsed++;
                    stats.totalRectTransforms += result.rectTransforms.count;
                    stats.totalScripts += result.scripts.count;

                    if (stats.prefabs.parsed % 50 === 0) {
                        console.log(`  Parsed: ${stats.prefabs.parsed} prefabs...`);
                    }
                } else {
                    stats.prefabs.failed++;
                }
            } catch (e) {
                stats.prefabs.failed++;
            }
        }
        if (resumeMode && skippedCount > 0) {
            console.log(`  Skipped (resume): ${skippedCount}`);
        }
        console.log(`  Prefabs complete: ${stats.prefabs.parsed} parsed, ${stats.prefabs.failed} failed`);
    }

    // Summary
    console.log(`\n${'='.repeat(60)}`);
    console.log(`RESULTS`);
    console.log(`${'='.repeat(60)}`);
    console.log(`Scenes:           ${stats.scenes.parsed}/${stats.scenes.total}`);
    console.log(`Prefabs:          ${stats.prefabs.parsed}/${stats.prefabs.total}`);
    console.log(`RectTransforms:   ${stats.totalRectTransforms}`);
    console.log(`Canvas:           ${stats.totalCanvases}`);
    console.log(`Custom Scripts:   ${stats.totalScripts}`);
    console.log(`${'='.repeat(60)}`);

    if (mongoEnabled) {
        try {
            const dbClient = require('./lib/db-client');
            await dbClient.close();
        } catch { }
    }
}

main().catch(e => { console.error(e); process.exit(1); });
