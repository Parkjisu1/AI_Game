using System.Collections.Generic;
using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.Data
{
    /// <summary>
    /// Centralized resource loading utility that caches loaded assets to avoid
    /// repeated Resources.Load calls. All systems must route resource loading
    /// through this class rather than calling Resources.Load directly.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Generic
    /// Role: Provider
    /// System: Data
    /// Phase: 1
    /// </remarks>
    public class ResourceContainer : Singleton<ResourceContainer>
    {
        #region Fields

        private readonly Dictionary<string, Object> _cache = new();

        #endregion

        #region Properties

        /// <summary>
        /// Returns the number of currently cached assets.
        /// </summary>
        public int CachedCount => _cache.Count;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            _cache.Clear();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Loads a prefab or asset of type T from Resources. Returns cached result on subsequent calls.
        /// </summary>
        /// <typeparam name="T">Type of the asset to load (must be UnityEngine.Object).</typeparam>
        /// <param name="path">Resources-relative path (e.g. "Prefabs/Hero").</param>
        /// <returns>The loaded asset, or null if not found.</returns>
        public T LoadPrefab<T>(string path) where T : Object
        {
            if (string.IsNullOrEmpty(path))
            {
                Debug.LogWarning("[ResourceContainer] LoadPrefab called with null or empty path.");
                return null;
            }

            // Step 1: Check cache
            if (_cache.TryGetValue(path, out Object cached))
            {
                return cached as T;
            }

            // Step 2: Load from Resources
            T loaded = Resources.Load<T>(path);

            if (loaded == null)
            {
                Debug.LogWarning($"[ResourceContainer] Asset not found at path: {path}");
                return null;
            }

            // Step 3: Store in cache
            _cache[path] = loaded;
            return loaded;
        }

        /// <summary>
        /// Loads a Sprite from Resources. Returns cached result on subsequent calls.
        /// </summary>
        /// <param name="path">Resources-relative path (e.g. "Sprites/Hero/hero_01").</param>
        /// <returns>The loaded Sprite, or null if not found.</returns>
        public Sprite LoadSprite(string path)
        {
            return LoadPrefab<Sprite>(path);
        }

        /// <summary>
        /// Loads a JSON string from a TextAsset in Resources. Returns cached content on subsequent calls.
        /// </summary>
        /// <param name="path">Resources-relative path to a .json TextAsset (e.g. "Data/stage_data").</param>
        /// <returns>The JSON string content, or null if not found.</returns>
        public string LoadJson(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                Debug.LogWarning("[ResourceContainer] LoadJson called with null or empty path.");
                return null;
            }

            // Use a suffixed key to distinguish TextAsset from other types at same path
            string cacheKey = path + "::json";

            if (_cache.TryGetValue(cacheKey, out Object cached))
            {
                return (cached as TextAsset)?.text;
            }

            TextAsset textAsset = Resources.Load<TextAsset>(path);

            if (textAsset == null)
            {
                Debug.LogWarning($"[ResourceContainer] TextAsset not found at path: {path}");
                return null;
            }

            _cache[cacheKey] = textAsset;
            return textAsset.text;
        }

        /// <summary>
        /// Preloads a set of resource paths into the cache to avoid runtime hitches.
        /// Attempts to load each path as an Object; logs a warning for any that fail.
        /// </summary>
        /// <param name="paths">Array of Resources-relative paths to preload.</param>
        public void PreloadAll(string[] paths)
        {
            if (paths == null || paths.Length == 0)
            {
                Debug.LogWarning("[ResourceContainer] PreloadAll called with null or empty paths array.");
                return;
            }

            foreach (string path in paths)
            {
                if (string.IsNullOrEmpty(path))
                {
                    continue;
                }

                if (_cache.ContainsKey(path))
                {
                    continue;
                }

                Object loaded = Resources.Load<Object>(path);

                if (loaded == null)
                {
                    Debug.LogWarning($"[ResourceContainer] Preload failed - asset not found: {path}");
                    continue;
                }

                _cache[path] = loaded;
            }
        }

        /// <summary>
        /// Removes a specific entry from the cache and unloads the asset from memory.
        /// </summary>
        /// <param name="path">The Resources-relative path to evict.</param>
        public void Evict(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return;
            }

            if (_cache.TryGetValue(path, out Object asset))
            {
                _cache.Remove(path);
                Resources.UnloadAsset(asset);
            }
        }

        /// <summary>
        /// Clears all cached assets and unloads unused assets from memory.
        /// Call this on scene transitions to free memory.
        /// </summary>
        public void ClearAll()
        {
            _cache.Clear();
            Resources.UnloadUnusedAssets();
        }

        #endregion
    }
}
