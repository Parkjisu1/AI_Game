using System.Collections.Generic;
using UnityEngine;

namespace VeilBreaker.Core
{
    /// <summary>
    /// Tag-based object pooling system for efficient GameObject reuse.
    /// Supports pre-warming, dynamic expansion, and organized hierarchy.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Pool
    /// Phase: 0
    /// </remarks>
    public class ObjectPool : Singleton<ObjectPool>
    {
        #region Fields

        private readonly Dictionary<string, Queue<GameObject>> _pools = new();
        private readonly Dictionary<string, GameObject> _prefabs = new();
        private readonly Dictionary<string, Transform> _parents = new();
        private readonly Dictionary<string, List<GameObject>> _activeObjects = new();

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize a pool with the specified tag, prefab, and initial size.
        /// Skips if the tag is already registered.
        /// </summary>
        /// <param name="tag">Unique identifier for this pool.</param>
        /// <param name="prefab">Prefab to instantiate.</param>
        /// <param name="size">Number of instances to pre-create.</param>
        public void Init(string tag, GameObject prefab, int size)
        {
            if (string.IsNullOrEmpty(tag) || prefab == null)
            {
                Debug.LogWarning("[ObjectPool] Init called with invalid tag or null prefab.");
                return;
            }

            if (_pools.ContainsKey(tag))
            {
                Debug.LogWarning($"[ObjectPool] Pool '{tag}' already initialized. Skipping.");
                return;
            }

            _prefabs[tag] = prefab;
            _pools[tag] = new Queue<GameObject>();
            _activeObjects[tag] = new List<GameObject>();

            var parent = new GameObject($"Pool_{tag}");
            parent.transform.SetParent(transform);
            _parents[tag] = parent.transform;

            for (int i = 0; i < size; i++)
            {
                var obj = CreateInstance(tag);
                obj.SetActive(false);
                _pools[tag].Enqueue(obj);
            }
        }

        /// <summary>
        /// Spawn an object from the pool. If the pool is empty, dynamically creates a new instance.
        /// </summary>
        /// <param name="tag">Pool tag to spawn from.</param>
        /// <param name="position">World position.</param>
        /// <param name="rotation">World rotation.</param>
        /// <returns>Activated GameObject, or null if the tag is not registered.</returns>
        public GameObject Spawn(string tag, Vector3 position, Quaternion rotation)
        {
            if (!_pools.ContainsKey(tag))
            {
                Debug.LogWarning($"[ObjectPool] Pool '{tag}' not found. Call Init first.");
                return null;
            }

            GameObject obj;

            if (_pools[tag].Count > 0)
            {
                obj = _pools[tag].Dequeue();

                // Skip destroyed objects
                while (obj == null && _pools[tag].Count > 0)
                {
                    obj = _pools[tag].Dequeue();
                }

                if (obj == null)
                {
                    obj = CreateInstance(tag);
                }
            }
            else
            {
                obj = CreateInstance(tag);
            }

            obj.transform.position = position;
            obj.transform.rotation = rotation;
            obj.SetActive(true);

            _activeObjects[tag].Add(obj);

            return obj;
        }

        /// <summary>
        /// Spawn an object from the pool under a specific parent transform.
        /// </summary>
        public GameObject Spawn(string tag, Vector3 position, Quaternion rotation, Transform parent)
        {
            var obj = Spawn(tag, position, rotation);
            if (obj != null && parent != null)
            {
                obj.transform.SetParent(parent);
            }
            return obj;
        }

        /// <summary>
        /// Return an object to the pool. Deactivates the object and re-parents it.
        /// </summary>
        /// <param name="obj">GameObject to return.</param>
        public void Despawn(GameObject obj)
        {
            if (obj == null) return;

            obj.SetActive(false);

            var poolTag = obj.GetComponent<PoolTag>();
            if (poolTag == null)
            {
                Debug.LogWarning($"[ObjectPool] Despawning object '{obj.name}' without PoolTag. Destroying instead.");
                Destroy(obj);
                return;
            }

            string tag = poolTag.Tag;

            if (_activeObjects.ContainsKey(tag))
            {
                _activeObjects[tag].Remove(obj);
            }

            if (_parents.ContainsKey(tag))
            {
                obj.transform.SetParent(_parents[tag]);
            }

            if (_pools.ContainsKey(tag))
            {
                _pools[tag].Enqueue(obj);
            }
            else
            {
                Destroy(obj);
            }
        }

        /// <summary>
        /// Get the number of available (inactive) objects in a pool.
        /// </summary>
        public int GetAvailableCount(string tag)
        {
            if (_pools.TryGetValue(tag, out var queue))
            {
                return queue.Count;
            }
            return 0;
        }

        /// <summary>
        /// Get the number of currently active objects from a pool.
        /// </summary>
        public int GetActiveCount(string tag)
        {
            if (_activeObjects.TryGetValue(tag, out var list))
            {
                return list.Count;
            }
            return 0;
        }

        /// <summary>
        /// Clear all pools and destroy all pooled objects.
        /// </summary>
        public void ClearAll()
        {
            foreach (var kvp in _pools)
            {
                while (kvp.Value.Count > 0)
                {
                    var obj = kvp.Value.Dequeue();
                    if (obj != null) Destroy(obj);
                }
            }

            foreach (var kvp in _activeObjects)
            {
                foreach (var obj in kvp.Value)
                {
                    if (obj != null) Destroy(obj);
                }
            }

            _pools.Clear();
            _prefabs.Clear();
            _parents.Clear();
            _activeObjects.Clear();
        }

        #endregion

        #region Private Methods

        private GameObject CreateInstance(string tag)
        {
            if (!_prefabs.TryGetValue(tag, out var prefab))
            {
                Debug.LogError($"[ObjectPool] No prefab registered for tag '{tag}'.");
                return null;
            }

            var parent = _parents.ContainsKey(tag) ? _parents[tag] : transform;
            var obj = Instantiate(prefab, parent);
            obj.name = $"{prefab.name}_{tag}";

            var poolTag = obj.GetComponent<PoolTag>();
            if (poolTag == null)
            {
                poolTag = obj.AddComponent<PoolTag>();
            }
            poolTag.Tag = tag;

            return obj;
        }

        #endregion
    }

    /// <summary>
    /// Lightweight component attached to pooled objects to track their pool tag.
    /// Used by ObjectPool.Despawn to return objects to the correct pool.
    /// </summary>
    public class PoolTag : MonoBehaviour
    {
        /// <summary>
        /// The pool tag this object belongs to.
        /// </summary>
        [HideInInspector]
        public string Tag;
    }
}
