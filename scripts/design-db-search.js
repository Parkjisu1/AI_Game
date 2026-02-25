#!/usr/bin/env node
/**
 * Design DB Search CLI - Base/Expert Design DB 검색 자동화
 * 5단계 우선순위 검색 + 유사도 스코어링
 *
 * Usage:
 *   node design-db-search.js --genre rpg --domain InGame --system "전투 > 데미지"
 *   node design-db-search.js --genre idle --domain Balance --data_type formula --json
 *   node design-db-search.js --genre generic --domain BM --top 3
 *   node design-db-search.js --genre rpg --min-score 0.6 --project MyGame
 */

const fs = require('fs');
const path = require('path');

// Shared libraries
const { normalizeDomain } = require('./lib/domain-utils');

// ============================================================
// Configuration
// ============================================================

const DESIGN_DB_ROOT = process.env.DESIGN_DB_ROOT || 'E:/AI/db/design';
const DEFAULT_TOP_N = 5;

const GENRES = ['generic', 'rpg', 'idle', 'merge', 'slg', 'tycoon', 'simulation', 'puzzle', 'casual'];
const DOMAINS = ['ingame', 'outgame', 'balance', 'content', 'bm', 'liveops', 'ux', 'social', 'meta', 'projects'];

// Source preference scores
const SOURCE_SCORES = {
    'internal_original': 0.1,
    'internal_produced': 0.05,
    'observed': 0.02,
};

// ============================================================
// CLI Argument Parsing
// ============================================================

function parseArgs(argv) {
    const args = {
        genre: null,
        domain: null,
        system: null,
        data_type: null,
        balance_area: null,
        topN: DEFAULT_TOP_N,
        json: false,
        minScore: null,
        project: null,
    };

    for (let i = 0; i < argv.length; i++) {
        switch (argv[i]) {
            case '--genre':       args.genre = argv[++i]; break;
            case '--domain':      args.domain = argv[++i]; break;
            case '--system':      args.system = argv[++i]; break;
            case '--data_type':   args.data_type = argv[++i]; break;
            case '--balance_area': args.balance_area = argv[++i]; break;
            case '--top':         args.topN = parseInt(argv[++i]) || DEFAULT_TOP_N; break;
            case '--json':        args.json = true; break;
            case '--min-score':   args.minScore = parseFloat(argv[++i]); break;
            case '--project':     args.project = argv[++i]; break;
            case '--help': case '-h': printUsage(); process.exit(0);
        }
    }

    return args;
}

function printUsage() {
    console.log(`
Design DB Search CLI - Base/Expert Design DB 검색

Usage:
  node design-db-search.js --genre <genre> [options]

Options:
  --genre <genre>            장르 (권장): rpg, idle, merge, slg, tycoon, simulation, puzzle, casual, generic
  --domain <domain>          도메인 필터: InGame, OutGame, Balance, Content, BM, LiveOps, UX, Social, Meta, Projects
  --system <system>          시스템 필터 (부분 일치): "전투 > 데미지", "가챠", etc.
  --data_type <type>         데이터 타입 필터: formula, table, flow, config, spec, etc.
  --balance_area <area>      밸런스 영역 필터: "전투 밸런스", "경제 밸런스", etc.
  --top <n>                  상위 N개 결과 (기본: 5)
  --min-score <float>        최소 DB 신뢰도 점수 필터 (e.g. 0.6)
  --project <name>           프로젝트 이름 필터
  --json                     JSON 출력 (에이전트용)
  --help, -h                 도움말

Examples:
  node design-db-search.js --genre rpg --domain InGame --system "전투"
  node design-db-search.js --genre idle --domain Balance --data_type formula --json
  node design-db-search.js --genre generic --domain BM --top 3
  node design-db-search.js --genre rpg --min-score 0.6 --project MyGame
`);
}

// ============================================================
// Index Loading
// ============================================================

