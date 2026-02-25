using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using MagicSort.Core;

namespace MagicSort.Game
{
    /// <summary>
    /// Controls the Title screen: loading bar simulation and transition to Home scene.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Puzzle
    /// Role: Controller
    /// Phase: 1
    /// </remarks>
    public class TitleController : MonoBehaviour
    {
        #region Fields

        [Header("UI References")]
        [SerializeField] private Slider loadingBar;
        [SerializeField] private Text versionText;

        [Header("Settings")]
        [SerializeField] private float loadDuration = 2f;
        [SerializeField] private string versionString = "v1.0.0";

        private bool _isLoading;

        #endregion

        #region Unity Lifecycle

        private void Start()
        {
            if (versionText != null)
            {
                versionText.text = versionString;
            }

            if (loadingBar != null)
            {
                loadingBar.value = 0f;
            }

            StartCoroutine(SimulateLoadingAndTransition());
        }

        #endregion

        #region Private Methods

        private IEnumerator SimulateLoadingAndTransition()
        {
            if (_isLoading)
            {
                yield break;
            }

            _isLoading = true;
            float elapsed = 0f;

            while (elapsed < loadDuration)
            {
                elapsed += Time.deltaTime;
                float progress = Mathf.Clamp01(elapsed / loadDuration);

                if (loadingBar != null)
                {
                    loadingBar.value = progress;
                }

                yield return null;
            }

            if (loadingBar != null)
            {
                loadingBar.value = 1f;
            }

            // Brief pause at 100% before transitioning
            yield return new WaitForSeconds(0.3f);

            // Transition to Home scene via SceneLoader if available, else fallback
            if (SceneLoader.HasInstance)
            {
                SceneLoader.Instance.LoadScene(SceneName.Home);
            }
            else
            {
                UnityEngine.SceneManagement.SceneManager.LoadScene("Home");
            }
        }

        #endregion
    }
}
