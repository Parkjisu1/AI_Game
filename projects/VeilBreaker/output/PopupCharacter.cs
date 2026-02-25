using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using VeilBreaker.Character;
using VeilBreaker.Core;
using VeilBreaker.Data;
using VeilBreaker.UI;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Hero detail and enhancement popup.
    /// Displays hero stats, portrait, equipment slots, and provides level-up/star-up buttons.
    /// Refreshes automatically on OnCharacterLevelUp event.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// System: UI
    /// Phase: 3
    /// </remarks>
    public class PopupCharacter : PopupBase
    {
        #region Fields

        [SerializeField] private TextMeshProUGUI _heroNameText;
        [SerializeField] private TextMeshProUGUI _levelText;
        [SerializeField] private TextMeshProUGUI _atkText;
        [SerializeField] private TextMeshProUGUI _defText;
        [SerializeField] private TextMeshProUGUI _hpText;
        [SerializeField] private TextMeshProUGUI _starsText;
        [SerializeField] private Button _levelUpButton;
        [SerializeField] private Button _starUpButton;
        [SerializeField] private Button _closeButton;
        [SerializeField] private Image _heroPortrait;

        private string _currentHeroId;

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            _levelUpButton?.onClick.AddListener(OnLevelUpClicked);
            _starUpButton?.onClick.AddListener(OnStarUpClicked);
            _closeButton?.onClick.AddListener(OnCloseClicked);

            EventManager.Subscribe(GameConstants.Events.OnCharacterLevelUp, OnCharacterLevelUp);
            EventManager.Subscribe(GameConstants.Events.OnCharacterStatChanged, OnCharacterStatChanged);
        }

        private void OnDisable()
        {
            _levelUpButton?.onClick.RemoveListener(OnLevelUpClicked);
            _starUpButton?.onClick.RemoveListener(OnStarUpClicked);
            _closeButton?.onClick.RemoveListener(OnCloseClicked);

            EventManager.Unsubscribe(GameConstants.Events.OnCharacterLevelUp, OnCharacterLevelUp);
            EventManager.Unsubscribe(GameConstants.Events.OnCharacterStatChanged, OnCharacterStatChanged);
        }

        #endregion

        #region Public Methods (PopupBase override)

        /// <summary>
        /// Opens the popup and initializes with hero data.
        /// </summary>
        /// <param name="data">Expected: heroId string.</param>
        public override void Open(object data = null)
        {
            _currentHeroId = data as string;

            if (string.IsNullOrEmpty(_currentHeroId))
            {
                // Default to first owned hero if none specified
                if (CharacterManager.HasInstance)
                {
                    var heroes = CharacterManager.Instance.GetOwnedHeroes();
                    if (heroes?.Count > 0)
                        _currentHeroId = heroes[0].heroId;
                }
            }

            RefreshHeroInfo(_currentHeroId);
        }

        /// <summary>
        /// Closes the popup and clears hero context.
        /// </summary>
        public override void Close()
        {
            _currentHeroId = null;
        }

        /// <summary>
        /// Refreshes all hero info UI for the given heroId.
        /// </summary>
        /// <param name="heroId">Hero to display.</param>
        public void RefreshHeroInfo(string heroId)
        {
            if (string.IsNullOrEmpty(heroId)) return;
            if (!CharacterManager.HasInstance || !DataManager.HasInstance) return;

            UserHeroData userHero = DataManager.Instance.GetUserHeroData(heroId);
            HeroData heroData = DataManager.Instance.GetHeroData(heroId);

            if (userHero == null || heroData == null)
            {
                Debug.LogWarning($"[PopupCharacter] Hero data not found for: {heroId}");
                return;
            }

            // Stats scale with level: baseStat + growthStat * (level - 1)
            float atk = heroData.baseAtk + heroData.growthAtk * (userHero.level - 1);
            float def = heroData.baseDef + heroData.growthDef * (userHero.level - 1);
            float hp = heroData.baseHp + heroData.growthHp * (userHero.level - 1);

            if (_heroNameText != null) _heroNameText.text = heroData.name;
            if (_levelText != null) _levelText.text = $"Lv.{userHero.level}";
            if (_atkText != null) _atkText.text = Mathf.RoundToInt(atk).ToString("N0");
            if (_defText != null) _defText.text = Mathf.RoundToInt(def).ToString("N0");
            if (_hpText != null) _hpText.text = Mathf.RoundToInt(hp).ToString("N0");
            if (_starsText != null) _starsText.text = new string('★', userHero.stars);

            RefreshButtonStates(userHero);
        }

        #endregion

        #region Private Methods - Button Handlers

        private void OnLevelUpClicked()
        {
            if (string.IsNullOrEmpty(_currentHeroId) || !CharacterManager.HasInstance) return;

            CharacterManager.Instance.LevelUpHero(_currentHeroId);
        }

        private void OnStarUpClicked()
        {
            if (string.IsNullOrEmpty(_currentHeroId) || !CharacterManager.HasInstance) return;

            CharacterManager.Instance.StarUpHero(_currentHeroId);
        }

        private void OnCloseClicked()
        {
            CloseThis();
        }

        #endregion

        #region Private Methods - Event Handlers

        private void OnCharacterLevelUp(object data)
        {
            // data is (string heroId, int newLevel) tuple
            if (data is System.ValueTuple<string, int> tuple && tuple.Item1 == _currentHeroId)
            {
                RefreshHeroInfo(_currentHeroId);
            }
        }

        private void OnCharacterStatChanged(object data)
        {
            string heroId = data as string;
            if (heroId == _currentHeroId)
            {
                RefreshHeroInfo(_currentHeroId);
            }
        }

        private void RefreshButtonStates(UserHeroData userHero)
        {
            if (_levelUpButton != null)
            {
                bool atMaxLevel = userHero.level >= GameConstants.Hero.MaxLevel;
                _levelUpButton.interactable = !atMaxLevel;
            }

            if (_starUpButton != null)
            {
                bool atMaxStars = userHero.stars >= GameConstants.Hero.MaxStars;
                _starUpButton.interactable = !atMaxStars;
            }
        }

        #endregion
    }
}
