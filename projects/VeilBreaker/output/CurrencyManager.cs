using System;
using System.Collections.Generic;
using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.Economy
{
    /// <summary>
    /// Manages all in-game currencies (Gold, Gem, Tickets, etc.).
    /// Provides atomic add/spend operations with balance validation and event notification.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 1
    /// System: Economy
    /// </remarks>
    public class CurrencyManager : Singleton<CurrencyManager>
    {
        #region Fields

        private Dictionary<GameConstants.CurrencyType, long> _balances = new();

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            InitializeBalances();
            EventManager.Subscribe(GameConstants.Events.OnDataLoaded, OnDataLoaded);
        }

        protected override void OnDestroy()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnDataLoaded, OnDataLoaded);
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Adds the specified amount to the given currency type.
        /// Amount must be positive. Fires OnCurrencyChanged after update.
        /// </summary>
        /// <param name="type">The currency type to add to.</param>
        /// <param name="amount">Amount to add (must be > 0).</param>
        public void AddCurrency(GameConstants.CurrencyType type, long amount)
        {
            if (amount <= 0)
            {
                Debug.LogWarning($"[CurrencyManager] AddCurrency called with invalid amount: {amount} for {type}");
                return;
            }

            if (!_balances.ContainsKey(type))
            {
                _balances[type] = 0;
            }

            _balances[type] += amount;
            SaveBalance();
            PublishCurrencyChanged(type);
        }

        /// <summary>
        /// Attempts to spend the specified amount from the given currency type.
        /// Returns false if balance is insufficient.
        /// </summary>
        /// <param name="type">The currency type to spend from.</param>
        /// <param name="amount">Amount to spend (must be > 0).</param>
        /// <returns>True if spend was successful; false if insufficient balance.</returns>
        public bool SpendCurrency(GameConstants.CurrencyType type, long amount)
        {
            if (amount <= 0)
            {
                Debug.LogWarning($"[CurrencyManager] SpendCurrency called with invalid amount: {amount} for {type}");
                return false;
            }

            if (!HasEnough(type, amount))
            {
                Debug.Log($"[CurrencyManager] Insufficient {type}: need {amount}, have {GetBalance(type)}");
                return false;
            }

            _balances[type] -= amount;
            SaveBalance();
            PublishCurrencyChanged(type);
            return true;
        }

        /// <summary>
        /// Returns true if the current balance for the given type is >= amount.
        /// </summary>
        /// <param name="type">The currency type to check.</param>
        /// <param name="amount">The required amount.</param>
        public bool HasEnough(GameConstants.CurrencyType type, long amount)
        {
            return GetBalance(type) >= amount;
        }

        /// <summary>
        /// Returns the current balance for the given currency type.
        /// Returns 0 if no balance entry exists.
        /// </summary>
        /// <param name="type">The currency type to query.</param>
        public long GetBalance(GameConstants.CurrencyType type)
        {
            return _balances.TryGetValue(type, out var balance) ? balance : 0;
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Initializes all currency balances to zero.
        /// </summary>
        private void InitializeBalances()
        {
            _balances.Clear();
            foreach (GameConstants.CurrencyType type in Enum.GetValues(typeof(GameConstants.CurrencyType)))
            {
                _balances[type] = 0;
            }
        }

        /// <summary>
        /// Called when DataManager finishes loading user data.
        /// Syncs balances from UserCurrency loaded by DataManager.
        /// </summary>
        private void OnDataLoaded(object data)
        {
            LoadFromDataManager();
        }

        /// <summary>
        /// Loads currency balances from DataManager's UserCurrency record.
        /// Falls back to zero if DataManager is not ready.
        /// </summary>
        private void LoadFromDataManager()
        {
            if (!DataManager.HasInstance)
            {
                Debug.LogWarning("[CurrencyManager] DataManager not available. Starting with zero balances.");
                return;
            }

            var userCurrency = DataManager.Instance.GetUserCurrency();
            if (userCurrency == null)
            {
                Debug.LogWarning("[CurrencyManager] GetUserCurrency returned null. Starting with zero balances.");
                return;
            }

            _balances[GameConstants.CurrencyType.Gold] = userCurrency.Gold;
            _balances[GameConstants.CurrencyType.Gem] = userCurrency.Gem;
            _balances[GameConstants.CurrencyType.StageTicket] = userCurrency.StageTicket;
            _balances[GameConstants.CurrencyType.DungeonTicket] = userCurrency.DungeonTicket;
            _balances[GameConstants.CurrencyType.TowerTicket] = userCurrency.TowerTicket;

            Debug.Log("[CurrencyManager] Balances loaded from DataManager.");
        }

        /// <summary>
        /// Persists current balances to DataManager and triggers a save via SaveManager.
        /// </summary>
        private void SaveBalance()
        {
            if (!DataManager.HasInstance) return;

            var userCurrency = DataManager.Instance.GetUserCurrency();
            if (userCurrency == null) return;

            userCurrency.Gold = _balances[GameConstants.CurrencyType.Gold];
            userCurrency.Gem = _balances[GameConstants.CurrencyType.Gem];
            userCurrency.StageTicket = _balances[GameConstants.CurrencyType.StageTicket];
            userCurrency.DungeonTicket = _balances[GameConstants.CurrencyType.DungeonTicket];
            userCurrency.TowerTicket = _balances[GameConstants.CurrencyType.TowerTicket];

            DataManager.Instance.UpdateUserCurrency(userCurrency);
        }

        /// <summary>
        /// Publishes OnCurrencyChanged event with the changed currency type as payload.
        /// </summary>
        private void PublishCurrencyChanged(GameConstants.CurrencyType type)
        {
            EventManager.Publish(GameConstants.Events.OnCurrencyChanged, type);
        }

        #endregion
    }
}
