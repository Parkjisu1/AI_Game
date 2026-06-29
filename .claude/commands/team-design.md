---
description: Orchestrate Designer + Design Validator for design workflow
---

# Team Design

Launch design generation + validation workflow.

## Input
$ARGUMENTS — project path [stage: concept|systems|balance|content|bm]

## Workflow

1. **Stage 2 — Designer generates**:
   - 2-1: Concept (core fun + pillars)
   - 2-2: Systems (system_spec.yaml)
   - 2-3: Balance (curves, economy) — parallel with 2-4
   - 2-4: Content (levels, progression) — parallel with 2-3
   - 2-5: BM + LiveOps
   - Each outputs YAML + triggers Docx generation
2. **Stage 3 — Design Validator validates**:
   - Cross-consistency check (all systems reference each other correctly)
   - User journey simulation (new player → day-30 veteran)
   - Gap detection (missing systems, undefined currencies, dead-end flows)
   - Score calculation (logic_completeness, balance_stability, impl_complexity)
3. **Stage 4 — Director review gate** (human):
   - Present validation report to user
   - Wait for approval or feedback
4. **Stage 5 — If feedback**:
   - Designer applies changes
   - Design Validator re-validates
   - Feedback history recorded
5. **Stage 6 — DB accumulation**:
   - Design DB Builder saves to design_base
   - Score >= 0.6 → promote to design_expert
   - Extract reusable rules

## Agent Configuration
```
Designer: subagent_type=designer, model=sonnet
Design Validator: subagent_type=design-validator, model=sonnet
Design DB Builder: subagent_type=design-db-builder, model=sonnet (Stage 6 only)
```
