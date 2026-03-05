#!/usr/bin/env node
/**
 * DB Search CLI - Base/Expert Code DB 검색 자동화
 * 5단계 우선순위 검색 + 유사도 스코어링
 *
 * Usage:
 *   node db-search.js --genre Rpg --role Manager --system Battle
 *   node db-search.js --genre Rpg --role UX --provides "void PlayEffect" --json
 *   node db-search.js --genre Idle --role Manager --top 3
 */

const fs = require('fs');
const path = require('path');

// Shared libraries
const { applyHybridScoring, getSearchModeInfo } = require('./lib/search-strategy');

// ============================================================
// Configuration
// ============================================================

const DB_ROOT = process.env.DB_ROOT || 'E:/AI/db';
const DEFAULT_TOP_N = 5;

const GENRES = ['generic', 'rpg', 'idle', 'merge', 'slg', 'tycoon', 'simulation', 'puzzle', 'playable'];
const LAYERS = ['core', 'domain', 'game'];

// ============================================================
// CLI Argument Parsing
// ============================================================

function parseArgs(argv) {
    const args = {
        genre: null,
        role: null,
        system: null,
        provides: null,
        layer: null,
        topN: DEFAULT_TOP_N,
        json: false,
    };

    for (let i = 0; i < argv.length; i++) {
        switch (argv[i]) {
            case '--genre': args.genre = argv[++i]; break;
            case '--role': args.role = argv[++i]; break;
            case '--system': args.system = argv[++i]; break;
            case '--provides': args.provides = argv[++i]; break;
            case '--layer': args.layer = argv[++i]; break;
            case '--top': args.topN = parseInt(argv[++i]) || DEFAULT_TOP_N; break;
            case '--json': args.json = true; break;
            case '--help': case '-h': printUsage(); process.exit(0);
        }
    }

    return args;
}

function printUsage() {
    console.log(`
DB Search CLI - Base/Expert Code DB 검색

Usage:
  node db-search.js --genre <genre> [options]

Options:
  --genre <genre>      장르 (필수): Rpg, Idle, Merge, SLG, Tycoon, Simulation, Puzzle, Generic
  --role <role>        Role 필터: Manager, Controller, UX, Handler, etc.
  --system <system>    System 필터: Battle, Inventory, Quest, etc.
  --provides <sig>     provides 시그니처 검색 (부분 일치)
  --layer <layer>      Layer 필터: Core, Domain, Game
  --top <n>            상위 N개 결과 (기본: 5)
  --json               JSON 출력 (에이전트용)
  --help, -h           도움말

Examples:
  node db-search.js --genre Rpg --role Manager --system Battle
  node db-search.js --genre Idle --role UX --json
  node db-search.js --genre Generic --role Helper --top 3
`);
}

// ============================================================
// Index Loading
// ============================================================

function loadIndex(indexPath) {
    try {
        if (!fs.existsSync(indexPath)) return [];
        const data = fs.readFileSync(indexPath, 'utf-8');
        return JSON.parse(data);
    } catch (e) {
        return [];
    }
}

function loadFileDetail(filePath) {
    try {
        if (!fs.existsSync(filePath)) return null;
        const data = fs.readFileSync(filePath, 'utf-8');
        return JSON.parse(data);
    } catch (e) {
        return null;
    }
}

// ============================================================
// Search Functions
// ============================================================

/**
 * 5단계 우선순위 검색
 * 1. Expert DB (해당 장르)
 * 2. Expert DB (Generic)
 * 3. Genre Base DB
 * 4. Generic Base DB
 * 5. 없음
 */
function searchAll(args) {
    const results = [];
    const genre = args.genre ? args.genre.toLowerCase() : 'generic';

    // Step 1: Expert DB (해당 장르)
    const expertEntries = loadIndex(path.join(DB_ROOT, 'expert', 'index.json'));
    const expertGenre = expertEntries.filter(e =>
        e.genre && e.genre.toLowerCase() === genre && (e.score || 0) >= 0.6
    );
    for (const entry of expertGenre) {
        results.push({ ...entry, source: 'Expert', priority: 1 });
    }

    // Step 2: Expert DB (Generic)
    if (genre !== 'generic') {
        const expertGeneric = expertEntries.filter(e =>
            e.genre && e.genre.toLowerCase() === 'generic' && (e.score || 0) >= 0.6
        );
        for (const entry of expertGeneric) {
            results.push({ ...entry, source: 'Expert(Generic)', priority: 2 });
        }
    }

    // Step 3: Genre Base DB
    for (const layer of LAYERS) {
        const indexPath = path.join(DB_ROOT, 'base', genre, layer, 'index.json');
        const entries = loadIndex(indexPath);
        for (const entry of entries) {
            results.push({ ...entry, source: `Base(${genre}/${layer})`, priority: 3 });
        }
    }

    // Step 4: Generic Base DB
    if (genre !== 'generic') {
        for (const layer of LAYERS) {
            const indexPath = path.join(DB_ROOT, 'base', 'generic', layer, 'index.json');
            const entries = loadIndex(indexPath);
            for (const entry of entries) {
                results.push({ ...entry, source: `Base(generic/${layer})`, priority: 4 });
            }
        }
    }

    return results;
}

