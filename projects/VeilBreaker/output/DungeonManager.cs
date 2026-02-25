using System;
using System.Collections.Generic;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Economy;

namespace VeilBreaker.Content
{
    /// <summary>
    /// Manages special dungeon content: entry validation, battle delegation,
    /// reward distribution, and daily entry reset.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 2
    /// System: Dungeon
    /// </remarks>
    public class DungeonManager : Singleton<DungeonManager>
    {
        #region Data Structures

        /// <summary>
        /// Chart data for a single dungeon.
        /// </summary>
        [System.Serializable]
        public class DungeonData
        {
            public string dungeonId;
            public string name;
            public int maxDailyEntries;
            public string rewardType;       // "gold" | "equipment" | "material"
            public long rewardAmount;
            public string rewardItemId;     // for equipment/material rewards
            public string dungeonStageId;   // maps to StageData used by BattleManager
        }

        #endregion

        #region Fields

        // dungeonId → remaining entries today
        private Dictionary<string, int> _remainEntries = new();

        // Cache of all available dungeon chart data
        private List<DungeonData> _dungeonList = new();

        private DateTime _lastResetDate;

        // Active dungeon being played (for reward resolution on completion)
        private string _activeDungeonId;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            EventManager.Subscribe(GameConstants.Events.OnDataLoaded,   OnDataLoaded);
            EventManager.Subscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
        }

