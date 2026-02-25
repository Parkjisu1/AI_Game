#if FIREBASE_ANALYTICS
using Firebase;
using Firebase.Analytics;
using Firebase.Extensions;
#endif
using UnityEngine;
using BlockBlast.Core;

namespace BlockBlast.SDK
{
    public class FirebaseManager : Singleton<FirebaseManager>
    {
#if FIREBASE_ANALYTICS
        private bool _isInitialized;

        protected override void Awake()
        {
            base.Awake();
            InitFirebase();
        }

        private void InitFirebase()
        {
            FirebaseApp.CheckAndFixDependenciesAsync().ContinueWithOnMainThread(task =>
            {
                if (task.Result == DependencyStatus.Available)
                {
                    _isInitialized = true;
                    FirebaseAnalytics.SetAnalyticsCollectionEnabled(true);
                    Debug.Log("[Firebase] Initialized successfully");
                }
                else
                {
                    Debug.LogError($"[Firebase] Could not resolve dependencies: {task.Result}");
                }
            });
        }

        public void LogEvent(string eventName)
        {
            if (!_isInitialized) return;
            FirebaseAnalytics.LogEvent(eventName);
        }

        public void LogEvent(string eventName, string paramName, int paramValue)
        {
            if (!_isInitialized) return;
            FirebaseAnalytics.LogEvent(eventName, paramName, paramValue);
        }

        public void LogEvent(string eventName, string paramName, string paramValue)
        {
            if (!_isInitialized) return;
            FirebaseAnalytics.LogEvent(eventName, paramName, paramValue);
        }

        public void SetUserProperty(string name, string value)
        {
            if (!_isInitialized) return;
            FirebaseAnalytics.SetUserProperty(name, value);
        }

        public void SetUserId(string userId)
        {
            if (!_isInitialized) return;
            FirebaseAnalytics.SetUserId(userId);
        }
#else
        // ===== Simulation Mode =====
        protected override void Awake()
        {
            base.Awake();
            Debug.Log("[Firebase Sim] Initialized (simulation mode)");
        }

        public void LogEvent(string eventName)
        {
            Debug.Log($"[Firebase Sim] Event: {eventName}");
        }

        public void LogEvent(string eventName, string paramName, int paramValue)
        {
            Debug.Log($"[Firebase Sim] Event: {eventName}, {paramName}={paramValue}");
        }

        public void LogEvent(string eventName, string paramName, string paramValue)
        {
            Debug.Log($"[Firebase Sim] Event: {eventName}, {paramName}={paramValue}");
        }

        public void SetUserProperty(string name, string value)
        {
            Debug.Log($"[Firebase Sim] UserProperty: {name}={value}");
        }

        public void SetUserId(string userId)
        {
            Debug.Log($"[Firebase Sim] UserId: {userId}");
        }
#endif
    }
}
