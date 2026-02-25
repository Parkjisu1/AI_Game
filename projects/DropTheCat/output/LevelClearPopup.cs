using UnityEngine;
using UnityEngine.UI;
using DropTheCat.Core;
using DropTheCat.Domain;

#if DOTWEEN
using DG.Tweening;
#endif

namespace DropTheCat.Game
{
    /// <summary>
    /// Level clear result popup with star animations, score/coin counting, and navigation buttons.
    /// </summary>
    /// <remarks>
    /// Layer: Game | Genre: Puzzle | Role: Handler | Phase: 3
    /// DOTween animations use #if DOTWEEN conditional compilation.
    /// GameManager.GoToMain() is expected from GameManager.cs (Phase 3).
    /// </remarks>
    public class LevelClearPopup : MonoBehaviour
    {
        #region Constants

        private const float STAR_ANIM_DELAY = 0.3f;
        private const float STAR_ANIM_DURATION = 0.4f;
        private const float COUNT_ANIM_DURATION = 1.0f;
        private const float POPUP_SCALE_DURATION = 0.3f;

        #endregion

        #region Fields

        [Header("Stars")]
        [SerializeField] private Image[] starImages;
        [SerializeField] private Sprite starFilledSprite;
        [SerializeField] private Sprite starEmptySprite;

        [Header("Text")]
        [SerializeField] private Text scoreText;
        [SerializeField] private Text coinText;

        [Header("Buttons")]
        [SerializeField] private Button nextBtn;
        [SerializeField] private Button retryBtn;
        [SerializeField] private Button mainMenuBtn;

        [Header("Root")]
        [SerializeField] private GameObject popupRoot;
        [SerializeField] private CanvasGroup dimBackground;
        [SerializeField] private Transform popupPanel;

        private int _displayedStars;
        private int _earnedCoinReward;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            if (nextBtn != null)
            {
                nextBtn.onClick.AddListener(OnNextLevelClicked);
            }

            if (retryBtn != null)
            {
                retryBtn.onClick.AddListener(OnRetryClicked);
            }

            if (mainMenuBtn != null)
            {
                mainMenuBtn.onClick.AddListener(OnMainMenuClicked);
            }
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Shows the popup with level clear results and plays animations.
        /// </summary>
        public void Show(int stars, int score, int coinReward)
        {
            _displayedStars = Mathf.Clamp(stars, 0, 3);
            _earnedCoinReward = coinReward;

            if (popupRoot != null)
            {
                popupRoot.SetActive(true);
            }
            else
            {
                gameObject.SetActive(true);
            }

            ResetDisplay();
            PlayShowAnimation(score, coinReward);
        }

        /// <summary>
        /// Hides the popup.
        /// </summary>
        public void Hide()
        {
#if DOTWEEN
            if (popupPanel != null)
            {
                popupPanel.DOScale(Vector3.zero, POPUP_SCALE_DURATION)
                    .SetEase(Ease.InBack)
                    .OnComplete(DeactivatePopup);
                return;
            }
#endif
            DeactivatePopup();
        }

        /// <summary>
        /// Advances to the next level and hides the popup.
        /// </summary>
        public void OnNextLevelClicked()
        {
            Hide();

            if (LevelManager.HasInstance)
            {
                LevelManager.Instance.NextLevel();
            }
        }

        /// <summary>
        /// Retries the current level and hides the popup.
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
        /// Returns to the main menu and hides the popup.
        /// </summary>
        public void OnMainMenuClicked()
        {
            Hide();

            // GameManager.GoToMain() defined in GameManager.cs (Phase 3)
            if (GameManager.HasInstance)
            {
                GameManager.Instance.GoToMain();
            }
        }

        #endregion

        #region Private Methods

