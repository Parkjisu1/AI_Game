#!/usr/bin/env node
/**
 * C10+ Spec to Design DB Converter
 * C10+ spec YAML 파일을 파싱하여 Design DB에 저장
 *
 * Usage:
 *   node c10-to-design-db.js --game ash_n_veil --genre Idle
 *   node c10-to-design-db.js --game ash_n_veil --genre Idle --dry-run
 *   node c10-to-design-db.js --game ash_n_veil --genre Idle --projects-root /path/to/projects
 */

const fs = require('fs');
const path = require('path');

// Shared libraries
const { parseYaml } = require('./lib/yaml-utils');
const { writeJsonAtomic, upsertIndex, ensureDir } = require('./lib/safe-io');
const { normalizeDomain, displayDomain, normalizeGenre } = require('./lib/domain-utils');

// ============================================================
// Configuration
// ============================================================

const DB_ROOT = process.env.DB_ROOT || 'E:/AI/db';

// Bug 3 fix: PROJECTS_ROOT is resolved from CLI arg > env var > cwd (no hardcoded default)
// Resolved after argument parsing below.

// Confidence → accuracy_estimate mapping
const CONFIDENCE_MAP = {
    confirmed: 0.95,
    high: 0.85,
    medium: 0.70,
    low: 0.40,
    null: 0.0,
};

// Known confidence values for normalization (Bug 1)
const KNOWN_CONFIDENCE_VALUES = new Set(['confirmed', 'high', 'medium', 'low', null]);

// C10+ parameter name → domain mapping
// Returns array of domain names
const PARAM_TO_DOMAIN = {
    // Progression params → content + balance
    max_chapter:          ['content', 'balance'],
    stages_per_chapter:   ['content', 'balance'],
    boss_frequency:       ['content', 'balance'],
    difficulty_modes:     ['content', 'balance'],
    daily_quest_count:    ['content', 'balance'],
    attendance_days:      ['content'],

    // Growth params → balance
    base_hp_lv1:          ['balance'],
    base_atk_lv1:         ['balance'],
    hp_growth_formula:    ['balance'],
    atk_growth_formula:   ['balance'],
    exp_curve_formula:    ['balance'],
    auto_battle_unlock:   ['balance'],
    active_skill_count:   ['balance'],
    skill_cooldown_range: ['balance'],
    auto_attack_speed:    ['balance'],
    damage_formula:       ['balance'],
    critical_rate:        ['balance'],
    critical_multiplier:  ['balance'],

    // Equipment params → outgame + balance
    gear_slot_count:      ['outgame', 'balance'],
    gear_grade_count:     ['outgame', 'balance'],
    enhance_max_level:    ['outgame', 'balance'],
    enhance_cost_formula: ['outgame', 'balance'],

    // Combat params → ingame + balance
    state_count:          ['ingame', 'balance'],

    // Gacha params → outgame + bm
    gacha_cost_1x:        ['outgame', 'bm'],
    gacha_cost_10x:       ['outgame', 'bm'],
    gacha_ssr_rate:       ['outgame', 'bm'],
    gacha_pity_count:     ['outgame', 'bm'],

    // Economy params → balance + bm
    currency_types:       ['balance', 'bm'],
    idle_gold_per_min:    ['balance', 'bm'],
    idle_max_accumulation: ['balance', 'bm'],

    // Visual params → ux
    ui_reference_resolution: ['ux'],

    // System params → ingame
    pet_system_exists:    ['ingame'],
};

// Domain → system name mapping
const DOMAIN_SYSTEM_MAP = {
    ingame:  'CoreGameplay',
    outgame: 'ItemEquipment',
    balance: 'GameBalance',
    content: 'ContentProgression',
    bm:      'Monetization',
    ux:      'UIPresentation',
    social:  'SocialSystem',
    meta:    'MetaProgression',
    liveops: 'LiveOps',
};

// ============================================================
// CLI Argument Parsing
// ============================================================

function parseArgs(argv) {
    const args = {
        game: null,
        genre: null,
        dryRun: false,
        help: false,
        projectsRoot: null,
    };

    for (let i = 0; i < argv.length; i++) {
        switch (argv[i]) {
            case '--game':          args.game = argv[++i]; break;
            case '--genre':         args.genre = argv[++i]; break;
            case '--dry-run':       args.dryRun = true; break;
            case '--projects-root': args.projectsRoot = argv[++i]; break;
            case '--help': case '-h': args.help = true; break;
        }
    }

    return args;
}

