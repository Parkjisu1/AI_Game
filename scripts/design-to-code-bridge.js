#!/usr/bin/env node
/**
 * Design to Code Bridge
 * design_workflow/ 출력물을 코드 파이프라인 형식으로 변환
 * (system_spec.yaml + nodes/*.yaml)
 *
 * Usage:
 *   node design-to-code-bridge.js --project MyGame \
 *     --input E:/AI/projects/MyGame/designs/design_workflow \
 *     --output E:/AI/projects/MyGame/designs
 */

const fs = require('fs');
const path = require('path');
const { parseYaml, serializeYaml } = require('./lib/yaml-utils');
const { ensureDir } = require('./lib/safe-io');

// ============================================================
// Configuration
// ============================================================

// Domain → Code System mapping
const DOMAIN_TO_CODE_SYSTEMS = {
    ingame:  ['Battle', 'Skill', 'Character', 'Stage'],
    outgame: ['Inventory', 'Shop', 'Item'],
    balance: [], // Calculator/Processor per Domain — handled dynamically
    content: ['Quest', 'Stage', 'Reward'],
    bm:      ['Shop', 'IAP'],
    ux:      ['UI', 'Audio'],
    social:  ['Network', 'Guild'],
    meta:    ['Achievement', 'Collection'],
    liveops: [], // no code mapping
};

// Domain → preferred Role
const DOMAIN_TO_ROLE = {
    ingame:  'Manager',
    outgame: 'Manager',
    balance: 'Calculator',
    content: 'Manager',
    bm:      'Manager',
    ux:      'Handler',
    social:  'Manager',
    meta:    'Manager',
    liveops: 'Manager',
};

// Phase assignment based on dependency depth
const DOMAIN_PHASE = {
    ingame:  1,
    outgame: 1,
    balance: 1,
    content: 2,
    bm:      2,
    ux:      2,
    social:  2,
    meta:    2,
    liveops: 3,
};

// ============================================================
// CLI Argument Parsing
// ============================================================

function parseArgs(argv) {
    const args = {
        project: null,
        input: null,
        output: null,
        flowContract: null,
        help: false,
    };

    for (let i = 0; i < argv.length; i++) {
        const option = argv[i];
        const value = () => {
            const next = argv[++i];
            if (!next || next.startsWith('--')) throw new Error(`${option} requires a value`);
            return next;
        };
        switch (argv[i]) {
            case '--project': args.project = value(); break;
            case '--input':   args.input   = value(); break;
            case '--output':  args.output  = value(); break;
            case '--flow-contract': args.flowContract = value(); break;
            case '--help': case '-h': args.help = true; break;
            default: throw new Error(`Unknown option: ${option}`);
        }
    }

    return args;
}

function printUsage() {
    console.log(`
Design to Code Bridge

Usage:
  node design-to-code-bridge.js --project <name> --input <design-workflow-path> --output <designs-path>

Options:
  --project <name>   프로젝트 이름
  --input <path>     design_workflow 폴더 경로
  --output <path>    designs 출력 폴더 경로
  --flow-contract <path>  검증할 의도/역설계 계약 (기본: 출력 폴더의 flow-contract.json)
  --help, -h         도움말

Examples:
  node design-to-code-bridge.js \\
    --project MyGame \\
    --input E:/AI/projects/MyGame/designs/design_workflow \\
    --output E:/AI/projects/MyGame/designs
`);
}

// ============================================================
// Design Workflow Reader
// ============================================================

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function readYamlFiles(dir, strict = false) {
    if (!fs.existsSync(dir)) return [];
    return fs.readdirSync(dir)
        .filter(f => f.endsWith('.yaml') || f.endsWith('.yml'))
        .map(f => {
            try {
                const content = fs.readFileSync(path.join(dir, f), 'utf-8');
                const data = parseYaml(content);
                if (strict && !isObject(data)) throw new Error('Expected a design object');
                return { file: f, data, raw: content };
            } catch (e) {
                if (strict) throw new Error(`${f}: ${e.message}`);
                console.warn(`  경고: ${f} 파싱 실패 - ${e.message}`);
                return null;
            }
        })
        .filter(Boolean);
}

