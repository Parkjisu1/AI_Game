---
description: Final polish pass — validation + auto-fix cycle
---

# Team Polish

Run final polishing pass on completed project: validate everything, fix what's fixable, report what's not.

## Input
$ARGUMENTS — project path

## Workflow

1. **Full validation sweep**:
   - Run /validate-code on all output/*.cs
   - Run /validate-design on all design_workflow/**/*.yaml
   - Run gap-detect.sh for missing artifacts
   - Run asset-validate.sh for naming/path issues
2. **Auto-fix pass** (Stage 1-4 errors):
   - Syntax errors → auto-fix
   - Missing dependencies → add using/import
   - Contract mismatches → update _CONTRACTS.yaml
   - SerializeField wiring → update SceneBuilder
3. **Manual review queue** (Stage 5+ errors):
   - Logic errors → report with context
   - Design intent violations → flag with L3 YAML reference
   - Performance concerns → suggest alternatives
4. **Integration re-validation**:
   - Re-run Stage 5.5 on all fixed files
   - Verify _CONTRACTS.yaml consistency
   - Verify _ASSET_MANIFEST.yaml completeness
5. **Final report**:
   - Files touched in polish
   - Remaining issues (manual resolution needed)
   - Overall quality score

## Output Format
```
=== Polish Report: {project} ===
Files scanned: 42 | Auto-fixed: 8 | Manual needed: 3

Auto-fixed:
  - ScoreManager.cs: Added missing EventBus.Subscribe
  - SceneBuilder.cs: Added WireField for _scoreText
  - _CONTRACTS.yaml: Added OnLevelComplete event

Manual needed:
  - LevelManager.cs:L45: Logic ambiguity — check L3 node for intended behavior
  - PopProcessor.cs:L89: Performance — nested loop O(n²) in Update

Quality Score: 8.5/10
```
