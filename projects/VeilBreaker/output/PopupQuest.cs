using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using VeilBreaker.Core;
using VeilBreaker.Quest;
using VeilBreaker.UI;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Quest popup with three tabs: Daily, Weekly, Achievements.
    /// Uses ObjectPool for quest item rows to avoid repeated Instantiate/Destroy.
    /// Refreshes specific quests in response to OnQuestProgress/OnQuestComplete events.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// System: UI
    /// Phase: 3
    /// </remarks>
    public class PopupQuest : PopupBase
    {
        #region Fields

        [SerializeField] private Toggle[] _tabToggles;     // 0=Daily, 1=Weekly, 2=Achievement
        [SerializeField] private Transform _questListContent;
        [SerializeField] private GameObject _questItemPrefab;
        [SerializeField] private Button _closeButton;

        private QuestTabType _currentTab = QuestTabType.Daily;
        private readonly List<QuestItemUI> _activeItems = new();

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            _closeButton?.onClick.AddListener(OnCloseClicked);

            if (_tabToggles != null)
            {
                for (int i = 0; i < _tabToggles.Length; i++)
                {
                    int tabIndex = i;
                    _tabToggles[i]?.onValueChanged.AddListener(on => { if (on) OnTabSelected(tabIndex); });
                }
            }

            EventManager.Subscribe(GameConstants.Events.OnQuestProgress, OnQuestProgress);
            EventManager.Subscribe(GameConstants.Events.OnQuestComplete, OnQuestComplete);
        }

        private void OnDisable()
        {
            _closeButton?.onClick.RemoveListener(OnCloseClicked);

            if (_tabToggles != null)
            {
                foreach (var toggle in _tabToggles)
                    toggle?.onValueChanged.RemoveAllListeners();
            }

            EventManager.Unsubscribe(GameConstants.Events.OnQuestProgress, OnQuestProgress);
            EventManager.Unsubscribe(GameConstants.Events.OnQuestComplete, OnQuestComplete);
        }

        #endregion

        #region Public Methods (PopupBase override)

        /// <summary>
        /// Opens the quest popup on the Daily tab by default.
        /// </summary>
        public override void Open(object data = null)
        {
            _currentTab = QuestTabType.Daily;
            if (_tabToggles?.Length > 0)
                _tabToggles[0].isOn = true;

            LoadTab(_currentTab);
        }

        /// <summary>
        /// Clears the quest list on close.
        /// </summary>
        public override void Close()
        {
            ClearQuestList();
        }

        /// <summary>
        /// Refreshes the UI row for the specified questId if it is currently visible.
        /// </summary>
        /// <param name="questId">Quest ID whose row should be refreshed.</param>
        public void RefreshQuestList(string questId)
        {
            if (string.IsNullOrEmpty(questId)) return;

            foreach (QuestItemUI item in _activeItems)
            {
                if (item?.QuestId == questId)
                {
                    item.Refresh();
                    break;
                }
            }
        }

        #endregion

        #region Private Methods

        private void OnTabSelected(int tabIndex)
        {
            _currentTab = (QuestTabType)tabIndex;
            LoadTab(_currentTab);
        }

        private void LoadTab(QuestTabType tab)
        {
            if (!QuestManager.HasInstance) return;

            List<QuestManager.UserQuestData> quests = tab switch
            {
                QuestTabType.Daily => QuestManager.Instance.GetDailyQuests(),
                QuestTabType.Weekly => QuestManager.Instance.GetWeeklyQuests(),
                QuestTabType.Achievement => QuestManager.Instance.GetAchievements(),
                _ => null
            };

            ClearQuestList();
            if (quests == null) return;

            foreach (var questData in quests)
            {
                if (questData == null) continue;

                QuestItemUI item = SpawnQuestItem();
                item?.SetQuest(questData, this);
            }
        }

        private QuestItemUI SpawnQuestItem()
        {
            if (_questListContent == null || _questItemPrefab == null) return null;

            // Reuse from ObjectPool if possible
            GameObject go;
            if (ObjectPool.HasInstance)
            {
                go = ObjectPool.Instance.Spawn("QuestItem", _questListContent.position, Quaternion.identity);
                if (go != null) go.transform.SetParent(_questListContent, false);
            }
            else
            {
                go = Object.Instantiate(_questItemPrefab, _questListContent);
            }

            if (go == null) return null;

            var itemUI = go.GetComponent<QuestItemUI>() ?? go.AddComponent<QuestItemUI>();
            _activeItems.Add(itemUI);
            return itemUI;
        }

        private void ClearQuestList()
        {
            foreach (QuestItemUI item in _activeItems)
            {
                if (item == null) continue;
                if (ObjectPool.HasInstance)
                    ObjectPool.Instance.Despawn(item.gameObject);
                else
                    Destroy(item.gameObject);
            }
            _activeItems.Clear();
        }

        private void OnQuestProgress(object data)
        {
            RefreshQuestList(data as string);
        }

        private void OnQuestComplete(object data)
        {
            RefreshQuestList(data as string);
        }

        private void OnCloseClicked()
        {
            CloseThis();
        }

        #endregion

        #region Enums

        private enum QuestTabType { Daily = 0, Weekly = 1, Achievement = 2 }

        #endregion
    }

    /// <summary>
    /// A single row in the quest list. Connected to QuestManager.ClaimReward.
    /// User assigns TextMeshProUGUI/Button fields via Inspector or SetQuest populates them by code.
    /// </summary>
    public class QuestItemUI : MonoBehaviour
    {
        #region Fields

        [SerializeField] private TextMeshProUGUI _titleText;
        [SerializeField] private TextMeshProUGUI _progressText;
        [SerializeField] private Button _claimButton;

        private QuestManager.UserQuestData _questData;
        private PopupQuest _parentPopup;

        #endregion

        #region Properties

        /// <summary>Quest ID for targeted refresh.</summary>
        public string QuestId => _questData?.questId;

        #endregion

        #region Public Methods

        /// <summary>
        /// Populates the row with quest data.
        /// </summary>
        public void SetQuest(QuestManager.UserQuestData questData, PopupQuest parent)
        {
            _questData = questData;
            _parentPopup = parent;

            _claimButton?.onClick.RemoveAllListeners();
            _claimButton?.onClick.AddListener(OnClaimClicked);

            Refresh();
        }

        /// <summary>
        /// Refreshes this row's display from current quest state.
        /// </summary>
        public void Refresh()
        {
            if (_questData == null) return;

            if (_titleText != null) _titleText.text = _questData.questId;
            if (_progressText != null)
            {
                _progressText.text = _questData.isComplete ? "Complete!" : $"{_questData.progress}";
            }

            if (_claimButton != null)
            {
                _claimButton.interactable = _questData.isComplete && !_questData.isClaimed;
            }
        }

        #endregion

        #region Private Methods

        private void OnClaimClicked()
        {
            if (_questData == null || !QuestManager.HasInstance) return;

            QuestManager.Instance.ClaimReward(_questData.questId);
            Refresh();
        }

        #endregion
    }
}
