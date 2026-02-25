using System;
using System.IO;
using System.Collections;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

using VeilBreaker.Core;

namespace VeilBreaker.Data
{
    /// <summary>
    /// Local JSON-based save/load system.
    /// Handles user data persistence with optional AES encryption.
    /// PlayerPrefs for lightweight settings, file-based JSON for user data.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 1
    /// </remarks>
    public class SaveManager : Singleton<SaveManager>
    {
        #region Fields

        private string _saveDirectoryPath;
        private const string SAVE_FILE_NAME = "save_data.json";
        private const string ENCRYPTION_KEY = "VeilBreaker2026!";
        private const int ENCRYPTION_KEY_SIZE = 128;

        [SerializeField] private bool _useEncryption;

        private Dictionary<string, string> _dataStore = new();
        private bool _isDirty;
        private Coroutine _autoSaveCoroutine;

        #endregion

        #region Properties

        private string SaveFilePath => Path.Combine(_saveDirectoryPath, SAVE_FILE_NAME);

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize save system. Sets up save path, loads existing data or creates defaults.
        /// </summary>
        public void Init()
        {
            _saveDirectoryPath = Path.Combine(Application.persistentDataPath, "data");

            if (!Directory.Exists(_saveDirectoryPath))
            {
                Directory.CreateDirectory(_saveDirectoryPath);
            }

            if (File.Exists(SaveFilePath))
            {
                LoadAllFromDisk();
            }
            else
            {
                _dataStore = new Dictionary<string, string>();
                SaveToDisk();
            }

            _autoSaveCoroutine = StartCoroutine(AutoSaveRoutine());

            EventManager.Publish(GameConstants.Events.OnDataLoaded);
        }

        /// <summary>
        /// Save a typed object under the specified key.
        /// Serializes to JSON and marks data as dirty for auto-save.
        /// </summary>
        /// <typeparam name="T">Serializable data type.</typeparam>
        /// <param name="key">Save key from GameConstants.Save.</param>
        /// <param name="data">Data object to serialize and save.</param>
        public void Save<T>(string key, T data)
        {
            if (string.IsNullOrEmpty(key))
            {
                Debug.LogWarning("[SaveManager] Save called with null or empty key.");
                return;
            }

            string json = JsonUtility.ToJson(data);
            _dataStore[key] = json;
            _isDirty = true;
        }

        /// <summary>
        /// Flush all pending changes to disk immediately.
        /// Called automatically by auto-save, but can be called manually.
        /// </summary>
        public void Save()
        {
            SaveToDisk();
            EventManager.Publish(GameConstants.Events.OnGameSaved);
        }

        /// <summary>
        /// Load a typed object from the specified key.
        /// Returns a new instance of T if the key does not exist.
        /// </summary>
        /// <typeparam name="T">Serializable data type with parameterless constructor.</typeparam>
        /// <param name="key">Save key from GameConstants.Save.</param>
        /// <returns>Deserialized data or new default instance.</returns>
        public T Load<T>(string key) where T : new()
        {
            if (string.IsNullOrEmpty(key))
            {
                Debug.LogWarning("[SaveManager] Load called with null or empty key.");
                return new T();
            }

            if (_dataStore.TryGetValue(key, out var json) && !string.IsNullOrEmpty(json))
            {
                try
                {
                    return JsonUtility.FromJson<T>(json);
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[SaveManager] Failed to deserialize key '{key}': {ex.Message}");
                    return new T();
                }
            }

            return new T();
        }

        /// <summary>
        /// Check if a save key exists in the data store.
        /// </summary>
        public bool HasKey(string key)
        {
            return !string.IsNullOrEmpty(key) && _dataStore.ContainsKey(key);
        }

        /// <summary>
        /// Delete a specific key from the data store.
        /// </summary>
        public void DeleteKey(string key)
        {
            if (_dataStore.Remove(key))
            {
                _isDirty = true;
            }
        }

        /// <summary>
        /// Delete all saved data. Removes file and clears in-memory store.
        /// </summary>
        public void DeleteAll()
        {
            _dataStore.Clear();
            _isDirty = false;

            if (File.Exists(SaveFilePath))
            {
                try
                {
                    File.Delete(SaveFilePath);
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[SaveManager] Failed to delete save file: {ex.Message}");
                }
            }

            PlayerPrefs.DeleteAll();
        }

        /// <summary>
        /// Returns true if no save file exists (first launch).
        /// </summary>
        public bool IsFirstPlay()
        {
            return !File.Exists(SaveFilePath);
        }

        #endregion

        #region Settings (PlayerPrefs)

        /// <summary>
        /// Save a lightweight setting to PlayerPrefs.
        /// Use for sound on/off, language, notification preferences.
        /// </summary>
        public void SaveSetting(string key, int value)
        {
            PlayerPrefs.SetInt(key, value);
            PlayerPrefs.Save();
        }