function collectDesignElements(inputDir, strict = false) {
    const elements = {
        systems: [],
        balance: [],
        content: [],
        bm: [],
        all: [],
    };

    // Read systems/
    const systemFiles = readYamlFiles(path.join(inputDir, 'systems'), strict);
    elements.systems = systemFiles;

    // Read balance/
    const balanceFiles = readYamlFiles(path.join(inputDir, 'balance'), strict);
    elements.balance = balanceFiles;

    // Read content/
    const contentFiles = readYamlFiles(path.join(inputDir, 'content'), strict);
    elements.content = contentFiles;

    // Read bm/
    const bmFiles = readYamlFiles(path.join(inputDir, 'bm'), strict);
    elements.bm = bmFiles;

    elements.all = [...systemFiles, ...balanceFiles, ...contentFiles, ...bmFiles];
    return elements;
}

// ============================================================
// Code Node Generation
// ============================================================

function sanitizeNodeId(name) {
    if (!name) return 'UnknownSystem';
    // Convert to PascalCase
    return name
        .replace(/[_\-\s]+(.)/g, (_, c) => c.toUpperCase())
        .replace(/^[a-z]/, c => c.toUpperCase())
        .replace(/[^a-zA-Z0-9]/g, '');
}

function inferGenre(data, project) {
    const genre = data.genre || data.game_genre || data.main_genre || '';
    if (genre) return genre.charAt(0).toUpperCase() + genre.slice(1).toLowerCase();
    return 'Generic';
}

function inferRoleFromSystem(systemName, domain) {
    const name = (systemName || '').toLowerCase();
    if (/calculator|formula|balance|stat/.test(name)) return 'Calculator';
    if (/processor|pipeline|batch/.test(name)) return 'Processor';
    if (/factory|spawner/.test(name)) return 'Factory';
    if (/handler|listener/.test(name)) return 'Handler';
    if (/validator|checker/.test(name)) return 'Validator';
    if (/provider|service/.test(name)) return 'Provider';
    if (/ui|view|panel|screen/.test(name)) return 'UX';
    return DOMAIN_TO_ROLE[domain] || 'Manager';
}

function buildContract(systemName, domain, data, strict = false) {
    if (data.contract !== undefined && data.contracts !== undefined && JSON.stringify(data.contract) !== JSON.stringify(data.contracts)) {
        throw new Error(`${systemName}: conflicting contract and contracts`);
    }
    const explicit = data.contract ?? data.contracts;
    if (explicit !== undefined) {
        if (!isObject(explicit) || !Array.isArray(explicit.provides) || !Array.isArray(explicit.requires)) {
            throw new Error(`${systemName}: explicit contract requires provides/requires arrays`);
        }
        for (const field of ['provides', 'requires']) {
            if (explicit[field].some(item => !(typeof item === 'string' && item.trim()) && !(isObject(item) && Object.keys(item).length))) {
                throw new Error(`${systemName}: contract ${field} entries must be nonempty strings or objects`);
            }
        }
        return explicit;
    }
    if (strict) throw new Error(`${systemName}: explicit contract provides/requires required`);
    const provides = [];
    const requires = [];

    // Domain-specific provides
    switch (domain) {
        case 'ingame':
            provides.push(`void Start${sanitizeNodeId(systemName)}()`);
            provides.push(`void End${sanitizeNodeId(systemName)}()`);
            provides.push(`${sanitizeNodeId(systemName)}State GetCurrentState()`);
            break;
        case 'outgame':
            provides.push(`void Add${sanitizeNodeId(systemName)}(string itemId, int count)`);
            provides.push(`bool Has${sanitizeNodeId(systemName)}(string itemId)`);
            provides.push(`List<${sanitizeNodeId(systemName)}Data> GetAll()`);
            requires.push('EventManager.OnDataLoaded');
            break;
        case 'balance':
            provides.push(`float Calculate(float baseValue, int level)`);
            provides.push(`BalanceConfig GetConfig()`);
            break;
        case 'content':
            provides.push(`void UnlockContent(string contentId)`);
            provides.push(`bool IsContentUnlocked(string contentId)`);
            provides.push(`ContentData GetCurrentContent()`);
            requires.push('EventManager.OnPlayerLevelUp');
            break;
        case 'bm':
            provides.push(`void ShowShop()`);
            provides.push(`void PurchaseItem(string productId)`);
            requires.push('EventManager.OnPurchaseComplete');
            break;
        case 'ux':
            provides.push(`void ShowUI(string panelId)`);
            provides.push(`void HideUI(string panelId)`);
            provides.push(`void PlayEffect(string effectId)`);
            break;
        case 'social':
            provides.push(`void FetchPlayerData(string userId)`);
            provides.push(`void SyncRanking()`);
            break;
        case 'meta':
            provides.push(`void UnlockAchievement(string achievementId)`);
            provides.push(`bool IsUnlocked(string achievementId)`);
            break;
        default:
            provides.push(`void Initialize()`);
            provides.push(`void Dispose()`);
    }

    return { provides, requires };
}