        protected override void OnDestroy()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnDataLoaded,   OnDataLoaded);
            EventManager.Unsubscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Attempts to enter the specified dungeon.
        /// Validates remaining entries, consumes a DungeonTicket, and starts the battle.
        /// Returns false if entry conditions are not met.
        /// </summary>
        /// <param name="dungeonId">ID of the dungeon to enter.</param>
        /// <returns>True if entry was successful and battle was started.</returns>
        public bool EnterDungeon(string dungeonId)
        {
            if (string.IsNullOrEmpty(dungeonId))
            {
                Debug.LogWarning("[DungeonManager] EnterDungeon called with empty dungeonId.");
                return false;
            }

            CheckAndResetEntries();

            if (GetRemainingEntries(dungeonId) <= 0)
            {
                Debug.Log($"[DungeonManager] No remaining entries for dungeon '{dungeonId}'.");
                return false;
            }

            if (!CurrencyManager.HasInstance ||
                !CurrencyManager.Instance.SpendCurrency(GameConstants.CurrencyType.DungeonTicket, 1))
            {
                Debug.Log("[DungeonManager] Insufficient DungeonTicket to enter dungeon.");
                return false;
            }

            _remainEntries[dungeonId]--;
            _activeDungeonId = dungeonId;
            SaveDungeonState();

            var dungeonData = GetDungeonData(dungeonId);
            if (dungeonData == null)
            {
                Debug.LogWarning($"[DungeonManager] DungeonData not found for '{dungeonId}'.");
                return false;
            }

            StartDungeonBattle(dungeonData);
            return true;
        }

        /// <summary>
        /// Returns the number of entries remaining today for the specified dungeon.
        /// Returns 0 if the dungeon ID is unknown.
        /// </summary>
        /// <param name="dungeonId">Dungeon to check.</param>
        public int GetRemainingEntries(string dungeonId)
        {
            if (string.IsNullOrEmpty(dungeonId)) return 0;
            return _remainEntries.TryGetValue(dungeonId, out var count) ? count : 0;
        }

        /// <summary>
        /// Returns all dungeons available to the player.
        /// </summary>
        public List<DungeonData> GetAvailableDungeons()
        {
            return _dungeonList ?? new List<DungeonData>();
        }

        /// <summary>
        /// Resets daily entry counts for all dungeons back to their maximum.
        /// Called automatically at the start of each day.
        /// </summary>
        public void ResetDailyEntries()
        {
            foreach (var dungeon in _dungeonList)
            {
                _remainEntries[dungeon.dungeonId] = dungeon.maxDailyEntries;
            }
            _lastResetDate = DateTime.Now.Date;
            SaveDungeonState();
            Debug.Log("[DungeonManager] Daily dungeon entries reset.");
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
                Debug.LogWarning("[DungeonManager] DataManager not available.");
                return;
            }

            var savedState = DataManager.Instance.GetUserDungeonData();
            if (savedState != null)
            {
                _remainEntries = savedState.remainEntries ?? new Dictionary<string, int>();
                _lastResetDate = savedState.lastResetDate;
            }

            var dungeons = DataManager.Instance.GetDungeonList();
            _dungeonList = dungeons ?? new List<DungeonData>();

            // Ensure all dungeon IDs have an entry in _remainEntries
            foreach (var d in _dungeonList)
            {
                if (!_remainEntries.ContainsKey(d.dungeonId))
                    _remainEntries[d.dungeonId] = d.maxDailyEntries;
            }

            CheckAndResetEntries();
            Debug.Log("[DungeonManager] Dungeon data loaded.");
        }

        private void CheckAndResetEntries()
        {
            if (DateTime.Now.Date > _lastResetDate.Date)
                ResetDailyEntries();
        }

        private void StartDungeonBattle(DungeonData dungeonData)
        {
            if (!BattleManager.HasInstance)
            {
                Debug.LogWarning("[DungeonManager] BattleManager not available. Cannot start dungeon battle.");
                return;
            }

            if (DataManager.HasInstance)
            {
                var stageData = DataManager.Instance.GetStageData(dungeonData.dungeonStageId);
                BattleManager.Instance.InitBattle(stageData);
            }
        }

        private void OnStageComplete(object data)
        {
            if (string.IsNullOrEmpty(_activeDungeonId)) return;

            GrantDungeonRewards(_activeDungeonId);
            SaveDungeonState();

            EventManager.Publish(GameConstants.Events.OnDungeonComplete, _activeDungeonId);
            _activeDungeonId = null;
        }

        private void GrantDungeonRewards(string dungeonId)
        {
            var dungeonData = GetDungeonData(dungeonId);
            if (dungeonData == null) return;

            switch (dungeonData.rewardType)
            {
                case "gold":
                    if (CurrencyManager.HasInstance)
                        CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.Gold, dungeonData.rewardAmount);
                    break;

                case "gem":
                    if (CurrencyManager.HasInstance)
                        CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.Gem, dungeonData.rewardAmount);
                    break;

                case "equipment":
                case "material":
                    if (VeilBreaker.Inventory.InventoryManager.HasInstance && !string.IsNullOrEmpty(dungeonData.rewardItemId))
                        VeilBreaker.Inventory.InventoryManager.Instance.AddItem(dungeonData.rewardItemId, (int)dungeonData.rewardAmount);
                    break;

                default:
                    Debug.LogWarning($"[DungeonManager] Unknown reward type '{dungeonData.rewardType}' for dungeon '{dungeonId}'.");
                    break;
            }

            Debug.Log($"[DungeonManager] Rewards granted for dungeon '{dungeonId}': {dungeonData.rewardType} x{dungeonData.rewardAmount}");
        }

        private DungeonData GetDungeonData(string dungeonId)
        {
            if (_dungeonList == null) return null;
            foreach (var d in _dungeonList)
            {
                if (d.dungeonId == dungeonId)
                    return d;
            }

            if (DataManager.HasInstance)
                return DataManager.Instance.GetDungeonData(dungeonId) as DungeonData;

            return null;
        }

        private void SaveDungeonState()
        {
            if (!DataManager.HasInstance) return;

            DataManager.Instance.UpdateUserDungeonData(new UserDungeonSaveData
            {
                remainEntries = _remainEntries,
                lastResetDate = _lastResetDate
            });
        }

        #endregion
    }

    /// <summary>
    /// Save state container for dungeon manager.
    /// </summary>
    [System.Serializable]
    public class UserDungeonSaveData
    {
        public Dictionary<string, int> remainEntries;
        public DateTime lastResetDate;
    }
}
