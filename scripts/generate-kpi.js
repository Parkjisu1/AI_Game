#!/usr/bin/env node
/**
 * KPI & History Auto-Generator
 * 프로젝트 완료 후 KPI 보고서와 History 문서를 자동 생성
 *
 * Usage:
 *   node generate-kpi.js <프로젝트명>
 *   node generate-kpi.js DropTheCat
 *   node generate-kpi.js CarMatch --genre Puzzle
 */

const fs = require('fs');
const path = require('path');

// ============================================================
// Configuration
// ============================================================

const AI_ROOT = process.env.AI_ROOT || 'E:/AI';
const DB_ROOT = path.join(AI_ROOT, 'db');
const PROJECTS_ROOT = path.join(AI_ROOT, 'projects');
const HISTORY_ROOT = path.join(AI_ROOT, 'History');

const ROLES = ['Manager', 'Controller', 'Calculator', 'Processor', 'Handler',
    'Listener', 'Provider', 'Factory', 'Service', 'Validator', 'Converter',
    'Builder', 'Pool', 'State', 'Command', 'Observer', 'Helper', 'Wrapper',
    'Context', 'Config', 'UX', 'Component', 'Model', 'Data', 'View',
    'Interface', 'Enum', 'Base', 'Message', 'Table', 'Entity', 'StateHandler'];

const FEEDBACK_CATEGORIES = [
    'LOGIC.NULL_REF', 'LOGIC.OFF_BY_ONE', 'LOGIC.RACE_COND', 'LOGIC.WRONG_CALC',
    'PATTERN.API_MISMATCH', 'PATTERN.STRUCTURE', 'PATTERN.NAMING', 'PATTERN.DI',
    'CONTRACT.SIGNATURE_MISMATCH', 'CONTRACT.MISSING_METHOD',
    'PERF.GC_ALLOC', 'PERF.LOOP_OPT', 'PERF.CACHE', 'PERF.ASYNC',
    'READABLE.COMMENT', 'READABLE.FORMATTING', 'READABLE.COMPLEXITY',
    'SECURITY.INPUT_VALID', 'SECURITY.DATA_LEAK',
    'ROLE.WRONG_ROLE', 'ROLE.ROLE_VIOLATION',
];

// ============================================================
// CLI
// ============================================================

function parseArgs(argv) {
    const args = { project: null, genre: null };
    if (argv.length < 1) {
        console.log('Usage: node generate-kpi.js <프로젝트명> [--genre <genre>]');
        process.exit(1);
    }
    args.project = argv[0];
    for (let i = 1; i < argv.length; i++) {
        if (argv[i] === '--genre') args.genre = argv[++i];
    }
    return args;
}

// ============================================================
// Data Collection
// ============================================================

function safeReadJson(filePath) {
    try {
        if (!fs.existsSync(filePath)) return null;
        return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    } catch { return null; }
}

function safeReadDir(dirPath) {
    try {
        if (!fs.existsSync(dirPath)) return [];
        return fs.readdirSync(dirPath);
    } catch { return []; }
}

function collectFeedbacks(projectPath) {
    const feedbackDir = path.join(projectPath, 'feedback');
    const files = safeReadDir(feedbackDir).filter(f => f.endsWith('.json'));
    const feedbacks = [];

    for (const file of files) {
        const data = safeReadJson(path.join(feedbackDir, file));
        if (data) feedbacks.push(data);
    }

    return feedbacks;
}

function collectOutputFiles(projectPath) {
    const outputDir = path.join(projectPath, 'output');
    const files = safeReadDir(outputDir).filter(f => f.endsWith('.cs'));
    return files.map(f => path.parse(f).name);
}

function collectDesignNodes(projectPath) {
    const nodesDir = path.join(projectPath, 'designs', 'nodes');
    const files = safeReadDir(nodesDir).filter(f => f.endsWith('.yaml') || f.endsWith('.yml'));
    return files.map(f => path.parse(f).name);
}