// ============================================================
// Scoring
// ============================================================

function calculateScore(entry, args) {
    let score = 0;

    // Role 일치: +0.3
    if (args.role && entry.role) {
        if (entry.role.toLowerCase() === args.role.toLowerCase()) {
            score += 0.3;
        }
    }

    // System 일치: +0.2
    if (args.system && entry.system) {
        if (entry.system.toLowerCase() === args.system.toLowerCase()) {
            score += 0.2;
        } else if (entry.system.toLowerCase().includes(args.system.toLowerCase()) ||
                   args.system.toLowerCase().includes(entry.system.toLowerCase())) {
            score += 0.1; // 부분 일치
        }
    }

    // Layer 일치: bonus +0.05
    if (args.layer && entry.layer) {
        if (entry.layer.toLowerCase() === args.layer.toLowerCase()) {
            score += 0.05;
        }
    }

    // provides 유사도: +0.3
    if (args.provides && entry.provides && entry.provides.length > 0) {
        const searchTerm = args.provides.toLowerCase();
        const matchCount = entry.provides.filter(p =>
            p.toLowerCase().includes(searchTerm)
        ).length;
        if (matchCount > 0) {
            score += 0.3 * Math.min(matchCount / entry.provides.length, 1);
        }
    }

    // 우선순위 보너스 (Expert > Base)
    score += (5 - entry.priority) * 0.05;

    // DB 신뢰도 점수 반영
    if (entry.score) {
        score += entry.score * 0.1;
    }

    return score;
}

function filterAndRank(results, args) {
    // 필터링
    let filtered = results;

    if (args.role) {
        const roleMatched = filtered.filter(e =>
            e.role && e.role.toLowerCase() === args.role.toLowerCase()
        );
        // Role 일치가 있으면 그것만, 없으면 전체에서 스코어링
        if (roleMatched.length > 0) {
            filtered = roleMatched;
        }
    }

    if (args.layer) {
        const layerMatched = filtered.filter(e =>
            e.layer && e.layer.toLowerCase() === args.layer.toLowerCase()
        );
        if (layerMatched.length > 0) {
            filtered = layerMatched;
        }
    }

    // 하이브리드 스코어링 (DB 규모에 따라 자동 전환)
    const scored = applyHybridScoring(filtered, args, calculateScore);

    // 정렬: matchScore 내림차순 → priority 오름차순
    scored.sort((a, b) => {
        if (b.matchScore !== a.matchScore) return b.matchScore - a.matchScore;
        return (a.priority || 4) - (b.priority || 4);
    });

    // 중복 fileId 제거 (높은 점수 유지)
    const seen = new Set();
    const unique = [];
    for (const entry of scored) {
        if (!seen.has(entry.fileId)) {
            seen.add(entry.fileId);
            unique.push(entry);
        }
    }

    return unique.slice(0, args.topN);
}

// ============================================================
// Detail Loading
// ============================================================

function loadDetail(entry) {
    const genre = entry.genre ? entry.genre.toLowerCase() : 'generic';
    const layer = entry.layer ? entry.layer.toLowerCase() : 'domain';

    // Expert DB에서 먼저 시도
    if (entry.source && entry.source.startsWith('Expert')) {
        const expertPath = path.join(DB_ROOT, 'expert', 'files', `${entry.fileId}.json`);
        const detail = loadFileDetail(expertPath);
        if (detail) return detail;
    }

    // Base DB에서 시도
    const basePath = path.join(DB_ROOT, 'base', genre, layer, 'files', `${entry.fileId}.json`);
    const detail = loadFileDetail(basePath);
    if (detail) return detail;

    return null;
}

