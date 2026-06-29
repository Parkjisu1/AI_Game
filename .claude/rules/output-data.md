---
description: ScriptableObject data asset rules for output/Data/*.cs
globs: projects/*/output/Data/*.cs
---

# Data Asset Rules (ScriptableObject)

## REQUIRED
- Inherit from `ScriptableObject`
- `[CreateAssetMenu]` attribute with meaningful path
- All data fields serializable (`[SerializeField]` or public)
- Validation method (`OnValidate()`) for range checks
- XML doc comments on all public fields

## PATTERN
```csharp
[CreateAssetMenu(fileName = "NewLevelData", menuName = "Game/Level Data")]
public class LevelData : ScriptableObject
{
    [SerializeField, Range(1, 100)] int _levelNumber;
    [SerializeField] float _timeLimit;
    [SerializeField] List<WaveConfig> _waves;

    public int LevelNumber => _levelNumber;
    public float TimeLimit => _timeLimit;
    public IReadOnlyList<WaveConfig> Waves => _waves;

    void OnValidate()
    {
        if (_timeLimit <= 0) _timeLimit = 60f;
    }
}
```

## STYLE
- Immutable public API (properties with private setters or readonly)
- Collections exposed as `IReadOnlyList<T>` or `IReadOnlyDictionary<K,V>`
- Nested data classes marked `[System.Serializable]`
- File name = class name (PascalCase)

## FORBIDDEN
- MonoBehaviour logic in data classes
- Runtime state stored in ScriptableObject (use runtime wrapper)
- Direct field access without property wrapper
