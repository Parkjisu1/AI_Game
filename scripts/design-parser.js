#!/usr/bin/env node
/**
 * Design Parser - 기획 자료를 Design DB JSON 형식으로 정규화
 * 지원 입력 형식: YAML, CSV, JSON, MD
 *
 * Usage:
 *   node design-parser.js --input <path> --format yaml --genre rpg --project MyGame
 *   node design-parser.js --input E:/AI/designs/battle.yaml --format yaml --genre rpg --project MyGame --output E:/AI/db/design
 *   node design-parser.js --input E:/AI/designs/balance.csv --format csv --genre idle --project IdleQuest
 *
 * C10+ parameter→domain mapping:
 *   progression → Content + Balance
 *   growth      → Balance
 *   equipment   → OutGame + Balance
 *   combat      → InGame + Balance
 *   gacha       → OutGame + BM
 *   economy     → Balance + BM
 *   system      → InGame
 *   visual      → UX
 *   architecture → skip
 */

const fs = require('fs');
const path = require('path');
const { parseYaml } = require('./lib/yaml-utils');
const { ensureDir, upsertIndex } = require('./lib/safe-io');
const { normalizeDomain, displayDomain, displayGenre } = require('./lib/domain-utils');
const dbClient = require('./lib/db-client');

// ============================================================
// Configuration
// ============================================================

const DESIGN_DB_ROOT = process.env.DESIGN_DB_ROOT || 'E:/AI/db/design';

const GENRES = ['generic', 'rpg', 'idle', 'merge', 'slg', 'tycoon', 'simulation', 'puzzle', 'casual'];

const DOMAINS = ['ingame', 'outgame', 'balance', 'content', 'bm', 'liveops', 'ux', 'social', 'meta', 'projects'];

// C10+ parameter → domain mapping
const C10_DOMAIN_MAP = {
    'progression': ['content', 'balance'],
    'growth': ['balance'],
    'equipment': ['outgame', 'balance'],
    'combat': ['ingame', 'balance'],
    'gacha': ['outgame', 'bm'],
    'economy': ['balance', 'bm'],
    'system': ['ingame'],
    'visual': ['ux'],
    'architecture': null, // skip
    // Additional common mappings
    'ui': ['ux'],
    'shop': ['outgame', 'bm'],
    'quest': ['content'],
    'skill': ['ingame'],
    'map': ['ingame'],
    'pvp': ['ingame'],
    'guild': ['social'],
    'event': ['liveops'],
    'season': ['liveops'],
    'achievement': ['content'],
    'leaderboard': ['social'],
    'tutorial': ['ux'],
    'notification': ['liveops'],
};

// Domain name normalization
const DOMAIN_NORMALIZE = {
    'ingame': 'InGame',
    'in_game': 'InGame',
    'in-game': 'InGame',
    'outgame': 'OutGame',
    'out_game': 'OutGame',
    'out-game': 'OutGame',
    'balance': 'Balance',
    'content': 'Content',
    'bm': 'BM',
    'business_model': 'BM',
    'monetization': 'BM',
    'liveops': 'LiveOps',
    'live_ops': 'LiveOps',
    'live-ops': 'LiveOps',
    'ux': 'UX',
    'social': 'Social',
    'meta': 'Meta',
    'projects': 'Projects',
};

// ============================================================
// CLI Argument Parsing
// ============================================================

function parseArgs(argv) {
    const args = {
        input: null,
        format: null,
        genre: 'generic',
        project: null,
        output: DESIGN_DB_ROOT,
        mongoOnly: false,
    };

    for (let i = 0; i < argv.length; i++) {
        switch (argv[i]) {
            case '--input': args.input = argv[++i]; break;
            case '--format': args.format = argv[++i]?.toLowerCase(); break;
            case '--genre': args.genre = argv[++i]?.toLowerCase(); break;
            case '--project': args.project = argv[++i]; break;
            case '--output': args.output = argv[++i]; break;
            case '--mongo-only': args.mongoOnly = true; break;
            case '--help': case '-h': printUsage(); process.exit(0);
        }
    }

    return args;
}

