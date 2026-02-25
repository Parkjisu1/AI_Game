#if UNITY_IAP
using UnityEngine.Purchasing;
using UnityEngine.Purchasing.Extension;
#endif
using System;
using UnityEngine;
using BlockBlast.Core;

namespace BlockBlast.SDK
{
#if UNITY_IAP
    public class IAPManager : Singleton<IAPManager>, IDetailedStoreListener
    {
        private IStoreController _storeController;
        private IExtensionProvider _extensionProvider;
        private Action<bool> _purchaseCallback;

        // Product IDs
        public const string PRODUCT_REMOVE_ADS = "remove_ads";
        public const string PRODUCT_UNDO_PACK_5 = "undo_pack_5";

        protected override void Awake()
        {
            base.Awake();
            InitializePurchasing();
        }

        private void InitializePurchasing()
        {
            var builder = ConfigurationBuilder.Instance(StandardPurchasingModule.Instance());
            builder.AddProduct(PRODUCT_REMOVE_ADS, ProductType.NonConsumable);
            builder.AddProduct(PRODUCT_UNDO_PACK_5, ProductType.Consumable);
            UnityPurchasing.Initialize(this, builder);
        }

        public bool IsInitialized => _storeController != null && _extensionProvider != null;

        public void BuyProduct(string productId)
        {
            BuyProduct(productId, null);
        }

        public void BuyProduct(string productId, Action<bool> callback)
        {
            _purchaseCallback = callback;

            if (!IsInitialized)
            {
                Debug.LogError("[IAP] Not initialized");
                _purchaseCallback?.Invoke(false);
                _purchaseCallback = null;
                return;
            }

            var product = _storeController.products.WithID(productId);
            if (product != null && product.availableToPurchase)
            {
                _storeController.InitiatePurchase(product);
            }
            else
            {
                Debug.LogError($"[IAP] Product not available: {productId}");
                _purchaseCallback?.Invoke(false);
                _purchaseCallback = null;
            }
        }

        public string GetLocalizedPrice(string productId)
        {
            if (!IsInitialized) return "";
            var product = _storeController.products.WithID(productId);
            return product?.metadata.localizedPriceString ?? "";
        }

        // IStoreListener
        public void OnInitialized(IStoreController controller, IExtensionProvider extensions)
        {
            _storeController = controller;
            _extensionProvider = extensions;
            Debug.Log("[IAP] Initialized successfully");

            // Restore non-consumable purchases
            var removeAds = _storeController.products.WithID(PRODUCT_REMOVE_ADS);
            if (removeAds != null && removeAds.hasReceipt)
            {
                SaveManager.Instance.SetAdsRemoved();
            }
        }

        public void OnInitializeFailed(InitializationFailureReason error)
        {
            Debug.LogError($"[IAP] Init failed: {error}");
        }

        public void OnInitializeFailed(InitializationFailureReason error, string message)
        {
            Debug.LogError($"[IAP] Init failed: {error} - {message}");
        }

        public PurchaseProcessingResult ProcessPurchase(PurchaseEventArgs args)
        {
            var productId = args.purchasedProduct.definition.id;
            Debug.Log($"[IAP] Purchase complete: {productId}");

            if (productId == PRODUCT_REMOVE_ADS)
            {
                SaveManager.Instance.SetAdsRemoved();
            }
            else if (productId == PRODUCT_UNDO_PACK_5)
            {
                // Add undo uses
                int current = SaveManager.Instance.LoadInt("UndoCount", 0);
                SaveManager.Instance.SaveInt("UndoCount", current + 5);
            }

            _purchaseCallback?.Invoke(true);
            _purchaseCallback = null;
            return PurchaseProcessingResult.Complete;
        }

        public void OnPurchaseFailed(Product product, PurchaseFailureReason reason)
        {
            Debug.LogError($"[IAP] Purchase failed: {product.definition.id} - {reason}");
            _purchaseCallback?.Invoke(false);
            _purchaseCallback = null;
        }

        public void OnPurchaseFailed(Product product, PurchaseFailureDescription failureDescription)
        {
            Debug.LogError($"[IAP] Purchase failed: {product.definition.id} - {failureDescription.message}");
            _purchaseCallback?.Invoke(false);
            _purchaseCallback = null;
        }
    }
#else
    // ===== Simulation Mode =====
    public class IAPManager : Singleton<IAPManager>
    {
        public const string PRODUCT_REMOVE_ADS = "remove_ads";
        public const string PRODUCT_UNDO_PACK_5 = "undo_pack_5";

        protected override void Awake()
        {
            base.Awake();
            Debug.Log("[IAP Sim] Initialized (simulation mode)");
        }

        public bool IsInitialized => true;

        public void BuyProduct(string productId)
        {
            BuyProduct(productId, null);
        }

        public void BuyProduct(string productId, Action<bool> callback)
        {
            Debug.Log($"[IAP Sim] Purchase: {productId}");

            if (productId == PRODUCT_REMOVE_ADS)
            {
                SaveManager.Instance.SetAdsRemoved();
            }
            else if (productId == PRODUCT_UNDO_PACK_5)
            {
                int current = SaveManager.Instance.LoadInt("UndoCount", 0);
                SaveManager.Instance.SaveInt("UndoCount", current + 5);
            }

            callback?.Invoke(true);
        }

        public string GetLocalizedPrice(string productId)
        {
            return "$0.99";
        }
    }
#endif
}