function buildLogicFlow(domain, systemName) {
    const steps = [];
    const node = sanitizeNodeId(systemName);

    switch (domain) {
        case 'ingame':
            steps.push({ step: 1, tag: 'StateControl', action: 'Initialize system state and register event listeners', next: 2 });
            steps.push({ step: 2, tag: 'FlowControl', action: `Subscribe to game loop events (OnBattleStart, OnBattleEnd)`, next: 3 });
            steps.push({ step: 3, tag: 'ResponseTrigger', action: `On trigger: update state, calculate results, fire output events`, next: null });
            break;
        case 'outgame':
            steps.push({ step: 1, tag: 'DataSync', action: 'Load saved data from persistence layer on Awake', next: 2 });
            steps.push({ step: 2, tag: 'StateControl', action: 'Initialize internal collections and indexes', next: 3 });
            steps.push({ step: 3, tag: 'ResponseTrigger', action: 'Expose CRUD API to other systems via events', next: null });
            break;
        case 'balance':
            steps.push({ step: 1, tag: 'DataSync', action: 'Load balance config from ScriptableObject or JSON', next: 2 });
            steps.push({ step: 2, tag: 'Calculate', action: 'Apply formula: baseValue × growthCurve(level)', next: 3 });
            steps.push({ step: 3, tag: 'Notify', action: 'Return calculated value or fire OnBalanceUpdated event', next: null });
            break;
        case 'content':
            steps.push({ step: 1, tag: 'StateControl', action: 'Track unlocked content set via persistent storage', next: 2 });
            steps.push({ step: 2, tag: 'ConditionCheck', action: 'Check unlock conditions (level, quest, prerequisite)', next: 3 });
            steps.push({ step: 3, tag: 'ResponseTrigger', action: 'Fire OnContentUnlocked event and update UI', next: null });
            break;
        case 'bm':
            steps.push({ step: 1, tag: 'FlowControl', action: 'Register product catalog on Initialize', next: 2 });
            steps.push({ step: 2, tag: 'Validate', action: 'Validate purchase: product exists, sufficient currency', next: 3 });
            steps.push({ step: 3, tag: 'ResourceTransfer', action: 'Process transaction and fire OnPurchaseComplete', next: null });
            break;
        case 'ux':
            steps.push({ step: 1, tag: 'StateControl', action: 'Initialize UI panel registry on Awake', next: 2 });
            steps.push({ step: 2, tag: 'Assign', action: 'Bind SerializeField references, set initial visibility', next: 3 });
            steps.push({ step: 3, tag: 'ResponseTrigger', action: 'Respond to show/hide events via EventManager', next: null });
            break;
        default:
            steps.push({ step: 1, tag: 'StateControl', action: 'Initialize and register with EventManager', next: 2 });
            steps.push({ step: 2, tag: 'FlowControl', action: 'Subscribe to relevant game events', next: 3 });
            steps.push({ step: 3, tag: 'ResponseTrigger', action: 'Execute domain logic and notify dependents', next: null });
    }

    return steps;
}

function buildReferencePatterns(domain, role) {
    const patterns = [];

    if (role === 'Manager') {
        patterns.push({ source: 'Core', pattern: 'Singleton<T> inheritance' });
        patterns.push({ source: 'Core', pattern: 'EventManager subscribe/publish' });
    }
    if (role === 'Calculator' || role === 'Processor') {
        patterns.push({ source: 'Domain', pattern: 'Stateless calculation with config injection' });
        patterns.push({ source: 'Domain', pattern: 'ScriptableObject for balance config' });
    }
    if (domain === 'ux') {
        patterns.push({ source: 'Game', pattern: '[SerializeField] UI reference binding' });
        patterns.push({ source: 'Game', pattern: 'DOTween or coroutine for animations' });
    }

    return patterns;
}

