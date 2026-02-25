using UnityEngine;

namespace DropTheCat.Core
{
    /// <summary>
    /// Singleton pattern base class for all Managers.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Base
    /// Phase: 0
    /// </remarks>
    public class Singleton<T> : MonoBehaviour where T : MonoBehaviour
    {
        #region Fields

        private static T _instance;
        private static readonly object _lock = new object();
        private static bool _applicationIsQuitting;

        #endregion

        #region Properties

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
                    return _instance;
                }
            }
        }

        public static bool HasInstance => _instance != null;

        #endregion

        #region Unity Lifecycle

        protected virtual void Awake()
        {
            if (_instance != null && _instance != this)
            {
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
            _applicationIsQuitting = true;
        }

        #endregion

        #region Protected Methods

        /// <summary>
        /// Called after singleton instance is set. Override instead of Awake.
        /// </summary>
        protected virtual void OnSingletonAwake() { }

        #endregion
    }
}
