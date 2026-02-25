using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Economy;

namespace VeilBreaker.Quest
{
    /// <summary>
    /// Manages daily, weekly, and achievement quests.
    /// Listens to game events to automatically update quest progress.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 2
    /// System: Quest
    /// </remarks>
    public class QuestManager : Singleton<QuestManager>
    {
        #region Enums

        /// <summary>
        /// Quest category used for grouping and reset scheduling.
        /// </summary>
        public enum QuestCategory
        {
            Daily,
            Weekly,
            Achievement
        }

        #endregion

        #region Data Structures

        /// <summary>
        /// Runtime quest state for a single quest entry.
        /// </summary>
        [System.Serializable]
        public class UserQuestData
        {
            public string questId;
            public QuestCategory category;
            public string condition;
            public int targetCount;
            public int progress;
            public bool isComplete;
            public bool isClaimed;

            /// <summary>Reward currency type key (e.g. "Gold", "Gem").</summary>
            public string rewardCurrencyType;
            public long rewardAmount;
        }

        #endregion

        #region Fields

        private List<UserQuestData> _dailyQuests   = new();
        private List<UserQuestData> _weeklyQuests  = new();
        private List<UserQuestData> _achievements  = new();

        private DateTime _lastDailyReset;
        private DateTime _lastWeeklyReset;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            EventManager.Subscribe(GameConstants.Events.OnDataLoaded,    OnDataLoaded);
            EventManager.Subscribe(GameConstants.Events.OnEnemyDie,      OnEnemyDie);
            EventManager.Subscribe(GameConstants.Events.OnStageComplete,  OnStageComplete);
            EventManager.Subscribe(GameConstants.Events.OnGachaResult,    OnGachaResult);
            EventManager.Subscribe(GameConstants.Events.OnCharacterLevelUp, OnCharacterLevelUp);
        }

