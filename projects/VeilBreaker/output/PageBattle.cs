using UnityEngine;
using UnityEngine.UI;
using TMPro;
using VeilBreaker.Core;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Battle page controller. Manages speed toggle, lobby navigation,
    /// and delegates result popup opening to UISystem on stage end.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// Phase: 3
    /// System: UI
    /// </remarks>
    public class PageBattle : PageBase
    {
        #region Fields

        [SerializeField] private Button             _speedButton;
        [SerializeField] private TextMeshProUGUI    _speedText;
        [SerializeField] private Button             _lobbyButton;
        [SerializeField] private HUD                _hud;

        private static readonly float[] SpeedOptions = { 1f, 2f, 4f };
        private int _speedIndex;

        #endregion

        #region PageBase Overrides

        /// <summary>
        /// Called when the battle page becomes visible. Initialises HUD and resets speed.
        /// </summary>
        public override void Show(object data = null)
        {
            _speedIndex = 0;
            RefreshSpeedText();

            _hud?.Init();

            _speedButton?.onClick.RemoveAllListeners();
            _speedButton?.onClick.AddListener(OnSpeedButton);

            _lobbyButton?.onClick.RemoveAllListeners();
            _lobbyButton?.onClick.AddListener(OnLobbyButton);

            EventManager.Subscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            EventManager.Subscribe(GameConstants.Events.OnStageFail,     OnStageFail);
        }

        /// <summary>
        /// Called when the battle page is hidden. Unsubscribes events.
        /// </summary>
        public override void Hide()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            EventManager.Unsubscribe(GameConstants.Events.OnStageFail,     OnStageFail);

            _speedButton?.onClick.RemoveAllListeners();
            _lobbyButton?.onClick.RemoveAllListeners();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Updates the speed button label to reflect the given multiplier.
        /// </summary>
        /// <param name="multiplier">Speed multiplier to display.</param>
        public void SetSpeedButtonText(float multiplier)
        {
            if (_speedText != null)
                _speedText.text = $"x{multiplier:0.#}";
        }

        /// <summary>
        /// Shows the battle page with initial state.
        /// </summary>
        public void Show()
        {
            Show(null);
        }

        /// <summary>
        /// Hides the battle page.
        /// </summary>
        public void Hide()
        {
            ((PageBase)this).Hide();
        }

        #endregion

        #region Private Methods

        private void OnSpeedButton()
        {
            _speedIndex = (_speedIndex + 1) % SpeedOptions.Length;
            float speed = SpeedOptions[_speedIndex];

            if (BattleManager.HasInstance)
                BattleManager.Instance.SetSpeed(speed);

            SetSpeedButtonText(speed);
        }

        private void OnLobbyButton()
        {
            if (BattleManager.HasInstance)
                BattleManager.Instance.StopBattle();

            if (UISystem.HasInstance)
                UISystem.Instance.OpenPage<PageLobby>();
        }

        private void OnStageComplete(object data)
        {
            if (UISystem.HasInstance)
                UISystem.Instance.OpenPopup<PopupResult>(data);
        }

        private void OnStageFail(object data)
        {
            if (UISystem.HasInstance)
                UISystem.Instance.OpenPopup<PopupResult>(data);
        }

        private void RefreshSpeedText()
        {
            SetSpeedButtonText(SpeedOptions[_speedIndex]);
        }

        #endregion
    }
}
