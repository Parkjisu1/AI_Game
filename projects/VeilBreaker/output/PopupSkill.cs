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
    /// Skill management popup. Displays up to 3 skill slots for the current hero
    /// with level-up functionality. Cooldown display is handled by the battle HUD, not here.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// System: UI
    /// Phase: 3
    /// </remarks>
    public class PopupSkill : PopupBase
    {
        #region Fields

        [SerializeField] private SkillSlotUI[] _skillSlots;
        [SerializeField] private Button _closeButton;
        [SerializeField] private TextMeshProUGUI _skillStoneText;

        private string _currentHeroId;

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            _closeButton?.onClick.AddListener(OnCloseClicked);
            EventManager.Subscribe(GameConstants.Events.OnCharacterStatChanged, OnSkillUpdated);
        }

        private void OnDisable()
        {
            _closeButton?.onClick.RemoveListener(OnCloseClicked);
            EventManager.Unsubscribe(GameConstants.Events.OnCharacterStatChanged, OnSkillUpdated);
        }

        #endregion

        #region Public Methods (PopupBase override)

        /// <summary>
        /// Opens the popup for the specified hero and populates skill slots.
        /// </summary>
        /// <param name="data">Expected: heroId string.</param>
        public override void Open(object data = null)
        {
            _currentHeroId = data as string;
            RefreshSkillSlots();
        }

        /// <summary>
        /// Clears hero context on close.
        /// </summary>
        public override void Close()
        {
            _currentHeroId = null;
        }

        #endregion

        #region Private Methods

        private void RefreshSkillSlots()
        {
            if (string.IsNullOrEmpty(_currentHeroId)) return;
            if (!SkillManager.HasInstance) return;

            List<SkillData> skills = SkillManager.Instance.GetHeroSkills(_currentHeroId);

            if (_skillSlots != null)
            {
                for (int i = 0; i < _skillSlots.Length; i++)
                {
                    if (_skillSlots[i] == null) continue;

                    if (i < skills.Count)
                    {
                        _skillSlots[i].SetSkill(skills[i], _currentHeroId, this);
                        _skillSlots[i].gameObject.SetActive(true);
                    }
                    else
                    {
                        _skillSlots[i].gameObject.SetActive(false);
                    }
                }
            }

            RefreshSkillStoneText();
        }

        private void RefreshSkillStoneText()
        {
            if (_skillStoneText == null) return;
            // SkillStone uses DungeonTicket in current CurrencyType mapping
            if (VeilBreaker.Economy.CurrencyManager.HasInstance)
            {
                long stones = VeilBreaker.Economy.CurrencyManager.Instance
                    .GetBalance(GameConstants.CurrencyType.DungeonTicket);
                _skillStoneText.text = stones.ToString("N0");
            }
        }

        private void OnSkillUpdated(object data)
        {
            string heroId = data as string;
            if (heroId == _currentHeroId) RefreshSkillSlots();
        }

        private void OnCloseClicked()
        {
            CloseThis();
        }

        #endregion
    }

    /// <summary>
    /// UI component representing a single skill slot in PopupSkill.
    /// Attach to each skill slot prefab child. User connects fields via Inspector.
    /// </summary>
    public class SkillSlotUI : MonoBehaviour
    {
        #region Fields

        [SerializeField] private TextMeshProUGUI _skillNameText;
        [SerializeField] private TextMeshProUGUI _skillLevelText;
        [SerializeField] private TextMeshProUGUI _skillDescText;
        [SerializeField] private Button _levelUpButton;

        private SkillData _skillData;
        private string _heroId;
        private PopupSkill _parentPopup;

        #endregion

        #region Public Methods

        /// <summary>
        /// Populates this slot with skill data and wires the level-up button.
        /// </summary>
        public void SetSkill(SkillData skill, string heroId, PopupSkill parent)
        {
            _skillData = skill;
            _heroId = heroId;
            _parentPopup = parent;

            if (_skillNameText != null) _skillNameText.text = skill?.name ?? "";
            if (_skillDescText != null) _skillDescText.text = skill?.description ?? "";
            if (_skillLevelText != null) _skillLevelText.text = "Lv.1";

            _levelUpButton?.onClick.RemoveAllListeners();
            _levelUpButton?.onClick.AddListener(OnLevelUpClicked);
        }

        #endregion

        #region Private Methods

        private void OnLevelUpClicked()
        {
            if (_skillData == null || string.IsNullOrEmpty(_heroId)) return;
            if (!SkillManager.HasInstance) return;

            SkillManager.Instance.LevelUpSkill(_heroId, _skillData.skillId);
        }

        #endregion
    }
}
