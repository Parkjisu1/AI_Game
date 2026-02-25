using UnityEngine;

namespace VeilBreaker.Core
{
    /// <summary>
    /// Generic singleton base class for MonoBehaviour managers.
    /// Ensures a single instance persists across scenes via DontDestroyOnLoad.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Helper
    /// Phase: 0
    /// </remarks>
    public abstract class Singleton<T> : MonoBehaviour where T : MonoBehaviour
    {
        #region Fields

        private static T _instance;
        private static bool _isQuitting;

        #endregion

        #region Properties

        /// <summary>
        /// Global access point for the singleton instance.
        /// Creates instance via FindObjectOfType if not yet assigned (Awake fallback only).
        /// </summary>
        public static T Instance
        {
            get
            {
                if (_isQuitting)
                {
                    Debug.LogWarning($"[Singleton] Instance of {typeof(T).Name} requested after application quit.");
                    return null;
                }

                if (_instance == null)
                {
                    _instance = FindObjectOfType<T>();

                    if (_instance == null)
                    {
                        Debug.LogWarning($"[Singleton] No instance of {typeof(T).Name} found in scene.");
                    }
                }

                return _instance;
            }
        }

        /// <summary>
        /// Returns true if the singleton instance exists and is not destroyed.
        /// </summary>
        public static bool HasInstance => _instance != null;

        #endregion

        #region Unity Lifecycle

        protected virtual void Awake()
        {
            if (_instance != null && _instance != this)
            {
                Debug.LogWarning($"[Singleton] Duplicate {typeof(T).Name} detected. Destroying duplicate on '{gameObject.name}'.");
                Destroy(gameObject);
                return;
            }

            _instance = this as T;
            DontDestroyOnLoad(gameObject);
            OnSingletonAwake();
        }

        protected virtual void OnDestroy()
        {
            if (_instance == this)
            {
                _instance = null;
            }
        }

        protected virtual void OnApplicationQuit()
        {
            _isQuitting = true;
            _instance = null;
        }

        #endregion

        #region Protected Methods

        /// <summary>
        /// Called after singleton initialization in Awake.
        /// Override this instead of Awake in derived classes.
        /// </summary>
        protected virtual void OnSingletonAwake() { }

        #endregion
    }
}
