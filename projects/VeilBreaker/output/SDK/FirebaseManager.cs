#if FIREBASE_ANALYTICS
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Firebase;
using Firebase.Analytics;
#endif

using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.SDK
{
    /// <summary>
    /// Firebase Analytics wrapper with conditional compilation.
    /// When FIREBASE_ANALYTICS symbol is defined, wraps real Firebase SDK.
    /// Otherwise runs in simulation mode using Debug.Log.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Generic
    /// Role: Manager
    /// System: SDK
    /// Phase: 3
    /// SDK: Firebase Analytics 13.7.0+ (minSdkVersion >= 24)
    /// </remarks>
    public class FirebaseManager : Singleton<FirebaseManager>
    {
        #region Fields

#if FIREBASE_ANALYTICS
        private bool _isInitialized;
#endif

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            EventManager.Subscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            EventManager.Subscribe(GameConstants.Events.OnIAPPurchased, OnIAPPurchased);
        }

        protected override void OnDestroy()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            EventManager.Unsubscribe(GameConstants.Events.OnIAPPurchased, OnIAPPurchased);
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize Firebase. In simulation mode, logs initialization message.
        /// Must be called before any LogEvent calls.
        /// </summary>
        public void Init()
        {
#if FIREBASE_ANALYTICS
            FirebaseApp.CheckAndFixDependenciesAsync().ContinueWith(task =>
            {
                if (task.Result == DependencyStatus.Available)
                {
                    _isInitialized = true;
                    FirebaseAnalytics.SetAnalyticsCollectionEnabled(true);
                    Debug.Log("[FirebaseManager] Firebase initialized successfully.");
                }
                else
                {
                    Debug.LogError($"[FirebaseManager] Firebase dependency check failed: {task.Result}");
                }
            });
#else
            Debug.Log("[Firebase Sim] Initialized");
#endif
        }

        /// <summary>
        /// Logs a named event with no parameters.
        /// </summary>
        /// <param name="name">Event name (snake_case recommended).</param>
        public void LogEvent(string name)
        {
            if (string.IsNullOrEmpty(name)) return;

#if FIREBASE_ANALYTICS
            if (!_isInitialized)
            {
                Debug.LogWarning($"[FirebaseManager] LogEvent '{name}' called before initialization.");
                return;
            }
            FirebaseAnalytics.LogEvent(name);
#else
            Debug.Log($"[Firebase Sim] Event: {name}");
#endif
        }

        /// <summary>
        /// Logs a named event with a parameter dictionary.
        /// </summary>
        /// <param name="name">Event name.</param>
        /// <param name="parameters">Key-value parameter pairs. Values are converted to string.</param>
        public void LogEvent(string name, System.Collections.Generic.Dictionary<string, object> parameters)
        {
            if (string.IsNullOrEmpty(name)) return;

#if FIREBASE_ANALYTICS
            if (!_isInitialized)
            {
                Debug.LogWarning($"[FirebaseManager] LogEvent '{name}' called before initialization.");
                return;
            }

            if (parameters == null || parameters.Count == 0)
            {
                FirebaseAnalytics.LogEvent(name);
            }
            else
            {
                var firebaseParams = parameters
                    .Select(kv => new Parameter(kv.Key, kv.Value?.ToString() ?? ""))
                    .ToArray();
                FirebaseAnalytics.LogEvent(name, firebaseParams);
            }
#else
            string paramStr = parameters != null
                ? string.Join(", ", parameters.Select(kv => $"{kv.Key}={kv.Value}"))
                : "";
            Debug.Log($"[Firebase Sim] Event: {name} | Params: {paramStr}");
#endif
        }

        /// <summary>
        /// Logs a stage clear event with the completed stageId.
        /// </summary>
        /// <param name="stageId">Cleared stage ID (e.g. "1_5").</param>
        public void LogStageClear(string stageId)
        {
            if (string.IsNullOrEmpty(stageId)) return;

            LogEvent("stage_clear", new System.Collections.Generic.Dictionary<string, object>
            {
                { "stage_id", stageId }
            });
        }

        /// <summary>
        /// Logs a gacha pull event with banner and result grade.
        /// </summary>
        /// <param name="bannerId">Banner pulled from.</param>
        /// <param name="result">Result grade (e.g. "SSR", "SR", "R").</param>
        public void LogGachaPull(string bannerId, string result)
        {
            LogEvent("gacha_pull", new System.Collections.Generic.Dictionary<string, object>
            {
                { "banner_id", bannerId ?? "" },
                { "result", result ?? "" }
            });
        }

        /// <summary>
        /// Logs an IAP purchase event.
        /// Uses "item_id" string key (Firebase SDK 13.7.0+; ParameterItemId constant removed).
        /// </summary>
        /// <param name="productId">IAP product ID.</param>
        /// <param name="price">Purchase price in local currency.</param>
        public void LogIAPPurchase(string productId, double price)
        {
            LogEvent("purchase", new System.Collections.Generic.Dictionary<string, object>
            {
                { "item_id", productId ?? "" },      // Use string literal, not ParameterItemId
                { "value", price.ToString("F2") }
            });
        }

        #endregion

        #region Private Methods

        private void OnStageComplete(object data)
        {
            string stageId = data as string;
            if (!string.IsNullOrEmpty(stageId))
            {
                LogStageClear(stageId);
            }
        }

        private void OnIAPPurchased(object data)
        {
            string productId = data as string;
            if (!string.IsNullOrEmpty(productId))
            {
                LogIAPPurchase(productId, 0.0);
            }
        }

        #endregion
    }
}
