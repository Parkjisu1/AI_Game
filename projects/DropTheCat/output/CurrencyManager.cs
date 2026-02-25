using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Manages player coin balance with persistent save/load and event notification.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Generic | Role: Manager | Phase: 1
    /// </remarks>
    public class CurrencyManager : Singleton<CurrencyManager>
    {
        #region Constants

        private const string SAVE_KEY = "PlayerCoins";

        #endregion

        #region Fields

        private int _coins;

        #endregion

        #region Properties

        public int Coins => _coins;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            LoadBalance();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Adds coins to the player's balance. Amount must be positive.
        /// </summary>
        public void AddCoins(int amount)
        {
            if (amount <= 0)
            {
                Debug.LogWarning($"[CurrencyManager] AddCoins called with non-positive amount: {amount}");
                return;
            }

            _coins += amount;
            SaveBalance();
            PublishCoinChanged(amount);
        }

        /// <summary>
        /// Attempts to spend coins. Returns true if successful, false if insufficient balance.
        /// </summary>
        public bool SpendCoins(int amount)
        {
            if (amount <= 0)
            {
                Debug.LogWarning($"[CurrencyManager] SpendCoins called with non-positive amount: {amount}");
                return false;
            }

            if (!CanAfford(amount))
            {
                return false;
            }

            _coins -= amount;
            SaveBalance();
            PublishCoinChanged(-amount);

            return true;
        }

        /// <summary>
        /// Returns the current coin balance.
        /// </summary>
        public int GetBalance()
        {
            return _coins;
        }

        /// <summary>
        /// Checks whether the player can afford the given amount.
        /// </summary>
        public bool CanAfford(int amount)
        {
            return amount >= 0 && _coins >= amount;
        }

        #endregion

        #region Private Methods

        private void LoadBalance()
        {
            if (SaveManager.HasInstance)
            {
                _coins = SaveManager.Instance.LoadInt(SAVE_KEY, 0);
            }

            if (_coins < 0)
            {
                _coins = 0;
            }
        }

        private void SaveBalance()
        {
            if (SaveManager.HasInstance)
            {
                SaveManager.Instance.SaveInt(SAVE_KEY, _coins);
            }
        }

        private void PublishCoinChanged(int delta)
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnCoinChanged
                {
                    Balance = _coins,
                    Delta = delta
                });
            }
        }

        #endregion
    }
}
