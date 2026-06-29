---
description: Runtime C# code rules for output/*.cs (excludes Editor/, SDK/, Data/)
globs: projects/*/output/*.cs
---

# Runtime Code Rules

## FORBIDDEN (instant reject)
- `new GameObject()` — Use Resources.Load / ObjectPool
- `AddComponent<T>()` — Components must be on prefabs
- `Find()`, `FindObjectOfType()`, `FindWithTag()` — Use [SerializeField] or cached refs
- `Instantiate()` in loops without ObjectPool — Use ObjectPool.Get/Return
- `Destroy()` on pooled objects — Use ObjectPool.Return
- Bare `using Firebase;` or `using Google.MobileAds;` outside `#if` block

## REQUIRED
- All inter-object references via `[SerializeField]` (wired by SceneBuilder)
- Repeated create/destroy objects use ObjectPool pattern
- Event communication via EventBus (registered in _CONTRACTS.yaml)
- Public API methods must match _CONTRACTS.yaml `method_calls` entries
- Every class must trace to an L3 YAML node (`nodeId`)
- Use `delta time` for all frame-dependent calculations

## STYLE
- PascalCase filenames matching class name
- Private fields: `_camelCase` with underscore prefix
- No magic numbers — use `const`, `[SerializeField]`, or ScriptableObject
- Max 1 MonoBehaviour per file
- Regions only for large files (200+ lines)