// ============================================================
// System Spec Generation
// ============================================================

function buildSystemSpec(nodes, project, genre) {
    const systemList = { Core: [], Domain: [], Game: [] };
    const systems = [];

    for (const node of nodes) {
        const layer = node.layer || 'Domain';
        if (systemList[layer]) systemList[layer].push(node.nodeId);
        else systemList['Domain'].push(node.nodeId);

        systems.push({
            nodeId: node.nodeId,
            layer,
            genre: node.genre || genre,
            role: node.role,
            purpose: node.purpose,
            responsibilities: node.responsibilities || [],
            states: node.states || [],
            behaviors: node.behaviors || [],
            contract: node.contract,
            logicFlow: node.logicFlow,
            generation_assumptions: node.generation_assumptions,
            ...(node.flow_trace ? { flow_trace: node.flow_trace } : {}),
            relations: node.relations || { uses: [], usedBy: [], publishes: [], subscribes: [] },
        });
    }

    return { system_list: systemList, systems };
}

function buildBuildOrder(nodes) {
    const phases = {};
    for (const node of nodes) {
        const phase = node.phase || 1;
        if (!phases[phase]) phases[phase] = [];
        phases[phase].push(node.nodeId);
    }
    return { phases };
}

// ============================================================
// File Writing
// ============================================================

function writeYamlFile(filePath, data, comment = '') {
    ensureDir(path.dirname(filePath));
    let content = '';
    if (comment) content += `# ${comment}\n`;
    content += serializeYaml(data);
    fs.writeFileSync(filePath, content, 'utf-8');
}

// ============================================================
// Main Processing
// ============================================================

function processDesignElements(elements, project, genre, options = {}) {
    const { strict = false } = options;
    const nodes = [];
    const seenNodes = new Set();
    function add(data, file, fixedDomain, suffix = '') {
        if (strict && !isObject(data)) throw new Error(file + ': expected a system object');
        const name = typeof data === 'string' ? data : (data.nodeId || data.name || data.id || data.system || path.basename(file, path.extname(file)));
        const nodeId = data.nodeId || (sanitizeNodeId(name) + suffix);
        if (typeof nodeId !== 'string' || !/^[A-Za-z][A-Za-z0-9_]*$/.test(nodeId)) {
            throw new Error(file + ': invalid nodeId ' + nodeId);
        }
        // Output is consumed on Windows too; distinct C# casing must not overwrite one YAML file.
        const outputKey = strict ? nodeId.toLowerCase() : nodeId;
        if (seenNodes.has(outputKey)) {
            if (strict) throw new Error('Duplicate nodeId: ' + nodeId);
            return;
        }
        seenNodes.add(outputKey);
        const domain = fixedDomain || data.domain || inferDomainFromName(name);
        const role = data.role || inferRoleFromSystem(name, domain);
        const contract = buildContract(name, domain, data, strict);
        nodes.push(buildNode(nodeId, name, domain, role, genre, data, contract, options));
    }
    for (const { file, data } of elements.systems) {
        if (strict && !isObject(data)) throw new Error(file + ': expected a design object');
        const systemList = data.systems ?? data.system_list;
        if (systemList !== undefined && strict && !Array.isArray(systemList)) {
            throw new Error(file + ': systems must be an array');
        }
        if (Array.isArray(systemList) && systemList.length) {
            for (const sys of systemList) add(sys, file);
        } else if (systemList === undefined || !strict) {
            add(data, file);
        }
    }
    for (const [key, domain, suffix] of [['balance', 'balance', 'Calculator'], ['content', 'content', 'Manager'], ['bm', 'bm', 'Manager']]) {
        for (const { file, data } of elements[key]) add(data, file, domain, suffix);
    }
    if (nodes.length === 0) {
        if (strict) throw new Error('No explicit design nodes; default game generation is disabled');
        console.warn('No design nodes found; generating unverified domain templates.');
        for (const [domain, systems] of Object.entries(DOMAIN_TO_CODE_SYSTEMS)) {
            for (const sys of systems) {
                const nodeId = sys + 'Manager';
                const contract = buildContract(nodeId, domain, {});
                nodes.push(buildNode(nodeId, sys, domain, DOMAIN_TO_ROLE[domain] || 'Manager', genre, {}, contract));
            }
        }
    }
    return nodes;
}

