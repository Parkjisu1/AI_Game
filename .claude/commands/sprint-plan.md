---
description: Generate sprint/phase plan from build order
---

# Sprint Plan

Generate a structured sprint plan based on build_order.yaml.

## Input
$ARGUMENTS — project path

## Steps

1. **Load** build_order.yaml and _CONTRACTS.yaml
2. **Group** nodes by phase
3. **Assign** to coders:
   - Phase 0: Main Coder only (core architecture)
   - Phase 1+: Main Coder (complex, requires>=3) + Sub Coders (others)
4. **Calculate** per phase:
   - Node count and complexity estimate
   - Dependencies (blocked-by relationships)
   - Critical path (longest dependency chain)
   - Parallel capacity (independent nodes)
5. **Generate** sprint board format

## Output Format
```
=== Sprint Plan: {project} ===

## Phase 0 — Core Foundation
Assignee: Main Coder (solo)
Nodes: GameBootstrap, EventBus, ObjectPoolManager, StateManager, DataManager
Deliverables: _ARCHITECTURE.md, _CONTRACTS.yaml, _ASSET_MANIFEST.yaml
Gate: Validator Stage 1-5 + ICS artifacts

## Phase 1 — Core Gameplay
| Node | Assignee | Depends On | Complexity |
|------|----------|-----------|------------|
| BalloonController | Main | ObjectPoolManager | High |
| PopProcessor | Sub-1 | EventBus | Medium |
| ScoreManager | Sub-2 | EventBus | Medium |

Critical Path: GameBootstrap → BalloonController → PopProcessor
Parallel: ScoreManager + PopProcessor (independent)
```
