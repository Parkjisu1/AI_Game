using System;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Data;
using VeilBreaker.Economy;

namespace VeilBreaker.Content
{
    /// <summary>
    /// Manages Veil Tower infinite dungeon progression.
    /// Delegates battle execution to BattleManager via events.
    /// Floors must be challenged sequentially; skipping is not permitted.
    /// Daily attempt limit: 3 per day.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// System: Tower
    /// Phase: 2
    /// </remarks>
    public class TowerManager : Singleton<TowerManager>
    {
        #region Constants

        private const int MaxDailyAttempts = 3;
        private const float BaseEnemyMultiplierPerFloor = 0.05f;
        private const float CycleMultiplierTier2 = 1.5f; // floors 101-200
        private const int FloorCycleSize = 100;
        private const string TowerCoinCurrencyKey = "TowerCoin";

        #endregion

        #region Fields

        private int _maxFloor;
        private int _currentFloor;
        private int _dailyAttempts;
        private string _lastAttemptDate;

        #endregion

        #region Properties

        /// <summary>
        /// Current floor being challenged.
        /// </summary>
        public int CurrentFloor => _currentFloor;

        /// <summary>
        /// Highest floor ever cleared.
        /// </summary>
        public int MaxFloor => _maxFloor;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            EventManager.Subscribe(GameConstants.Events.OnDataLoaded, OnDataLoaded);
            EventManager.Subscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            EventManager.Subscribe(GameConstants.Events.OnStageFail, OnStageFail);
        }

