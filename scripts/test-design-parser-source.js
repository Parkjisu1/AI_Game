'use strict';

// All checks use in-memory fixtures. Loading the DB client is a test failure.
const assert = require('node:assert/strict');
const test = require('node:test');
const Module = require('node:module');
const originalLoad = Module._load;
Module._load = function (request, ...rest) {
    if (request === './lib/db-client' || request === 'mongodb') {
        throw new Error('Database access is forbidden in parser source tests');
    }
    return originalLoad.call(this, request, ...rest);
};
const parser = require('./design-parser');

const args = (extra = []) => parser.parseArgs(['--input', 'fixture.json', '--project', 'SourceTest', ...extra]);
const checkSources = (entries, expected) => {
    assert.deepEqual(entries.map(e => e.indexEntry.source), expected);
    assert.deepEqual(entries.map(e => e.detailFile.source), expected);
};

test('documented observed CLI source survives JSON conversion in index and detail', () => {
    checkSources(parser.convertJson({ name: 'tap', system: 'Input' }, args(['--source-type', 'observed'])), ['observed']);
});

test('source alias preserves arbitrary legacy source strings', () => {
    checkSources(parser.convertJson({ name: 'tap' }, args(['--source', 'legacy_partner_v2'])), ['legacy_partner_v2']);
});

test('explicit inferred/proposed sources override CLI default for single and array input', () => {
    const options = args(['--source-type', 'observed']);
    checkSources(parser.convertJson({ source: 'inferred' }, options), ['inferred']);
    checkSources(parser.convertJson([{ source: 'proposed' }, { source: 'observed' }], options), ['proposed', 'observed']);
});

test('multi-system input preserves per-system source then document source then CLI default', () => {
    const options = args(['--source-type', 'observed']);
    checkSources(parser.convertJson({ source: 'reference_document', systems: {
        ChangedRule: { source: 'proposed' }, OriginalRule: {},
    } }, options), ['proposed', 'reference_document']);
    checkSources(parser.convertJson({ systems: { DefaultRule: {} } }, options), ['observed']);
});

test('C10 source precedence is parameter then document then CLI, including primitive values', () => {
    const options = args(['--source-type', 'observed']);
    checkSources(parser.convertJson({ source: 'inferred', parameters: { combat: { value: 5 } } }, options), ['inferred', 'inferred']);
    checkSources(parser.convertJson({ source: 'observed', parameters: {
        combat: { value: 5, source: 'inferred' }, economy: { value: 7 },
    } }, options), ['inferred', 'inferred', 'observed', 'observed']);
    checkSources(parser.convertJson({ parameters: {
        combat: { value: 5, source: 'proposed' }, economy: 7,
    } }, options), ['proposed', 'proposed', 'observed', 'observed']);
});

test('CSV rows retain row source with CLI fallback', () => {
    const rows = parser.parseCsv('name,system,source\na,Input,proposed\nb,Input,');
    checkSources(parser.convertCsv(rows, args(['--source-type', 'observed'])), ['proposed', 'observed']);
});

test('Markdown importer uses observed CLI default', () => {
    checkSources(parser.convertMd(parser.parseMd('# Input\nTap triggers feedback.'), args(['--source-type', 'observed'])), ['observed']);
});

test('legacy imports without source retain internal_produced default', () => {
    checkSources(parser.convertJson({ name: 'legacy' }, args()), ['internal_produced']);
});

test('exporter-shaped reimport preserves parameter evidence and interpretation in canonical fields', () => {
    const input = {
        source: 'observed', system: 'Rules',
        content: {
            summary: 'Observation import', formula: '', flow: [], edge_cases: ['unreadable screen'],
            references: ['screen-1'], parameters: {
                P1: { name: 'limit', value: 7, confidence: 0.4, status: 'inferred',
                    sources: [{ observer: 1, notes: 'OCR' }], context: { build: 'fixture' } },
                P2: { name: 'missing', value: null, confidence: 0, status: 'not_observed', sources: [] },
            },
        },
        evidence_interpretation: { consensus: 'not_established_by_export' },
    };
    const detail = parser.convertJson(input, args())[0].detailFile;
    assert.deepEqual(detail.content, input.content);
    assert.deepEqual(detail.evidence_interpretation, input.evidence_interpretation);
    assert.deepEqual(JSON.parse(detail.versions[0].data), input);
    const flat = parser.convertJson({ ...input, summary: '', formula: 'flat', params: {},
        edge_cases: [], references: [] }, args())[0].detailFile;
    assert.deepEqual(flat.content, { summary: '', formula: 'flat', parameters: {}, edge_cases: [], references: [], flow: [] });
    assert.equal(parser.convertJson({ summary: 'flat', content: 'legacy text' }, args())[0].detailFile.content.summary, 'flat');
});

test('source typos, missing values and conflicting aliases fail before writes', () => {
    assert.throws(() => args(['--sorce-type', 'observed']), /Unknown argument/);
    assert.throws(() => args(['--source-type']), /Missing value/);
    assert.throws(() => args(['--source-type', '--mongo-only']), /Missing value/);
    assert.throws(() => args(['--source-type', '   ']), /Missing value/);
    assert.throws(() => args(['--source-type', 'observed', '--source', 'proposed']), /Conflicting/);
    assert.equal(args(['--source-type', 'observed', '--source', 'observed']).source, 'observed');
});
