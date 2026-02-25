using UnityEngine;
using UnityEngine.UI;
using DropTheCat.Core;
using DropTheCat.Domain;

namespace DropTheCat.Game
{
    /// <summary>
    /// Popup shown when a level is failed. Offers retry, watch ad for booster, or quit options.
    /// </summary>
    /// <remarks>
    /// Layer: Game | Genre: Puzzle | Role: Handler | Phase: 3
    /// </remarks>
    public class LevelFailPopup : MonoBehaviour
    {
        #region Fields

        [SerializeField] private Text failReasonText;
        [SerializeField] private Button retryBtn;
        [SerializeField] private Button watchAdBtn;
        [SerializeField] private Button quitBtn;
        [SerializeField] private GameObject popupRoot;

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            if (retryBtn != null)
            {
                retryBtn.onClick.AddListener(OnRetryClicked);
            }

            if (watchAdBtn != null)
            {
                watchAdBtn.onClick.AddListener(OnWatchAdClicked);
            }

            if (quitBtn != null)
            {
                quitBtn.onClick.AddListener(OnQuitClicked);
            }
        }

        private void OnDisable()
        {
            if (retryBtn != null)
            {
                retryBtn.onClick.RemoveListener(OnRetryClicked);
            }

            if (watchAdBtn != null)
            {
                watchAdBtn.onClick.RemoveListener(OnWatchAdClicked);
            }

            if (quitBtn != null)
            {
                quitBtn.onClick.RemoveListener(OnQuitClicked);
            }
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Show the fail popup with the given fail reason message.
        /// </summary>
        public void Show(string failReason)
        {
            if (failReasonText != null)
            {
                failReasonText.text = GetFailReasonMessage(failReason);
            }

            if (popupRoot != null)
            {
                popupRoot.SetActive(true);
            }
            else
            {
                gameObject.SetActive(true);
            }
        }

        /// <summary>
        /// Hide the fail popup.
        /// </summary>
        public void Hide()
        {
            if (popupRoot != null)
            {
                popupRoot.SetActive(false);
            }
            else
            {
                gameObject.SetActive(false);
            }
        }

        /// <summary>
        /// Retry the current level.
        /// </summary>
        public void OnRetryClicked()
        {
            Hide();

            if (LevelManager.HasInstance)
            {
                LevelManager.Instance.RetryLevel();
            }
        }

        /// <summary>
        /// Watch a rewarded ad to receive a Hint booster, then continue the level.
        /// Ad display is handled externally; this triggers the reward callback.
        /// </summary>
        public void OnWatchAdClicked()
        {
            // Reward ad display would be handled by AdMobManager or similar SDK wrapper.
            // On successful reward callback, grant a Hint booster.
            OnRewardedAdCompleted();
        }

        /// <summary>
        /// Quit to the main menu.
        /// </summary>
        public void OnQuitClicked()
        {
            Hide();

            if (GameManager.Instance != null)
            {
                GameManager.Instance.GoToMain();
            }
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Called when a rewarded ad is successfully completed.
        /// Grants a Hint booster and hides the popup to continue playing.
        /// </summary>
        private void OnRewardedAdCompleted()
        {
            if (BoosterManager.HasInstance)
            {
                BoosterManager.Instance.AddBooster(BoosterType.Hint, 1);
            }

            Hide();
        }

        private string GetFailReasonMessage(string failReason)
        {
            if (string.IsNullOrEmpty(failReason)) return "Level Failed!";

            switch (failReason)
            {
                case nameof(FailReason.TrapHole):
                    return "A cat fell into a trap!";
                case nameof(FailReason.OutOfMoves):
                    return "Out of moves!";
                case nameof(FailReason.PlayerQuit):
                    return "You quit the level.";
                default:
                    return "Level Failed!";
            }
        }

        #endregion
    }
}
