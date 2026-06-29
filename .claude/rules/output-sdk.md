---
description: SDK integration rules for output/SDK/*.cs
globs: projects/*/output/SDK/*.cs
---

# SDK Integration Rules

## REQUIRED
- ALL `using` statements inside `#if SYMBOL` blocks
- `#else` block with simulation implementation (Debug.Log fallback)
- Singleton pattern (inherits from Singleton<T> or implements own)
- Initialization status check before any SDK call

## CONDITIONAL COMPILATION SYMBOLS
| SDK | Symbol | File |
|-----|--------|------|
| Firebase Analytics | `FIREBASE_ANALYTICS` | FirebaseManager.cs |
| Google AdMob | `GOOGLE_MOBILE_ADS` | AdMobManager.cs |
| Unity IAP | `UNITY_IAP` | IAPManager.cs |

## PATTERN
```csharp
#if FIREBASE_ANALYTICS
using Firebase;
using Firebase.Analytics;
#endif

public class FirebaseManager : Singleton<FirebaseManager>
{
#if FIREBASE_ANALYTICS
    // Real implementation
#else
    public void LogEvent(string name) => Debug.Log($"[Firebase Sim] {name}");
#endif
}
```

## FORBIDDEN
- SDK using outside #if block
- Missing #else simulation block
- Hardcoded API keys in source (use ScriptableObject or remote config)
- `FirebaseAnalytics.ParameterItemId` — use string `"item_id"` instead (SDK 13.7.0+)