function printUsage() {
    console.log(`
Design Parser - 기획 자료를 Design DB JSON 형식으로 정규화

Usage:
  node design-parser.js --input <path> --format <format> --genre <genre> --project <name> [options]

Required:
  --input <path>       입력 파일 경로 (YAML, CSV, JSON, MD)
  --format <format>    입력 형식: yaml | csv | json | md
  --genre <genre>      장르: rpg, idle, merge, slg, tycoon, simulation, puzzle, casual, generic
  --project <name>     프로젝트명 (designId prefix)

Optional:
  --output <db-path>   Design DB 경로 (기본: E:/AI/db/design)
  --mongo-only         MongoDB에만 저장 (로컬 JSON 파일 쓰기 건너뜀)
  --help, -h           도움말

Output:
  - index.json에 인덱스 엔트리 추가
  - files/{designId}.json에 상세 파일 생성

Examples:
  node design-parser.js --input E:/AI/designs/battle.yaml --format yaml --genre rpg --project MyRPG
  node design-parser.js --input E:/AI/designs/balance.csv --format csv --genre idle --project IdleQuest
  node design-parser.js --input E:/AI/designs/spec.md --format md --genre generic --project Common
`);
}

// ============================================================
// Input Parsers
// ============================================================

/**
 * Parse CSV content into array of objects
 */
function parseCsv(content) {
    content = content.replace(/^\uFEFF/, '');
    const lines = content.split('\n').filter(l => l.trim());
    if (lines.length === 0) return [];

    const headers = parseCsvLine(lines[0]);
    const rows = [];

    for (let i = 1; i < lines.length; i++) {
        const values = parseCsvLine(lines[i]);
        const row = {};
        headers.forEach((h, idx) => {
            row[h.trim()] = values[idx]?.trim() || '';
        });
        rows.push(row);
    }

    return rows;
}

function parseCsvLine(line) {
    const result = [];
    let inQuotes = false;
    let current = '';

    for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') {
            inQuotes = !inQuotes;
        } else if (ch === ',' && !inQuotes) {
            result.push(current);
            current = '';
        } else {
            current += ch;
        }
    }
    result.push(current);
    return result;
}

/**
 * Parse Markdown into structured sections
 */
