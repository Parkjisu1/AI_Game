#!/usr/bin/env node
/**
 * balance-simulator.js
 * Pure numeric computation script for game design validation.
 * Invoked by Design Validator Agent.
 *
 * Modes: economy | combat | gacha | growth
 * Usage: node balance-simulator.js --input <yaml-path> --mode <mode> [--days 30] --output <results-path>
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { parseYaml } = require('./lib/yaml-utils');

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const next = argv[i + 1];
      if (next && !next.startsWith('--')) {
        args[key] = next;
        i++;
      } else {
        args[key] = true;
      }
    }
  }
  return args;
}

// ---------------------------------------------------------------------------
// Seeded PRNG for reproducible Monte Carlo
// ---------------------------------------------------------------------------
function seededRandom(seed) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) & 0xFFFFFFFF;
    return (s >>> 0) / 0xFFFFFFFF;
  };
}

// ---------------------------------------------------------------------------
// Simulation modes
// ---------------------------------------------------------------------------

/**
 * Economy simulation: models 30-day (configurable) resource flow.
 * Expected YAML input shape:
 * {
 *   currency: { name, initial_amount },
 *   daily_income: { base, events, ads },
 *   daily_costs: [ { name, amount, frequency_per_day } ],
 *   sinks: [ { name, price, unlock_day } ]
 * }
 */
function simulateEconomy(data, days) {
  const currency = data.currency || {};
  let balance = Number(currency.initial_amount || 0);
  const dailyIncome = data.daily_income || {};
  const baseIncome = Number(dailyIncome.base || 0);
  const eventsIncome = Number(dailyIncome.events || 0);
  const adsIncome = Number(dailyIncome.ads || 0);
  const totalDailyIncome = baseIncome + eventsIncome + adsIncome;

  const dailyCosts = Array.isArray(data.daily_costs) ? data.daily_costs : [];
  const totalDailyCost = dailyCosts.reduce((sum, c) => {
    return sum + Number(c.amount || 0) * Number(c.frequency_per_day || 1);
  }, 0);

  const timeline = [];
  const outliers = [];

  for (let day = 1; day <= days; day++) {
    const income = totalDailyIncome;
    const cost = totalDailyCost;
    balance += income - cost;

    let drainRate;
    if (totalDailyIncome > 0) {
      drainRate = (cost / income) * 100;
    } else if (totalDailyCost > 0) {
      drainRate = 99999; // Infinity-safe sentinel: costs exist but zero income
      outliers.push({
        type: 'ECONOMY_GAP',
        day,
        detail: `Zero income with non-zero daily cost (${totalDailyCost}) — economy has no income source`
      });
    } else {
      drainRate = 0;
    }

    timeline.push({
      day,
      balance: Math.round(balance),
      income,
      cost,
      drain_rate: Math.round(Math.min(drainRate, 99999) * 10) / 10
    });

    if (drainRate > 100 && drainRate < 99999) {
      outliers.push({
        type: 'ECONOMY_GAP',
        day,
        detail: `Drain rate ${drainRate.toFixed(1)}% exceeds 100% — spending more than earning`
      });
    }
    if (balance < 0) {
      outliers.push({
        type: 'NEGATIVE_BALANCE',
        day,
        detail: `Balance went negative (${balance}) on day ${day}`
      });
    }
  }

  const finalBalance = timeline.length > 0 ? timeline[timeline.length - 1].balance : 0;
  const avgDrainRate = timeline.reduce((s, t) => s + t.drain_rate, 0) / (timeline.length || 1);

  return {
    mode: 'economy',
    days_simulated: days,
    currency_name: currency.name || 'currency',
    initial_balance: Number(currency.initial_amount || 0),
    final_balance: finalBalance,
    total_income: totalDailyIncome * days,
    total_cost: totalDailyCost * days,
    avg_drain_rate: Math.round(avgDrainRate * 10) / 10,
    timeline,
    outliers
  };
}

