---
description: Quick balance/economy validation
---

# Balance Check

Quick validation of game balance numbers and economy curves.

## Input
$ARGUMENTS — YAML file path (balance/*.yaml, content/*.yaml) or project path

## Steps

1. **Load** balance data from design_workflow/balance/ and design_workflow/content/
2. **Curve Analysis**:
   - Growth curves: check for too-steep (>2x per level) or too-flat (<1.1x per level)
   - Economy: income vs drain ratio (healthy: 1.2~1.8x income surplus early game)
   - Difficulty: verify flow channel (not too easy, not too hard)
3. **Cross-reference**:
   - Currency sources vs sinks (every currency must have both)
   - Reward pacing vs session length
   - Prestige/reset value proposition
4. **Simulation** (if balance-simulator.js available):
   - Run `node scripts/balance-simulator.js --project {project}`
   - Report anomalies (zero income, infinite loops, unreachable content)
5. **Output** balance report

## Output Format
```
=== Balance Check: {project} ===
[OK] Currency flow: 3 sources, 4 sinks for Gold
[WARN] Level 15-20: difficulty spike (3.2x jump)
[FAIL] Diamond: no free source — pay-wall risk
Recommendation: Add diamond rewards at milestone levels
```
