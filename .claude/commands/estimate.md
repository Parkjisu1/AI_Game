---
description: Complexity and effort estimation for nodes/systems
---

# Estimate

Estimate complexity and generation effort for L3 nodes.

## Input
$ARGUMENTS — project path or specific node YAML path

## Steps

1. **Load** node YAML(s) from layer3/nodes/
2. **Score** each node on complexity factors:
   | Factor | Weight | Low (1) | Med (2) | High (3) |
   |--------|--------|---------|---------|----------|
   | Dependencies | 30% | 0-2 requires | 3-5 | 6+ |
   | Public API | 20% | 1-3 provides | 4-7 | 8+ |
   | Logic Steps | 25% | 1-5 steps | 6-12 | 13+ |
   | Patterns | 15% | 1 pattern | 2-3 | 4+ |
   | DB References | 10% | Has expert ref | Has base ref | No ref |
3. **Classify**: Simple (1.0-1.5) / Medium (1.6-2.2) / Complex (2.3-3.0)
4. **Assign** recommendation: Sub Coder (Simple/Medium) / Main Coder (Complex)

## Output Format
```
=== Estimate: {project} ===

| Node | Deps | API | Logic | Patterns | DB | Score | Class | Assignee |
|------|------|-----|-------|----------|----|-------|-------|----------|
| GameBootstrap | 5 | 8 | 15 | 3 | expert | 2.7 | Complex | Main |
| ScoreManager | 2 | 3 | 6 | 1 | expert | 1.4 | Simple | Sub |
| PopProcessor | 3 | 4 | 8 | 2 | base | 1.9 | Medium | Sub |

Total: 12 nodes (3 Complex, 5 Medium, 4 Simple)
Recommended: Main Coder handles 3 complex + Phase 0
             Sub Coders handle 9 remaining (parallel)
```