function parseMd(content) {
    const lines = content.split('\n');
    const sections = [];
    let currentSection = null;
    let currentContent = [];

    for (const rawLine of lines) {
        const line = rawLine.replace(/\r$/, '');

        // H1 or H2 - new section
        const h1Match = line.match(/^# (.+)$/);
        const h2Match = line.match(/^## (.+)$/);
        const h3Match = line.match(/^### (.+)$/);

        if (h1Match) {
            if (currentSection) {
                sections.push({ ...currentSection, content: currentContent.join('\n').trim() });
            }
            currentSection = { title: h1Match[1].trim(), level: 1 };
            currentContent = [];
        } else if (h2Match) {
            if (currentSection) {
                sections.push({ ...currentSection, content: currentContent.join('\n').trim() });
            }
            currentSection = { title: h2Match[1].trim(), level: 2 };
            currentContent = [];
        } else if (h3Match) {
            if (currentSection) {
                sections.push({ ...currentSection, content: currentContent.join('\n').trim() });
            }
            currentSection = { title: h3Match[1].trim(), level: 3 };
            currentContent = [];
        } else {
            currentContent.push(line);
        }
    }

    if (currentSection) {
        sections.push({ ...currentSection, content: currentContent.join('\n').trim() });
    }

    return sections;
}

// ============================================================
// Domain Resolution
// ============================================================

function normalizeDomainName(raw) {
    return displayDomain(normalizeDomain(raw));
}

function resolveDomainFromC10(parameter) {
    if (!parameter) return ['InGame'];
    const lower = parameter.toLowerCase().trim();
    const mapped = C10_DOMAIN_MAP[lower];
    if (mapped === null) return null; // skip
    if (!mapped) return ['InGame']; // default
    return mapped.map(d => normalizeDomainName(d));
}

function inferDomainFromContent(data) {
    // Try to infer domain from various fields
    const text = JSON.stringify(data).toLowerCase();

    const domainScores = {};
    const keywords = {
        'InGame': ['battle', 'combat', 'skill', 'attack', 'damage', 'hit', 'pvp', 'dungeon', 'boss', 'wave', 'combat', '전투', '스킬', '데미지', '공격'],
        'OutGame': ['equipment', 'gear', 'inventory', 'shop', 'store', 'upgrade', 'enhance', 'gacha', '장비', '인벤토리', '상점', '강화', '가챠'],
        'Balance': ['formula', 'value', 'coefficient', 'multiplier', 'stat', 'curve', 'growth', 'progression', '밸런스', '수치', '공식', '성장'],
        'Content': ['quest', 'stage', 'chapter', 'mission', 'achievement', 'reward', 'progression', '퀘스트', '스테이지', '미션', '업적'],
        'BM': ['purchase', 'payment', 'monetization', 'revenue', 'price', 'gem', 'crystal', '구매', '결제', '수익', '가격'],
        'LiveOps': ['event', 'season', 'limited', 'schedule', 'update', 'notification', '이벤트', '시즌', '한정', '알림'],
        'UX': ['ui', 'interface', 'animation', 'visual', 'effect', 'tutorial', 'onboarding', 'ui', '인터페이스', '애니메이션', '튜토리얼'],
        'Social': ['guild', 'clan', 'friends', 'ranking', 'leaderboard', 'chat', 'social', '길드', '클랜', '친구', '랭킹'],
    };

    for (const [domain, kws] of Object.entries(keywords)) {
        let score = 0;
        for (const kw of kws) {
            if (text.includes(kw)) score++;
        }
        if (score > 0) domainScores[domain] = score;
    }

    if (Object.keys(domainScores).length === 0) return 'InGame';

    // Return domain with highest score
    return Object.entries(domainScores).sort((a, b) => b[1] - a[1])[0][0];
}

// ============================================================
// Design Entry Generation
// ============================================================

function generateDesignId(project, domain, system, name) {
    const sanitize = s => (s || '').toLowerCase()
        .replace(/[^a-z0-9가-힣]/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_|_$/g, '')
        .substring(0, 30);

    const parts = [
        sanitize(project),
        sanitize(domain),
        sanitize(system || name),
    ].filter(Boolean);

    return parts.join('__');
}

function createIndexEntry(designId, domain, genre, system, data_type, balance_area, project, source) {
    return {
        designId,
        domain: normalizeDomainName(domain),
        genre: displayGenre(genre || 'generic'),
        system: system || '',
        score: 0.4,
        source: source || 'internal_produced',
        data_type: data_type || 'spec',
        balance_area: balance_area || null,
        version: '1.0.0',
        project: project || null,
        provides: [],
        requires: [],
        tags: []
    };
}

function createDetailFile(designId, project, domain, genre, system, source, content, data) {
    const now = new Date().toISOString();
    const domainNorm = normalizeDomainName(domain);

    // Extract content fields from parsed data
    const summary = data.summary || data.description || data.desc || data.overview || '';
    const formula = data.formula || data.equation || data.calculation || '';
    const parameters = data.parameters || data.params || data.variables || {};
    const edgeCases = data.edge_cases || data.edgeCases || data.edge_case || [];
    const references = data.references || data.refs || [];

    return {
        designId,
        project: project || null,
        domain: domainNorm,
        genre: displayGenre(genre || 'generic'),
        system: system || '',
        source: source || 'internal_produced',
        version: '1.0.0',
        score: 0.4,
        auto_scores: {
            logic_completeness: null,
            balance_stability: null,
            implementation_complexity: null
        },
        post_launch_label: null,
        accuracy_estimate: null,
        content: {
            summary: typeof summary === 'string' ? summary : JSON.stringify(summary),
            formula: typeof formula === 'string' ? formula : JSON.stringify(formula),
            parameters: typeof parameters === 'object' ? parameters : {},
            edge_cases: Array.isArray(edgeCases) ? edgeCases : [edgeCases].filter(Boolean),
            references: Array.isArray(references) ? references : [references].filter(Boolean)
        },
        versions: [{
            version: '1.0.0',
            phase: 'pre_launch',
            data: content,
            note: 'Initial parse from design materials'
        }],
        feedback_history: [],
        code_mapping: {
            code_domain: '',
            code_roles: [],
            related_code_nodes: []
        },
        timestamp: now
    };
}

function capitalizeFirst(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

// ============================================================
// Format-specific Converters
// ============================================================

/**
 * Convert YAML-parsed data to design entries
 */
function convertYaml(data, args) {
    const entries = [];

    // Handle array of design items
    if (Array.isArray(data)) {
        for (const item of data) {
            const converted = convertSingleItem(item, args);
            entries.push(...converted);
        }
        return entries;
    }

    // Handle single design item or document with top-level sections
    if (data && typeof data === 'object') {
        // Check if this is a C10+ format document
        if (data.parameters || data.parameter_list) {
            return convertC10Format(data, args);
        }

        // Check if this is a multi-system document
        if (data.systems || data.system_list) {
            const systems = data.systems || data.system_list;
            for (const [sysName, sysData] of Object.entries(systems)) {
                const item = { ...sysData, system: sysName, ...args };
                const converted = convertSingleItem(item, args);
                entries.push(...converted);
            }
            return entries;
        }

        // Single item
        return convertSingleItem(data, args);
    }

    return entries;
}

/**
 * Convert C10+ parameter-based format
 * C10 is a game design framework with categorized parameters
 */
function convertC10Format(data, args) {
    const entries = [];
    const params = data.parameters || data.parameter_list || {};

    for (const [paramName, paramData] of Object.entries(params)) {
        const domains = resolveDomainFromC10(paramName);

        if (domains === null) {
            console.log(`[SKIP] Parameter '${paramName}' maps to 'architecture' - skipping`);
            continue;
        }

        const system = paramData.system || paramData.name || paramName;
        const content = JSON.stringify(paramData);

        for (const domain of domains) {
            const domainDir = domain.toLowerCase().replace(/\s/g, '');
            const designId = generateDesignId(args.project, domainDir, system, paramName);
            const source = data.source || args.source || 'internal_produced';
            const data_type = paramData.data_type || data.data_type || 'formula';
            const balance_area = paramData.balance_area || data.balance_area || null;

            const indexEntry = createIndexEntry(
                designId, domain, args.genre, system, data_type, balance_area, args.project, source
            );
            const detailFile = createDetailFile(
                designId, args.project, domain, args.genre, system, source, content, paramData
            );

            entries.push({ indexEntry, detailFile, domain: domainDir });
        }
    }

    return entries;
}

function convertSingleItem(item, args) {
    if (!item || typeof item !== 'object') return [];

    const rawDomain = item.domain || args.domain || inferDomainFromContent(item);
    const domainDir = normalizeDomain(rawDomain);
    const domain = displayDomain(domainDir);
    const system = item.system || item.name || item.title || 'unknown';
    const content = JSON.stringify(item);
    const source = item.source || args.source || 'internal_produced';
    const data_type = item.data_type || args.data_type || 'spec';
    const balance_area = item.balance_area || args.balance_area || null;

    const designId = generateDesignId(args.project, domainDir, system, item.name);
    const indexEntry = createIndexEntry(
        designId, domain, args.genre, system, data_type, balance_area, args.project, source
    );
    const detailFile = createDetailFile(
        designId, args.project, domain, args.genre, system, source, content, item
    );

    return [{ indexEntry, detailFile, domain: domainDir }];
}

/**
 * Convert CSV rows to design entries
 * Expected columns: domain, system, name, summary, formula, data_type, balance_area, source
 */
function convertCsv(rows, args) {
    const entries = [];

    for (const row of rows) {
        if (!row || Object.keys(row).length === 0) continue;

        const rawDomain = row.domain || row.Domain || args.domain || inferDomainFromContent(row);
        const domainDir = normalizeDomain(rawDomain);
        const domain = displayDomain(domainDir);
        const system = row.system || row.System || row.name || row.Name || 'unknown';
        const source = row.source || row.Source || args.source || 'internal_produced';
        const data_type = row.data_type || row.DataType || args.data_type || 'table';
        const balance_area = row.balance_area || row.BalanceArea || null;
        const content = JSON.stringify(row);

        const designId = generateDesignId(args.project, domainDir, system, row.name || row.Name);

        // Build data object from CSV row
        const data = {
            summary: row.summary || row.Summary || row.description || '',
            formula: row.formula || row.Formula || '',
            parameters: {},
            edge_cases: [],
            references: []
        };

        // Map remaining columns to parameters
        const skipCols = new Set(['domain', 'system', 'name', 'summary', 'formula', 'data_type',
                                   'balance_area', 'source', 'Domain', 'System', 'Name', 'Summary',
                                   'Formula', 'DataType', 'BalanceArea', 'Source']);
        for (const [col, val] of Object.entries(row)) {
            if (!skipCols.has(col) && val) {
                data.parameters[col] = val;
            }
        }

        const indexEntry = createIndexEntry(
            designId, domain, args.genre, system, data_type, balance_area, args.project, source
        );
        const detailFile = createDetailFile(
            designId, args.project, domain, args.genre, system, source, content, data
        );

        entries.push({ indexEntry, detailFile, domain: domainDir });
    }

    return entries;
}

/**
 * Convert Markdown sections to design entries
 */
function convertMd(sections, args) {
    const entries = [];

    // Group sections by H1/H2 (top-level = one design entry each)
    const topSections = sections.filter(s => s.level <= 2);

    for (const section of topSections) {
        const rawDomain = args.domain || inferDomainFromContent({ title: section.title, content: section.content });
        const domainDir = normalizeDomain(rawDomain);
        const domain = displayDomain(domainDir);
        const system = section.title;
        const content = section.content;
        const source = args.source || 'internal_produced';
        const data_type = args.data_type || 'spec';

        // Extract formula and parameters from content
        const formulaMatch = content.match(/```[\s\S]*?```/) || content.match(/`([^`]+)`/);
        const formula = formulaMatch ? formulaMatch[0].replace(/```/g, '').trim() : '';

        // Extract bullet points as parameters
        const bulletPoints = content.match(/^[-*]\s+.+$/gm) || [];
        const parameters = {};
        for (const bp of bulletPoints) {
            const [key, ...vals] = bp.replace(/^[-*]\s+/, '').split(':');
            if (vals.length > 0) {
                parameters[key.trim()] = vals.join(':').trim();
            }
        }

        const data = {
            summary: content.split('\n')[0] || section.title,
            formula,
            parameters,
            edge_cases: [],
            references: []
        };

        const designId = generateDesignId(args.project, domainDir, system, null);
        const indexEntry = createIndexEntry(
            designId, domain, args.genre, system, data_type, null, args.project, source
        );
        const detailFile = createDetailFile(
            designId, args.project, domain, args.genre, system, source, content, data
        );

        entries.push({ indexEntry, detailFile, domain: domainDir });
    }

    return entries;
}

/**
 * Convert JSON data to design entries
 */
function convertJson(data, args) {
    // Reuse YAML converter since JSON is a subset
    return convertYaml(data, args);
}

// ============================================================
// DB Writing
// ============================================================

function incrementSemver(version) {
    const parts = (version || '1.0.0').split('.');
    const major = parseInt(parts[0] || '1', 10);
    const minor = parseInt(parts[1] || '0', 10);
    const patch = parseInt(parts[2] || '0', 10);
    return `${major}.${minor}.${patch + 1}`;
}

function writeEntryLocal(entry, genre, dbRoot) {
    const { indexEntry, detailFile, domain } = entry;
    const genreDir = (genre || 'generic').toLowerCase();
    const domainDir = domain || 'ingame';

    // Paths
    const baseDir = path.join(dbRoot, 'base', genreDir, domainDir);
    const filesDir = path.join(baseDir, 'files');
    const indexPath = path.join(baseDir, 'index.json');
    const detailPath = path.join(filesDir, `${indexEntry.designId}.json`);

    // Ensure directories exist
    ensureDir(filesDir);

    // Check for existing entry to determine version bump
    const existingIndex = fs.existsSync(indexPath)
        ? (() => { try { const d = JSON.parse(fs.readFileSync(indexPath, 'utf-8')); return Array.isArray(d) ? d : []; } catch { return []; } })()
        : [];

    const existing = existingIndex.find(e => e.designId === indexEntry.designId);
    if (existing) {
        indexEntry.version = incrementSemver(existing.version || '1.0.0');
        console.log(`[UPDATE] ${indexEntry.designId} (${genreDir}/${domainDir}) → v${indexEntry.version}`);
    } else {
        console.log(`[ADD]    ${indexEntry.designId} (${genreDir}/${domainDir})`);
    }

    // Atomic upsert index
    upsertIndex(indexPath, indexEntry, 'designId');

    // Write detail file atomically via fs (safe-io writeJsonAtomic)
    const { writeJsonAtomic } = require('./lib/safe-io');
    writeJsonAtomic(detailPath, detailFile);
}

/**
 * Write a design entry to MongoDB
 * The document contains all detail fields plus index fields merged together.
 */
async function writeEntryMongo(entry) {
    const { indexEntry, detailFile } = entry;
    // Merge index fields into the detail document for a single flat document
    const doc = { ...detailFile, ...indexEntry };
    await dbClient.upsertDesign(doc);
    console.log(`[MONGO]  ${indexEntry.designId}`);
}

/**
 * Write entry to both local files and MongoDB (dual-write).
 * If mongoOnly is true, skip local file writes.
 */
async function writeEntry(entry, genre, dbRoot, mongoOnly) {
    if (!mongoOnly) {
        writeEntryLocal(entry, genre, dbRoot);
    }
    await writeEntryMongo(entry);
}

// ============================================================
// Main
// ============================================================

async function main() {
    const args = parseArgs(process.argv.slice(2));

    // Validate required args
    if (!args.input) {
        console.error('Error: --input is required');
        printUsage();
        process.exit(1);
    }
    if (!args.format) {
        // Try to infer from extension
        const ext = path.extname(args.input).toLowerCase();
        const extMap = { '.yaml': 'yaml', '.yml': 'yaml', '.csv': 'csv', '.json': 'json', '.md': 'md' };
        args.format = extMap[ext];
        if (!args.format) {
            console.error('Error: --format is required (yaml|csv|json|md)');
            printUsage();
            process.exit(1);
        }
        console.log(`[INFO] Inferred format from extension: ${args.format}`);
    }
    if (!args.project) {
        console.error('Error: --project is required');
        printUsage();
        process.exit(1);
    }

    // Validate genre
    if (!GENRES.includes(args.genre)) {
        console.warn(`[WARN] Unknown genre '${args.genre}'. Using 'generic'.`);
        args.genre = 'generic';
    }

    // Read input file
    let content;
    try {
        content = fs.readFileSync(args.input, 'utf-8');
    } catch (e) {
        console.error(`Error: Cannot read input file: ${args.input}`);
        console.error(e.message);
        process.exit(1);
    }

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Design Parser`);
    console.log(`Input: ${args.input}`);
    console.log(`Format: ${args.format} | Genre: ${args.genre} | Project: ${args.project}`);
    console.log(`Output DB: ${args.output}`);
    console.log(`${'='.repeat(60)}\n`);

    // Parse input
    let parsed;
    let entries = [];

    try {
        switch (args.format) {
            case 'yaml':
            case 'yml':
                parsed = parseYaml(content);
                entries = convertYaml(parsed, args);
                break;

            case 'csv':
                parsed = parseCsv(content);
                entries = convertCsv(parsed, args);
                break;

            case 'json':
                parsed = JSON.parse(content);
                entries = convertJson(parsed, args);
                break;

            case 'md':
            case 'markdown':
                parsed = parseMd(content);
                entries = convertMd(parsed, args);
                break;

            default:
                console.error(`Error: Unsupported format '${args.format}'`);
                process.exit(1);
        }
    } catch (e) {
        console.error(`Error: Failed to parse ${args.format} file`);
        console.error(e.message);
        process.exit(1);
    }

    if (entries.length === 0) {
        console.log('[WARN] No entries generated from input file.');
        console.log('Check that the file has the expected structure.');
        process.exit(0);
    }

    // Write entries to DB (dual-write: local + MongoDB, unless --mongo-only)
    let successCount = 0;
    for (const entry of entries) {
        try {
            await writeEntry(entry, args.genre, args.output, args.mongoOnly);
            successCount++;
        } catch (e) {
            console.error(`[ERROR] Failed to write ${entry.indexEntry?.designId}: ${e.message}`);
        }
    }

    // Close MongoDB connection
    await dbClient.close();

    const modeLabel = args.mongoOnly ? 'MongoDB only' : 'Local + MongoDB';
    console.log(`\n${'='.repeat(60)}`);
    console.log(`완료: ${successCount}/${entries.length}개 엔트리 저장됨 (${modeLabel})`);
    if (!args.mongoOnly) {
        console.log(`Local DB 경로: ${args.output}/base/${args.genre.toLowerCase()}/`);
    }
    console.log(`${'='.repeat(60)}\n`);
}

main().catch(err => {
    console.error(`[FATAL] ${err.message}`);
    dbClient.close().finally(() => process.exit(1));
});