        private void ResetDisplay()
        {
            // Reset stars to empty
            if (starImages != null)
            {
                for (int i = 0; i < starImages.Length; i++)
                {
                    if (starImages[i] == null) continue;

                    starImages[i].sprite = starEmptySprite;
                    starImages[i].transform.localScale = Vector3.zero;
                }
            }

            if (scoreText != null)
            {
                scoreText.text = "0";
            }

            if (coinText != null)
            {
                coinText.text = "0";
            }

            // Reset popup panel scale
            if (popupPanel != null)
            {
                popupPanel.localScale = Vector3.zero;
            }

            // Reset dim background
            if (dimBackground != null)
            {
                dimBackground.alpha = 0f;
            }
        }

        private void PlayShowAnimation(int score, int coinReward)
        {
#if DOTWEEN
            Sequence sequence = DOTween.Sequence();

            // Dim background fade in
            if (dimBackground != null)
            {
                sequence.Append(dimBackground.DOFade(1f, POPUP_SCALE_DURATION));
            }

            // Popup scale in
            if (popupPanel != null)
            {
                sequence.Append(popupPanel.DOScale(Vector3.one, POPUP_SCALE_DURATION)
                    .SetEase(Ease.OutBack));
            }

            // Star animations
            for (int i = 0; i < _displayedStars; i++)
            {
                int starIndex = i;
                sequence.AppendInterval(STAR_ANIM_DELAY);
                sequence.AppendCallback(() => AnimateStar(starIndex));
            }

            // Score counting
            sequence.AppendInterval(0.2f);
            int tempScore = 0;
            sequence.Append(DOTween.To(() => tempScore, x =>
            {
                tempScore = x;
                if (scoreText != null)
                {
                    scoreText.text = tempScore.ToString("N0");
                }
            }, score, COUNT_ANIM_DURATION).SetEase(Ease.OutQuad));

            // Coin counting
            int tempCoin = 0;
            sequence.Append(DOTween.To(() => tempCoin, x =>
            {
                tempCoin = x;
                if (coinText != null)
                {
                    coinText.text = tempCoin.ToString("N0");
                }
            }, coinReward, COUNT_ANIM_DURATION).SetEase(Ease.OutQuad));

            // Grant coins after animation
            sequence.AppendCallback(() => GrantCoinReward(coinReward));
#else
            // No DOTween: set values directly
            if (dimBackground != null)
            {
                dimBackground.alpha = 1f;
            }

            if (popupPanel != null)
            {
                popupPanel.localScale = Vector3.one;
            }

            SetStarsImmediate();

            if (scoreText != null)
            {
                scoreText.text = score.ToString("N0");
            }

            if (coinText != null)
            {
                coinText.text = coinReward.ToString("N0");
            }

            GrantCoinReward(coinReward);
#endif
        }

        private void AnimateStar(int starIndex)
        {
            if (starImages == null || starIndex < 0 || starIndex >= starImages.Length) return;
            if (starImages[starIndex] == null) return;

            starImages[starIndex].sprite = starFilledSprite;

#if DOTWEEN
            starImages[starIndex].transform.localScale = Vector3.zero;
            starImages[starIndex].transform.DOScale(Vector3.one, STAR_ANIM_DURATION)
                .SetEase(Ease.OutBack);
            starImages[starIndex].transform.DORotate(new Vector3(0, 0, 360f), STAR_ANIM_DURATION, RotateMode.FastBeyond360)
                .SetEase(Ease.OutQuad);
#else
            starImages[starIndex].transform.localScale = Vector3.one;
#endif

            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlaySFX("star_earn");
            }
        }

        private void SetStarsImmediate()
        {
            if (starImages == null) return;

            for (int i = 0; i < starImages.Length; i++)
            {
                if (starImages[i] == null) continue;

                starImages[i].sprite = i < _displayedStars ? starFilledSprite : starEmptySprite;
                starImages[i].transform.localScale = Vector3.one;
            }
        }

        private void GrantCoinReward(int coinReward)
        {
            if (coinReward <= 0) return;

            if (CurrencyManager.HasInstance)
            {
                CurrencyManager.Instance.AddCoins(coinReward);
            }
        }

        private void DeactivatePopup()
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

        #endregion
    }
}