/**
 * Combat simulation: compares DPS of multiple unit types.
 * Expected YAML input shape:
 * {
 *   units: [
 *     { name, base_attack, attack_speed, crit_rate, crit_multiplier, defense_penetration }
 *   ],
 *   enemies: [
 *     { name, defense_rate }
 *   ],
 *   duration_seconds: 10
 * }
 */
function simulateCombat(data) {
  const units = Array.isArray(data.units) ? data.units : [];
  const enemies = Array.isArray(data.enemies) ? data.enemies : [{ name: 'default', defense_rate: 0 }];
  const duration = Number(data.duration_seconds || 10);

  const outliers = [];
  const results = [];

  for (const unit of units) {
    const baseAtk = Number(unit.base_attack || 0);
    const atkSpeed = Number(unit.attack_speed || 1); // attacks per second
    const critRate = Number(unit.crit_rate || 0) / 100;
    const critMult = Number(unit.crit_multiplier || 1.5);
    const defPen = Number(unit.defense_penetration || 0) / 100;

    const unitResults = [];
    for (const enemy of enemies) {
      const defRate = Math.max(0, (Number(enemy.defense_rate || 0) / 100) - defPen);
      const avgDmgPerHit = baseAtk * (1 - defRate) * (1 + critRate * (critMult - 1));
      const dps = avgDmgPerHit * atkSpeed;
      const totalDamage = dps * duration;

      unitResults.push({
        enemy: enemy.name,
        dps: Math.round(dps * 10) / 10,
        total_damage: Math.round(totalDamage)
      });
    }

    results.push({
      unit: unit.name,
      base_attack: baseAtk,
      attack_speed: atkSpeed,
      crit_rate: unit.crit_rate,
      by_enemy: unitResults
    });
  }

  // Check DPS ratio between highest and lowest
  if (results.length >= 2) {
    const allDps = results.map(r => r.by_enemy[0]?.dps || 0);
    const maxDps = Math.max(...allDps);
    const minDps = Math.min(...allDps.filter(d => d > 0));
    const ratio = minDps > 0 ? maxDps / minDps : 0;

    if (ratio > 3.0) {
      outliers.push({
        type: 'STAT_OUTLIER',
        detail: `DPS ratio between strongest/weakest unit is ${ratio.toFixed(2)} (threshold: 3.0) — consider rebalancing`
      });
    }
  }

  return {
    mode: 'combat',
    duration_seconds: duration,
    results,
    outliers
  };
}

/**
 * Gacha simulation: computes expected pulls to obtain a target item.
 * Expected YAML input shape:
 * {
 *   rates: [ { rarity, probability, pity_ceiling } ],
 *   target_rarity: "SSR",
 *   simulations: 10000
 * }
 */
function simulateGacha(data, rng) {
  const rates = Array.isArray(data.rates) ? data.rates : [];
  const targetRarity = data.target_rarity || '';
  const simCount = Math.min(Number(data.simulations || 1000), 100000);
  const rand = rng || Math.random.bind(Math);

  const targetRate = rates.find(r => r.rarity === targetRarity);
  if (!targetRate) {
    return {
      mode: 'gacha',
      error: `Target rarity "${targetRarity}" not found in rates`,
      outliers: []
    };
  }

  const baseProb = Number(targetRate.probability || 0) / 100;
  const pity = Number(targetRate.pity_ceiling || 0);

  if (baseProb <= 0) {
    return { mode: 'gacha', error: 'Base probability must be > 0', outliers: [] };
  }
  if (baseProb > 1.0) {
    return { mode: 'gacha', error: `Base probability ${baseProb * 100}% exceeds 100% — invalid probability value`, outliers: [] };
  }

  // Monte-Carlo simulation
  let totalPulls = 0;
  const pullCounts = [];

  for (let sim = 0; sim < simCount; sim++) {
    let pulls = 0;
    let obtained = false;

    while (!obtained) {
      pulls++;
      const effectiveProb = (pity > 0 && pulls >= pity) ? 1.0 : baseProb;
      if (rand() < effectiveProb) {
        obtained = true;
      }
      // Safety cap
      if (pulls > (pity > 0 ? pity * 2 : 10000)) break;
    }

    pullCounts.push(pulls);
    totalPulls += pulls;
  }

  pullCounts.sort((a, b) => a - b);
  const expectedPulls = totalPulls / simCount;
  const median = pullCounts[Math.floor(simCount / 2)];
  const p90 = pullCounts[Math.floor(simCount * 0.9)];
  const p99 = pullCounts[Math.floor(simCount * 0.99)];

  const outliers = [];
  if (pity > 0 && expectedPulls > pity) {
    outliers.push({
      type: 'GACHA_EXPECTED',
      detail: `Expected pulls (${Math.round(expectedPulls)}) exceeds pity ceiling (${pity}) — check probability formula`
    });
  }

  return {
    mode: 'gacha',
    target_rarity: targetRarity,
    base_probability_pct: baseProb * 100,
    pity_ceiling: pity,
    simulations: simCount,
    expected_pulls: Math.round(expectedPulls),
    median_pulls: median,
    p90_pulls: p90,
    p99_pulls: p99,
    outliers
  };
}