function printUsage() {
    console.log(`
C10+ Spec to Design DB Converter

Usage:
  node c10-to-design-db.js --game <name> --genre <genre> [options]

Options:
  --game <name>              게임 이름 (e.g. ash_n_veil)
  --genre <genre>            장르 (e.g. Idle, RPG, Merge, Casual)
  --projects-root <path>     프로젝트 루트 경로 (기본값: PROJECTS_ROOT 환경변수 또는 현재 디렉터리)
  --dry-run                  DB에 저장하지 않고 결과만 출력
  --help, -h                 도움말

Examples:
  node c10-to-design-db.js --game ash_n_veil --genre Idle
  node c10-to-design-db.js --game ash_n_veil --genre Idle --dry-run
  node c10-to-design-db.js --game ash_n_veil --genre Idle --projects-root /path/to/projects
`);
}

// ============================================================
// Domain Classification
// ============================================================

function classifyParamToDomains(paramName) {
    if (!paramName) return ['balance']; // default

    // Exact match
    if (PARAM_TO_DOMAIN[paramName]) {
        return PARAM_TO_DOMAIN[paramName];
    }

    // Keyword-based classification
    const name = paramName.toLowerCase();
    const domains = new Set();

    if (/progression|chapter|stage|mission|quest|attendance|dungeon|content/.test(name)) {
        domains.add(normalizeDomain('content'));
        domains.add(normalizeDomain('balance'));
    }
    if (/growth|formula|curve|base_|_lv\d|level|exp|exp_|unlock|auto_|skill|cooldown|attack|speed/.test(name)) {
        domains.add(normalizeDomain('balance'));
    }
    if (/gear|equip|enhance|slot|grade|upgrade|item_/.test(name)) {
        domains.add(normalizeDomain('outgame'));
        domains.add(normalizeDomain('balance'));
    }
    if (/combat|battle|damage|critical|crit|state_count/.test(name)) {
        domains.add(normalizeDomain('ingame'));
        domains.add(normalizeDomain('balance'));
    }
    if (/gacha|summon|pity|ssr|rate/.test(name)) {
        domains.add(normalizeDomain('outgame'));
        domains.add(normalizeDomain('bm'));
    }
    if (/currency|gold|diamond|economy|idle_gold|idle_max|shop|cost/.test(name)) {
        domains.add(normalizeDomain('balance'));
        domains.add(normalizeDomain('bm'));
    }
    if (/ui_|visual|resolution|layout|hud/.test(name)) {
        domains.add(normalizeDomain('ux'));
    }
    if (/pet|guild|social|friend|rank|pvp/.test(name)) {
        domains.add(normalizeDomain('social'));
    }
    if (/achievement|collection|trophy|meta/.test(name)) {
        domains.add(normalizeDomain('meta'));
    }

    return domains.size > 0 ? Array.from(domains) : ['balance'];
}

// ============================================================
// Design DB Entry Creation
// ============================================================

function createDesignId(project, domain, system, name) {
    // Sanitize: replace spaces/special chars with underscore
    const sanitize = str => (str || '').toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/__+/g, '_');
    return `${sanitize(project)}__${sanitize(domain)}__${sanitize(system)}__${sanitize(name)}`;
}

function inferDataType(param) {
    const name = (param.name || '').toLowerCase();
    const value = param.value;

    if (/formula|curve/.test(name)) return 'formula';
    if (/rate|multiplier|ratio/.test(name)) return 'formula';
    if (typeof value === 'number' && !Number.isInteger(value)) return 'formula';
    if (typeof value === 'string' && value.includes('~')) return 'range';
    if (typeof value === 'string' && /\d.*[+\-*/×].*\d/.test(value)) return 'formula';
    if (/count|max|min|_lv\d|level|slot|day/.test(name)) return 'constant';
    if (/exists|enabled|unlock/.test(name)) return 'flag';
    if (value === null) return 'unknown';
    return 'constant';
}

function inferBalanceArea(paramName, domain) {
    const name = (paramName || '').toLowerCase();
    if (/hp|atk|def|spd|crit|damage|combat/.test(name)) return 'combat';
    if (/exp|level|growth/.test(name)) return 'progression';
    if (/gold|diamond|currency|economy|idle_gold/.test(name)) return 'economy';
    if (/gacha|pity|ssr/.test(name)) return 'gacha';
    if (/gear|equip|enhance/.test(name)) return 'equipment';
    if (/stage|chapter|mission|quest/.test(name)) return 'content';
    if (/ui|visual|resolution/.test(name)) return 'ux';
    return domain || 'general';
}

