---
description: Design workflow YAML rules for design_workflow/**/*.yaml
globs: projects/*/design_workflow/**/*.yaml
---

# Design Workflow YAML Rules

## FORMAT
- YAML only (no JSON, no tabs)
- UTF-8 encoding
- 2-space indentation
- No trailing whitespace

## LAYER 1 (game_design.yaml) REQUIRED SECTIONS
- `game_name`, `genre`, `platform`, `target_audience`
- `core_loop` (with steps)
- `session_structure` (with timing)
- `monetization` (model type)
- `key_features` (3+ items)

## LAYER 2 (system_spec.yaml) REQUIRED PER SYSTEM
- `system_name`, `layer` (Core/Domain/Game), `genre`
- `responsibilities` (list)
- `provides` (public API methods/events)
- `requires` (dependencies)
- `data_structures` (key types)

## LAYER 3 (nodes/*.yaml) REQUIRED FIELDS
- `nodeId` (must match filename)
- `contracts.provides` (methods list)
- `contracts.requires` (dependencies list)
- `logicFlow` (step-by-step logic)
- `patterns` (design patterns used)
- `phase` (build order phase number)

## BUILD ORDER (build_order.yaml)
- Phase 0: Core systems only (Main Coder)
- Phase 1+: Domain/Game systems (parallel)
- Each entry: `nodeId`, `phase`, `assignee` (main/sub), `dependencies`

## CROSS-REFERENCES
- Every system in system_spec must have a corresponding L3 node
- Every L3 node `requires` must reference existing system names
- Build order must list all L3 nodes

## FORBIDDEN
- Tab characters
- Duplicate nodeId values
- Circular dependencies in requires/provides
- L3 node without matching L2 system entry