        /// <summary>
        /// Load a lightweight setting from PlayerPrefs.
        /// </summary>
        public int LoadSetting(string key, int defaultValue = 0)
        {
            return PlayerPrefs.GetInt(key, defaultValue);
        }

        #endregion

        #region Private Methods

        private void SaveToDisk()
        {
            try
            {
                string wrapperJson = JsonUtility.ToJson(new SaveWrapper(_dataStore));

                if (_useEncryption)
                {
                    wrapperJson = Encrypt(wrapperJson);
                }

                File.WriteAllText(SaveFilePath, wrapperJson, Encoding.UTF8);
                _isDirty = false;
            }
            catch (Exception ex)
            {
                Debug.LogError($"[SaveManager] Failed to save to disk: {ex.Message}");
            }
        }

        private void LoadAllFromDisk()
        {
            try
            {
                string fileContent = File.ReadAllText(SaveFilePath, Encoding.UTF8);

                if (_useEncryption)
                {
                    fileContent = Decrypt(fileContent);
                }

                var wrapper = JsonUtility.FromJson<SaveWrapper>(fileContent);
                _dataStore = wrapper?.ToDictionary() ?? new Dictionary<string, string>();
            }
            catch (Exception ex)
            {
                Debug.LogError($"[SaveManager] Failed to load from disk: {ex.Message}. Creating fresh data.");
                _dataStore = new Dictionary<string, string>();
            }
        }

        private IEnumerator AutoSaveRoutine()
        {
            var wait = new WaitForSeconds(GameConstants.Battle.AutoSaveInterval);

            while (true)
            {
                yield return wait;

                if (_isDirty)
                {
                    Save();
                }
            }
        }

        #endregion

        #region Encryption

        private string Encrypt(string plainText)
        {
            try
            {
                byte[] keyBytes = Encoding.UTF8.GetBytes(ENCRYPTION_KEY);
                byte[] ivBytes = new byte[16];
                Array.Copy(keyBytes, ivBytes, Mathf.Min(keyBytes.Length, 16));

                using var aes = Aes.Create();
                aes.KeySize = ENCRYPTION_KEY_SIZE;
                aes.Key = keyBytes.Length >= 16 ? keyBytes[..16] : keyBytes;
                aes.IV = ivBytes;
                aes.Mode = CipherMode.CBC;
                aes.Padding = PaddingMode.PKCS7;

                using var encryptor = aes.CreateEncryptor();
                byte[] plainBytes = Encoding.UTF8.GetBytes(plainText);
                byte[] encrypted = encryptor.TransformFinalBlock(plainBytes, 0, plainBytes.Length);

                return Convert.ToBase64String(encrypted);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[SaveManager] Encryption failed: {ex.Message}");
                return plainText;
            }
        }

        private string Decrypt(string cipherText)
        {
            try
            {
                byte[] keyBytes = Encoding.UTF8.GetBytes(ENCRYPTION_KEY);
                byte[] ivBytes = new byte[16];
                Array.Copy(keyBytes, ivBytes, Mathf.Min(keyBytes.Length, 16));

                using var aes = Aes.Create();
                aes.KeySize = ENCRYPTION_KEY_SIZE;
                aes.Key = keyBytes.Length >= 16 ? keyBytes[..16] : keyBytes;
                aes.IV = ivBytes;
                aes.Mode = CipherMode.CBC;
                aes.Padding = PaddingMode.PKCS7;

                using var decryptor = aes.CreateDecryptor();
                byte[] cipherBytes = Convert.FromBase64String(cipherText);
                byte[] decrypted = decryptor.TransformFinalBlock(cipherBytes, 0, cipherBytes.Length);

                return Encoding.UTF8.GetString(decrypted);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[SaveManager] Decryption failed: {ex.Message}. Returning raw content.");
                return cipherText;
            }
        }

        #endregion

        #region Unity Lifecycle

        protected override void OnDestroy()
        {
            if (_autoSaveCoroutine != null)
            {
                StopCoroutine(_autoSaveCoroutine);
            }

            if (_isDirty)
            {
                SaveToDisk();
            }

            base.OnDestroy();
        }

        #endregion

        #region Save Wrapper

        /// <summary>
        /// Serializable wrapper for Dictionary since JsonUtility cannot serialize dictionaries directly.
        /// </summary>
        [Serializable]
        private class SaveWrapper
        {
            public List<string> keys = new();
            public List<string> values = new();

            public SaveWrapper() { }

            public SaveWrapper(Dictionary<string, string> dict)
            {
                foreach (var kvp in dict)
                {
                    keys.Add(kvp.Key);
                    values.Add(kvp.Value);
                }
            }

            public Dictionary<string, string> ToDictionary()
            {
                var dict = new Dictionary<string, string>();
                int count = Mathf.Min(keys.Count, values.Count);

                for (int i = 0; i < count; i++)
                {
                    dict[keys[i]] = values[i];
                }

                return dict;
            }
        }

        #endregion
    }
}
