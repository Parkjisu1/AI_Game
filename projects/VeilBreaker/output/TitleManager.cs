using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using VeilBreaker.Core;
using VeilBreaker.Data;

namespace VeilBreaker.Scene
{
    /// <summary>
    /// Orchestrates the title scene initialization sequence.
    /// Initializes all Core and Domain managers in order across multiple frames
    /// so the loading bar animates smoothly. Transitions to Main scene when complete.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Generic
    /// Role: Manager
    /// System: Scene
    /// Phase: 3
    /// </remarks>
    public class TitleManager : MonoBehaviour
    {
        #region Fields

        [SerializeField] private Slider _loadingBar;
        [SerializeField] private TextMeshProUGUI _loadingText;
        [SerializeField] private float _minLoadingDuration = 0.5f;

        #endregion

        #region Unity Lifecycle

        private void Start()
        {
            StartCoroutine(InitializeGame());
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Coroutine that initializes all managers in priority order.
        /// Progress milestones: EventManager(10%) → SaveManager(30%) → DataManager(70%) → Others(90%) → Done(100%)
        /// </summary>
        public IEnumerator InitializeGame()
        {
            UpdateLoadingProgress(0f, "Starting...");
            yield return null;

            // Step 2: EventManager + ObjectPool (these are singletons already awoken,
            //         no explicit Init needed - progress marker only)
            UpdateLoadingProgress(0.1f, "Loading core systems...");
            yield return null;

            // Step 3: SaveManager
            UpdateLoadingProgress(0.2f, "Loading save data...");
            yield return null;

            if (SaveManager.HasInstance)
            {
                SaveManager.Instance.Init();
            }
            else
            {
                Debug.LogError("[TitleManager] SaveManager not found in scene.");
            }

            UpdateLoadingProgress(0.3f, "Save data loaded.");
            yield return null;

            // Step 4: DataManager (chart loading - may be slow)
            UpdateLoadingProgress(0.4f, "Loading game data...");
            yield return null;

            if (DataManager.HasInstance)
            {
                DataManager.Instance.Init();
            }
            else
            {
                Debug.LogError("[TitleManager] DataManager not found in scene.");
            }

            UpdateLoadingProgress(0.7f, "Game data loaded.");
            yield return null;

            // Step 5: Domain managers - no explicit Init needed (event-driven, subscribe on Awake)
            UpdateLoadingProgress(0.8f, "Preparing managers...");
            yield return null;

            UpdateLoadingProgress(0.9f, "Almost ready...");
            yield return null;

            // Ensure minimum loading duration for smooth UX
            yield return new WaitForSeconds(_minLoadingDuration);

            // Step 6: Complete - transition to Main scene
            UpdateLoadingProgress(1.0f, "Done!");
            yield return null;

            Util.LoadScene(GameConstants.Scenes.Main);
        }

        /// <summary>
        /// Updates loading bar and text to reflect current progress.
        /// </summary>
        /// <param name="progress">Progress value 0.0 to 1.0.</param>
        /// <param name="message">Optional status message for loading text.</param>
        public void UpdateLoadingProgress(float progress, string message = null)
        {
            float clamped = Mathf.Clamp01(progress);

            if (_loadingBar != null)
            {
                _loadingBar.value = clamped;
            }

            if (_loadingText != null && !string.IsNullOrEmpty(message))
            {
                _loadingText.text = message;
            }
        }

        #endregion
    }
}
