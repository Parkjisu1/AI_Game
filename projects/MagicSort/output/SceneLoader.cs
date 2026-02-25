using System;
using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace MagicSort.Core
{
    /// <summary>
    /// Async scene loading wrapper with progress callbacks.
    /// Provides a clean API for scene transitions with loading progress feedback.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Service
    /// Phase: 0
    /// </remarks>
    public class SceneLoader : Singleton<SceneLoader>
    {
        #region Fields

        private bool _isLoading;
        private Coroutine _loadCoroutine;

        #endregion

        #region Properties

        /// <summary>Whether a scene is currently being loaded.</summary>
        public bool IsLoading => _isLoading;

        #endregion

        #region Events

        /// <summary>
        /// Invoked during loading with normalized progress (0-1).
        /// </summary>
        public event Action<float> OnProgress;

        /// <summary>
        /// Invoked when the scene load completes.
        /// </summary>
        public event Action<SceneName> OnSceneLoaded;

        #endregion

        #region Public Methods

        /// <summary>
        /// Loads a scene asynchronously by SceneName enum.
        /// </summary>
        /// <param name="sceneName">The scene to load.</param>
        /// <param name="onProgress">Optional per-call progress callback (0-1).</param>
        /// <param name="onComplete">Optional per-call completion callback.</param>
        public void LoadScene(SceneName sceneName, Action<float> onProgress = null, Action onComplete = null)
        {
            LoadScene(sceneName.ToString(), onProgress, onComplete);
        }

        /// <summary>
        /// Loads a scene asynchronously by string name.
        /// </summary>
        /// <param name="sceneName">The scene name matching Unity Build Settings.</param>
        /// <param name="onProgress">Optional per-call progress callback (0-1).</param>
        /// <param name="onComplete">Optional per-call completion callback.</param>
        public void LoadScene(string sceneName, Action<float> onProgress = null, Action onComplete = null)
        {
            if (_isLoading)
            {
                Debug.LogWarning($"[SceneLoader] Already loading a scene. Ignoring request for '{sceneName}'.");
                return;
            }

            if (string.IsNullOrEmpty(sceneName))
            {
                Debug.LogError("[SceneLoader] Scene name cannot be null or empty.");
                return;
            }

            _loadCoroutine = StartCoroutine(LoadSceneCoroutine(sceneName, onProgress, onComplete));
        }

        /// <summary>
        /// Loads a scene additively (without unloading current scene).
        /// </summary>
        /// <param name="sceneName">The scene to load.</param>
        /// <param name="onComplete">Optional completion callback.</param>
        public void LoadSceneAdditive(string sceneName, Action onComplete = null)
        {
            if (string.IsNullOrEmpty(sceneName))
            {
                Debug.LogError("[SceneLoader] Scene name cannot be null or empty.");
                return;
            }

            StartCoroutine(LoadSceneAdditiveCoroutine(sceneName, onComplete));
        }

        /// <summary>
        /// Unloads an additively loaded scene.
        /// </summary>
        /// <param name="sceneName">The scene to unload.</param>
        /// <param name="onComplete">Optional completion callback.</param>
        public void UnloadScene(string sceneName, Action onComplete = null)
        {
            if (string.IsNullOrEmpty(sceneName))
            {
                Debug.LogError("[SceneLoader] Scene name cannot be null or empty.");
                return;
            }

            StartCoroutine(UnloadSceneCoroutine(sceneName, onComplete));
        }

        /// <summary>
        /// Gets the name of the currently active scene.
        /// </summary>
        /// <returns>The active scene name.</returns>
        public string GetActiveSceneName()
        {
            return SceneManager.GetActiveScene().name;
        }

        #endregion

        #region Private Methods

        private IEnumerator LoadSceneCoroutine(string sceneName, Action<float> onProgress, Action onComplete)
        {
            _isLoading = true;

            OnProgress?.Invoke(0f);
            onProgress?.Invoke(0f);

            AsyncOperation asyncOp = SceneManager.LoadSceneAsync(sceneName);
            if (asyncOp == null)
            {
                Debug.LogError($"[SceneLoader] Failed to start loading scene '{sceneName}'.");
                _isLoading = false;
                yield break;
            }

            asyncOp.allowSceneActivation = false;

            // Progress phase: 0.0 to 0.9 is loading, 0.9 to 1.0 is activation
            while (asyncOp.progress < 0.9f)
            {
                float progress = Mathf.Clamp01(asyncOp.progress / 0.9f);
                OnProgress?.Invoke(progress);
                onProgress?.Invoke(progress);
                yield return null;
            }

            // Loading done, activate scene
            OnProgress?.Invoke(1f);
            onProgress?.Invoke(1f);

            asyncOp.allowSceneActivation = true;

            // Wait until scene is fully loaded
            while (!asyncOp.isDone)
            {
                yield return null;
            }

            _isLoading = false;
            _loadCoroutine = null;

            // Try to parse SceneName enum for event
            if (Enum.TryParse(sceneName, out SceneName parsedName))
            {
                OnSceneLoaded?.Invoke(parsedName);
            }

            onComplete?.Invoke();
        }

        private IEnumerator LoadSceneAdditiveCoroutine(string sceneName, Action onComplete)
        {
            AsyncOperation asyncOp = SceneManager.LoadSceneAsync(sceneName, LoadSceneMode.Additive);
            if (asyncOp == null)
            {
                Debug.LogError($"[SceneLoader] Failed to start additive loading of '{sceneName}'.");
                yield break;
            }

            while (!asyncOp.isDone)
            {
                yield return null;
            }

            onComplete?.Invoke();
        }

        private IEnumerator UnloadSceneCoroutine(string sceneName, Action onComplete)
        {
            AsyncOperation asyncOp = SceneManager.UnloadSceneAsync(sceneName);
            if (asyncOp == null)
            {
                Debug.LogError($"[SceneLoader] Failed to start unloading scene '{sceneName}'.");
                yield break;
            }

            while (!asyncOp.isDone)
            {
                yield return null;
            }

            onComplete?.Invoke();
        }

        #endregion
    }
}