        protected override void OnDestroy()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnDataLoaded, OnDataLoaded);
            EventManager.Unsubscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            EventManager.Unsubscribe(GameConstants.Events.OnStageFail, OnStageFail);
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Starts a tower battle on the specified floor.
        /// Floor must be <= maxFloor + 1 (sequential only).
        /// Requires daily attempts remaining.
        /// </summary>
        /// <param name="floor">Floor number to challenge (1-based).</param>
        public void StartTower(int floor)
        {
            if (floor <= 0)
            {
                Debug.LogWarning($"[TowerManager] Invalid floor: {floor}");
                return;
            }

            // Step 1: Validate sequential challenge
            if (floor > _maxFloor + 1)
            {
                Debug.LogWarning($"[TowerManager] Cannot skip floors. MaxFloor={_maxFloor}, requested={floor}");
                return;
            }

            if (!CanAttempt())
            {
                Debug.Log("[TowerManager] No daily attempts remaining.");
                return;
            }

            if (!DataManager.HasInstance) return;

            // Step 2: Calculate floor enemy stat multiplier
            TowerFloorData floorData = GetFloorData(floor);
            if (floorData == null)
            {
                Debug.LogWarning($"[TowerManager] No floor data for floor {floor}. Generating default.");
                floorData = GenerateDefaultFloorData(floor);
            }

            _currentFloor = floor;
            _dailyAttempts++;
            PersistTowerData();

            // Step 3: Delegate battle to BattleManager via event
            EventManager.Publish(GameConstants.Events.OnStageStart, floorData);
        }

        /// <summary>
        /// Returns the highest cleared floor.
        /// </summary>
        public int GetMaxFloor()
        {
            return _maxFloor;
        }

        /// <summary>
        /// Returns the floor currently being challenged.
        /// </summary>
        public int GetCurrentFloor()
        {
            return _currentFloor;
        }

        /// <summary>
        /// Returns floor configuration data, including enemy multiplier.
        /// Returns null if no chart data exists for the floor.
        /// </summary>
        /// <param name="floor">Floor number (1-based).</param>
        public TowerFloorData GetFloorData(int floor)
        {
            if (!DataManager.HasInstance) return null;

            TowerData chartData = DataManager.Instance.GetTowerData(floor);
            if (chartData == null) return null;

            float multiplier = CalculateEnemyMultiplier(floor, chartData.enemyMultiplier);

            return new TowerFloorData
            {
                floor = floor,
                enemyIds = chartData.enemyIds,
                enemyMultiplier = multiplier,
                rewards = chartData.rewards
            };
        }

        /// <summary>
        /// Returns true if the player has remaining daily tower attempts.
        /// Resets daily counter if the last attempt date has changed.
        /// </summary>
        public bool CanAttempt()
        {
            RefreshDailyAttemptsIfNeeded();
            return _dailyAttempts < MaxDailyAttempts;
        }

        #endregion

        #region Private Methods

        private void OnDataLoaded(object data)
        {
            if (!DataManager.HasInstance) return;

            UserTowerData userTower = DataManager.Instance.GetUserStageData() != null
                ? LoadUserTowerData()
                : null;

            if (userTower == null) return;

            _maxFloor = userTower.maxFloor;
            _currentFloor = userTower.currentFloor;
            _lastAttemptDate = userTower.lastAttemptAt;
            _dailyAttempts = LoadDailyAttempts();
        }

        private void OnStageComplete(object data)
        {
            // Only handle if we are in a tower battle context
            // TowerManager tracks context by _currentFloor > 0
            if (_currentFloor <= 0) return;

            int clearedFloor = _currentFloor;

            // Step 4: Update max floor
            if (clearedFloor > _maxFloor)
            {
                _maxFloor = clearedFloor;
            }

            // Grant tower coin reward: floor / 10 coins (minimum 1)
            int coinReward = Mathf.Max(1, clearedFloor / 10);
            if (CurrencyManager.HasInstance)
            {
                CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.TowerTicket, coinReward);
            }

            PersistTowerData();

            // Step 5: Notify
            EventManager.Publish(GameConstants.Events.OnTowerFloorComplete, clearedFloor);

            _currentFloor = 0;
        }

        private void OnStageFail(object data)
        {
            _currentFloor = 0;
        }

        private float CalculateEnemyMultiplier(int floor, float chartMultiplier)
        {
            // Tier 1: floors 1-100: 1 + floor * 0.05
            // Tier 2: floors 101-200: tier1_max * 1.5 additional
            // Beyond 200: repeating cycle with increasing weight

            if (floor <= FloorCycleSize)
            {
                return 1f + floor * BaseEnemyMultiplierPerFloor;
            }

            int cycle = (floor - 1) / FloorCycleSize;
            int floorInCycle = ((floor - 1) % FloorCycleSize) + 1;

            float baseMultiplier = 1f + floorInCycle * BaseEnemyMultiplierPerFloor;
            float cycleBonus = 1f + (cycle - 1) * (CycleMultiplierTier2 - 1f);

            return baseMultiplier * cycleBonus;
        }

        private TowerFloorData GenerateDefaultFloorData(int floor)
        {
            return new TowerFloorData
            {
                floor = floor,
                enemyIds = null,
                enemyMultiplier = CalculateEnemyMultiplier(floor, 1f),
                rewards = null
            };
        }

        private void RefreshDailyAttemptsIfNeeded()
        {
            string today = DateTime.UtcNow.ToString("yyyy-MM-dd");
            if (_lastAttemptDate != today)
            {
                _dailyAttempts = 0;
                _lastAttemptDate = today;
                PersistTowerData();
            }
        }

        private void PersistTowerData()
        {
            if (!DataManager.HasInstance) return;

            // UserTowerData is stored via SaveManager with a known key
            var towerData = new UserTowerData
            {
                maxFloor = _maxFloor,
                currentFloor = _currentFloor,
                lastAttemptAt = _lastAttemptDate
            };

            SaveManager.Instance?.Save("UserTower", towerData);
            SaveManager.Instance?.Save("TowerDailyAttempts", _dailyAttempts);
        }

        private UserTowerData LoadUserTowerData()
        {
            return SaveManager.HasInstance
                ? SaveManager.Instance.Load<UserTowerData>("UserTower")
                : new UserTowerData();
        }

        private int LoadDailyAttempts()
        {
            if (!SaveManager.HasInstance) return 0;

            int saved = SaveManager.Instance.Load<int>("TowerDailyAttempts");
            string today = DateTime.UtcNow.ToString("yyyy-MM-dd");

            if (_lastAttemptDate != today) return 0;
            return saved;
        }

        #endregion
    }

    /// <summary>
    /// Runtime floor data used to initialize a tower battle.
    /// </summary>
    [Serializable]
    public class TowerFloorData
    {
        /// <summary>Floor number.</summary>
        public int floor;
        /// <summary>Enemy IDs for this floor (may be null, BattleManager uses chart defaults).</summary>
        public System.Collections.Generic.List<string> enemyIds;
        /// <summary>Computed enemy stat multiplier for this floor.</summary>
        public float enemyMultiplier;
        /// <summary>Reward item IDs granted on floor clear.</summary>
        public System.Collections.Generic.List<string> rewards;
    }
}
