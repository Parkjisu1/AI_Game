using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Generic Singleton base class for MonoBehaviour managers.
    /// Ensures only one instance exists and optionally persists across scenes.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Helper
    /// Phase: 0
    /// </remarks>
    /// <typeparam name="T">The type of the singleton MonoBehaviour.</typeparam>
    public abstract class Singleton<T> : MonoBehaviour where T : MonoBehaviour
    {
        #region Fields

        private static T _instance;
        private static readonly object _lock = new object();
        private static bool _applicationIsQuitting;

        [SerializeField] private bool persistAcrossScenes = true;

        #endregion

        #region Properties

        /// <summary>
        /// Gets the singleton instance. Returns null if the application is quitting.
        /// </summary>
        public static T Instance
        {
            get
            {
                if (_applicationIsQuitting)
                {
                    Debug.LogWarning($"[Singleton] Instance of {typeof(T)} already destroyed on application quit.");
                    return null;
                }

                lock (_lock)
                {
                    if (_instance == null)
                    {
                        Debug.LogWarning($"[Singleton] Instance of {typeof(T)} is null. Ensure it exists in the scene.");
                    }

                    return _instance;
                }
            }
        }

        /// <summary>
        /// Returns true if a valid instance exists and the application is not quitting.
        /// </summary>
        public static bool HasInstance => _instance != null && !_applicationIsQuitting;

        #endregion

        #region Unity Lifecycle

        protected virtual void Awake()
        {
            lock (_lock)
            {
                if (_instance == null)
                {
                    _instance = this as T;

                    if (persistAcrossScenes)
                    {
                        if (transform.parent != null)
                        {
                            transform.SetParent(null);
                        }
                        DontDestroyOnLoad(gameObject);
                    }

                    OnSingletonAwake();
                }
                else if (_instance != this)
                {
                    Debug.LogWarning($"[Singleton] Duplicate instance of {typeof(T)} found on {gameObject.name}. Destroying.");
                    Destroy(gameObject);
                }
            }
        }

        protected virtual void OnDestroy()
        {
            if (_instance == this)
            {
                OnSingletonDestroy();
                _instance = null;
            }
        }

        protected virtual void OnApplicationQuit()
        {
            _applicationIsQuitting = true;
        }

        #endregion

        #region Protected Methods

        /// <summary>
        /// Called once when the singleton is first initialized.
        /// Override this instead of Awake for initialization logic.
        /// </summary>
        protected virtual void OnSingletonAwake() { }

        /// <summary>
        /// Called when the singleton instance is being destroyed.
        /// Override this for cleanup logic.
        /// </summary>
        protected virtual void OnSingletonDestroy() { }

        #endregion
    }
}