// ============================================================
// Output Formatting
// ============================================================

function formatPretty(results, args) {
    if (results.length === 0) {
        console.log('\n검색 결과 없음.');
        console.log(`조건: genre=${args.genre || 'any'}, role=${args.role || 'any'}, system=${args.system || 'any'}`);
        console.log('→ AI_기획서 기반으로 새로 생성하세요. (우선순위 5)\n');
        return;
    }

    const modeInfo = getSearchModeInfo(results.length > 0 ? (results[0]._candidateCount || 0) : 0);
    console.log(`\n${'='.repeat(60)}`);
    console.log(`DB 검색 결과 (상위 ${results.length}건)`);
    console.log(`조건: genre=${args.genre || 'any'}, role=${args.role || 'any'}, system=${args.system || 'any'}`);
    console.log(`검색 모드: ${modeInfo.reason}`);
    console.log(`${'='.repeat(60)}\n`);

    for (let i = 0; i < results.length; i++) {
        const r = results[i];
        console.log(`[${i + 1}] ${r.fileId}`);
        const scoreDetail = r._searchMode === 'hybrid'
            ? ` (structured: ${r._structuredScore}, cosine: ${r._cosineScore})`
            : '';
        console.log(`    Source: ${r.source} | Score: ${r.matchScore.toFixed(2)}${scoreDetail} | DB Score: ${r.score || 0.4}`);
        console.log(`    Layer: ${r.layer} | Genre: ${r.genre} | Role: ${r.role} | System: ${r.system || '-'}`);

        if (r.provides && r.provides.length > 0) {
            console.log(`    Provides: ${r.provides.slice(0, 3).join(', ')}${r.provides.length > 3 ? '...' : ''}`);
        }
        if (r.requires && r.requires.length > 0) {
            console.log(`    Requires: ${r.requires.slice(0, 3).join(', ')}${r.requires.length > 3 ? '...' : ''}`);
        }

        // 상세 정보 로드
        const detail = loadDetail(r);
        if (detail) {
            if (detail.filePath) {
                console.log(`    FilePath: ${detail.filePath}`);
            }
            if (detail.classes && detail.classes.length > 0) {
                const cls = detail.classes[0];
                if (cls.baseClass) console.log(`    BaseClass: ${cls.baseClass}`);
                const publicMethods = (cls.methods || []).filter(m => m.accessModifier === 'public');
                if (publicMethods.length > 0) {
                    console.log(`    Public Methods (${publicMethods.length}): ${publicMethods.slice(0, 3).map(m => m.methodName).join(', ')}${publicMethods.length > 3 ? '...' : ''}`);
                }
            }
        }

        console.log('');
    }
}

function formatJson(results) {
    const modeInfo = getSearchModeInfo(results.length > 0 ? (results[0]._candidateCount || 0) : 0);
    const output = {
        count: results.length,
        searchMode: modeInfo,
        results: results.map(r => {
            const detail = loadDetail(r);
            return {
                fileId: r.fileId,
                source: r.source,
                matchScore: parseFloat(r.matchScore.toFixed(3)),
                dbScore: r.score || 0.4,
                layer: r.layer,
                genre: r.genre,
                role: r.role,
                system: r.system || null,
                provides: r.provides || [],
                requires: r.requires || [],
                detail: detail ? {
                    filePath: detail.filePath || null,
                    namespace: detail.namespace || null,
                    baseClass: detail.classes?.[0]?.baseClass || null,
                    publicMethods: (detail.classes?.[0]?.methods || [])
                        .filter(m => m.accessModifier === 'public')
                        .map(m => m.signature || m.methodName),
                    fields: (detail.classes?.[0]?.fields || [])
                        .filter(f => f.hasSerializeField || f.accessModifier === 'public')
                        .map(f => `${f.fieldType} ${f.fieldName}`),
                } : null
            };
        })
    };

    console.log(JSON.stringify(output, null, 2));
}

// ============================================================
// Main
// ============================================================

function main() {
    const args = parseArgs(process.argv.slice(2));

    if (!args.genre && !args.role && !args.system) {
        printUsage();
        process.exit(1);
    }

    // 검색
    const allResults = searchAll(args);

    // 필터링 및 랭킹
    const ranked = filterAndRank(allResults, args);

    // 출력
    if (args.json) {
        formatJson(ranked);
    } else {
        formatPretty(ranked, args);
    }
}

main();