function countDbEntries(dbType, genre) {
    const counts = { total: 0, byLayer: {}, byRole: {}, byScore: { '0.0-0.3': 0, '0.4-0.5': 0, '0.6-0.7': 0, '0.8-1.0': 0 } };

    if (dbType === 'expert') {
        const entries = safeReadJson(path.join(DB_ROOT, 'expert', 'index.json')) || [];
        counts.total = entries.length;
        for (const e of entries) {
            counts.byRole[e.role] = (counts.byRole[e.role] || 0) + 1;
            counts.byLayer[e.layer] = (counts.byLayer[e.layer] || 0) + 1;
            const score = e.score || 0.4;
            if (score <= 0.3) counts.byScore['0.0-0.3']++;
            else if (score <= 0.5) counts.byScore['0.4-0.5']++;
            else if (score <= 0.7) counts.byScore['0.6-0.7']++;
            else counts.byScore['0.8-1.0']++;
        }
        return counts;
    }

    // Base DB
    const genres = genre ? [genre.toLowerCase()] : safeReadDir(path.join(DB_ROOT, 'base'));
    for (const g of genres) {
        const layers = ['core', 'domain', 'game'];
        for (const layer of layers) {
            const entries = safeReadJson(path.join(DB_ROOT, 'base', g, layer, 'index.json')) || [];
            const key = `${g}/${layer}`;
            counts.byLayer[key] = entries.length;
            counts.total += entries.length;
            for (const e of entries) {
                counts.byRole[e.role] = (counts.byRole[e.role] || 0) + 1;
                const score = e.score || 0.4;
                if (score <= 0.3) counts.byScore['0.0-0.3']++;
                else if (score <= 0.5) counts.byScore['0.4-0.5']++;
                else if (score <= 0.7) counts.byScore['0.6-0.7']++;
                else counts.byScore['0.8-1.0']++;
            }
        }
    }

    return counts;
}

function countRules() {
    const rulesDir = path.join(DB_ROOT, 'rules');
    let count = 0;
    for (const file of safeReadDir(rulesDir)) {
        if (file.endsWith('.json')) {
            const data = safeReadJson(path.join(rulesDir, file));
            if (Array.isArray(data)) count += data.length;
            else if (data) count++;
        }
    }
    return count;
}

// ============================================================
// KPI Report Generation
// ============================================================

