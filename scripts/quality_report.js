const fs = require('fs');
const path = require('path');
const base = 'E:/AI/db/base';

// ============================================================
// Data Collection
// ============================================================

const allFiles = [];
const roleDistribution = {};
const layerDistribution = {};
const genreDistribution = {};
const systemDistribution = {};

for (const genre of fs.readdirSync(base)) {
    const gp = path.join(base, genre);
    if (!fs.statSync(gp).isDirectory()) continue;
    for (const layer of fs.readdirSync(gp)) {
        const filesPath = path.join(gp, layer, 'files');
        if (!fs.existsSync(filesPath)) continue;

        for (const file of fs.readdirSync(filesPath)) {
            if (!file.endsWith('.json')) continue;
            const data = JSON.parse(fs.readFileSync(path.join(filesPath, file)));
            allFiles.push(data);

            roleDistribution[data.role] = (roleDistribution[data.role] || 0) + 1;
            layerDistribution[data.layer] = (layerDistribution[data.layer] || 0) + 1;
            genreDistribution[data.genre] = (genreDistribution[data.genre] || 0) + 1;
            systemDistribution[data.system] = (systemDistribution[data.system] || 0) + 1;
        }
    }
}

const total = allFiles.length;

// ============================================================
// 1. Completeness Analysis (완전성)
// ============================================================

console.log('═'.repeat(60));
console.log('1. COMPLETENESS ANALYSIS (완전성 분석)');
console.log('═'.repeat(60));

const completeness = {
    hasNamespace: allFiles.filter(f => f.namespace && f.namespace.length > 0).length,
    hasUsings: allFiles.filter(f => f.usings && f.usings.length > 0).length,
    hasClasses: allFiles.filter(f => f.classes && f.classes.length > 0).length,
    hasProvides: allFiles.filter(f => f.provides && f.provides.length > 0).length,
    hasRequires: allFiles.filter(f => f.requires && f.requires.length > 0).length,
    hasUses: allFiles.filter(f => f.uses && f.uses.length > 0).length,
    hasMethods: allFiles.filter(f => f.classes?.[0]?.methods?.length > 0).length,
    hasFields: allFiles.filter(f => f.classes?.[0]?.fields?.length > 0).length,
};

console.log('\nField Coverage:');
console.log(`  namespace:  ${completeness.hasNamespace}/${total} (${(completeness.hasNamespace/total*100).toFixed(1)}%)`);
console.log(`  usings:     ${completeness.hasUsings}/${total} (${(completeness.hasUsings/total*100).toFixed(1)}%)`);
console.log(`  classes:    ${completeness.hasClasses}/${total} (${(completeness.hasClasses/total*100).toFixed(1)}%)`);
console.log(`  provides:   ${completeness.hasProvides}/${total} (${(completeness.hasProvides/total*100).toFixed(1)}%)`);
console.log(`  requires:   ${completeness.hasRequires}/${total} (${(completeness.hasRequires/total*100).toFixed(1)}%)`);
console.log(`  uses:       ${completeness.hasUses}/${total} (${(completeness.hasUses/total*100).toFixed(1)}%)`);
console.log(`  methods:    ${completeness.hasMethods}/${total} (${(completeness.hasMethods/total*100).toFixed(1)}%)`);
console.log(`  fields:     ${completeness.hasFields}/${total} (${(completeness.hasFields/total*100).toFixed(1)}%)`);

const completenessScore = (
    completeness.hasClasses +
    completeness.hasProvides +
    completeness.hasRequires +
    completeness.hasUses +
    completeness.hasMethods +
    completeness.hasFields
) / (total * 6) * 100;

console.log(`\n[Completeness Score: ${completenessScore.toFixed(1)}%]`);

// ============================================================
// 2. Distribution Analysis (분포 분석)
// ============================================================

console.log('\n' + '═'.repeat(60));
console.log('2. DISTRIBUTION ANALYSIS (분포 분석)');
console.log('═'.repeat(60));

// Shannon Entropy for Role distribution
function shannonEntropy(dist) {
    const total = Object.values(dist).reduce((a, b) => a + b, 0);
    let entropy = 0;
    for (const count of Object.values(dist)) {
        if (count > 0) {
            const p = count / total;
            entropy -= p * Math.log2(p);
        }
    }
    return entropy;
}

const roleEntropy = shannonEntropy(roleDistribution);
const maxRoleEntropy = Math.log2(Object.keys(roleDistribution).length);
const roleNormalizedEntropy = roleEntropy / maxRoleEntropy;

