---
description: Pre-release build checklist
---

# Release Checklist

Comprehensive checklist before Unity build or playable delivery.

## Input
$ARGUMENTS — project path [platform: unity|playable]

## Unity Checklist

### Code
- [ ] All Validator Stage 1-5 passed
- [ ] Integration Validation (5.5) passed
- [ ] No TODO(critical) remaining
- [ ] No Debug.Log in production code (or wrapped in #if DEBUG)
- [ ] SDK conditional compilation verified (#if blocks)
- [ ] No hardcoded test values

### Assets
- [ ] _ASSET_MANIFEST.yaml complete
- [ ] All prefab paths valid
- [ ] SceneBuilder version key current
- [ ] PrefabBuilder version key current
- [ ] Build Settings has all 3 scenes (Title, Main, GameScene)

### Build Settings
- [ ] minSdkVersion >= 24 (Firebase requirement)
- [ ] targetArchitectures = 5 (ARMv7 + ARM64) for production
- [ ] No plugin conflicts (check .aar vs .androidlib duplicates)
- [ ] Gradle packagingOptions: arm64-v8a NOT excluded

### Performance
- [ ] No Find() in Update/FixedUpdate
- [ ] ObjectPool used for repeated instantiation
- [ ] No allocations in hot paths (Update, FixedUpdate)

## Playable Checklist
- [ ] Single HTML file
- [ ] Zero external HTTP requests
- [ ] Touch + mouse events work
- [ ] CTA button visible and functional
- [ ] File size under network limit
- [ ] requestAnimationFrame (not setInterval)

## Output
Generate pass/fail for each item with file references for failures.