function generateKPI(projectName, args) {
    const projectPath = path.join(PROJECTS_ROOT, projectName);
    const feedbacks = collectFeedbacks(projectPath);
    const outputFiles = collectOutputFiles(projectPath);
    const designNodes = collectDesignNodes(projectPath);
    const genre = args.genre || detectGenre(feedbacks) || 'Generic';
    const date = new Date().toISOString().split('T')[0];

    const baseCounts = countDbEntries('base', null);
    const expertCounts = countDbEntries('expert', null);
    const rulesCount = countRules();

    // === Feedback Analysis ===
    const totalFeedbacks = feedbacks.reduce((sum, f) => sum + (f.feedbacks ? f.feedbacks.length : 0), 0);
    const categoryDist = {};
    const nodeResults = {};

    for (const fb of feedbacks) {
        const nodeId = fb.nodeId || 'Unknown';
        if (!nodeResults[nodeId]) {
            nodeResults[nodeId] = { result: fb.validationResult, feedbackCount: 0, categories: [], score: fb.score || 0.4 };
        }
        nodeResults[nodeId].result = fb.validationResult;
        nodeResults[nodeId].score = fb.score || nodeResults[nodeId].score;

        if (fb.feedbacks) {
            nodeResults[nodeId].feedbackCount += fb.feedbacks.length;
            for (const item of fb.feedbacks) {
                const cat = item.category || 'OTHER';
                categoryDist[cat] = (categoryDist[cat] || 0) + 1;
                if (!nodeResults[nodeId].categories.includes(cat)) {
                    nodeResults[nodeId].categories.push(cat);
                }
            }
        }
    }

    // === DB Reference Analysis ===
    const dbRefCount = feedbacks.filter(f => f.dbReference && f.dbReference !== 'none').length;
    const expertRefCount = feedbacks.filter(f => f.dbReference === 'expert').length;
    const baseRefCount = feedbacks.filter(f => f.dbReference === 'base').length;
    const noRefCount = outputFiles.length - dbRefCount;
    const refRatio = outputFiles.length > 0 ? ((dbRefCount / outputFiles.length) * 100).toFixed(1) : '0.0';

    // === Expert Promotion ===
    const passCount = feedbacks.filter(f => f.validationResult === 'pass').length;
    const promotionRate = feedbacks.length > 0 ? ((passCount / feedbacks.length) * 100).toFixed(1) : '0.0';

    // === UX Nodes ===
    const uxNodes = outputFiles.filter(f =>
        f.endsWith('Effect') || f.endsWith('Tweener') || f.endsWith('Performer') ||
        f.endsWith('Presenter') || f.endsWith('Particle')
    );

    // === Role Distribution ===
    const roleDistribution = {};
    for (const file of outputFiles) {
        const role = classifyRole(file);
        roleDistribution[role] = (roleDistribution[role] || 0) + 1;
    }

    // === Build Report ===
    let report = `# ${projectName} KPI 보고서\n\n`;
    report += `## 프로젝트 기본 정보\n`;
    report += `| 항목 | 값 |\n|------|-----|\n`;
    report += `| 프로젝트명 | ${projectName} |\n`;
    report += `| 장르 | ${genre} |\n`;
    report += `| 보고 일자 | ${date} |\n`;
    report += `| 생성 노드 수 | ${outputFiles.length} |\n\n`;
    report += `---\n\n`;

    // Section 1: Debugging
    report += `## 1. 검증 결과 요약\n\n`;
    report += `| 노드명 | 검증 결과 | 피드백 수 | 점수 | 주요 카테고리 |\n`;
    report += `|--------|----------|----------|------|---------------|\n`;
    for (const [nodeId, info] of Object.entries(nodeResults)) {
        report += `| ${nodeId} | ${info.result || '-'} | ${info.feedbackCount} | ${info.score} | ${info.categories.slice(0, 2).join(', ') || '-'} |\n`;
    }
    report += `\n`;

    // Section 2: Feedback
    report += `## 2. 피드백 횟수\n\n`;
    report += `**총 피드백 수**: ${totalFeedbacks}\n\n`;
    if (Object.keys(categoryDist).length > 0) {
        report += `| 카테고리 | 횟수 | 비율 |\n|----------|------|------|\n`;
        const sortedCats = Object.entries(categoryDist).sort((a, b) => b[1] - a[1]);
        for (const [cat, count] of sortedCats) {
            const ratio = totalFeedbacks > 0 ? ((count / totalFeedbacks) * 100).toFixed(1) : '0.0';
            report += `| ${cat} | ${count} | ${ratio}% |\n`;
        }
    }
    report += `\n---\n\n`;

    // Section 3: DB Reference
    report += `## 3. 베이스 코드 편입 비율\n\n`;
    report += `| 항목 | 수치 |\n|------|------|\n`;
    report += `| 전체 생성 노드 수 | ${outputFiles.length} |\n`;
    report += `| DB 참조 사용 노드 수 | ${dbRefCount} |\n`;
    report += `| Expert DB 참조 | ${expertRefCount} |\n`;
    report += `| Base DB 참조 | ${baseRefCount} |\n`;
    report += `| 순수 생성 (참조 없음) | ${noRefCount} |\n`;
    report += `| **베이스 코드 편입 비율** | **${refRatio}%** |\n\n`;
    report += `---\n\n`;

    // Section 4: Dataset
    report += `## 4. 데이터셋 수\n\n`;
    report += `### Base Code DB\n`;
    report += `| 구분 | 수 |\n|------|----|\n`;
    for (const [key, count] of Object.entries(baseCounts.byLayer)) {
        report += `| ${key} | ${count} |\n`;
    }
    report += `| **합계** | **${baseCounts.total}** |\n\n`;

    report += `### Expert DB\n`;
    report += `| 항목 | 수치 |\n|------|------|\n`;
    report += `| Expert 코드 수 | ${expertCounts.total} |\n`;
    report += `| 승격률 | ${promotionRate}% |\n\n`;

    report += `### Rules DB\n`;
    report += `| 항목 | 수치 |\n|------|------|\n`;
    report += `| Rules 수 | ${rulesCount} |\n\n`;
    report += `---\n\n`;

    // Section 5: Score Distribution
    report += `## 5. 신뢰도 점수 분포\n\n`;
    report += `| 점수 구간 | Base DB | Expert DB |\n|-----------|---------|----------|\n`;
    for (const range of ['0.0-0.3', '0.4-0.5', '0.6-0.7', '0.8-1.0']) {
        report += `| ${range} | ${baseCounts.byScore[range]} | ${expertCounts.byScore[range]} |\n`;
    }
    report += `\n`;

    // Section 5.2: Role Distribution
    report += `### Role별 생성 코드 수\n`;
    report += `| Role | 수 |\n|------|----|\n`;
    const sortedRoles = Object.entries(roleDistribution).sort((a, b) => b[1] - a[1]);
    for (const [role, count] of sortedRoles) {
        report += `| ${role} | ${count} |\n`;
    }
    report += `\n---\n\n`;

    // Section 6: UX
    report += `## 6. UX 연출 항목\n\n`;
    if (uxNodes.length > 0) {
        report += `| 노드명 | Role |\n|--------|------|\n`;
        for (const node of uxNodes) {
            report += `| ${node} | UX |\n`;
        }
    } else {
        report += `UX 노드 없음\n`;
    }
    report += `\n---\n\n`;

    // Section 7: Summary
    report += `## 7. 종합 요약\n\n`;
    report += `| KPI 지표 | 수치 |\n|----------|------|\n`;
    report += `| 총 피드백 횟수 | ${totalFeedbacks} |\n`;
    report += `| 베이스 코드 편입 비율 | ${refRatio}% |\n`;
    report += `| 데이터셋 총 수 (Base) | ${baseCounts.total} |\n`;
    report += `| 데이터셋 총 수 (Expert) | ${expertCounts.total} |\n`;
    report += `| Expert 승격률 | ${promotionRate}% |\n`;
    report += `| UX 노드 수 | ${uxNodes.length} |\n\n`;
    report += `---\n\n`;

    // Section 8: Notes
    report += `## 8. 개선 사항 / 특이 사항\n\n`;
    report += `### 반복 발생 이슈\n`;
    if (Object.keys(categoryDist).length > 0) {
        const topIssues = Object.entries(categoryDist).sort((a, b) => b[1] - a[1]).slice(0, 3);
        for (const [cat, count] of topIssues) {
            report += `- ${cat}: ${count}회\n`;
        }
    } else {
        report += `- 없음\n`;
    }
    report += `\n### 다음 프로젝트 적용 사항\n- (자동 생성 완료 후 수동 작성)\n`;

    return report;
}

