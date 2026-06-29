---
description: Orchestrate Main + Sub Coders for parallel code generation
---

# Team Code

Launch parallel code generation with Main Coder + Sub Coders.

## Input
$ARGUMENTS — project path [phase_number]

## Workflow

1. **Pre-check**:
   - Verify previous phase gate passed (run /gate-check)
   - Load build_order.yaml for target phase
   - Ensure _CONTRACTS.yaml and _ASSET_MANIFEST.yaml exist
2. **Assign** nodes:
   - Complex nodes (score >= 2.3) → Main Coder
   - Simple/Medium nodes → Sub Coder 1, Sub Coder 2 (round-robin)
   - Respect dependency order within assignee
3. **Launch** parallel agents:
   - Main Coder: reads _ARCHITECTURE.md, generates complex nodes
   - Sub Coder 1: reads _CONTRACTS.yaml, generates assigned nodes
   - Sub Coder 2: reads _CONTRACTS.yaml, generates assigned nodes
4. **Validate** as completed:
   - Each completed node → Validator (Stage 1-5)
   - All phase nodes done → Validator (Stage 5.5 Integration)
   - Failures → feedback back to originating coder
5. **Update** contracts:
   - Main Coder updates _CONTRACTS.yaml with new entries
   - Run /gate-check for phase completion

## Agent Configuration
```
Main Coder: subagent_type=main-coder, model=opus
Sub Coder 1: subagent_type=sub-coder, model=sonnet
Sub Coder 2: subagent_type=sub-coder, model=sonnet
Validator: subagent_type=validator, model=sonnet
```

Use Agent Teams with `team_name: AI-Game-Creator` for coordinated execution.
