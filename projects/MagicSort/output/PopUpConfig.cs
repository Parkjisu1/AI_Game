using System;
using System.Collections.Generic;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// ScriptableObject that maps popup names to their prefabs.
    /// Create via Assets > Create > MagicSort > PopUp Config.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Config
    /// Phase: 0
    /// </remarks>
    [CreateAssetMenu(fileName = "PopUpConfig", menuName = "MagicSort/PopUp Config")]
    public class PopUpConfig : ScriptableObject
    {
        #region Nested Types

        /// <summary>
        /// Maps a popup identifier to its prefab.
        /// </summary>
        [Serializable]
        public class PopUpEntry
        {
            [Tooltip("Unique identifier for this popup (used in ShowPopup calls).")]
            public string popupName;

            [Tooltip("The popup prefab to instantiate.")]
            public GameObject prefab;
        }

        #endregion

        #region Fields

        [SerializeField] private List<PopUpEntry> popupEntries = new List<PopUpEntry>();

        private Dictionary<string, GameObject> _lookupCache;

        #endregion

        #region Properties

        /// <summary>
        /// Number of registered popup entries.
        /// </summary>
        public int Count => popupEntries != null ? popupEntries.Count : 0;

        #endregion

        #region Public Methods

        /// <summary>
        /// Gets the prefab for a popup by name.
        /// </summary>
        /// <param name="popupName">The popup identifier.</param>
        /// <returns>The prefab GameObject, or null if not found.</returns>
        public GameObject GetPrefab(string popupName)
        {
            if (string.IsNullOrEmpty(popupName)) return null;

            EnsureCacheBuilt();

            if (_lookupCache.TryGetValue(popupName, out GameObject prefab))
            {
                return prefab;
            }

            Debug.LogWarning($"[PopUpConfig] Popup '{popupName}' not found in config.");
            return null;
        }

        /// <summary>
        /// Checks if a popup name exists in the config.
        /// </summary>
        /// <param name="popupName">The popup identifier.</param>
        /// <returns>True if the popup is registered.</returns>
        public bool HasPopup(string popupName)
        {
            if (string.IsNullOrEmpty(popupName)) return false;

            EnsureCacheBuilt();
            return _lookupCache.ContainsKey(popupName);
        }

        /// <summary>
        /// Forces the lookup cache to rebuild. Call if entries are modified at runtime.
        /// </summary>
        public void InvalidateCache()
        {
            _lookupCache = null;
        }

        #endregion

        #region Private Methods

        private void EnsureCacheBuilt()
        {
            if (_lookupCache != null) return;

            _lookupCache = new Dictionary<string, GameObject>();

            if (popupEntries == null) return;

            for (int i = 0; i < popupEntries.Count; i++)
            {
                PopUpEntry entry = popupEntries[i];
                if (entry == null || string.IsNullOrEmpty(entry.popupName)) continue;

                if (_lookupCache.ContainsKey(entry.popupName))
                {
                    Debug.LogWarning($"[PopUpConfig] Duplicate popup name: '{entry.popupName}'. Using first entry.");
                    continue;
                }

                _lookupCache[entry.popupName] = entry.prefab;
            }
        }

        private void OnValidate()
        {
            InvalidateCache();
        }

        #endregion
    }
}
