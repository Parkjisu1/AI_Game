using System;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// PlayerPrefs-based JSON save/load wrapper.
    /// Provides type-safe serialization for persistent game data.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Manager
    /// Phase: 0
    /// </remarks>
    public class SaveManager : Singleton<SaveManager>
    {
        #region Fields

        private const string KEY_PREFIX = "MS_";

        #endregion

        #region Public Methods

        /// <summary>
        /// Saves data as JSON to PlayerPrefs.
        /// </summary>
        /// <typeparam name="T">The data type to serialize.</typeparam>
        /// <param name="key">The save key (auto-prefixed).</param>
        /// <param name="data">The data to save.</param>
        public void Save<T>(string key, T data)
        {
            if (string.IsNullOrEmpty(key))
            {
                Debug.LogError("[SaveManager] Save key cannot be null or empty.");
                return;
            }

            try
            {
                string json = JsonUtility.ToJson(data);
                PlayerPrefs.SetString(GetPrefixedKey(key), json);
                PlayerPrefs.Save();
            }
            catch (Exception ex)
            {
                Debug.LogError($"[SaveManager] Failed to save key '{key}': {ex.Message}");
            }
        }

        /// <summary>
        /// Loads data from PlayerPrefs and deserializes from JSON.
        /// </summary>
        /// <typeparam name="T">The data type to deserialize.</typeparam>
        /// <param name="key">The save key.</param>
        /// <param name="defaultValue">Default value if key not found.</param>
        /// <returns>The deserialized data or default value.</returns>
        public T Load<T>(string key, T defaultValue = default)
        {
            if (string.IsNullOrEmpty(key))
            {
                Debug.LogError("[SaveManager] Load key cannot be null or empty.");
                return defaultValue;
            }

            string prefixedKey = GetPrefixedKey(key);

            if (!PlayerPrefs.HasKey(prefixedKey))
            {
                return defaultValue;
            }

            try
            {
                string json = PlayerPrefs.GetString(prefixedKey);
                if (string.IsNullOrEmpty(json))
                {
                    return defaultValue;
                }

                return JsonUtility.FromJson<T>(json);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[SaveManager] Failed to load key '{key}': {ex.Message}");
                return defaultValue;
            }
        }

        /// <summary>
        /// Saves an integer value directly (no JSON overhead).
        /// </summary>
        /// <param name="key">The save key.</param>
        /// <param name="value">The integer value.</param>
        public void SaveInt(string key, int value)
        {
            PlayerPrefs.SetInt(GetPrefixedKey(key), value);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Loads an integer value directly.
        /// </summary>
        /// <param name="key">The save key.</param>
        /// <param name="defaultValue">Default value if key not found.</param>
        /// <returns>The integer value or default.</returns>
        public int LoadInt(string key, int defaultValue = 0)
        {
            return PlayerPrefs.GetInt(GetPrefixedKey(key), defaultValue);
        }

        /// <summary>
        /// Saves a float value directly (no JSON overhead).
        /// </summary>
        /// <param name="key">The save key.</param>
        /// <param name="value">The float value.</param>
        public void SaveFloat(string key, float value)
        {
            PlayerPrefs.SetFloat(GetPrefixedKey(key), value);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Loads a float value directly.
        /// </summary>
        /// <param name="key">The save key.</param>
        /// <param name="defaultValue">Default value if key not found.</param>
        /// <returns>The float value or default.</returns>
        public float LoadFloat(string key, float defaultValue = 0f)
        {
            return PlayerPrefs.GetFloat(GetPrefixedKey(key), defaultValue);
        }

        /// <summary>
        /// Saves a string value directly.
        /// </summary>
        /// <param name="key">The save key.</param>
        /// <param name="value">The string value.</param>
        public void SaveString(string key, string value)
        {
            PlayerPrefs.SetString(GetPrefixedKey(key), value ?? string.Empty);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Loads a string value directly.
        /// </summary>
        /// <param name="key">The save key.</param>
        /// <param name="defaultValue">Default value if key not found.</param>
        /// <returns>The string value or default.</returns>
        public string LoadString(string key, string defaultValue = "")
        {
            return PlayerPrefs.GetString(GetPrefixedKey(key), defaultValue);
        }

        /// <summary>
        /// Checks if a key exists in PlayerPrefs.
        /// </summary>
        /// <param name="key">The save key.</param>
        /// <returns>True if the key exists.</returns>
        public bool HasKey(string key)
        {
            return PlayerPrefs.HasKey(GetPrefixedKey(key));
        }

        /// <summary>
        /// Deletes a specific key from PlayerPrefs.
        /// </summary>
        /// <param name="key">The save key to delete.</param>
        public void Delete(string key)
        {
            string prefixedKey = GetPrefixedKey(key);
            if (PlayerPrefs.HasKey(prefixedKey))
            {
                PlayerPrefs.DeleteKey(prefixedKey);
                PlayerPrefs.Save();
            }
        }

        /// <summary>
        /// Deletes all saved data. Use with caution.
        /// </summary>
        public void DeleteAll()
        {
            PlayerPrefs.DeleteAll();
            PlayerPrefs.Save();
            Debug.LogWarning("[SaveManager] All saved data has been deleted.");
        }

        #endregion

        #region Private Methods

        private string GetPrefixedKey(string key)
        {
            return KEY_PREFIX + key;
        }

        #endregion
    }
}
