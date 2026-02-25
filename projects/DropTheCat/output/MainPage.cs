using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using DropTheCat.Core;
using DropTheCat.Domain;

namespace DropTheCat.Game
{
    /// <summary>
    /// Main menu page with scrollable level map, coin display, and navigation buttons.
    /// Subscribes to OnCoinChanged and OnLevelProgressUpdated for live UI updates.
    /// </summary>
    /// <remarks>
    /// Layer: Game | Genre: Puzzle | Role: Handler | Phase: 3
    /// </remarks>
    public class MainPage : MonoBehaviour
    {
        #region Fields

        [Header("Level Map")]
        [SerializeField] private ScrollRect levelScrollRect;
        [SerializeField] private RectTransform levelButtonContainer;
        [SerializeField] private Button levelButtonPrefab;
        [SerializeField] private int totalLevels = 50;

        [Header("Coin Display")]
        [SerializeField] private Text coinText;

        [Header("Navigation")]
        [SerializeField] private Button settingsButton;
        [SerializeField] private Button shopButton;

        [Header("Level Button Visuals")]
        [SerializeField] private UnityEngine.Color unlockedColor = UnityEngine.Color.white;
        [SerializeField] private UnityEngine.Color lockedColor = UnityEngine.Color.gray;
        [SerializeField] private Sprite starFilledSprite;
        [SerializeField] private Sprite starEmptySprite;

        private readonly List<Button> _levelButtons = new List<Button>();

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Subscribe<OnCoinChanged>(HandleCoinChanged);
                EventManager.Instance.Subscribe<OnLevelProgressUpdated>(HandleProgressUpdated);
            }

            if (settingsButton != null)
            {
                settingsButton.onClick.AddListener(OnSettingsButtonClicked);
            }

            if (shopButton != null)
            {
                shopButton.onClick.AddListener(OnShopButtonClicked);
            }

            RefreshCoinDisplay();
            RefreshLevelMap();
        }

        private void OnDisable()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Unsubscribe<OnCoinChanged>(HandleCoinChanged);
                EventManager.Instance.Unsubscribe<OnLevelProgressUpdated>(HandleProgressUpdated);
            }

            if (settingsButton != null)
            {
                settingsButton.onClick.RemoveListener(OnSettingsButtonClicked);
            }

            if (shopButton != null)
            {
                shopButton.onClick.RemoveListener(OnShopButtonClicked);
            }
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Rebuild the level map: create/update level buttons with unlock state and star display.
        /// </summary>
        public void RefreshLevelMap()
        {
            EnsureLevelButtons();

            for (int i = 0; i < _levelButtons.Count; i++)
            {
                int levelNumber = i + 1;
                Button btn = _levelButtons[i];
                if (btn == null) continue;

                bool unlocked = LevelManager.HasInstance && LevelManager.Instance.IsLevelUnlocked(levelNumber);
                int stars = LevelManager.HasInstance ? LevelManager.Instance.GetStars(levelNumber) : 0;

                btn.interactable = unlocked;

                // Update button color
                Image btnImage = btn.GetComponent<Image>();
                if (btnImage != null)
                {
                    btnImage.color = unlocked ? unlockedColor : lockedColor;
                }

                // Update level number text
                Text btnText = btn.GetComponentInChildren<Text>();
                if (btnText != null)
                {
                    btnText.text = unlocked ? levelNumber.ToString() : "";
                }

                // Update star images
                Image[] starImages = btn.GetComponentsInChildren<Image>();
                UpdateStarDisplay(starImages, stars);
            }

            ScrollToCurrentLevel();
        }

        /// <summary>
        /// Update the coin display text with current balance.
        /// </summary>
        public void RefreshCoinDisplay()
        {
            if (coinText == null) return;

            int balance = CurrencyManager.HasInstance ? CurrencyManager.Instance.GetBalance() : 0;
            coinText.text = balance.ToString("N0");
        }

        /// <summary>
        /// Handle level button click: start the selected level via GameManager.
        /// </summary>
        public void OnLevelButtonClicked(int levelNumber)
        {
            if (GameManager.Instance == null) return;

            if (LevelManager.HasInstance && !LevelManager.Instance.IsLevelUnlocked(levelNumber))
            {
                return;
            }

            GameManager.Instance.StartLevel(levelNumber);
        }

        /// <summary>
        /// Open the settings popup.
        /// </summary>
        public void OnSettingsButtonClicked()
        {
            // Settings popup is handled externally; this is the click entry point.
            Debug.Log("[MainPage] Settings button clicked.");
        }

        /// <summary>
        /// Open the shop popup.
        /// </summary>
        public void OnShopButtonClicked()
        {
            // Shop popup is handled externally; this is the click entry point.
            Debug.Log("[MainPage] Shop button clicked.");
        }

        #endregion

        #region Private Methods

        private void EnsureLevelButtons()
        {
            if (levelButtonPrefab == null || levelButtonContainer == null) return;

            // Create buttons if not yet populated
            while (_levelButtons.Count < totalLevels)
            {
                int levelNumber = _levelButtons.Count + 1;
                Button btn = Instantiate(levelButtonPrefab, levelButtonContainer);
                btn.gameObject.name = $"LevelButton_{levelNumber}";

                int captured = levelNumber;
                btn.onClick.AddListener(() => OnLevelButtonClicked(captured));

                _levelButtons.Add(btn);
            }
        }

        private void UpdateStarDisplay(Image[] starImages, int stars)
        {
            if (starImages == null || starFilledSprite == null || starEmptySprite == null) return;

            // Skip first image (the button background itself)
            int starIndex = 0;
            for (int i = 0; i < starImages.Length; i++)
            {
                if (starImages[i].gameObject == starImages[i].transform.parent?.gameObject) continue;
                if (starImages[i].sprite == starFilledSprite || starImages[i].sprite == starEmptySprite)
                {
                    starImages[i].sprite = starIndex < stars ? starFilledSprite : starEmptySprite;
                    starIndex++;
                }
            }
        }

        private void ScrollToCurrentLevel()
        {
            if (levelScrollRect == null || levelButtonContainer == null) return;
            if (!LevelManager.HasInstance) return;

            int currentLevel = LevelManager.Instance.MaxClearedLevel + 1;
            if (currentLevel < 1) currentLevel = 1;
            if (currentLevel > totalLevels) currentLevel = totalLevels;

            float normalizedPos = Mathf.Clamp01((float)(currentLevel - 1) / Mathf.Max(1, totalLevels - 1));
            levelScrollRect.verticalNormalizedPosition = 1f - normalizedPos;
        }

        private void HandleCoinChanged(OnCoinChanged eventData)
        {
            RefreshCoinDisplay();
        }

        private void HandleProgressUpdated(OnLevelProgressUpdated eventData)
        {
            RefreshLevelMap();
        }

        #endregion
    }
}