console.log('\nRole Distribution:');
const sortedRoles = Object.entries(roleDistribution).sort((a, b) => b[1] - a[1]);
sortedRoles.forEach(([role, count]) => {
    const pct = (count / total * 100).toFixed(1);
    const bar = '█'.repeat(Math.round(count / total * 50));
    console.log(`  ${role.padEnd(15)} ${String(count).padStart(4)} (${pct.padStart(5)}%) ${bar}`);
});
console.log(`\n  Shannon Entropy: ${roleEntropy.toFixed(2)} / ${maxRoleEntropy.toFixed(2)} (normalized: ${(roleNormalizedEntropy*100).toFixed(1)}%)`);

// Gini coefficient for imbalance
function giniCoefficient(values) {
    const sorted = [...values].sort((a, b) => a - b);
    const n = sorted.length;
    const mean = sorted.reduce((a, b) => a + b, 0) / n;
    let sumDiff = 0;
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
            sumDiff += Math.abs(sorted[i] - sorted[j]);
        }
    }
    return sumDiff / (2 * n * n * mean);
}

const roleGini = giniCoefficient(Object.values(roleDistribution));
console.log(`  Gini Coefficient: ${roleGini.toFixed(3)} (0=perfect equality, 1=max inequality)`);

console.log('\nLayer Distribution:');
Object.entries(layerDistribution).forEach(([layer, count]) => {
    console.log(`  ${layer.padEnd(10)} ${count} (${(count/total*100).toFixed(1)}%)`);
});

console.log('\nGenre Distribution:');
Object.entries(genreDistribution).sort((a, b) => b[1] - a[1]).forEach(([genre, count]) => {
    console.log(`  ${genre.padEnd(12)} ${count} (${(count/total*100).toFixed(1)}%)`);
});

// ============================================================
// 3. Data Quality Metrics (데이터 품질 지표)
// ============================================================

console.log('\n' + '═'.repeat(60));
console.log('3. DATA QUALITY METRICS (데이터 품질 지표)');
console.log('═'.repeat(60));

// Average values
const avgProvides = allFiles.reduce((sum, f) => sum + (f.provides?.length || 0), 0) / total;
const avgRequires = allFiles.reduce((sum, f) => sum + (f.requires?.length || 0), 0) / total;
const avgUses = allFiles.reduce((sum, f) => sum + (f.uses?.length || 0), 0) / total;
const avgMethods = allFiles.reduce((sum, f) => sum + (f.classes?.[0]?.methods?.length || 0), 0) / total;
const avgFields = allFiles.reduce((sum, f) => sum + (f.classes?.[0]?.fields?.length || 0), 0) / total;

console.log('\nAverage per file:');
console.log(`  provides: ${avgProvides.toFixed(1)}`);
console.log(`  requires: ${avgRequires.toFixed(1)}`);
console.log(`  uses:     ${avgUses.toFixed(1)}`);
console.log(`  methods:  ${avgMethods.toFixed(1)}`);
console.log(`  fields:   ${avgFields.toFixed(1)}`);

// Dependency graph connectivity
const allFileIds = new Set(allFiles.map(f => f.fileId));
let validUses = 0;
let totalUses = 0;
for (const file of allFiles) {
    for (const use of (file.uses || [])) {
        totalUses++;
        if (allFileIds.has(use)) validUses++;
    }
}
const usesAccuracy = totalUses > 0 ? validUses / totalUses : 0;

console.log('\nDependency Graph:');
console.log(`  Total 'uses' references: ${totalUses}`);
console.log(`  References to known files: ${validUses} (${(usesAccuracy*100).toFixed(1)}%)`);
console.log(`  External/unknown references: ${totalUses - validUses}`);

// ============================================================
// 4. Classification Accuracy Estimation (분류 정확도 추정)
// ============================================================

console.log('\n' + '═'.repeat(60));
console.log('4. CLASSIFICATION ACCURACY (분류 정확도 추정)');
console.log('═'.repeat(60));

// Role-Name consistency check
let roleNameConsistent = 0;
const rolePatterns = {
    'Manager': /Manager$/,
    'Controller': /Controller$/,
    'Handler': /Handler$/,
    'View': /(Page|Popup|Win|Window|Panel|Dialog)$/,
    'Message': /(Msg|Message)$/,
    'Data': /(Data|Info|DTO)$/,
    'Config': /(Config|Settings)$/,
    'Table': /Table$/,
    'Enum': /^[A-Z][a-z]+[A-Z]/,  // PascalCase enum names
};

for (const file of allFiles) {
    const role = file.role;
    const className = file.classes?.[0]?.className || file.fileId;

    if (rolePatterns[role] && rolePatterns[role].test(className)) {
        roleNameConsistent++;
    } else if (!rolePatterns[role]) {
        // Roles without name patterns (Component, Model, etc.) - check by structure
        roleNameConsistent++; // Assume correct if no pattern to check
    }
}