/**
 * Growth curve simulation: analyzes stat progression curves.
 * Expected YAML input shape:
 * {
 *   stat_name: "hp",
 *   levels: [
 *     { level: 1, value: 100 },
 *     { level: 10, value: 500 },
 *     ...
 *   ],
 *   target_curve: "linear|exponential|polynomial",
 *   max_level: 100
 * }
 */
function simulateGrowth(data) {
  const statName = data.stat_name || 'stat';
  const levels = Array.isArray(data.levels) ? data.levels : [];
  const targetCurve = data.target_curve || 'linear';
  const maxLevel = Number(data.max_level || 100);

  if (levels.length < 2) {
    return { mode: 'growth', error: 'At least 2 level data points required', outliers: [] };
  }

  // Sort by level
  levels.sort((a, b) => Number(a.level) - Number(b.level));

  const minLevel = Number(levels[0].level);
  const minValue = Number(levels[0].value);
  const maxDataLevel = Number(levels[levels.length - 1].level);
  const maxDataValue = Number(levels[levels.length - 1].value);

  // Compute growth factors between consecutive levels
  const growthFactors = [];
  const outliers = [];

  for (let i = 1; i < levels.length; i++) {
    const prevLevel = Number(levels[i - 1].level);
    const prevValue = Number(levels[i - 1].value);
    const curLevel = Number(levels[i].level);
    const curValue = Number(levels[i].value);
    const levelDiff = curLevel - prevLevel;
    const valueDiff = curValue - prevValue;
    const factor = prevValue > 0 ? curValue / prevValue : 0;

    growthFactors.push({
      from_level: prevLevel,
      to_level: curLevel,
      value_start: prevValue,
      value_end: curValue,
      value_increase: valueDiff,
      growth_factor: Math.round(factor * 1000) / 1000,
      per_level_increase: levelDiff > 0 ? Math.round(valueDiff / levelDiff) : 0
    });
  }

  // Detect anomalies: sudden spikes or drops
  const factors = growthFactors.map(g => g.growth_factor);
  const avgFactor = factors.reduce((s, f) => s + f, 0) / factors.length;

  for (const g of growthFactors) {
    if (g.growth_factor > avgFactor * 2) {
      outliers.push({
        type: 'CURVE_SPIKE',
        detail: `Level ${g.from_level}→${g.to_level}: growth factor ${g.growth_factor} is >2x average (${avgFactor.toFixed(2)})`
      });
    }
    if (g.growth_factor < avgFactor * 0.3 && avgFactor > 1.0) {
      outliers.push({
        type: 'CURVE_DROP',
        detail: `Level ${g.from_level}→${g.to_level}: growth factor ${g.growth_factor} is <0.3x average (${avgFactor.toFixed(2)})`
      });
    }
  }

  // Extrapolate to max_level if data doesn't cover it
  let extrapolated = null;
  if (maxDataLevel < maxLevel) {
    const avgFactorForExtrap = factors.length > 0 ? factors.reduce((s, f) => s + f, 0) / factors.length : 1;
    let projected = maxDataValue;
    for (let lv = maxDataLevel + 1; lv <= maxLevel; lv++) {
      projected *= avgFactorForExtrap;
    }
    const projectedRounded = Math.round(projected);
    extrapolated = {
      note: `Extrapolated using average growth factor (${Math.round(avgFactorForExtrap * 1000) / 1000}) from level ${maxDataLevel} to ${maxLevel}`,
      projected_max_value: projectedRounded
    };
    if (maxDataValue > 0 && projectedRounded > maxDataValue * 10) {
      outliers.push({
        type: 'CURVE_EXTRAPOLATION_WARNING',
        detail: `Projected max value (${projectedRounded}) exceeds 10x observed max (${maxDataValue}) — extrapolation may be unreliable`
      });
    }
  }

  const totalGrowthRatio = minValue > 0 ? maxDataValue / minValue : 0;

  return {
    mode: 'growth',
    stat_name: statName,
    target_curve: targetCurve,
    level_range: { min: minLevel, max: maxDataLevel },
    value_range: { min: minValue, max: maxDataValue },
    total_growth_ratio: Math.round(totalGrowthRatio * 100) / 100,
    avg_growth_factor: Math.round(avgFactor * 1000) / 1000,
    growth_factors: growthFactors,
    extrapolated,
    outliers
  };
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------
const VALID_MODES = ['economy', 'combat', 'gacha', 'growth'];

function main() {
  const args = parseArgs(process.argv);

  if (!args.input) {
    console.error('Error: --input <yaml-path> is required');
    process.exit(1);
  }
  if (!args.mode) {
    console.error('Error: --mode <economy|combat|gacha|growth> is required');
    process.exit(1);
  }
  if (!args.output) {
    console.error('Error: --output <results-path> is required');
    process.exit(1);
  }

  const inputPath = path.resolve(args.input);
  const outputPath = path.resolve(args.output);
  const mode = args.mode;
  const days = Number(args.days || 30);

  if (!VALID_MODES.includes(mode)) {
    console.error(`Error: Unknown mode "${mode}". Available modes: ${VALID_MODES.join(' | ')}`);
    process.exit(1);
  }

  if (!fs.existsSync(inputPath)) {
    console.error(`Error: Input file not found: ${inputPath}`);
    process.exit(1);
  }

  const yamlText = fs.readFileSync(inputPath, 'utf8');
  const data = parseYaml(yamlText);

  // Set up RNG (seeded for reproducibility if --seed provided)
  const rng = args.seed !== undefined ? seededRandom(Number(args.seed)) : Math.random.bind(Math);

  let results;
  switch (mode) {
    case 'economy':
      results = simulateEconomy(data, days);
      break;
    case 'combat':
      results = simulateCombat(data);
      break;
    case 'gacha':
      results = simulateGacha(data, rng);
      break;
    case 'growth':
      results = simulateGrowth(data);
      break;
  }

  results.generated_at = new Date().toISOString();
  results.input_file = inputPath;
  results.summary = {
    mode,
    outlier_count: results.outliers ? results.outliers.length : 0,
    has_critical_issues: results.outliers ? results.outliers.length > 0 : false
  };

  // Ensure output directory exists
  const outputDir = path.dirname(outputPath);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  fs.writeFileSync(outputPath, JSON.stringify(results, null, 2), 'utf8');

  console.log(`[balance-simulator] Mode: ${mode}`);
  console.log(`[balance-simulator] Input: ${inputPath}`);
  console.log(`[balance-simulator] Output: ${outputPath}`);
  console.log(`[balance-simulator] Outliers found: ${results.outliers ? results.outliers.length : 0}`);

  if (results.outliers && results.outliers.length > 0) {
    console.log('[balance-simulator] --- Flagged Issues ---');
    for (const o of results.outliers) {
      console.log(`  [${o.type}] ${o.detail}`);
    }
  } else {
    console.log('[balance-simulator] No critical issues detected.');
  }
}

main();
