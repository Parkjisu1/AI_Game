using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using VeilBreaker.Core;

namespace VeilBreaker.UI
{
    /// <summary>
    /// In-game HUD displaying currency, stage info, hero HP bars, and boss HP bar.
    /// All UI references are connected via Inspector. Updated exclusively via events.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// Phase: 3
    /// System: UI
    /// </remarks>
    public class HUD : MonoBehaviour
    {
        #region Fields

        [SerializeField] private TextMeshProUGUI _goldText;
        [SerializeField] private TextMeshProUGUI _gemText;
        [SerializeField] private TextMeshProUGUI _stageLabel;

        [SerializeField] private Slider   _bossHpBar;
        [SerializeField] private GameObject _bossHpBarRoot;

        /// <summary>
        /// Hero HP bar sliders indexed by formation slot (0-4).
        /// Assign in Inspector in the same order as hero formation.
        /// </summary>
        [SerializeField] private Slider[] _heroHpBars;

        // heroId → slider index mapping (populated at Init)
        private readonly Dictionary<string, int> _heroSlotMap = new();

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            EventManager.Subscribe(GameConstants.Events.OnCurrencyChanged,    OnCurrencyChanged);
            EventManager.Subscribe(GameConstants.Events.OnHeroDie,            OnHeroDie);
            EventManager.Subscribe(GameConstants.Events.OnBossSpawn,          OnBossSpawn);
            EventManager.Subscribe(GameConstants.Events.OnStageStart,         OnStageStart);
            EventManager.Subscribe(GameConstants.Events.OnStageComplete,      OnStageEnd);
            EventManager.Subscribe(GameConstants.Events.OnStageFail,          OnStageEnd);
        }

        private void OnDisable()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnCurrencyChanged,  OnCurrencyChanged);
            EventManager.Unsubscribe(GameConstants.Events.OnHeroDie,          OnHeroDie);
            EventManager.Unsubscribe(GameConstants.Events.OnBossSpawn,        OnBossSpawn);
            EventManager.Unsubscribe(GameConstants.Events.OnStageStart,       OnStageStart);
            EventManager.Unsubscribe(GameConstants.Events.OnStageComplete,    OnStageEnd);
            EventManager.Unsubscribe(GameConstants.Events.OnStageFail,        OnStageEnd);
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialises HUD, maps hero IDs to HP bar slots, and hides boss bar.
        /// </summary>
        public void Init()
        {
            _heroSlotMap.Clear();
            HideBossHpBar();
            RefreshCurrencyDisplay();
        }

        /// <summary>
        /// Sets the HP bar fill ratio for the specified hero.
        /// </summary>
        /// <param name="heroId">Hero identifier.</param>
        /// <param name="ratio">Fill ratio in range [0, 1].</param>
        public void UpdateHeroHpBar(string heroId, float ratio)
        {
            if (!_heroSlotMap.TryGetValue(heroId, out int slot)) return;
            if (_heroHpBars == null || slot >= _heroHpBars.Length) return;
            if (_heroHpBars[slot] == null) return;

            _heroHpBars[slot].value = Mathf.Clamp01(ratio);
        }

        /// <summary>
        /// Updates the boss HP bar fill ratio and ensures it is visible.
        /// </summary>
        /// <param name="ratio">Fill ratio in range [0, 1].</param>
        public void ShowBossHpBar(float ratio)
        {
            _bossHpBarRoot?.SetActive(true);
            if (_bossHpBar != null)
                _bossHpBar.value = Mathf.Clamp01(ratio);
        }

        /// <summary>
        /// Hides the boss HP bar.
        /// </summary>
        public void HideBossHpBar()
        {
            _bossHpBarRoot?.SetActive(false);
        }

        /// <summary>
        /// Updates the displayed amount for the given currency type.
        /// </summary>
        /// <param name="type">Currency type to update.</param>
        /// <param name="amount">New balance to display.</param>
        public void UpdateCurrencyDisplay(GameConstants.CurrencyType type, long amount)
        {
            switch (type)
            {
                case GameConstants.CurrencyType.Gold:
                    if (_goldText != null) _goldText.text = FormatNumber(amount);
                    break;
                case GameConstants.CurrencyType.Gem:
                    if (_gemText != null) _gemText.text = FormatNumber(amount);
                    break;
            }
        }

        /// <summary>
        /// Updates the stage label text.
        /// </summary>
        /// <param name="stageId">Stage identifier to display.</param>
        public void UpdateStageLabel(string stageId)
        {
            if (_stageLabel != null)
                _stageLabel.text = stageId;
        }

        /// <summary>
        /// Registers a hero ID to a formation slot index for HP bar mapping.
        /// Call this when setting up the formation before battle starts.
        /// </summary>
        /// <param name="heroId">Hero identifier.</param>
        /// <param name="slotIndex">Formation slot (0-based).</param>
        public void RegisterHeroSlot(string heroId, int slotIndex)
        {
            if (!string.IsNullOrEmpty(heroId))
                _heroSlotMap[heroId] = slotIndex;
        }

        #endregion

        #region Private Methods

        private void RefreshCurrencyDisplay()
        {
            if (!VeilBreaker.Economy.CurrencyManager.HasInstance) return;
            var cm = VeilBreaker.Economy.CurrencyManager.Instance;
            UpdateCurrencyDisplay(GameConstants.CurrencyType.Gold, cm.GetBalance(GameConstants.CurrencyType.Gold));
            UpdateCurrencyDisplay(GameConstants.CurrencyType.Gem,  cm.GetBalance(GameConstants.CurrencyType.Gem));
        }

        private void OnCurrencyChanged(object data)
        {
            if (data is GameConstants.CurrencyType type)
            {
                if (!VeilBreaker.Economy.CurrencyManager.HasInstance) return;
                long balance = VeilBreaker.Economy.CurrencyManager.Instance.GetBalance(type);
                UpdateCurrencyDisplay(type, balance);
            }
        }

        private void OnHeroDie(object data)
        {
            if (data is string heroId)
                UpdateHeroHpBar(heroId, 0f);
        }

        private void OnBossSpawn(object data)
        {
            ShowBossHpBar(1f);
        }

        private void OnStageStart(object data)
        {
            if (data is int stageId)
                UpdateStageLabel($"Stage {stageId}");
            else if (data is string stageStr)
                UpdateStageLabel(stageStr);

            HideBossHpBar();

            // Reset all hero bars to full
            if (_heroHpBars != null)
                foreach (var bar in _heroHpBars)
                    if (bar != null) bar.value = 1f;
        }

        private void OnStageEnd(object data)
        {
            HideBossHpBar();
        }

        private static string FormatNumber(long n)
        {
            if (n >= 1_000_000_000) return $"{n / 1_000_000_000f:0.#}B";
            if (n >= 1_000_000)     return $"{n / 1_000_000f:0.#}M";
            if (n >= 1_000)         return $"{n / 1_000f:0.#}K";
            return n.ToString();
        }

        #endregion
    }
}
