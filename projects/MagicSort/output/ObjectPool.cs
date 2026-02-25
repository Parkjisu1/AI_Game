using System;
using System.Collections.Generic;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Generic object pool for Unity Components.
    /// Reduces garbage collection overhead by reusing objects instead of Instantiate/Destroy.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Pool
    /// Phase: 0
    /// </remarks>
    /// <typeparam name="T">The Component type to pool.</typeparam>
    public class Pool<T> where T : Component
    {
        #region Fields

        private readonly T _prefab;
        private readonly Transform _parent;
        private readonly Queue<T> _available = new Queue<T>();
        private readonly HashSet<T> _inUse = new HashSet<T>();
        private readonly Action<T> _onGet;
        private readonly Action<T> _onReturn;
        private readonly Action<T> _onDestroy;

        #endregion

        #region Properties

        /// <summary>Number of objects currently available in the pool.</summary>
        public int AvailableCount => _available.Count;

        /// <summary>Number of objects currently in use (checked out).</summary>
        public int InUseCount => _inUse.Count;

        /// <summary>Total number of objects managed by this pool.</summary>
        public int TotalCount => _available.Count + _inUse.Count;

        #endregion

        #region Constructor

        /// <summary>
        /// Creates a new object pool.
        /// </summary>
        /// <param name="prefab">The prefab to instantiate.</param>
        /// <param name="parent">The parent Transform for pooled objects.</param>
        /// <param name="onGet">Optional callback when an object is retrieved.</param>
        /// <param name="onReturn">Optional callback when an object is returned.</param>
        /// <param name="onDestroy">Optional callback when an object is destroyed.</param>
        public Pool(T prefab, Transform parent = null, Action<T> onGet = null, Action<T> onReturn = null, Action<T> onDestroy = null)
        {
            _prefab = prefab;
            _parent = parent;
            _onGet = onGet;
            _onReturn = onReturn;
            _onDestroy = onDestroy;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Pre-instantiates a number of objects into the pool.
        /// </summary>
        /// <param name="count">Number of objects to create.</param>
        public void Preload(int count)
        {
            for (int i = 0; i < count; i++)
            {
                T instance = CreateInstance();
                instance.gameObject.SetActive(false);
                _available.Enqueue(instance);
            }
        }

        /// <summary>
        /// Gets an object from the pool. Creates a new one if none are available.
        /// </summary>
        /// <returns>An active pooled object.</returns>
        public T Get()
        {
            T instance;

            if (_available.Count > 0)
            {
                instance = _available.Dequeue();

                // Handle case where object was destroyed externally
                if (instance == null || instance.gameObject == null)
                {
                    instance = CreateInstance();
                }
            }
            else
            {
                instance = CreateInstance();
            }

            instance.gameObject.SetActive(true);
            _inUse.Add(instance);

            _onGet?.Invoke(instance);

            return instance;
        }

        /// <summary>
        /// Gets an object from the pool at a specific position and rotation.
        /// </summary>
        /// <param name="position">World position.</param>
        /// <param name="rotation">World rotation.</param>
        /// <returns>An active pooled object.</returns>
        public T Get(Vector3 position, Quaternion rotation)
        {
            T instance = Get();
            instance.transform.SetPositionAndRotation(position, rotation);
            return instance;
        }

        /// <summary>
        /// Returns an object to the pool for reuse.
        /// </summary>
        /// <param name="instance">The object to return.</param>
        public void Return(T instance)
        {
            if (instance == null) return;

            if (!_inUse.Remove(instance))
            {
                Debug.LogWarning($"[Pool<{typeof(T).Name}>] Returning object that was not tracked as in-use.");
            }

            _onReturn?.Invoke(instance);

            instance.gameObject.SetActive(false);

            if (_parent != null)
            {
                instance.transform.SetParent(_parent);
            }

            _available.Enqueue(instance);
        }

        /// <summary>
        /// Returns all in-use objects to the pool.
        /// </summary>
        public void ReturnAll()
        {
            // Copy to list to avoid collection modification during iteration
            List<T> inUseList = new List<T>(_inUse);
            for (int i = 0; i < inUseList.Count; i++)
            {
                if (inUseList[i] != null)
                {
                    Return(inUseList[i]);
                }
            }

            _inUse.Clear();
        }

        /// <summary>
        /// Destroys all pooled objects and clears the pool.
        /// </summary>
        public void Clear()
        {
            foreach (T instance in _available)
            {
                if (instance != null)
                {
                    _onDestroy?.Invoke(instance);
                    UnityEngine.Object.Destroy(instance.gameObject);
                }
            }

            foreach (T instance in _inUse)
            {
                if (instance != null)
                {
                    _onDestroy?.Invoke(instance);
                    UnityEngine.Object.Destroy(instance.gameObject);
                }
            }

            _available.Clear();
            _inUse.Clear();
        }

        #endregion

        #region Private Methods

        private T CreateInstance()
        {
            T instance = UnityEngine.Object.Instantiate(_prefab, _parent);
            instance.gameObject.name = $"{_prefab.name}_pooled_{TotalCount}";
            return instance;
        }

        #endregion
    }
}