        protected override void OnDestroy()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnDataLoaded,      OnDataLoaded);
            EventManager.Unsubscribe(GameConstants.Events.OnEnemyDie,        OnEnemyDie);
            EventManager.Unsubscribe(GameConstants.Events.OnStageComplete,   OnStageComplete);
            EventManager.Unsubscribe(GameConstants.Events.OnGachaResult,     OnGachaResult);
            EventManager.Unsubscribe(GameConstants.Events.OnCharacterLevelUp, OnCharacterLevelUp);
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Returns the current list of daily quests.
        /// </summary>
        public List<UserQuestData> GetDailyQuests() => _dailyQuests;

        /// <summary>
        /// Returns the current list of weekly quests.
        /// </summary>
        public List<UserQuestData> GetWeeklyQuests() => _weeklyQuests;

        /// <summary>
        /// Returns the full list of achievements.
        /// </summary>
        public List<UserQuestData> GetAchievements() => _achievements;

        /// <summary>
        /// Claims the reward for a completed quest.
        /// Returns false if the quest is not yet complete or already claimed.
        /// </summary>
        /// <param name="questId">ID of the quest to claim.</param>
        /// <returns>True if reward was successfully granted.</returns>
        public bool ClaimReward(string questId)
        {
            var quest = FindQuest(questId);
            if (quest == null)
            {
                Debug.LogWarning($"[QuestManager] Quest not found: {questId}");
                return false;
            }

            if (!quest.isComplete)
            {
                Debug.Log($"[QuestManager] Quest '{questId}' not yet complete.");
                return false;
            }

            if (quest.isClaimed)
            {
                Debug.Log($"[QuestManager] Quest '{questId}' already claimed.");
                return false;
            }

            GrantReward(quest);
            quest.isClaimed = true;
            SaveQuests();

            EventManager.Publish(GameConstants.Events.OnQuestComplete, questId);
            return true;
        }

        /// <summary>
        /// Updates progress for all quests matching the given condition string.
        /// Marks quests as complete when targetCount is reached.
        /// </summary>
        /// <param name="condition">Condition key (e.g. "kill_enemy", "clear_stage").</param>
        /// <param name="amount">Progress amount to add.</param>
        public void UpdateProgress(string condition, int amount)
        {
            if (string.IsNullOrEmpty(condition) || amount <= 0) return;

            CheckAndResetQuests();

            bool anyUpdated = false;
            foreach (var quest in AllQuests())
            {
                if (quest.isComplete) continue;
                if (!string.Equals(quest.condition, condition, StringComparison.Ordinal)) continue;

                quest.progress = Mathf.Min(quest.progress + amount, quest.targetCount);

                if (quest.progress >= quest.targetCount)
                    quest.isComplete = true;

                EventManager.Publish(GameConstants.Events.OnQuestProgress, quest.questId);
                anyUpdated = true;
            }

            if (anyUpdated)
                SaveQuests();
        }

        #endregion

        #region Private Methods

        private void OnDataLoaded(object data)
        {
            LoadFromDataManager();
        }

        private void LoadFromDataManager()
        {
            if (!DataManager.HasInstance)
            {
                Debug.LogWarning("[QuestManager] DataManager not available.");
                return;
            }

            var savedData = DataManager.Instance.GetUserQuestData();
            if (savedData != null)
            {
                _dailyQuests  = savedData.dailyQuests  ?? new List<UserQuestData>();
                _weeklyQuests = savedData.weeklyQuests ?? new List<UserQuestData>();
                _achievements = savedData.achievements ?? new List<UserQuestData>();
                _lastDailyReset  = savedData.lastDailyReset;
                _lastWeeklyReset = savedData.lastWeeklyReset;
            }

            CheckAndResetQuests();
            Debug.Log("[QuestManager] Quest data loaded.");
        }

        private void CheckAndResetQuests()
        {
            var now = DateTime.Now.Date;

            if (now > _lastDailyReset.Date)
            {
                ResetQuestList(_dailyQuests);
                _lastDailyReset = now;
                Debug.Log("[QuestManager] Daily quests reset.");
            }

            // Weekly reset on Monday
            if (now > _lastWeeklyReset.Date && now.DayOfWeek == DayOfWeek.Monday)
            {
                ResetQuestList(_weeklyQuests);
                _lastWeeklyReset = now;
                Debug.Log("[QuestManager] Weekly quests reset.");
            }
        }

        private void ResetQuestList(List<UserQuestData> quests)
        {
            if (quests == null) return;
            foreach (var q in quests)
            {
                q.progress   = 0;
                q.isComplete = false;
                q.isClaimed  = false;
            }
        }

        private void GrantReward(UserQuestData quest)
        {
            if (!CurrencyManager.HasInstance) return;

            if (!System.Enum.TryParse<GameConstants.CurrencyType>(quest.rewardCurrencyType, out var currencyType))
            {
                Debug.LogWarning($"[QuestManager] Unknown reward currency type: {quest.rewardCurrencyType}");
                return;
            }

            CurrencyManager.Instance.AddCurrency(currencyType, quest.rewardAmount);
            Debug.Log($"[QuestManager] Reward granted: {quest.rewardAmount} {currencyType} for quest '{quest.questId}'");
        }

        private void SaveQuests()
        {
            if (!DataManager.HasInstance) return;
            DataManager.Instance.UpdateUserQuestData(new UserQuestSaveData
            {
                dailyQuests      = _dailyQuests,
                weeklyQuests     = _weeklyQuests,
                achievements     = _achievements,
                lastDailyReset   = _lastDailyReset,
                lastWeeklyReset  = _lastWeeklyReset
            });
        }

        private UserQuestData FindQuest(string questId)
        {
            foreach (var quest in AllQuests())
            {
                if (quest.questId == questId)
                    return quest;
            }
            return null;
        }

        private IEnumerable<UserQuestData> AllQuests()
        {
            foreach (var q in _dailyQuests)  yield return q;
            foreach (var q in _weeklyQuests) yield return q;
            foreach (var q in _achievements) yield return q;
        }

        // ----- Event Handlers -----

        private void OnEnemyDie(object data)
        {
            UpdateProgress("kill_enemy", 1);
        }

        private void OnStageComplete(object data)
        {
            UpdateProgress("clear_stage", 1);
        }

        private void OnGachaResult(object data)
        {
            if (data is System.Collections.Generic.List<string> heroIds)
                UpdateProgress("pull_gacha", heroIds.Count);
            else
                UpdateProgress("pull_gacha", 1);
        }

        private void OnCharacterLevelUp(object data)
        {
            UpdateProgress("level_up_hero", 1);
        }

        #endregion
    }

    /// <summary>
    /// Serializable container for all quest save state.
    /// </summary>
    [System.Serializable]
    public class UserQuestSaveData
    {
        public List<QuestManager.UserQuestData> dailyQuests;
        public List<QuestManager.UserQuestData> weeklyQuests;
        public List<QuestManager.UserQuestData> achievements;
        public DateTime lastDailyReset;
        public DateTime lastWeeklyReset;
    }
}
