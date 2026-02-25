using System;
using UnityEngine;

namespace DropTheCat.Core
{
    /// <summary>
    /// Local save/load system wrapping PlayerPrefs with JSON serialization.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Manager
    /// Phase: 0
    /// </remarks>
    public class SaveManager : Singleton<SaveManager>
    {
        #region Constants

        private const string SAVE_PREFIX = "DTC_";

        #endregion

        #region Public Methods

        /// <summary>
        /// Save data as JSON to PlayerPrefs.
        /// </summary>
        public void Save<T>(string key, T data)
        {
            if (string.IsNullOrEmpty(key)) return;

            string json = JsonUtility.ToJson(data);
            PlayerPrefs.SetString(SAVE_PREFIX + key, json);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Save an int value to PlayerPrefs.
        /// </summary>
        public void SaveInt(string key, int value)
        {
            PlayerPrefs.SetInt(SAVE_PREFIX + key, value);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Save a float value to PlayerPrefs.
        /// </summary>
        public void SaveFloat(string key, float value)
        {
            PlayerPrefs.SetFloat(SAVE_PREFIX + key, value);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Save a string value to PlayerPrefs.
        /// </summary>
        public void SaveString(string key, string value)
        {
            PlayerPrefs.SetString(SAVE_PREFIX + key, value ?? string.Empty);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Load data from PlayerPrefs and deserialize from JSON.
        /// </summary>
        public T Load<T>(string key, T defaultValue = default)
        {
            if (string.IsNullOrEmpty(key)) return defaultValue;

            string fullKey = SAVE_PREFIX + key;
            if (!PlayerPrefs.HasKey(fullKey)) return defaultValue;

            string json = PlayerPrefs.GetString(fullKey);
            if (string.IsNullOrEmpty(json)) return defaultValue;

            try
            {
                return JsonUtility.FromJson<T>(json);
            }
            catch (Exception e)
            {
                Debug.LogError($"[SaveManager] Failed to load key '{key}': {e.Message}");
                return defaultValue;
            }
        }

        /// <summary>
        /// Load an int value from PlayerPrefs.
        /// </summary>
        public int LoadInt(string key, int defaultValue = 0)
        {
            return PlayerPrefs.GetInt(SAVE_PREFIX + key, defaultValue);
        }

        /// <summary>
        /// Load a float value from PlayerPrefs.
        /// </summary>
        public float LoadFloat(string key, float defaultValue = 0f)
        {
            return PlayerPrefs.GetFloat(SAVE_PREFIX + key, defaultValue);
        }

        /// <summary>
        /// Load a string value from PlayerPrefs.
        /// </summary>
        public string LoadString(string key, string defaultValue = "")
        {
            return PlayerPrefs.GetString(SAVE_PREFIX + key, defaultValue);
        }

        /// <summary>
        /// Check if a key exists in PlayerPrefs.
        /// </summary>
        public bool HasKey(string key)
        {
            return PlayerPrefs.HasKey(SAVE_PREFIX + key);
        }

        /// <summary>
        /// Delete a specific key from PlayerPrefs.
        /// </summary>
        public void DeleteKey(string key)
        {
            PlayerPrefs.DeleteKey(SAVE_PREFIX + key);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Delete all saved data.
        /// </summary>
        public void DeleteAll()
        {
            PlayerPrefs.DeleteAll();
            PlayerPrefs.Save();
        }

        #endregion
    }
}
