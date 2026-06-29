---
description: Editor script rules for output/Editor/*.cs
globs: projects/*/output/Editor/*.cs
---

# Editor Script Rules

## ALLOWED (editor-only)
- `new GameObject()`, `AddComponent<T>()` — for scene setup
- `PrefabUtility`, `AssetDatabase`, `EditorSceneManager`
- `SerializedObject` / `SerializedProperty` for wiring

## REQUIRED
- `[InitializeOnLoad]` with `EditorApplication.delayCall`
- `EditorPrefs.GetBool()` guard for one-time execution
- Version key format: `{Project}_{Script}_v{N}` (e.g., `BalloonFlow_SceneBuilt_v4`)
- `SerializedObject.ApplyModifiedProperties()` after every property change
- All created objects must be registered in `_ASSET_MANIFEST.yaml`

## STRUCTURE
- `SceneBuilder.cs` — Scene creation, hierarchy, Canvas, Manager placement, SerializeField wiring
- `PrefabBuilder.cs` — Prefab creation, component attachment, Resources/ placement
- `ProjectConfigurator.cs` — Build Settings, Player Settings, SDK symbols

## CANVAS DEFAULTS
- CanvasScaler: Scale With Screen Size
- Reference Resolution: from design doc (default 1080x1920)
- Pivot/anchor: match UI purpose (top-HUD, bottom-nav, center-popup, stretch-bg)

## FORBIDDEN
- Running without `delayCall` wrapper
- Missing `EditorPrefs` one-time guard
- Creating materials or high-quality art assets
- Runtime code inside Editor scripts
