using System;
using UnityEngine;
using UnityEngine.UI;
using DropTheCat.Core;
using DropTheCat.Domain;

#if UNITY_IAP
using UnityEngine.Purchasing;
#endif

namespace DropTheCat.Game
{
    /// <summary>
    /// Shop popup for purchasing coin packs, booster packs, and removing ads via IAP.
    /// </summary>
    /// <remarks>
    /// Layer: Game | Genre: Puzzle | Role: Handler | Phase: 3
    /// IAP logic uses #if UNITY_IAP conditional compilation with simulation fallback.
    /// </remarks>
    public class ShopPopup : MonoBehaviour
    {
        #region Constants

        private static readonly int[] COIN_PACK_AMOUNTS = { 500, 2000, 5000 };
        private const string REMOVE_ADS_KEY = "RemoveAds";

        #endregion

        #region Fields

        [Header("Coin Packs")]
        [SerializeField] private Button[] coinPackButtons;

        [Header("Booster Pack")]
        [SerializeField] private Button boosterPackBtn;
        [SerializeField] private int boosterPackQuantity = 3;

        [Header("Other")]
        [SerializeField] private Button removeAdsBtn;
        [SerializeField] private Button restoreBtn;
        [SerializeField] private Button closeBtn;

        [Header("Display")]
        [SerializeField] private Text balanceText;
        [SerializeField] private GameObject popupRoot;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            if (closeBtn != null)
            {
                closeBtn.onClick.AddListener(Hide);
            }

            if (boosterPackBtn != null)
            {
                boosterPackBtn.onClick.AddListener(OnPurchaseBoosterPack);
            }

            if (removeAdsBtn != null)
            {
                removeAdsBtn.onClick.AddListener(OnRemoveAds);
            }

            if (restoreBtn != null)
            {
                restoreBtn.onClick.AddListener(OnRestorePurchases);
            }

            SetupCoinPackButtons();
        }

