using UnityEngine;
using UnityEngine.UI;
using TMPro;
using VeilBreaker.Core;
using VeilBreaker.Economy;
using VeilBreaker.SDK;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Shop popup with three tabs: Currency purchases, IAP products, and ad rewards.
    /// Product IDs are loaded from ShopTable via DataManager (no hardcoding).
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// Phase: 3
    /// System: UI
    /// </remarks>
    public class PopupShop : PopupBase
    {
        #region Fields

        [SerializeField] private Toggle[]           _tabToggles;        // 0=Currency, 1=IAP, 2=AdReward
        [SerializeField] private GameObject[]       _tabPanels;         // matched index to _tabToggles

        [SerializeField] private Transform          _shopItemContent;
        [SerializeField] private GameObject         _shopItemPrefab;

        [SerializeField] private Button             _adRewardButton;
        [SerializeField] private Button             _closeButton;

        [SerializeField] private TextMeshProUGUI    _goldText;
        [SerializeField] private TextMeshProUGUI    _gemText;

        #endregion

        #region PopupBase Overrides

        /// <summary>
        /// Opens shop popup, initialises tab toggles, and refreshes currency display.
        /// </summary>
        public override void Open(object data = null)
        {
            SetupTabs();
            RefreshCurrencyDisplay();
            ShowTab(0);

            _adRewardButton?.onClick.RemoveAllListeners();
            _adRewardButton?.onClick.AddListener(OnAdRewardButton);

            _closeButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.AddListener(CloseThis);

            EventManager.Subscribe(GameConstants.Events.OnCurrencyChanged, OnCurrencyChanged);
            EventManager.Subscribe(GameConstants.Events.OnIAPPurchased,    OnIAPPurchased);
            EventManager.Subscribe(GameConstants.Events.OnAdWatched,       OnAdWatched);
        }

        /// <summary>
        /// Closes shop and unsubscribes events.
        /// </summary>
        public override void Close()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnCurrencyChanged, OnCurrencyChanged);
            EventManager.Unsubscribe(GameConstants.Events.OnIAPPurchased,    OnIAPPurchased);
            EventManager.Unsubscribe(GameConstants.Events.OnAdWatched,       OnAdWatched);

            _adRewardButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.RemoveAllListeners();

            if (_tabToggles != null)
                foreach (var t in _tabToggles)
                    t?.onValueChanged.RemoveAllListeners();
        }

        #endregion

        #region Private Methods

        private void SetupTabs()
        {
            if (_tabToggles == null) return;
            for (int i = 0; i < _tabToggles.Length; i++)
            {
                int tabIndex = i;
                _tabToggles[i]?.onValueChanged.RemoveAllListeners();
                _tabToggles[i]?.onValueChanged.AddListener(on =>
                {
                    if (on) ShowTab(tabIndex);
                });
            }
        }

        private void ShowTab(int index)
        {
            if (_tabPanels != null)
            {
                for (int i = 0; i < _tabPanels.Length; i++)
                    _tabPanels[i]?.SetActive(i == index);
            }

            if (_tabToggles != null && index < _tabToggles.Length && _tabToggles[index] != null)
                _tabToggles[index].isOn = true;

            // Populate content for selected tab
            switch (index)
            {
                case 0: PopulateShopItems("currency"); break;
                case 1: PopulateShopItems("iap");      break;
                case 2: /* ad reward tab - static layout */ break;
            }
        }

        private void PopulateShopItems(string category)
        {
            if (_shopItemContent == null || _shopItemPrefab == null) return;

            // Clear existing items
            for (int i = _shopItemContent.childCount - 1; i >= 0; i--)
                Destroy(_shopItemContent.GetChild(i).gameObject);

            if (!DataManager.HasInstance) return;

            var shopItems = DataManager.Instance.GetShopItems(category);
            if (shopItems == null) return;

            foreach (var item in shopItems)
            {
                var go = Instantiate(_shopItemPrefab, _shopItemContent);
                var row = go.GetComponent<ShopItemRowView>();
                row?.Bind(item, OnShopItemPurchase);
            }
        }

        private void OnShopItemPurchase(ShopItemData item)
        {
            if (item == null) return;

            switch (item.purchaseType)
            {
                case "iap":
                    if (IAPManager.HasInstance)
                        IAPManager.Instance.Purchase(item.productId);
                    break;

                case "gold":
                    if (CurrencyManager.HasInstance)
                        CurrencyManager.Instance.SpendCurrency(GameConstants.CurrencyType.Gold, item.price);
                    break;

                case "gem":
                    if (CurrencyManager.HasInstance)
                        CurrencyManager.Instance.SpendCurrency(GameConstants.CurrencyType.Gem, item.price);
                    break;
            }
        }

        private void OnAdRewardButton()
        {
            if (AdMobManager.HasInstance)
                AdMobManager.Instance.ShowRewardedAd(OnAdRewardComplete);
        }

        private void OnAdRewardComplete()
        {
            Debug.Log("[PopupShop] Ad reward granted.");
            RefreshCurrencyDisplay();
        }

        private void RefreshCurrencyDisplay()
        {
            if (!CurrencyManager.HasInstance) return;
            var cm = CurrencyManager.Instance;

            if (_goldText != null)
                _goldText.text = cm.GetBalance(GameConstants.CurrencyType.Gold).ToString("N0");
            if (_gemText != null)
                _gemText.text  = cm.GetBalance(GameConstants.CurrencyType.Gem).ToString("N0");
        }

        private void OnCurrencyChanged(object data)
        {
            RefreshCurrencyDisplay();
        }

        private void OnIAPPurchased(object data)
        {
            RefreshCurrencyDisplay();
        }

        private void OnAdWatched(object data)
        {
            RefreshCurrencyDisplay();
        }

        #endregion
    }

    /// <summary>
    /// View component for a single shop item row.
    /// </summary>
    public class ShopItemRowView : MonoBehaviour
    {
        [SerializeField] private TextMeshProUGUI _itemNameText;
        [SerializeField] private TextMeshProUGUI _priceText;
        [SerializeField] private Button          _buyButton;

        private System.Action<ShopItemData> _onPurchase;
        private ShopItemData _item;

        /// <summary>Binds shop item data and purchase callback.</summary>
        public void Bind(ShopItemData item, System.Action<ShopItemData> onPurchase)
        {
            _item       = item;
            _onPurchase = onPurchase;

            if (_itemNameText != null) _itemNameText.text = item?.name ?? string.Empty;
            if (_priceText    != null) _priceText.text    = item?.price.ToString("N0") ?? "0";

            _buyButton?.onClick.RemoveAllListeners();
            _buyButton?.onClick.AddListener(() => _onPurchase?.Invoke(_item));
        }
    }

    /// <summary>
    /// Shop product chart data model.
    /// </summary>
    [System.Serializable]
    public class ShopItemData
    {
        public string productId;
        public string name;
        public string purchaseType; // "iap" | "gold" | "gem"
        public long   price;
        public string rewardType;
        public long   rewardAmount;
    }
}