// ============================================================
// History Generation
// ============================================================

function generateHistory(projectName, args) {
    const projectPath = path.join(PROJECTS_ROOT, projectName);
    const outputFiles = collectOutputFiles(projectPath);
    const feedbacks = collectFeedbacks(projectPath);
    const genre = args.genre || detectGenre(feedbacks) || 'Generic';
    const date = new Date().toISOString().split('T')[0];

    let history = `# ${projectName} 프로젝트 개발 히스토리\n\n`;
    history += `## 프로젝트 개요\n`;
    history += `- **프로젝트명**: ${projectName}\n`;
    history += `- **장르**: ${genre}\n`;
    history += `- **생성 일자**: ${date}\n`;
    history += `- **생성 노드 수**: ${outputFiles.length}\n\n`;
    history += `---\n\n`;

    // 생성 파일 목록
    history += `## 1. 생성된 파일 목록\n\n`;
    history += `| 파일명 | Role |\n|--------|------|\n`;
    for (const file of outputFiles.sort()) {
        const role = classifyRole(file);
        history += `| ${file}.cs | ${role} |\n`;
    }
    history += `\n---\n\n`;

    // 검증 결과
    history += `## 2. 검증 히스토리\n\n`;
    if (feedbacks.length > 0) {
        history += `| 노드명 | 결과 | 점수 | 피드백 수 | 타임스탬프 |\n`;
        history += `|--------|------|------|----------|------------|\n`;
        for (const fb of feedbacks) {
            const ts = fb.timestamp || '-';
            const fbCount = fb.feedbacks ? fb.feedbacks.length : 0;
            history += `| ${fb.nodeId || '-'} | ${fb.validationResult || '-'} | ${fb.score || 0.4} | ${fbCount} | ${ts} |\n`;
        }
    } else {
        history += `검증 기록 없음\n`;
    }
    history += `\n---\n\n`;

    // 이슈 및 해결
    history += `## 3. 주요 이슈 및 해결\n\n`;
    const errorFeedbacks = feedbacks.filter(f => f.validationResult === 'fail');
    if (errorFeedbacks.length > 0) {
        for (const fb of errorFeedbacks) {
            history += `### ${fb.nodeId || 'Unknown'}\n`;
            if (fb.feedbacks) {
                for (const item of fb.feedbacks) {
                    history += `- **[${item.severity || 'warning'}]** ${item.category || '-'}: ${item.description || '-'}\n`;
                    if (item.suggestion) {
                        history += `  - 해결: ${item.suggestion}\n`;
                    }
                }
            }
            history += `\n`;
        }
    } else {
        history += `특이 이슈 없음\n`;
    }
    history += `\n---\n\n`;

    // 프로젝트 구조
    history += `## 4. 출력 구조\n\n`;
    history += `\`\`\`\n`;
    history += `E:\\AI\\projects\\${projectName}\\output\\\n`;
    for (const file of outputFiles.sort()) {
        history += `├── ${file}.cs\n`;
    }
    history += `\`\`\`\n`;

    return history;
}