function loadIndex(indexPath) {
    try {
        if (!fs.existsSync(indexPath)) return [];
        const data = fs.readFileSync(indexPath, 'utf-8');
        const parsed = JSON.parse(data);
        return Array.isArray(parsed) ? parsed : [];
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
    const genre = args.genre ? args.genre.toLowerCase() : null;
    const domainDir = args.domain ? normalizeDomain(args.domain) : null;

    // Step 1: Expert DB (해당 장르)
    const expertEntries = loadIndex(path.join(DESIGN_DB_ROOT, 'expert', 'index.json'));
    const expertGenre = expertEntries.filter(e => {
        if (!genre) return (e.score || 0) >= 0.6;
        return e.genre && e.genre.toLowerCase() === genre && (e.score || 0) >= 0.6;
    });
    for (const entry of expertGenre) {
        results.push({ ...entry, _source: 'Expert', _priority: 1 });
    }

    // Step 2: Expert DB (Generic) - 장르가 지정된 경우에만 추가 검색
    if (genre && genre !== 'generic') {
        const expertGeneric = expertEntries.filter(e =>
            e.genre && e.genre.toLowerCase() === 'generic' && (e.score || 0) >= 0.6
        );
        for (const entry of expertGeneric) {
            results.push({ ...entry, _source: 'Expert(Generic)', _priority: 2 });
        }
    }

    // Step 3: Genre Base DB
    if (genre) {
        const domainsToSearch = domainDir ? [domainDir] : DOMAINS;
        for (const dom of domainsToSearch) {
            const indexPath = path.join(DESIGN_DB_ROOT, 'base', genre, dom, 'index.json');
            const entries = loadIndex(indexPath);
            for (const entry of entries) {
                results.push({ ...entry, _source: `Base(${genre}/${dom})`, _priority: 3 });
            }
        }
    }

    // Step 4: Generic Base DB
    if (genre && genre !== 'generic') {
        const domainsToSearch = domainDir ? [domainDir] : DOMAINS;
        for (const dom of domainsToSearch) {
            const indexPath = path.join(DESIGN_DB_ROOT, 'base', 'generic', dom, 'index.json');
            const entries = loadIndex(indexPath);
            for (const entry of entries) {
                results.push({ ...entry, _source: `Base(generic/${dom})`, _priority: 4 });
            }
        }
    }

    // Step 5: 장르가 없는 경우 전체 Base DB 검색
    if (!genre) {
        for (const g of GENRES) {
            const domainsToSearch = domainDir ? [domainDir] : DOMAINS;
            for (const dom of domainsToSearch) {
                const indexPath = path.join(DESIGN_DB_ROOT, 'base', g, dom, 'index.json');
                const entries = loadIndex(indexPath);
                for (const entry of entries) {
                    results.push({ ...entry, _source: `Base(${g}/${dom})`, _priority: 4 });
                }
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

    // Domain 정확 일치: +0.3
    // Use normalizeDomain() to handle stored "combat"/"economy" aliases
    if (args.domain && entry.domain) {
        const searchDomain = normalizeDomain(args.domain);
        const entryDomain = normalizeDomain(entry.domain);
        if (entryDomain === searchDomain) {
            score += 0.3;
        }
    }

    // System 부분 일치: +0.1
    if (args.system && entry.system) {
        const searchSys = args.system.toLowerCase();
        const entrySys = entry.system.toLowerCase();
        if (entrySys === searchSys) {
            score += 0.1;
        } else if (entrySys.includes(searchSys) || searchSys.includes(entrySys)) {
            score += 0.05; // 부분 일치
        }
    }

    // Source 선호도
    if (entry.source) {
        score += SOURCE_SCORES[entry.source] || 0;
    }

    // data_type 일치: +0.1
    if (args.data_type && entry.data_type) {
        if (entry.data_type.toLowerCase() === args.data_type.toLowerCase()) {
            score += 0.1;
        }
    }

    // balance_area 부분 일치: +0.05
    if (args.balance_area && entry.balance_area) {
        if (entry.balance_area.toLowerCase().includes(args.balance_area.toLowerCase())) {
            score += 0.05;
        }
    }

    // 우선순위 보너스 (Expert > Base)
    score += (5 - (entry._priority || 4)) * 0.05;

    // DB 신뢰도 점수 반영
    if (entry.score) {
        score += entry.score * 0.1;
    }

    return score;
}

function filterAndRank(results, args) {
    let filtered = results;

    // Domain 필터링 (use normalizeDomain for stored alias compatibility)
    if (args.domain) {
        const searchDomain = normalizeDomain(args.domain);
        const domainMatched = filtered.filter(e =>
            e.domain && normalizeDomain(e.domain) === searchDomain
        );
        if (domainMatched.length > 0) {
            filtered = domainMatched;
        }
    }

    // data_type 필터링
    if (args.data_type) {
        const typeMatched = filtered.filter(e =>
            e.data_type && e.data_type.toLowerCase() === args.data_type.toLowerCase()
        );
        if (typeMatched.length > 0) {
            filtered = typeMatched;
        }
    }

    // --min-score 필터링
    if (args.minScore !== null && !isNaN(args.minScore)) {
        filtered = filtered.filter(e => (e.score || 0) >= args.minScore);
    }

    // --project 필터링
    if (args.project) {
        const projectLower = args.project.toLowerCase();
        const projectMatched = filtered.filter(e =>
            e.project && e.project.toLowerCase() === projectLower
        );
        if (projectMatched.length > 0) {
            filtered = projectMatched;
        }
    }

    // 스코어링
    const scored = filtered.map(entry => ({
        ...entry,
        matchScore: calculateScore(entry, args)
    }));

    // 정렬: matchScore 내림차순 → priority 오름차순
    scored.sort((a, b) => {
        if (b.matchScore !== a.matchScore) return b.matchScore - a.matchScore;
        return (a._priority || 4) - (b._priority || 4);
    });

    // 중복 designId 제거 (높은 점수 유지)
    const seen = new Set();
    const unique = [];
    for (const entry of scored) {
        if (!seen.has(entry.designId)) {
            seen.add(entry.designId);
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
    const domainDir = normalizeDomain(entry.domain) || 'ingame';

    // Expert DB에서 먼저 시도
    if (entry._source && entry._source.startsWith('Expert')) {
        const expertPath = path.join(DESIGN_DB_ROOT, 'expert', 'files', `${entry.designId}.json`);
        const detail = loadFileDetail(expertPath);
        if (detail) return detail;
    }

    // Base DB에서 시도
    const basePath = path.join(DESIGN_DB_ROOT, 'base', genre, domainDir, 'files', `${entry.designId}.json`);
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
        console.log(`조건: genre=${args.genre || 'any'}, domain=${args.domain || 'any'}, system=${args.system || 'any'}`);
        if (args.minScore !== null) console.log(`     min-score=${args.minScore}`);
        if (args.project)           console.log(`     project=${args.project}`);
        console.log('→ AI_기획서 기반으로 새로 생성하세요. (우선순위 5)\n');
        return;
    }

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Design DB 검색 결과 (상위 ${results.length}건)`);
    console.log(`조건: genre=${args.genre || 'any'}, domain=${args.domain || 'any'}, system=${args.system || 'any'}`);
    if (args.minScore !== null) console.log(`     min-score=${args.minScore}`);
    if (args.project)           console.log(`     project=${args.project}`);
    console.log(`${'='.repeat(60)}\n`);

    for (let i = 0; i < results.length; i++) {
        const r = results[i];
        console.log(`[${i + 1}] ${r.designId}`);
        console.log(`    Source: ${r._source} | MatchScore: ${r.matchScore.toFixed(2)} | DB Score: ${r.score || 0.4}`);
        console.log(`    Domain: ${r.domain} | Genre: ${r.genre} | System: ${r.system || '-'}`);
        console.log(`    DataType: ${r.data_type || '-'} | BalanceArea: ${r.balance_area || '-'} | Version: ${r.version || '-'}`);
        if (r.project) console.log(`    Project: ${r.project}`);

        if (r.provides && r.provides.length > 0) {
            console.log(`    Provides: ${r.provides.slice(0, 3).join(', ')}${r.provides.length > 3 ? '...' : ''}`);
        }
        if (r.tags && r.tags.length > 0) {
            console.log(`    Tags: ${r.tags.slice(0, 5).join(', ')}`);
        }

        // 상세 정보 로드
        const detail = loadDetail(r);
        if (detail && detail.content) {
            if (detail.content.summary) {
                console.log(`    Summary: ${detail.content.summary.substring(0, 100)}${detail.content.summary.length > 100 ? '...' : ''}`);
            }
        }

        console.log('');
    }
}

function formatJson(results) {
    const output = {
        count: results.length,
        results: results.map(r => {
            const detail = loadDetail(r);
            return {
                designId: r.designId,
                source: r._source,
                matchScore: parseFloat(r.matchScore.toFixed(3)),
                dbScore: r.score || 0.4,
                domain: r.domain,
                genre: r.genre,
                system: r.system || null,
                data_type: r.data_type || null,
                balance_area: r.balance_area || null,
                version: r.version || null,
                project: r.project || null,
                provides: r.provides || [],
                requires: r.requires || [],
                tags: r.tags || [],
                detail: detail ? {
                    summary: detail.content?.summary || null,
                    formula: detail.content?.formula || null,
                    parameters: detail.content?.parameters || null,
                    versions: (detail.versions || []).slice(0, 2),
                    code_mapping: detail.code_mapping || null,
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

    if (!args.genre && !args.domain && !args.system && !args.data_type) {
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