function buildProvidesTags(param, domain) {
    const provides = [];
    if (param.name) provides.push(param.name);
    if (param.value !== null) provides.push(`${param.name}:${param.value}`);
    return provides;
}

function buildTagsFromParam(param, domain) {
    const tags = [];
    const name = (param.name || '').toLowerCase();

    if (/formula|curve/.test(name)) tags.push('formula');
    if (/rate|ratio/.test(name)) tags.push('rate');
    if (/cost/.test(name)) tags.push('cost');
    if (/count|max/.test(name)) tags.push('count');
    if (/unlock/.test(name)) tags.push('unlock');
    if (param.confidence === 'confirmed' || param.confidence === 'high') tags.push('verified');
    if (param.confidence === 'low' || param.confidence === null) tags.push('estimated');

    return tags;
}

// ============================================================
// Confidence Normalization (Bug 1 fix)
// ============================================================

/**
 * Normalize a raw confidence string to a known value.
 * If unknown, logs a warning and defaults to 'medium'.
 */
function normalizeConfidence(rawConfidence) {
    if (rawConfidence === null || rawConfidence === undefined) return null;
    if (rawConfidence === 'null' || rawConfidence === '~') return null;

    const lower = rawConfidence.toLowerCase().trim();

    // Check direct match
    if (lower === 'confirmed') return 'confirmed';
    if (lower === 'high') return 'high';
    if (lower === 'medium') return 'medium';
    if (lower === 'low') return 'low';

    // Unknown confidence value
    console.warn(`  [경고] 알 수 없는 confidence 값: "${rawConfidence}" → "medium" 으로 기본값 적용`);
    return 'medium';
}

// ============================================================
// Main Processing
// ============================================================

function processSpec(specPath, game, genre, dryRun) {
    console.log(`\n처리 중: ${specPath}`);

    const raw = fs.readFileSync(specPath, 'utf-8');

    // Use shared yaml-utils parser instead of custom parseC10SpecYaml
    const parsed = parseYaml(raw);

    // Extract fields from the parsed object
    const spec = {
        game: parsed && parsed.game ? parsed.game : null,
        genre: parsed && parsed.genre ? parsed.genre : null,
        condition: parsed && parsed.condition ? parsed.condition : null,
        parameters: [],
    };

    // Extract parameters array
    if (parsed && Array.isArray(parsed.parameters)) {
        for (const p of parsed.parameters) {
            if (!p || typeof p !== 'object') continue;

            // Normalize confidence (Bug 1 fix)
            let rawConf = p.confidence !== undefined ? p.confidence : null;
            if (rawConf === 'null' || rawConf === '~') rawConf = null;
            const normalizedConf = (rawConf === null) ? null : normalizeConfidence(String(rawConf));

            spec.parameters.push({
                id: p.id || null,
                name: p.name || null,
                value: p.value !== undefined ? p.value : null,
                confidence: normalizedConf,
                source: p.source || null,
            });
        }
    }

    if (!spec.parameters || spec.parameters.length === 0) {
        console.log('  → 파라미터 없음. 건너뜀.');
        return { processed: 0, skipped: 0, entries: [] };
    }

    const genreLower = normalizeGenre(genre);
    const project = game;
    const entries = [];

    // Group parameters by domain
    const domainMap = {};

    for (const param of spec.parameters) {
        if (!param.name) continue;

        const domains = classifyParamToDomains(param.name);
        for (const domain of domains) {
            if (!domainMap[domain]) domainMap[domain] = [];
            domainMap[domain].push(param);
        }
    }

    // Create entries per domain
    for (const [domain, params] of Object.entries(domainMap)) {
        const system = DOMAIN_SYSTEM_MAP[domain] || domain;

        for (const param of params) {
            // Bug 1 fix: confidence is already normalized; use CONFIDENCE_MAP safely
            const confidenceKey = param.confidence === null ? 'null' : param.confidence;
            const accuracyEstimate = CONFIDENCE_MAP[confidenceKey] !== undefined
                ? CONFIDENCE_MAP[confidenceKey]
                : CONFIDENCE_MAP['medium']; // fallback: should not happen after normalization

            const designId = createDesignId(project, domain, system, param.name);

            const indexEntry = {
                designId,
                // Bug 3 (domain display): use displayDomain() from domain-utils
                domain: displayDomain(domain),
                genre: genre,
                system,
                score: 0.4,
                source: 'observed',
                data_type: inferDataType(param),
                balance_area: inferBalanceArea(param.name, domain),
                version: '1.0.0',
                project,
                provides: buildProvidesTags(param, domain),
                requires: [],
                tags: buildTagsFromParam(param, domain),
            };

            const fileDetail = {
                ...indexEntry,
                param_id: param.id,
                param_name: param.name,
                value: param.value,
                confidence: param.confidence,
                accuracy_estimate: accuracyEstimate,
                observation_source: param.source || null,
                raw_spec_file: path.basename(specPath),
                created_at: new Date().toISOString(),
            };

            entries.push({ domain, indexEntry, fileDetail });
        }
    }

    // Save to DB
    let savedCount = 0;
    let skippedCount = 0;

    for (const entry of entries) {
        const { domain, indexEntry, fileDetail } = entry;
        const domainDir = path.join(DB_ROOT, 'design', 'base', genreLower, domain);
        const indexPath = path.join(domainDir, 'index.json');
        const filesDir = path.join(domainDir, 'files');
        const filePath = path.join(filesDir, `${indexEntry.designId}.json`);

        if (dryRun) {
            console.log(`  [dry-run] Would save: ${indexEntry.designId} → ${domainDir}`);
            skippedCount++;
            continue;
        }

        // Ensure directories exist (using safe-io ensureDir via writeJsonAtomic)
        ensureDir(filesDir);

        // Update index (using safe-io upsertIndex - atomic write included)
        upsertIndex(indexPath, indexEntry);

        // Save file detail (using safe-io writeJsonAtomic)
        writeJsonAtomic(filePath, fileDetail);

        savedCount++;
    }

    console.log(`  → 파라미터 ${spec.parameters.length}개, 엔트리 ${entries.length}개 생성`);
    if (dryRun) {
        console.log(`  → [dry-run] 저장 건너뜀 (${skippedCount}개)`);
    } else {
        console.log(`  → DB 저장: ${savedCount}개`);
    }

    return { processed: savedCount, skipped: skippedCount, entries };
}