function inferDomainFromName(name) {
    const lower = name.toLowerCase();
    if (/battle|combat|fight|skill|stage|dungeon/.test(lower)) return 'ingame';
    if (/inventory|shop|item|equipment|gear/.test(lower)) return 'outgame';
    if (/balance|calculator|formula|stat|growth/.test(lower)) return 'balance';
    if (/quest|content|reward|mission|chapter/.test(lower)) return 'content';
    if (/bm|iap|purchase|monetization|payment/.test(lower)) return 'bm';
    if (/ui|panel|screen|view|audio|sound/.test(lower)) return 'ux';
    if (/guild|social|ranking|friend|pvp/.test(lower)) return 'social';
    if (/achievement|collection|trophy/.test(lower)) return 'meta';
    if (/live|event|season|pass/.test(lower)) return 'liveops';
    return 'ingame';
}

function buildNode(nodeId, systemName, domain, role, genre, sourceData, contract, options = {}) {
    const { strict = false } = options;
    const layer = sourceData.layer || DOMAIN_LAYER[domain] || 'Domain';
    const phase = sourceData.phase ?? DOMAIN_PHASE[domain] ?? 1;
    for (const field of ['logicFlow', 'behaviors']) {
        if (strict && (!Array.isArray(sourceData[field]) || sourceData[field].length === 0)) {
            throw new Error(`${nodeId}: explicit nonempty ${field} required`);
        }
        if (strict && sourceData[field].some(item => !isObject(item) || typeof item.action !== 'string' || !item.action.trim())) {
            throw new Error(`${nodeId}: ${field} entries must be objects with a nonempty action`);
        }
    }
    const logicFlow = sourceData.logicFlow ?? buildLogicFlow(domain, nodeId);
    const refPatterns = sourceData.referencePatterns ?? (strict ? [] : buildReferencePatterns(domain, role));
    const codeHints = sourceData.codeHints ?? (strict ? {} : {
        patterns: [role_to_hint(role)],
        avoidPatterns: ['Find() / FindObjectOfType()', 'new GameObject() for UI', 'Magic numbers'],
    });
    const generation_assumptions = [];
    for (const field of ['contract', 'logicFlow', 'behaviors', 'referencePatterns', 'codeHints']) {
        const missing = field === 'contract' ? sourceData.contract == null && sourceData.contracts == null
            : field === 'behaviors' ? !Array.isArray(sourceData.behaviors) : sourceData[field] == null;
        if (missing && (!strict || !['referencePatterns', 'codeHints'].includes(field))) {
            generation_assumptions.push({ field, reason: 'domain_template', basis: 'proposed', verification: 'untested' });
        }
    }
    for (const field of ['layer', 'phase', 'role', 'purpose', 'responsibilities']) {
        if (sourceData[field] === undefined && !(field === 'purpose' && sourceData.description !== undefined)) {
            generation_assumptions.push({ field, reason: 'domain_template', basis: 'proposed', verification: 'untested' });
        }
    }

    const behaviors = [];
    if (sourceData.behaviors && Array.isArray(sourceData.behaviors)) {
        behaviors.push(...sourceData.behaviors);
    } else {
        behaviors.push({ trigger: 'OnAwake', action: 'Initialize', result: 'System ready' });
    }

    return {
        nodeId,
        layer,
        genre: genre || 'Generic',
        role,
        purpose: sourceData.purpose || sourceData.description || `${systemName} 시스템 관리`,
        phase,
        domain,
        responsibilities: sourceData.responsibilities || [`${systemName} 로직 처리`],
        states: sourceData.states || [],
        behaviors,
        relations: {
            uses: sourceData.uses || (sourceData.relations && sourceData.relations.uses) || [],
            usedBy: sourceData.usedBy || (sourceData.relations && sourceData.relations.usedBy) || [],
            publishes: sourceData.publishes || (sourceData.relations && sourceData.relations.publishes) || [],
            subscribes: sourceData.subscribes || (sourceData.relations && sourceData.relations.subscribes) || [],
        },
        contract,
        logicFlow,
        referencePatterns: refPatterns,
        codeHints,
        generation_assumptions,
    };
}

// Map domain → layer (used in buildNode)
const DOMAIN_LAYER = {
    ingame:  'Domain',
    outgame: 'Domain',
    balance: 'Domain',
    content: 'Domain',
    bm:      'Domain',
    ux:      'Game',
    social:  'Domain',
    meta:    'Domain',
    liveops: 'Domain',
};

