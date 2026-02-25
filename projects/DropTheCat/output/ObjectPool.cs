using System.Collections.Generic;
using UnityEngine;

namespace DropTheCat.Core
{
    /// <summary>
    /// Generic GameObject pooling system. Manages multiple pools by prefab InstanceID.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Pool
    /// Phase: 0
    /// </remarks>
    public class ObjectPool : Singleton<ObjectPool>
    {
        #region Inner Types

        private class Pool
        {
            public readonly Queue<Component> Available = new Queue<Component>();
            public readonly List<Component> Active = new List<Component>();
            public GameObject Prefab;
            public Transform Parent;
        }

        #endregion

        #region Fields

        private readonly Dictionary<int, Pool> _pools = new Dictionary<int, Pool>();

        #endregion

        #region Public Methods

        /// <summary>
        /// Pre-warm a pool by pre-instantiating objects.
        /// </summary>
        public void PreWarm<T>(T prefab, int count, Transform parent = null) where T : Component
        {
            int id = prefab.gameObject.GetInstanceID();
            var pool = GetOrCreatePool(prefab.gameObject, id, parent);

            for (int i = 0; i < count; i++)
            {
                var obj = CreateInstance<T>(prefab.gameObject, pool.Parent);
                obj.gameObject.SetActive(false);
                pool.Available.Enqueue(obj);
            }
        }

        /// <summary>
        /// Pre-warm a pool using a GameObject prefab.
        /// </summary>
        public void PreWarm(GameObject prefab, int count, Transform parent = null)
        {
            int id = prefab.GetInstanceID();
            var pool = GetOrCreatePool(prefab, id, parent);

            for (int i = 0; i < count; i++)
            {
                var obj = CreateInstance<Transform>(prefab, pool.Parent);
                obj.gameObject.SetActive(false);
                pool.Available.Enqueue(obj);
            }
        }

        /// <summary>
        /// Get a pooled object of type T. Creates a new one if pool is empty.
        /// </summary>
        public T Get<T>(T prefab, Transform parent = null) where T : Component
        {
            int id = prefab.gameObject.GetInstanceID();
            var pool = GetOrCreatePool(prefab.gameObject, id, parent);

            T component;
            while (pool.Available.Count > 0)
            {
                var candidate = pool.Available.Dequeue();
                if (candidate == null) continue;

                component = candidate as T;
                if (component == null) continue;

                component.gameObject.SetActive(true);
                pool.Active.Add(component);
                return component;
            }

            // Pool empty, create new instance
            component = CreateInstance<T>(prefab.gameObject, pool.Parent);
            component.gameObject.SetActive(true);
            pool.Active.Add(component);
            return component;
        }

        /// <summary>
        /// Get a pooled GameObject. Creates a new one if pool is empty.
        /// </summary>
        public GameObject Get(GameObject prefab, Transform parent = null)
        {
            return Get(prefab.transform, parent).gameObject;
        }

        /// <summary>
        /// Return an object to its pool.
        /// </summary>
        public void Release(Component obj)
        {
            if (obj == null) return;

            obj.gameObject.SetActive(false);

            foreach (var kvp in _pools)
            {
                if (kvp.Value.Active.Remove(obj))
                {
                    kvp.Value.Available.Enqueue(obj);
                    return;
                }
            }

            // Object not found in any pool, just deactivate
            Debug.LogWarning($"[ObjectPool] Released object '{obj.name}' not found in any pool.");
        }

        /// <summary>
        /// Return a GameObject to its pool.
        /// </summary>
        public void Release(GameObject obj)
        {
            if (obj == null) return;
            Release(obj.transform);
        }

        /// <summary>
        /// Clear all pools and destroy pooled objects.
        /// </summary>
        public void ClearPool()
        {
            foreach (var kvp in _pools)
            {
                var pool = kvp.Value;
                while (pool.Available.Count > 0)
                {
                    var obj = pool.Available.Dequeue();
                    if (obj != null) Destroy(obj.gameObject);
                }
                foreach (var obj in pool.Active)
                {
                    if (obj != null) Destroy(obj.gameObject);
                }
                pool.Active.Clear();
            }
            _pools.Clear();
        }

        /// <summary>
        /// Clear a specific prefab's pool.
        /// </summary>
        public void ClearPool(GameObject prefab)
        {
            int id = prefab.GetInstanceID();
            if (!_pools.TryGetValue(id, out var pool)) return;

            while (pool.Available.Count > 0)
            {
                var obj = pool.Available.Dequeue();
                if (obj != null) Destroy(obj.gameObject);
            }
            foreach (var obj in pool.Active)
            {
                if (obj != null) Destroy(obj.gameObject);
            }
            pool.Active.Clear();
            _pools.Remove(id);
        }

        /// <summary>
        /// Release all active objects back to their pools.
        /// </summary>
        public void ReleaseAll()
        {
            foreach (var kvp in _pools)
            {
                var pool = kvp.Value;
                for (int i = pool.Active.Count - 1; i >= 0; i--)
                {
                    var obj = pool.Active[i];
                    if (obj != null)
                    {
                        obj.gameObject.SetActive(false);
                        pool.Available.Enqueue(obj);
                    }
                }
                pool.Active.Clear();
            }
        }

        #endregion

        #region Private Methods

        private Pool GetOrCreatePool(GameObject prefab, int id, Transform parent)
        {
            if (_pools.TryGetValue(id, out var pool)) return pool;

            pool = new Pool
            {
                Prefab = prefab,
                Parent = parent != null ? parent : transform
            };
            _pools[id] = pool;
            return pool;
        }

        private T CreateInstance<T>(GameObject prefab, Transform parent) where T : Component
        {
            var go = Instantiate(prefab, parent);
            go.name = prefab.name;
            var component = go.GetComponent<T>();
            return component;
        }

        #endregion

        #region Unity Lifecycle

        protected override void OnDestroy()
        {
            ClearPool();
            base.OnDestroy();
        }

        #endregion
    }
}