// ============================================================
// Helpers
// ============================================================

function detectGenre(feedbacks) {
    const genres = {};
    for (const fb of feedbacks) {
        if (fb.genre) {
            genres[fb.genre] = (genres[fb.genre] || 0) + 1;
        }
    }
    if (Object.keys(genres).length > 0) {
        return Object.entries(genres).sort((a, b) => b[1] - a[1])[0][0];
    }
    return null;
}

function classifyRole(fileName) {
    const patterns = {
        'Manager': /Manager$/,
        'Controller': /Controller$/,
        'Calculator': /Calculator$|Calc$/,
        'Processor': /Processor$/,
        'Handler': /Handler$/,
        'Listener': /Listener$/,
        'Provider': /Provider$/,
        'Factory': /Factory$/,
        'Service': /Service$/,
        'Validator': /Validator$/,
        'Converter': /Converter$/,
        'Builder': /Builder$/,
        'Pool': /Pool$|Pooler$/,
        'State': /State$/,
        'Command': /Command$|Cmd$/,
        'Observer': /Observer$/,
        'Helper': /Helper$|Util$|Utils$/,
        'Wrapper': /Wrapper$/,
        'Context': /Context$|Ctx$/,
        'Config': /Config$|Settings$/,
        'UX': /Effect$|Tweener$|Performer$|Presenter$|Particle$/,
        'View': /Page$|Popup$|Win$|Window$|Panel$|Dialog$/,
        'Data': /Data$|Info$|DTO$/,
    };

    for (const [role, pattern] of Object.entries(patterns)) {
        if (pattern.test(fileName)) return role;
    }
    return 'Component';
}

// ============================================================
// Main
// ============================================================

function main() {
    const args = parseArgs(process.argv.slice(2));
    const projectName = args.project;

    // Ensure History/{ProjectName} directory exists
    const projectHistoryDir = path.join(HISTORY_ROOT, projectName);
    if (!fs.existsSync(projectHistoryDir)) {
        fs.mkdirSync(projectHistoryDir, { recursive: true });
    }

    console.log(`\nGenerating KPI and History for: ${projectName}`);
    console.log('='.repeat(50));

    // Generate KPI
    const kpi = generateKPI(projectName, args);
    const kpiPath = path.join(projectHistoryDir, 'KPI.md');
    fs.writeFileSync(kpiPath, kpi, 'utf-8');
    console.log(`KPI Report: ${kpiPath}`);

    // Generate History
    const history = generateHistory(projectName, args);
    const historyPath = path.join(projectHistoryDir, 'Project_History.md');
    fs.writeFileSync(historyPath, history, 'utf-8');
    console.log(`History: ${historyPath}`);

    console.log('='.repeat(50));
    console.log('Done!\n');
}

main();