// ============================================================
// Entry Point
// ============================================================

function loadFlowContext(args) {
    const candidate = args.flowContract || path.join(args.output, 'flow-contract.json');
    if (!args.flowContract && !fs.existsSync(candidate)) return null;
    const contractPath = path.resolve(candidate);
    const content = fs.readFileSync(contractPath, 'utf8');
    const contract = JSON.parse(content.replace(/^\uFEFF/, ''));
    const { validateContract, sha256 } = require('./lib/flow-contract');
    const result = validateContract(contract, { stage: 'handoff', baseDir: path.dirname(contractPath) });
    if (!result.ok) throw new Error(`Flow contract validation failed: ${JSON.stringify(result.errors)}`);
    if (contract.project !== args.project) throw new Error('Flow contract project does not match --project');
    return { contract, contractPath, hash: sha256(content), content };
}

function attachFlowTrace(nodes, context) {
    const contract = context.contract;
    const requirements = new Map(contract.requirements.map(item => [item.id, item]));
    const nodeIds = new Set(nodes.map(node => node.nodeId));
    for (const item of contract.work_items) {
        for (const id of item.node_ids || []) {
            if (!nodeIds.has(id)) throw new Error(`Work item ${item.id}: unknown node ${id}`);
        }
    }
    for (const node of nodes) {
        const items = contract.work_items.filter(item => (item.node_ids || []).includes(node.nodeId));
        const requirementIds = [...new Set(items.flatMap(item => item.requirement_ids || []))];
        if (!requirementIds.length) throw new Error(`${node.nodeId}: no work item requirement mapping`);
        const linked = requirementIds.map(id => {
            if (!requirements.has(id)) throw new Error(`${node.nodeId}: unknown requirement ${id}`);
            return requirements.get(id);
        });
        const ids = key => [...new Set(linked.flatMap(item => item[key] || []))];
        const decisions = (contract.decisions || []).filter(item => ids('decision_ids').includes(item.id));
        const claimIds = [...new Set([...ids('claim_ids'), ...decisions.flatMap(item => item.claim_ids || [])])];
        const sourceIds = [...new Set((contract.claims || []).filter(item => claimIds.includes(item.id)).map(item => item.reference_id).filter(Boolean))];
        node.flow_trace = {
            contract_path: context.contractPath,
            contract_sha256: context.hash,
            snapshot_path: 'flow-contract.snapshot.json',
            work_item_ids: items.map(item => item.id),
            requirement_ids: requirementIds,
            goal_ids: ids('goal_ids'),
            claim_ids: claimIds,
            source_ids: sourceIds,
            decision_ids: ids('decision_ids'),
            acceptance_ids: ids('acceptance_ids'),
        };
    }
}

