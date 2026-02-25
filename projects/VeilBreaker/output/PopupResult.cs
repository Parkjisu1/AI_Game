using UnityEngine;
using UnityEngine.UI;
using TMPro;
using VeilBreaker.Core;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Stage result popup. Displays clear result (stars, rewards) or fail result
    /// with retry/lobby/next-stage navigation buttons.
    /// Clear and fail states use separate child panels for clean layout management.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// Phase: 3
    /// System: UI
    /// </remarks>
    public class PopupResult : PopupBase
    {
        #region Fields

        // Separate panels for clear and fail state
        [SerializeField] private GameObject _clearPanel;
        [SerializeField] private GameObject _failPanel;

        // Clear panel elements
        [SerializeField] private Image[]            _starImages;        // 3 star slots
        [SerializeField] private Sprite             _starFilledSprite;
        [SerializeField] private Sprite             _starEmptySprite;
        [SerializeField] private TextMeshProUGUI    _goldRewardText;
        [SerializeField] private TextMeshProUGUI    _expRewardText;
        [SerializeField] private Button             _nextStageButton;

        // Shared buttons
        [SerializeField] private Button _retryButton;
        [SerializeField] private Button _lobbyButton;

        #endregion

        #region PopupBase Overrides

        /// <summary>
        /// Opens the result popup. Expects data as StageResult for clear, or null for fail.
        /// </summary>
        public override void Open(object data = null)
        {
            if (data is StageResult result)
                ShowClearResult(result);
            else
                ShowFailResult();

            _nextStageButton?.onClick.RemoveAllListeners();
            _nextStageButton?.onClick.AddListener(OnNextStageButton);

            _retryButton?.onClick.RemoveAllListeners();
            _retryButton?.onClick.AddListener(OnRetryButton);

            _lobbyButton?.onClick.RemoveAllListeners();
            _lobbyButton?.onClick.AddListener(OnLobbyButton);
        }

        /// <summary>
        /// Cleans up on close.
        /// </summary>
        public override void Close()
        {
            _nextStageButton?.onClick.RemoveAllListeners();
            _retryButton?.onClick.RemoveAllListeners();
            _lobbyButton?.onClick.RemoveAllListeners();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Displays the stage clear result with star rating and reward summary.
        /// </summary>
        /// <param name="result">Stage clear result data.</param>
        public void ShowClearResult(StageResult result)
        {
            _clearPanel?.SetActive(true);
            _failPanel?.SetActive(false);

            SetStars(result?.stars ?? 0);

            if (_goldRewardText != null)
                _goldRewardText.text = result != null ? FormatNumber(result.goldReward) : "0";

            if (_expRewardText != null)
                _expRewardText.text = result != null ? FormatNumber(result.expReward) : "0";

            // Hide retry on clear; show next stage
            _retryButton?.gameObject.SetActive(false);
            _nextStageButton?.gameObject.SetActive(true);
        }

        /// <summary>
        /// Displays the stage fail state with retry and lobby buttons.
        /// </summary>
        public void ShowFailResult()
        {
            _clearPanel?.SetActive(false);
            _failPanel?.SetActive(true);

            _retryButton?.gameObject.SetActive(true);
            _nextStageButton?.gameObject.SetActive(false);
        }

        #endregion

        #region Private Methods

        private void SetStars(int count)
        {
            if (_starImages == null) return;

            for (int i = 0; i < _starImages.Length; i++)
            {
                if (_starImages[i] == null) continue;

                bool filled = i < count;
                _starImages[i].sprite = filled ? _starFilledSprite : _starEmptySprite;
                _starImages[i].enabled = true;
            }
        }

        private void OnNextStageButton()
        {
            CloseThis();
            if (StageManager.HasInstance)
                StageManager.Instance.StartNextStage();
        }

        private void OnRetryButton()
        {
            CloseThis();
            if (StageManager.HasInstance)
                StageManager.Instance.RetryStage();
        }

        private void OnLobbyButton()
        {
            CloseThis();
            if (UISystem.HasInstance)
                UISystem.Instance.OpenPage<PageLobby>();
        }

        private static string FormatNumber(long n)
        {
            if (n >= 1_000_000) return $"{n / 1_000_000f:0.#}M";
            if (n >= 1_000)     return $"{n / 1_000f:0.#}K";
            return n.ToString();
        }

        #endregion
    }

    /// <summary>
    /// Stage clear result data passed via OpenPopup.
    /// Full definition lives in StageManager / BattleManager.
    /// </summary>
    [System.Serializable]
    public class StageResult
    {
        public string stageId;
        public int    stars;        // 0-3
        public long   goldReward;
        public long   expReward;
        public float  clearTimeSeconds;
    }
}
