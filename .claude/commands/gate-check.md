---
description: Phase gate pass/fail verification
---

# Gate Check

Verify all Phase Gate conditions before proceeding to next phase.

## Input
$ARGUMENTS — project path phase_number

## Steps

1. **Load** build_order.yaml, _CONTRACTS.yaml, _ASSET_MANIFEST.yaml
2. **Check** gate conditions:

### Phase 0 Gate (Core)
- [ ] _ARCHITECTURE.md exists and has namespace/pattern sections
- [ ] _CONTRACTS.yaml exists with events, pool_keys, serialized_fields
- [ ] _ASSET_MANIFEST.yaml exists with prefabs, scenes, editor_scripts
- [ ] All Core nodes compiled (no syntax errors)
- [ ] Validator passed Stage 1-5 for all Core nodes
- [ ] EventBus, ObjectPool, Singleton base classes present

### Phase N Gate (Domain/Game)
- [ ] All Phase N nodes completed
- [ ] Validator Stage 1-5 passed for each node
- [ ] Stage 5.5 Integration Validation passed
- [ ] _CONTRACTS.yaml updated with new events/pools/fields
- [ ] _ASSET_MANIFEST.yaml updated with new prefabs/resources
- [ ] No unresolved error feedback
- [ ] Gap detection clean (run gap-detect.sh)

3. **Output** gate status

## Output Format
```
=== Gate Check: {project} Phase {N} ===

[PASS] _CONTRACTS.yaml updated (events: 12, pools: 5, fields: 18)
[PASS] All 8 nodes validated (Stage 1-5)
[PASS] Integration validation (Stage 5.5)
[FAIL] _ASSET_MANIFEST.yaml missing PrefabBuilder entry for "Enemy"
[WARN] 2 nodes have score < 0.5

GATE: BLOCKED — Fix 1 error before proceeding
```