// ============================================================
// Entry Point
// ============================================================

function main() {
    const args = parseArgs(process.argv.slice(2));

    if (args.help || !args.game || !args.genre) {
        printUsage();
        if (!args.help) {
            console.error('오류: --game 과 --genre 가 필요합니다.');
            process.exit(1);
        }
        process.exit(0);
    }

    // Bug 3 fix: resolve PROJECTS_ROOT from CLI arg > env var > cwd
    const PROJECTS_ROOT = args.projectsRoot
        || process.env.PROJECTS_ROOT
        || process.cwd();

    const gameName = args.game;
    const genre = args.genre;
    const dryRun = args.dryRun;

    console.log('='.repeat(60));
    console.log(`C10+ → Design DB Converter`);
    console.log(`Game: ${gameName} | Genre: ${genre}${dryRun ? ' | [DRY RUN]' : ''}`);
    console.log('='.repeat(60));

    // Find spec files
    const specsDir = path.join(PROJECTS_ROOT, gameName, 'specs');

    if (!fs.existsSync(specsDir)) {
        console.error(`오류: 스펙 디렉터리를 찾을 수 없습니다: ${specsDir}`);
        process.exit(1);
    }

    const specFiles = fs.readdirSync(specsDir)
        .filter(f => f.endsWith('.yaml') || f.endsWith('.yml'))
        .map(f => path.join(specsDir, f));

    if (specFiles.length === 0) {
        console.error(`오류: 스펙 YAML 파일을 찾을 수 없습니다: ${specsDir}`);
        process.exit(1);
    }

    console.log(`\n스펙 파일 ${specFiles.length}개 발견:`);
    specFiles.forEach(f => console.log(`  - ${path.basename(f)}`));

    let totalProcessed = 0;
    let totalSkipped = 0;

    for (const specFile of specFiles) {
        const result = processSpec(specFile, gameName, genre, dryRun);
        totalProcessed += result.processed;
        totalSkipped += result.skipped;
    }

    console.log('\n' + '='.repeat(60));
    console.log('완료 요약');
    console.log('='.repeat(60));
    console.log(`스펙 파일: ${specFiles.length}개`);
    if (dryRun) {
        console.log(`[dry-run] 예상 저장 엔트리: ${totalSkipped}개`);
    } else {
        console.log(`저장된 엔트리: ${totalProcessed}개`);
        console.log(`Design DB: ${path.join(DB_ROOT, 'design', 'base', normalizeGenre(args.genre))}`);
    }
}

main();
