using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Singleton manager for in-game currencies (coins and gems).
    /// Persists via SaveManager and fires CurrencyChangedSignal on changes.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Manager
    /// Phase: 1
    /// </remarks>
    public class CurrencyManager : Singleton<CurrencyManager>
    {
        #region Fields

        private const string SAVE_KEY_COINS = "Currency_Coins";
        private const string SAVE_KEY_GEMS = "Currency_Gems";
        private const int DEFAULT_STARTING_COINS = 100;
        private const int DEFAULT_STARTING_GEMS = 5;

        private int _coins;
        private int _gems;
        private SignalBus _signalBus;

        #endregion

        #region Properties

        /// <summary>Current coin balance.</summary>
        public int Coins => _coins;

        /// <summary>Current gem balance.</summary>
        public int Gems => _gems;

        #endregion

        #region Singleton Lifecycle

        protected override void OnSingletonAwake()
        {
            if (ProjectContext.HasInstance)
            {
                _signalBus = ProjectContext.Instance.Resolve<SignalBus>();
            }

            LoadCurrency();
        }

        #endregion

        #region Public Methods - Coins

        /// <summary>
        /// Adds coins to the balance.
        /// </summary>
        /// <param name="amount">Amount to add (must be positive).</param>
        public void AddCoins(int amount)
        {
            if (amount <= 0)
            {
                Debug.LogWarning("[CurrencyManager] AddCoins amount must be positive.");
                return;
            }

            int oldAmount = _coins;
            _coins += amount;
            SaveCurrency();
            FireCurrencyChanged("Coins", oldAmount, _coins);
        }

        /// <summary>
        /// Spends coins if sufficient balance exists.
        /// </summary>
        /// <param name="amount">Amount to spend (must be positive).</param>
        /// <returns>True if the transaction succeeded.</returns>
        public bool SpendCoins(int amount)
        {
            if (amount <= 0)
            {
                Debug.LogWarning("[CurrencyManager] SpendCoins amount must be positive.");
                return false;
            }

            if (_coins < amount)
            {
                Debug.Log($"[CurrencyManager] Insufficient coins. Have: {_coins}, Need: {amount}.");
                return false;
            }

            int oldAmount = _coins;
            _coins -= amount;
            SaveCurrency();
            FireCurrencyChanged("Coins", oldAmount, _coins);
            return true;
        }

        /// <summary>
        /// Returns the current coin balance.
        /// </summary>
        public int GetCoins()
        {
            return _coins;
        }

        /// <summary>
        /// Checks if the player has at least the specified number of coins.
        /// </summary>
        /// <param name="amount">Amount to check.</param>
        public bool HasEnoughCoins(int amount)
        {
            return _coins >= amount;
        }

        #endregion

        #region Public Methods - Gems

        /// <summary>
        /// Adds gems to the balance.
        /// </summary>
        /// <param name="amount">Amount to add (must be positive).</param>
        public void AddGems(int amount)
        {
            if (amount <= 0)
            {
                Debug.LogWarning("[CurrencyManager] AddGems amount must be positive.");
                return;
            }

            int oldAmount = _gems;
            _gems += amount;
            SaveCurrency();
            FireCurrencyChanged("Gems", oldAmount, _gems);
        }

        /// <summary>
        /// Spends gems if sufficient balance exists.
        /// </summary>
        /// <param name="amount">Amount to spend (must be positive).</param>
        /// <returns>True if the transaction succeeded.</returns>
        public bool SpendGems(int amount)
        {
            if (amount <= 0)
            {
                Debug.LogWarning("[CurrencyManager] SpendGems amount must be positive.");
                return false;
            }

            if (_gems < amount)
            {
                Debug.Log($"[CurrencyManager] Insufficient gems. Have: {_gems}, Need: {amount}.");
                return false;
            }

            int oldAmount = _gems;
            _gems -= amount;
            SaveCurrency();
            FireCurrencyChanged("Gems", oldAmount, _gems);
            return true;
        }

        /// <summary>
        /// Returns the current gem balance.
        /// </summary>
        public int GetGems()
        {
            return _gems;
        }

        /// <summary>
        /// Checks if the player has at least the specified number of gems.
        /// </summary>
        /// <param name="amount">Amount to check.</param>
        public bool HasEnoughGems(int amount)
        {
            return _gems >= amount;
        }

        #endregion

        #region Private Methods

        private void LoadCurrency()
        {
            if (!SaveManager.HasInstance)
            {
                _coins = DEFAULT_STARTING_COINS;
                _gems = DEFAULT_STARTING_GEMS;
                return;
            }

            _coins = SaveManager.Instance.LoadInt(SAVE_KEY_COINS, DEFAULT_STARTING_COINS);
            _gems = SaveManager.Instance.LoadInt(SAVE_KEY_GEMS, DEFAULT_STARTING_GEMS);
        }

        private void SaveCurrency()
        {
            if (!SaveManager.HasInstance)
            {
                return;
            }

            SaveManager.Instance.SaveInt(SAVE_KEY_COINS, _coins);
            SaveManager.Instance.SaveInt(SAVE_KEY_GEMS, _gems);
        }

        private void FireCurrencyChanged(string currencyId, int oldAmount, int newAmount)
        {
            if (_signalBus == null)
            {
                return;
            }

            _signalBus.Fire(new CurrencyChangedSignal
            {
                CurrencyId = currencyId,
                OldAmount = oldAmount,
                NewAmount = newAmount
            });
        }

        #endregion
    }
}
