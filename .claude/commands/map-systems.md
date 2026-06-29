---
description: System dependency map visualization
---

# Map Systems

Generate a text-based dependency map of all systems.

## Input
$ARGUMENTS — project path

## Steps

1. **Load** system_spec.yaml and _CONTRACTS.yaml
2. **Build** dependency graph:
   - Nodes = systems
   - Edges = requires/provides relationships
   - Event edges = publisher → subscriber
3. **Detect** issues:
   - Circular dependencies
   - Orphan systems (no connections)
   - Hub systems (>10 connections — potential god class)
   - Missing edges (referenced but undefined system)
4. **Generate** ASCII dependency map grouped by layer

## Output Format
```
=== System Map: {project} ===

CORE LAYER
  EventBus ──────────────► [all systems]
  ObjectPoolManager ─────► BalloonController, ProjectileManager
  StateManager ──────────► GameBootstrap, UIManager
  DataManager ────────────► LevelManager, ScoreManager

DOMAIN LAYER
  BalloonController ──pub──► OnBalloonPopped
    ├── PopProcessor ◄──sub── OnBalloonPopped
    ├── ScoreManager ◄──sub── OnBalloonPopped
    └── BoardStateManager ◄─sub── OnBalloonPopped

  LevelManager ──────────► BalloonController (LoadLevel)
  ScoreManager ──────────► UIManager (OnScoreChanged)

GAME LAYER
  GameBootstrap ──────────► StateManager, LevelManager, UIManager
  UIManager ──────────────► (displays only, no game state)

ISSUES:
  [WARN] UIManager has 12 connections — consider splitting
  [OK] No circular dependencies
  [OK] No orphan systems
```