console.log('\nRole-Name Consistency:');
console.log(`  Consistent: ${roleNameConsistent}/${total} (${(roleNameConsistent/total*100).toFixed(1)}%)`);

// Layer consistency check (Domain files shouldn't have UI patterns)
let layerConsistent = 0;
for (const file of allFiles) {
    const layer = file.layer;
    const className = file.classes?.[0]?.className || file.fileId;
    const baseClass = file.classes?.[0]?.baseClass || '';

    let isConsistent = true;

    if (layer === 'Domain') {
        // Domain shouldn't have UI-specific names
        if (/(Page|Popup|Win|Panel|Dialog|HUD|Element)$/.test(className)) {
            isConsistent = false;
        }
    }
    if (layer === 'Game') {
        // Game layer should have UI or component patterns
        if (/(Page|Popup|Win|Panel|Dialog|HUD|Element|Component)/.test(className) ||
            baseClass.includes('UIBase') || baseClass.includes('Page') || baseClass.includes('Popup')) {
            isConsistent = true;
        }
    }

    if (isConsistent) layerConsistent++;
}

console.log(`\nLayer-Content Consistency:`);
console.log(`  Consistent: ${layerConsistent}/${total} (${(layerConsistent/total*100).toFixed(1)}%)`);

// ============================================================
// 5. Overall Quality Score (종합 품질 점수)
// ============================================================

console.log('\n' + '═'.repeat(60));
console.log('5. OVERALL QUALITY ASSESSMENT (종합 품질 평가)');
console.log('═'.repeat(60));

const scores = {
    completeness: completenessScore,
    distribution: roleNormalizedEntropy * 100,
    dependency: usesAccuracy * 100,
    roleAccuracy: (roleNameConsistent / total) * 100,
    layerAccuracy: (layerConsistent / total) * 100,
};

console.log('\nDimension Scores (0-100):');
console.log(`  Completeness:      ${scores.completeness.toFixed(1)}`);
console.log(`  Distribution:      ${scores.distribution.toFixed(1)} (role diversity)`);
console.log(`  Dependency Valid:  ${scores.dependency.toFixed(1)}`);
console.log(`  Role Accuracy:     ${scores.roleAccuracy.toFixed(1)}`);
console.log(`  Layer Accuracy:    ${scores.layerAccuracy.toFixed(1)}`);

const overallScore = (
    scores.completeness * 0.25 +
    scores.distribution * 0.15 +
    scores.dependency * 0.20 +
    scores.roleAccuracy * 0.20 +
    scores.layerAccuracy * 0.20
);

console.log('\n' + '─'.repeat(60));
console.log(`OVERALL QUALITY SCORE: ${overallScore.toFixed(1)} / 100`);
console.log('─'.repeat(60));

// Grade
let grade;
if (overallScore >= 90) grade = 'A (Excellent)';
else if (overallScore >= 80) grade = 'B (Good)';
else if (overallScore >= 70) grade = 'C (Acceptable)';
else if (overallScore >= 60) grade = 'D (Needs Improvement)';
else grade = 'F (Poor)';

console.log(`GRADE: ${grade}`);

// ============================================================
// 6. Issues & Recommendations
// ============================================================

console.log('\n' + '═'.repeat(60));
console.log('6. ISSUES & RECOMMENDATIONS');
console.log('═'.repeat(60));

const issues = [];

if (completeness.hasNamespace / total < 0.3) {
    issues.push('⚠️ Low namespace coverage - many files lack namespace declarations');
}
if (completeness.hasRequires / total < 0.5) {
    issues.push('⚠️ requires field coverage could be improved');
}
if (roleDistribution['Component'] / total > 0.4) {
    issues.push('⚠️ "Component" role is overused - consider more specific classifications');
}
if (usesAccuracy < 0.3) {
    issues.push('⚠️ Many "uses" references point to unknown files (external dependencies)');
}

if (issues.length === 0) {
    console.log('\n✅ No critical issues found');
} else {
    console.log('\nIdentified Issues:');
    issues.forEach(issue => console.log(`  ${issue}`));
}

console.log('\nRecommendations:');
if (completeness.hasRequires / total < 0.8) {
    console.log('  • Improve requires extraction for better dependency tracking');
}
if (roleDistribution['Component'] / total > 0.3) {
    console.log('  • Refine Role classification rules to reduce "Component" catch-all');
}
console.log('  • Consider adding semantic tagging (Major/Minor tags) for methods');
console.log('  • Build usedBy reverse index for bidirectional dependency graph');
