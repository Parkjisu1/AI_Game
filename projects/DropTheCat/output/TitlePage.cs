using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using DropTheCat.Core;

namespace DropTheCat.Game
{
    /// <summary>
    /// Title screen with logo splash and loading progress bar.
    /// Transitions to Main scene after loading completes with minimum splash duration.
    /// </summary>
    /// <remarks>
    /// Layer: Game | Genre: Puzzle | Role: Handler | Phase: 3
    /// </remarks>
    public class TitlePage : MonoBehaviour
    {
        #region Constants

        private const float MIN_SPLASH_DURATION = 2.0f;

        #endregion

        #region Fields

        [SerializeField] private Image logo;
        [SerializeField] private Slider loadingBar;
        [SerializeField] private Text versionText;

        private bool _isLoading;

        #endregion

        #region Unity Lifecycle

        private void Start()
        {
            if (versionText != null)
            {
                versionText.text = $"v{Application.version}";
            }

            if (loadingBar != null)
            {
                loadingBar.value = 0f;
            }

            ShowLoading();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Start the loading coroutine with splash screen.
        /// </summary>
        public void ShowLoading()
        {
            if (_isLoading) return;

            _isLoading = true;
            StartCoroutine(LoadingRoutine());
        }

        /// <summary>
        /// Update the loading progress bar value (0 to 1).
        /// </summary>
        public void UpdateProgress(float progress)
        {
            if (loadingBar != null)
            {
                loadingBar.value = Mathf.Clamp01(progress);
            }
        }

        #endregion

        #region Private Methods

        private IEnumerator LoadingRoutine()
        {
            float elapsed = 0f;
            float fakeProgress = 0f;

            // Simulate loading progress during minimum splash duration
            while (elapsed < MIN_SPLASH_DURATION)
            {
                elapsed += Time.deltaTime;
                fakeProgress = Mathf.Clamp01(elapsed / MIN_SPLASH_DURATION);
                UpdateProgress(fakeProgress * 0.9f);
                yield return null;
            }

            UpdateProgress(1f);

            // Brief pause at 100%
            yield return new WaitForSeconds(0.2f);

            // Transition to Main via GameManager
            if (GameManager.Instance != null)
            {
                GameManager.Instance.GoToMain();
            }

            _isLoading = false;
        }

        #endregion
    }
}
