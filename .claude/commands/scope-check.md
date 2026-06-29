---
description: Scope creep detection and complexity assessment
---

# Scope Check

Detect scope creep by comparing current design against original concept.

## Input
$ARGUMENTS — project path

## Steps

1. **Load** concept.yaml (original scope) and current system_spec.yaml
2. **Count** systems by layer:
   - Core (expected: 3-7)
   - Domain (expected: varies by genre)
   - Game (expected: varies)
3. **Compare** against genre baselines:
   | Genre | Typical Total Systems |
   |-------|-----------------------|
   | Casual | 15-25 |
   | Puzzle | 20-35 |
   | Idle | 30-50 |
   | RPG | 40-70 |
4. **Flag** scope risks:
   - Total systems > genre baseline × 1.5 → OVER-SCOPED
   - Any system with >10 provides → consider splitting
   - Circular dependencies → architecture smell
   - Phase 0 has >7 systems → too much in core
5. **Estimate** Phase count and parallel capacity

## Output Format
```
=== Scope Check: {project} ===
Genre: Puzzle | Systems: 42 (baseline: 20-35) [OVER-SCOPED]
Core: 6 | Domain: 22 | Game: 14
Phase 0 (core): 6 systems — OK
Phase 1-3: 36 systems, ~12 per phase with 3 coders
Risk: SocialSystem has 15 provides — consider splitting
Recommendation: Defer Social + LiveOps to v2
```
