using TMPro;
using UnityEngine;
using UnityEngine.UI;
using VeilBreaker.Character;
using VeilBreaker.Core;
using VeilBreaker.Economy;
using VeilBreaker.Idle;
using VeilBreaker.UI;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Main lobby page. Displays stage info and currency, provides navigation
    /// to battle and all major popups.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// System: UI
    /// Phase: 3
    /// </remarks>
    public class PageLobby : PageBase
    {
        #region Fields

        [SerializeField] private Button _battleButton;
        [SerializeField] private Button _heroButton;
        [SerializeField] private Button _equipButton;
        [SerializeField] private Button _gachaButton;
        [SerializeField] private Button _questButton;
        [SerializeField] private Button _shopButton;
        [SerializeField] private Button _settingsButton;
        [SerializeField] private TextMeshProUGUI _stageLabel;
        [SerializeField] private TextMeshProUGUI _goldText;
        [SerializeField] private TextMeshProUGUI _gemText;

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            _battleButton?.onClick.AddListener(OnBattleClicked);
            _heroButton?.onClick.AddListener(OnHeroClicked);
            _equipButton?.onClick.AddListener(OnEquipClicked);
            _gachaButton?.onClick.AddListener(OnGachaClicked);
            _questButton?.onClick.AddListener(OnQuestClicked);
            _shopButton?.onClick.AddListener(OnShopClicked);
            _settingsButton?.onClick.AddListener(OnSettingsClicked);

            EventManager.Subscribe(GameConstants.Events.OnCurrencyChanged, OnCurrencyChanged);
            EventManager.Subscribe(GameConstants.Events.OnStageComplete, OnStageChanged);
        }

        private void OnDisable()
        {
            _battleButton?.onClick.RemoveListener(OnBattleClicked);
            _heroButton?.onClick.RemoveListener(OnHeroClicked);
            _equipButton?.onClick.RemoveListener(OnEquipClicked);
            _gachaButton?.onClick.RemoveListener(OnGachaClicked);
            _questButton?.onClick.RemoveListener(OnQuestClicked);
            _shopButton?.onClick.RemoveListener(OnShopClicked);
            _settingsButton?.onClick.RemoveListener(OnSettingsClicked);

            EventManager.Unsubscribe(GameConstants.Events.OnCurrencyChanged, OnCurrencyChanged);
            EventManager.Unsubscribe(GameConstants.Events.OnStageComplete, OnStageChanged);
        }

        #endregion

        #region Public Methods (PageBase override)

        /// <summary>
        /// Called by UISystem when this page is shown. Refreshes all UI.
        /// </summary>
        public override void Show(object data = null)
        {
            RefreshUI();
        }

        /// <summary>
        /// Called by UISystem when this page is hidden. No cleanup needed.
        /// </summary>
        public override void Hide()
        {
        }

        /// <summary>
        /// Refreshes all displayed data: stage label and currency values.
        /// </summary>
        public void RefreshUI()
        {
            RefreshStageLabel();
            RefreshCurrencyDisplay();
        }

        #endregion

        #region Private Methods - Button Handlers

        private void OnBattleClicked()
        {
            if (!StageManager.HasInstance) return;

            string currentStageId = StageManager.Instance.GetCurrentStageId();
            if (string.IsNullOrEmpty(currentStageId))
            {
                // Default to first unlocked stage if none active
                currentStageId = "1_1";
            }

            StageManager.Instance.StartStage(currentStageId);
        }

        private void OnHeroClicked()
        {
            if (UISystem.HasInstance)
                UISystem.Instance.OpenPopup<PopupCharacter>();
        }

        private void OnEquipClicked()
        {
            if (UISystem.HasInstance)
                UISystem.Instance.OpenPopup<PopupInventory>();
        }

        private void OnGachaClicked()
        {
            // GachaPopup not in current scope; log for future implementation
            Debug.Log("[PageLobby] Gacha button clicked.");
        }

        private void OnQuestClicked()
        {
            if (UISystem.HasInstance)
                UISystem.Instance.OpenPopup<PopupQuest>();
        }

        private void OnShopClicked()
        {
            Debug.Log("[PageLobby] Shop button clicked.");
        }

        private void OnSettingsClicked()
        {
            if (UISystem.HasInstance)
                UISystem.Instance.OpenPopup<PopupSettings>();
        }

        #endregion

        #region Private Methods - UI Refresh

        private void RefreshStageLabel()
        {
            if (_stageLabel == null) return;
            if (!StageManager.HasInstance) return;

            var userStage = StageManager.Instance.GetUserStageData();
            if (userStage != null)
            {
                _stageLabel.text = $"Chapter {userStage.currentChapter} - {userStage.currentStage}";
            }
            else
            {
                _stageLabel.text = "Chapter 1 - 1";
            }
        }

        private void RefreshCurrencyDisplay()
        {
            if (!CurrencyManager.HasInstance) return;

            if (_goldText != null)
            {
                long gold = CurrencyManager.Instance.GetBalance(GameConstants.CurrencyType.Gold);
                _goldText.text = Util.FormatNumber(gold);
            }

            if (_gemText != null)
            {
                long gem = CurrencyManager.Instance.GetBalance(GameConstants.CurrencyType.Gem);
                _gemText.text = gem.ToString("N0");
            }
        }

        private void OnCurrencyChanged(object data)
        {
            RefreshCurrencyDisplay();
        }

        private void OnStageChanged(object data)
        {
            RefreshStageLabel();
        }

        #endregion
    }
}