function main(argv = process.argv.slice(2)) {
    const args = parseArgs(argv);

    if (args.help || !args.project || !args.input || !args.output) {
        printUsage();
        if (!args.help) {
            console.error('오류: --project, --input, --output 가 필요합니다.');
            throw new Error('--project, --input, --output are required');
        }
        return;
    }

    const { project, input: inputDir, output: outputDir } = args;

    if (!fs.existsSync(inputDir)) {
        console.error(`오류: 입력 폴더가 없습니다: ${inputDir}`);
        console.error(`  design_workflow/ 폴더가 존재하는지 확인하세요.`);
        console.error(`  예: E:/AI/projects/${project}/designs/design_workflow`);
        throw new Error('Input folder does not exist');
    }

    console.log('='.repeat(60));
    console.log(`Design to Code Bridge`);
    console.log(`Project: ${project}`);
    console.log(`Input:   ${inputDir}`);
    console.log(`Output:  ${outputDir}`);
    console.log('='.repeat(60));

    const flowContext = loadFlowContext(args);
    const strict = !!flowContext;
    // Collect design elements
    console.log('\n기획 데이터 수집 중...');
    const elements = collectDesignElements(inputDir, strict);

    console.log(`  systems: ${elements.systems.length}개`);
    console.log(`  balance: ${elements.balance.length}개`);
    console.log(`  content: ${elements.content.length}개`);
    console.log(`  bm:      ${elements.bm.length}개`);

    // Infer genre from first system file
    let genre = 'Generic';
    if (elements.systems.length > 0) {
        genre = inferGenre(elements.systems[0].data, project);
    }
    console.log(`  Genre:   ${genre}`);

    // Generate nodes
    console.log('\n코드 노드 생성 중...');
    const nodes = processDesignElements(elements, project, genre, { strict });
    if (flowContext) attachFlowTrace(nodes, flowContext);
    console.log(`  → ${nodes.length}개 노드 생성`);

    // Prepare output directories
    const nodesDir = path.join(outputDir, 'nodes');
    if (strict && fs.existsSync(nodesDir)) {
        const expected = new Set(nodes.map(node => `${node.nodeId}.yaml`));
        const stale = fs.readdirSync(nodesDir).filter(file => /\.ya?ml$/i.test(file) && !expected.has(file));
        if (stale.length) throw new Error(`Existing nodes are outside this handoff: ${stale.join(', ')}; explicit cleanup/archive needed`);
    }
    ensureDir(outputDir);
    ensureDir(nodesDir);
    if (flowContext) fs.writeFileSync(path.join(outputDir, 'flow-contract.snapshot.json'), flowContext.content, 'utf8');

    // Write system_spec.yaml
    const systemSpec = buildSystemSpec(nodes, project, genre);
    const systemSpecPath = path.join(outputDir, 'system_spec.yaml');
    writeYamlFile(systemSpecPath, systemSpec, `Auto-generated by design-to-code-bridge.js | Project: ${project}`);
    console.log(`\n저장됨: ${systemSpecPath}`);

    // Write build_order.yaml
    const buildOrder = buildBuildOrder(nodes);
    const buildOrderPath = path.join(outputDir, 'build_order.yaml');
    writeYamlFile(buildOrderPath, buildOrder, `Build order | Project: ${project}`);
    console.log(`저장됨: ${buildOrderPath}`);

    // Write individual node YAML files
    for (const node of nodes) {
        const nodeData = {
            metadata: {
                nodeId: node.nodeId,
                version: '1.0.0',
                phase: node.phase,
                role: node.role,
            },
            dependencies: {
                internal: node.relations.uses || [],
                external: [],
            },
            contract: node.contract,
            tags: {
                layer: node.layer,
                genre: node.genre,
                role: node.role,
                system: node.domain,
                majorFunctions: ['StateControl', 'FlowControl'],
                minorFunctions: ['Assign', 'Notify'],
            },
            logicFlow: node.logicFlow,
            behaviors: node.behaviors,
            generation_assumptions: node.generation_assumptions,
            ...(node.flow_trace ? { flow_trace: node.flow_trace } : {}),
            referencePatterns: node.referencePatterns,
            codeHints: node.codeHints,
        };

        const nodePath = path.join(nodesDir, `${node.nodeId}.yaml`);
        writeYamlFile(nodePath, nodeData, `Node: ${node.nodeId} | Layer: ${node.layer} | Role: ${node.role}`);
    }

    console.log(`저장됨: ${nodesDir}/ (${nodes.length}개 노드 파일)`);

    console.log('\n' + '='.repeat(60));
    console.log('완료 요약');
    console.log('='.repeat(60));
    console.log(`총 노드: ${nodes.length}개`);
    const byPhase = {};
    for (const n of nodes) {
        const p = n.phase || 1;
        byPhase[p] = (byPhase[p] || 0) + 1;
    }
    for (const [phase, count] of Object.entries(byPhase).sort()) {
        console.log(`  Phase ${phase}: ${count}개`);
    }
}

function role_to_hint(role) {
    const hints = {
        Manager:    'Singleton<T> 상속, EventManager 사용',
        Calculator: 'Stateless static methods 또는 ScriptableObject config 주입',
        Processor:  'Pipeline 패턴, 단계별 처리',
        Handler:    'EventManager.Subscribe() 사용',
        UX:         '[SerializeField] UI 참조, DOTween 애니메이션',
        Factory:    'Object Pool 패턴 사용',
        Provider:   'Lazy initialization, cache 구조',
    };
    return hints[role] || 'Singleton 또는 일반 클래스';
}

module.exports = { main, parseArgs, collectDesignElements, processDesignElements, buildSystemSpec, buildNode, buildContract, attachFlowTrace };
if (require.main === module) {
    try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
