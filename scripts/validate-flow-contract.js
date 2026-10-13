#!/usr/bin/env node
'use strict';
const fs = require('fs');
const path = require('path');
const {validateContract} = require('./lib/flow-contract');

function main(argv = process.argv.slice(2)) {
    const args = {stage: 'handoff'};
    for (let i = 0; i < argv.length; i++) {
        const key = argv[i];
        if (key === '--help') {
            console.log('node scripts/validate-flow-contract.js --input <json> --stage handoff|acceptance [--scope technical|behavior|art|experience|market]');
            return 0;
        }
        if (!['--input', '--stage', '--scope'].includes(key)) throw new Error(`Unknown option ${key}`);
        if (!argv[i + 1] || argv[i + 1].startsWith('--')) throw new Error(`Missing value for ${key}`);
        args[key.slice(2)] = argv[++i];
    }
    if (!args.input) throw new Error('--input is required');
    const file = path.resolve(args.input);
    const contract = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
    const result = validateContract(contract, {stage: args.stage, scope: args.scope, baseDir: path.dirname(file)});
    console.log(JSON.stringify(result, null, 2));
    return result.ok ? 0 : 1;
}
if (require.main === module) {
    try { process.exitCode = main(); }
    catch (err) { console.error(JSON.stringify({ok: false, errors: [err.message]})); process.exitCode = 1; }
}
module.exports = {main};
