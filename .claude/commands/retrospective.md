---
description: Phase/project retrospective analysis
---

# Retrospective

Analyze completed phase or project for lessons learned.

## Input
$ARGUMENTS — project path [phase_number]

## Steps

1. **Gather data**:
   - Git log for the phase period
   - Validation feedback files (feedback/*.json)
   - Audit log (History/audit_log.jsonl)
   - Score changes in DB
2. **Analyze**:
   - First-pass success rate (validated without rework)
   - Common error categories (contract violations, null safety, pattern issues)
   - Rework cycles per node (how many feedback rounds)
   - Agent performance (Main vs Sub coder quality)
3. **Extract patterns**:
   - What worked well (high first-pass nodes)
   - What caused rework (recurring error types)
   - Process improvements (rules to add, checks to automate)
4. **Generate** retrospective report

## Output Format
```
=== Retrospective: {project} Phase {N} ===

## Stats
- Nodes completed: 12
- First-pass success: 8/12 (67%)
- Avg rework cycles: 1.3
- Total validation rounds: 19

## What Went Well
- EventBus contract system caught 4 integration bugs early
- ObjectPool pattern reuse from Expert DB saved time

## What Needs Improvement
- 3 nodes had SerializeField wiring errors → add pre-generation checklist
- Sub Coder missed _CONTRACTS.yaml update → enforce in rules

## Action Items
- [ ] Add SerializeField cross-check to pre-commit hook
- [ ] Update sub-coder.md with contract update reminder
```