        private void OnEnable()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Subscribe<OnCoinChanged>(HandleCoinChanged);
            }
        }

        private void OnDisable()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Unsubscribe<OnCoinChanged>(HandleCoinChanged);
            }
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Shows the shop popup and refreshes the UI.
        /// </summary>
        public void Show()
        {
            if (popupRoot != null)
            {
                popupRoot.SetActive(true);
            }
            else
            {
                gameObject.SetActive(true);
            }

            RefreshUI();
        }

        /// <summary>
        /// Hides the shop popup.
        /// </summary>
        public void Hide()
        {
            if (popupRoot != null)
            {
                popupRoot.SetActive(false);
            }
            else
            {
                gameObject.SetActive(false);
            }
        }

        /// <summary>
        /// Handles purchasing a coin pack by index.
        /// </summary>
        public void OnPurchaseCoinPack(int packIndex)
        {
            if (packIndex < 0 || packIndex >= COIN_PACK_AMOUNTS.Length)
            {
                Debug.LogWarning($"[ShopPopup] Invalid coin pack index: {packIndex}");
                return;
            }

            int amount = COIN_PACK_AMOUNTS[packIndex];

#if UNITY_IAP
            // IAP purchase flow - product ID mapped to pack index
            string productId = $"com.game.coinpack_{packIndex}";
            Debug.Log($"[ShopPopup] Initiating IAP purchase: {productId}");
            // IAPManager handles the actual purchase and calls back on success
            // On successful callback: GrantCoinPack(packIndex);
#else
            // Simulation mode: grant coins directly for testing
            Debug.Log($"[ShopPopup] [IAP Sim] Purchasing coin pack {packIndex}: {amount} coins");
            GrantCoinPack(packIndex);
#endif
        }

        /// <summary>
        /// Handles purchasing the booster pack.
        /// </summary>
        public void OnPurchaseBoosterPack()
        {
#if UNITY_IAP
            string productId = "com.game.boosterpack";
            Debug.Log($"[ShopPopup] Initiating IAP purchase: {productId}");
            // IAPManager handles the actual purchase and calls back on success
            // On successful callback: GrantBoosterPack();
#else
            // Simulation mode: grant boosters directly for testing
            Debug.Log("[ShopPopup] [IAP Sim] Purchasing booster pack");
            GrantBoosterPack();
#endif
        }

        /// <summary>
        /// Handles the remove ads purchase.
        /// </summary>
        public void OnRemoveAds()
        {
#if UNITY_IAP
            string productId = "com.game.removeads";
            Debug.Log($"[ShopPopup] Initiating IAP purchase: {productId}");
            // IAPManager handles the actual purchase and calls back on success
            // On successful callback: GrantRemoveAds();
#else
            // Simulation mode
            Debug.Log("[ShopPopup] [IAP Sim] Removing ads");
            GrantRemoveAds();
#endif
        }

        /// <summary>
        /// Restores previous IAP purchases.
        /// </summary>
        public void OnRestorePurchases()
        {
#if UNITY_IAP
            Debug.Log("[ShopPopup] Restoring purchases...");
            // IAPManager.Instance.RestorePurchases();
#else
            Debug.Log("[ShopPopup] [IAP Sim] Restore purchases (no-op in simulation)");
#endif
        }

        /// <summary>
        /// Refreshes all UI elements to reflect current state.
        /// </summary>
        public void RefreshUI()
        {
            UpdateBalanceDisplay();
            UpdateRemoveAdsButton();
        }

        #endregion

        #region Private Methods

        private void SetupCoinPackButtons()
        {
            if (coinPackButtons == null) return;

            for (int i = 0; i < coinPackButtons.Length; i++)
            {
                if (coinPackButtons[i] == null) continue;

                int index = i;
                coinPackButtons[i].onClick.AddListener(() => OnPurchaseCoinPack(index));
            }
        }

        private void HandleCoinChanged(OnCoinChanged eventData)
        {
            UpdateBalanceDisplay();
        }

        private void UpdateBalanceDisplay()
        {
            if (balanceText == null) return;

            if (CurrencyManager.HasInstance)
            {
                balanceText.text = CurrencyManager.Instance.GetBalance().ToString("N0");
            }
        }

        private void UpdateRemoveAdsButton()
        {
            if (removeAdsBtn == null) return;

            bool adsRemoved = PlayerPrefs.GetInt(REMOVE_ADS_KEY, 0) == 1;
            removeAdsBtn.interactable = !adsRemoved;
        }

        /// <summary>
        /// Called on successful coin pack purchase.
        /// </summary>
        public void GrantCoinPack(int packIndex)
        {
            if (packIndex < 0 || packIndex >= COIN_PACK_AMOUNTS.Length) return;

            int amount = COIN_PACK_AMOUNTS[packIndex];

            if (CurrencyManager.HasInstance)
            {
                CurrencyManager.Instance.AddCoins(amount);
            }

            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlaySFX("purchase_success");
            }
        }

        /// <summary>
        /// Called on successful booster pack purchase.
        /// </summary>
        public void GrantBoosterPack()
        {
            if (!BoosterManager.HasInstance) return;

            BoosterManager.Instance.AddBooster(BoosterType.Hint, boosterPackQuantity);
            BoosterManager.Instance.AddBooster(BoosterType.Undo, boosterPackQuantity);
            BoosterManager.Instance.AddBooster(BoosterType.Magnet, boosterPackQuantity);
            BoosterManager.Instance.AddBooster(BoosterType.Shuffle, boosterPackQuantity);

            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlaySFX("purchase_success");
            }
        }

        /// <summary>
        /// Called on successful remove ads purchase.
        /// </summary>
        public void GrantRemoveAds()
        {
            PlayerPrefs.SetInt(REMOVE_ADS_KEY, 1);
            PlayerPrefs.Save();
            UpdateRemoveAdsButton();

            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlaySFX("purchase_success");
            }
        }

        #endregion
    }
}
