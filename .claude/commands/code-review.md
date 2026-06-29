---
description: Quick code review (lightweight Validator)
---

# Code Review

Perform a lightweight code review on the specified file(s).

## Input
$ARGUMENTS — file path(s) or directory to review

## Steps

1. **Read** target file(s)
2. **Check against path-scoped rules** (`.claude/rules/`)
3. **Verify contracts** if `_CONTRACTS.yaml` exists:
   - provides/requires match actual code
   - EventBus publish/subscribe pairs
   - SerializeField declarations
4. **Pattern check**:
   - No god classes (>500 lines without clear separation)
   - No deep nesting (>4 levels)
   - No magic numbers in logic
   - Null safety on external data
5. **Output** review summary:
   - PASS / WARN / FAIL per file
   - Specific line references for issues
   - Suggested fixes (code snippets)

## Output Format
```
=== Code Review: {filename} ===
[PASS] Contract compliance
[WARN] L45: Magic number 300 — consider const
[FAIL] L89: new GameObject() in runtime code
Score: 7/10
```

Keep it concise. Focus on real issues, not style nitpicks.
