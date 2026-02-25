using System.Collections.Generic;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Manages popup lifecycle: instantiation, stacking, and closing.
    /// Popups are spawned from prefabs defined in PopUpConfig.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Service
    /// Phase: 0
    /// </remarks>
    public class PopUpService : Singleton<PopUpService>
    {
        #region Fields

        [SerializeField] private PopUpConfig popUpConfig;
        [SerializeField] private Transform popupParent;

        private readonly Stack<GameObject> _popupStack = new Stack<GameObject>();
        private readonly Dictionary<string, GameObject> _activePopups = new Dictionary<string, GameObject>();

        #endregion

        #region Properties

        /// <summary>Number of currently open popups.</summary>
        public int OpenCount => _popupStack.Count;

        /// <summary>Whether any popup is currently open.</summary>
        public bool HasOpenPopup => _popupStack.Count > 0;

        #endregion

        #region Public Methods

        /// <summary>
        /// Opens a popup by name. Instantiates from the prefab in PopUpConfig.
        /// Returns the component of type T on the instantiated popup.
        /// </summary>
        /// <typeparam name="T">The MonoBehaviour component type on the popup prefab.</typeparam>
        /// <param name="popupName">The popup name as registered in PopUpConfig.</param>
        /// <returns>The component of type T, or null if failed.</returns>
        public T ShowPopup<T>(string popupName) where T : MonoBehaviour
        {
            if (popUpConfig == null)
            {
                Debug.LogError("[PopUpService] PopUpConfig is not assigned.");
                return null;
            }

            if (string.IsNullOrEmpty(popupName))
            {
                Debug.LogError("[PopUpService] Popup name cannot be null or empty.");
                return null;
            }

            // Check if already open
            if (_activePopups.TryGetValue(popupName, out GameObject existing))
            {
                if (existing != null)
                {
                    existing.SetActive(true);
                    T existingComponent = existing.GetComponent<T>();
                    return existingComponent;
                }

                // Clean up stale reference
                _activePopups.Remove(popupName);
            }

            GameObject prefab = popUpConfig.GetPrefab(popupName);
            if (prefab == null)
            {
                Debug.LogError($"[PopUpService] No prefab found for popup '{popupName}'.");
                return null;
            }

            Transform parent = popupParent != null ? popupParent : transform;
            GameObject instance = Instantiate(prefab, parent);
            instance.name = popupName;

            _activePopups[popupName] = instance;
            _popupStack.Push(instance);

            T component = instance.GetComponent<T>();
            if (component == null)
            {
                Debug.LogWarning($"[PopUpService] Popup '{popupName}' does not have component {typeof(T).Name}.");
            }

            return component;
        }

        /// <summary>
        /// Opens a popup by name without requiring a specific component type.
        /// </summary>
        /// <param name="popupName">The popup name as registered in PopUpConfig.</param>
        /// <returns>The instantiated popup GameObject, or null if failed.</returns>
        public GameObject ShowPopup(string popupName)
        {
            if (popUpConfig == null)
            {
                Debug.LogError("[PopUpService] PopUpConfig is not assigned.");
                return null;
            }

            if (string.IsNullOrEmpty(popupName))
            {
                Debug.LogError("[PopUpService] Popup name cannot be null or empty.");
                return null;
            }

            if (_activePopups.TryGetValue(popupName, out GameObject existing))
            {
                if (existing != null)
                {
                    existing.SetActive(true);
                    return existing;
                }

                _activePopups.Remove(popupName);
            }

            GameObject prefab = popUpConfig.GetPrefab(popupName);
            if (prefab == null)
            {
                Debug.LogError($"[PopUpService] No prefab found for popup '{popupName}'.");
                return null;
            }

            Transform parent = popupParent != null ? popupParent : transform;
            GameObject instance = Instantiate(prefab, parent);
            instance.name = popupName;

            _activePopups[popupName] = instance;
            _popupStack.Push(instance);

            return instance;
        }

        /// <summary>
        /// Closes and destroys a popup by name.
        /// </summary>
        /// <param name="popupName">The popup name to close.</param>
        public void ClosePopup(string popupName)
        {
            if (string.IsNullOrEmpty(popupName)) return;

            if (_activePopups.TryGetValue(popupName, out GameObject instance))
            {
                _activePopups.Remove(popupName);

                if (instance != null)
                {
                    Destroy(instance);
                }

                RebuildStack();
            }
        }

        /// <summary>
        /// Closes the topmost popup on the stack.
        /// </summary>
        public void CloseTopPopup()
        {
            if (_popupStack.Count == 0) return;

            GameObject top = _popupStack.Pop();
            if (top != null)
            {
                // Find and remove from active dictionary
                string keyToRemove = null;
                foreach (var kvp in _activePopups)
                {
                    if (kvp.Value == top)
                    {
                        keyToRemove = kvp.Key;
                        break;
                    }
                }

                if (keyToRemove != null)
                {
                    _activePopups.Remove(keyToRemove);
                }

                Destroy(top);
            }
        }

        /// <summary>
        /// Closes all open popups.
        /// </summary>
        public void CloseAllPopups()
        {
            foreach (var kvp in _activePopups)
            {
                if (kvp.Value != null)
                {
                    Destroy(kvp.Value);
                }
            }

            _activePopups.Clear();
            _popupStack.Clear();
        }

        /// <summary>
        /// Checks if a specific popup is currently open.
        /// </summary>
        /// <param name="popupName">The popup name to check.</param>
        /// <returns>True if the popup is open.</returns>
        public bool IsOpen(string popupName)
        {
            if (string.IsNullOrEmpty(popupName)) return false;

            if (_activePopups.TryGetValue(popupName, out GameObject instance))
            {
                return instance != null && instance.activeInHierarchy;
            }

            return false;
        }

        /// <summary>
        /// Gets the instance of an active popup by name.
        /// </summary>
        /// <typeparam name="T">The component type to retrieve.</typeparam>
        /// <param name="popupName">The popup name.</param>
        /// <returns>The component, or null if not found.</returns>
        public T GetPopup<T>(string popupName) where T : MonoBehaviour
        {
            if (string.IsNullOrEmpty(popupName)) return null;

            if (_activePopups.TryGetValue(popupName, out GameObject instance))
            {
                if (instance != null)
                {
                    return instance.GetComponent<T>();
                }
            }

            return null;
        }

        #endregion

        #region Singleton Lifecycle

        protected override void OnSingletonDestroy()
        {
            CloseAllPopups();
        }

        #endregion

        #region Private Methods

        private void RebuildStack()
        {
            // Rebuild stack from active popups (order might shift, but stack integrity maintained)
            Stack<GameObject> newStack = new Stack<GameObject>();
            GameObject[] items = _popupStack.ToArray();

            // Reverse iterate since Stack.ToArray returns top-first
            for (int i = items.Length - 1; i >= 0; i--)
            {
                if (items[i] != null && items[i].activeInHierarchy)
                {
                    newStack.Push(items[i]);
                }
            }

            _popupStack.Clear();
            GameObject[] rebuiltItems = newStack.ToArray();
            for (int i = rebuiltItems.Length - 1; i >= 0; i--)
            {
                _popupStack.Push(rebuiltItems[i]);
            }
        }

        #endregion
    }
}
