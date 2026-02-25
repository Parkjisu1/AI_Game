using System;
using System.Collections.Generic;
using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Manages booster items: inventory, usage limits per level, purchasing, and effect delegation.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Manager | Phase: 2
    /// BoosterType enum is defined in EventManager.cs (Core): Hint, Undo, Magnet, Shuffle
    /// </remarks>
    public class BoosterManager : Singleton<BoosterManager>
    {
        #region Constants

        private const string SAVE_KEY = "BoosterCounts";
        private const int DEFAULT_MAX_USAGE_PER_LEVEL = 1;

        #endregion

        #region Fields

        [SerializeField] private int hintCost = 500;
        [SerializeField] private int undoCost = 300;
        [SerializeField] private int magnetCost = 800;
        [SerializeField] private int shuffleCost = 600;

        [SerializeField] private int maxUsagePerLevel = DEFAULT_MAX_USAGE_PER_LEVEL;

        private Dictionary<BoosterType, int> _boosterCounts = new Dictionary<BoosterType, int>();
        private Dictionary<BoosterType, int> _levelUsageCounts = new Dictionary<BoosterType, int>();
        private Dictionary<BoosterType, int> _boosterCosts;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            InitCosts();
            InitCountDictionaries();
            LoadBoosterCounts();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Attempts to use a booster. Checks inventory and level usage limit.
        /// Returns true if the booster was consumed, false otherwise.
        /// Actual booster effect should be handled by the subscribing system (GridManager, etc.).
        /// </summary>
        public bool UseBooster(BoosterType boosterType)
        {
            if (!CanUseBooster(boosterType))
            {
                return false;
            }

            _boosterCounts[boosterType]--;
            _levelUsageCounts[boosterType]++;

            SaveBoosterCounts();

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnBoosterUsed
                {
                    BoosterType = boosterType
                });

                EventManager.Instance.Publish(new OnBoosterCountChanged
                {
                    BoosterType = boosterType,
                    Count = _boosterCounts[boosterType]
                });
            }

            return true;
        }

        /// <summary>
        /// Checks if a booster can be used: has inventory and hasn't exceeded level usage limit.
        /// </summary>
        public bool CanUseBooster(BoosterType boosterType)
        {
            if (!_boosterCounts.ContainsKey(boosterType)) return false;

            if (_boosterCounts[boosterType] <= 0) return false;

            if (_levelUsageCounts.TryGetValue(boosterType, out int used) && used >= maxUsagePerLevel)
            {
                return false;
            }

            return true;
        }

        /// <summary>
        /// Returns the current inventory count for the specified booster.
        /// </summary>
        public int GetBoosterCount(BoosterType boosterType)
        {
            if (_boosterCounts.TryGetValue(boosterType, out int count))
            {
                return count;
            }
            return 0;
        }

        /// <summary>
        /// Adds boosters to inventory. Count must be positive.
        /// </summary>
        public void AddBooster(BoosterType boosterType, int count)
        {
            if (count <= 0)
            {
                Debug.LogWarning($"[BoosterManager] AddBooster called with non-positive count: {count}");
                return;
            }

            if (!_boosterCounts.ContainsKey(boosterType))
            {
                _boosterCounts[boosterType] = 0;
            }

            _boosterCounts[boosterType] += count;
            SaveBoosterCounts();

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnBoosterCountChanged
                {
                    BoosterType = boosterType,
                    Count = _boosterCounts[boosterType]
                });
            }
        }

        /// <summary>
        /// Purchases a booster using coins from CurrencyManager.
        /// Returns true if purchase succeeded, false if insufficient coins.
        /// </summary>
        public bool PurchaseBooster(BoosterType boosterType)
        {
            if (!_boosterCosts.TryGetValue(boosterType, out int cost))
            {
                Debug.LogWarning($"[BoosterManager] No cost defined for booster: {boosterType}");
                return false;
            }

            if (!CurrencyManager.HasInstance)
            {
                Debug.LogError("[BoosterManager] CurrencyManager is not available.");
                return false;
            }

            if (!CurrencyManager.Instance.SpendCoins(cost))
            {
                return false;
            }

            AddBooster(boosterType, 1);
            return true;
        }

        /// <summary>
        /// Resets per-level usage counts. Call this at the start of each level.
        /// </summary>
        public void ResetLevelUsage()
        {
            _levelUsageCounts.Clear();
            foreach (BoosterType type in Enum.GetValues(typeof(BoosterType)))
            {
                _levelUsageCounts[type] = 0;
            }
        }

        /// <summary>
        /// Returns the coin cost for the specified booster type.
        /// </summary>
        public int GetBoosterCost(BoosterType boosterType)
        {
            if (_boosterCosts.TryGetValue(boosterType, out int cost))
            {
                return cost;
            }
            return 0;
        }

        #endregion

        #region Private Methods

        private void InitCosts()
        {
            _boosterCosts = new Dictionary<BoosterType, int>
            {
                { BoosterType.Hint, hintCost },
                { BoosterType.Undo, undoCost },
                { BoosterType.Magnet, magnetCost },
                { BoosterType.Shuffle, shuffleCost }
            };
        }

        private void InitCountDictionaries()
        {
            foreach (BoosterType type in Enum.GetValues(typeof(BoosterType)))
            {
                if (!_boosterCounts.ContainsKey(type))
                {
                    _boosterCounts[type] = 0;
                }
                if (!_levelUsageCounts.ContainsKey(type))
                {
                    _levelUsageCounts[type] = 0;
                }
            }
        }

        private void LoadBoosterCounts()
        {
            if (!SaveManager.HasInstance) return;

            var savedData = SaveManager.Instance.Load<BoosterSaveData>(SAVE_KEY);
            if (savedData != null && savedData.types != null && savedData.counts != null)
            {
                int count = Mathf.Min(savedData.types.Length, savedData.counts.Length);
                for (int i = 0; i < count; i++)
                {
                    BoosterType type = (BoosterType)savedData.types[i];
                    _boosterCounts[type] = Mathf.Max(0, savedData.counts[i]);
                }
            }
        }

        private void SaveBoosterCounts()
        {
            if (!SaveManager.HasInstance) return;

            var saveData = new BoosterSaveData();
            int count = _boosterCounts.Count;
            saveData.types = new int[count];
            saveData.counts = new int[count];

            int index = 0;
            foreach (var kvp in _boosterCounts)
            {
                saveData.types[index] = (int)kvp.Key;
                saveData.counts[index] = kvp.Value;
                index++;
            }

            SaveManager.Instance.Save(SAVE_KEY, saveData);
        }

        #endregion

        #region Save Data

        /// <summary>
        /// Serializable save data for booster inventory.
        /// Uses parallel arrays because JsonUtility does not support Dictionary.
        /// Enum values stored as int for serialization compatibility.
        /// </summary>
        [Serializable]
        private class BoosterSaveData
        {
            public int[] types;
            public int[] counts;
        }

        #endregion
    }
}
