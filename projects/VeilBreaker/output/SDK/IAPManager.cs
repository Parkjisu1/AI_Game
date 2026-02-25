#if UNITY_IAP
using UnityEngine.Purchasing;
using UnityEngine.Purchasing.Security;
#endif

using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.SDK
{
    /// <summary>
    /// Unity IAP wrapper with conditional compilation.
    /// When UNITY_IAP symbol is defined, uses real UnityPurchasing with receipt validation.
    /// Otherwise runs in simulation mode (local-only game, server validation not required).
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Generic
    /// Role: Manager
    /// System: SDK
    /// Phase: 3
    /// SDK: Unity IAP
    /// </remarks>
    public class IAPManager : Singleton<IAPManager>
#if UNITY_IAP
        , IStoreListener
#endif
    {
        #region Fields

#if UNITY_IAP
        private IStoreController _controller;
        private IExtensionProvider _extensions;
        private bool _isInitialized;
#endif

        #endregion

        #region Product ID Constants

        /// <summary>
        /// IAP product identifier constants.
        /// </summary>
        public static class Products
        {
            public const string GemPackSmall = "gem_pack_small";
            public const string GemPackMedium = "gem_pack_medium";
            public const string GemPackLarge = "gem_pack_large";
            public const string MonthlyPass = "monthly_pass";
        }

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            // IAP is initialized explicitly via Init(), not on Awake
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initializes Unity IAP by registering all products.
        /// In simulation mode, logs initialization message.
        /// </summary>
        public void Init()
        {
#if UNITY_IAP
            if (_isInitialized) return;

            var module = StandardPurchasingModule.Instance();
            var builder = ConfigurationBuilder.Instance(module);

            builder.AddProduct(Products.GemPackSmall, ProductType.Consumable);
            builder.AddProduct(Products.GemPackMedium, ProductType.Consumable);
            builder.AddProduct(Products.GemPackLarge, ProductType.Consumable);
            builder.AddProduct(Products.MonthlyPass, ProductType.Subscription);

            UnityPurchasing.Initialize(this, builder);
            Debug.Log("[IAPManager] Initializing Unity IAP...");
#else
            Debug.Log("[IAP Sim] Initialized");
#endif
        }

        /// <summary>
        /// Initiates a purchase for the specified product ID.
        /// In simulation mode, immediately fires the OnIAPPurchased event.
        /// </summary>
        /// <param name="productId">Product ID from Products constants.</param>
        public void Purchase(string productId)
        {
            if (string.IsNullOrEmpty(productId))
            {
                Debug.LogWarning("[IAPManager] Purchase called with null or empty productId.");
                return;
            }

#if UNITY_IAP
            if (!_isInitialized || _controller == null)
            {
                Debug.LogWarning("[IAPManager] Purchase called before IAP initialization completed.");
                return;
            }

            Product product = _controller.products.WithID(productId);
            if (product == null || !product.availableToPurchase)
            {
                Debug.LogWarning($"[IAPManager] Product not available: {productId}");
                return;
            }

            _controller.InitiatePurchase(product);
#else
            Debug.Log($"[IAP Sim] Purchased: {productId}");
            EventManager.Publish(GameConstants.Events.OnIAPPurchased, productId);
#endif
        }

        /// <summary>
        /// Returns true if Unity IAP has been successfully initialized.
        /// Always returns false in simulation mode.
        /// </summary>
        public bool IsInitialized()
        {
#if UNITY_IAP
            return _isInitialized;
#else
            return false;
#endif
        }

        /// <summary>
        /// Returns the localized price string for the given product.
        /// Returns "N/A" in simulation mode or if the product is not found.
        /// </summary>
        /// <param name="productId">Product ID to look up.</param>
        public string GetLocalizedPrice(string productId)
        {
            if (string.IsNullOrEmpty(productId)) return "N/A";

#if UNITY_IAP
            if (!_isInitialized || _controller == null) return "N/A";

            Product product = _controller.products.WithID(productId);
            return product?.metadata?.localizedPriceString ?? "N/A";
#else
            return "N/A";
#endif
        }

        #endregion

        #region IStoreListener Implementation

#if UNITY_IAP

        /// <summary>
        /// Called when Unity IAP initialization succeeds.
        /// </summary>
        public void OnInitialized(IStoreController controller, IExtensionProvider extensions)
        {
            _controller = controller;
            _extensions = extensions;
            _isInitialized = true;
            Debug.Log("[IAPManager] Unity IAP initialized successfully.");
        }

        /// <summary>
        /// Called when Unity IAP initialization fails.
        /// </summary>
        public void OnInitializeFailed(InitializationFailureReason error)
        {
            _isInitialized = false;
            Debug.LogError($"[IAPManager] IAP initialization failed: {error}");
        }

        /// <summary>
        /// Called when Unity IAP initialization fails with a message.
        /// </summary>
        public void OnInitializeFailed(InitializationFailureReason error, string message)
        {
            _isInitialized = false;
            Debug.LogError($"[IAPManager] IAP initialization failed: {error} - {message}");
        }

        /// <summary>
        /// Called when a purchase completes. Validates receipt locally and fires event.
        /// </summary>
        public PurchaseProcessingResult ProcessPurchase(PurchaseEventArgs args)
        {
            if (args?.purchasedProduct == null) return PurchaseProcessingResult.Complete;

            string productId = args.purchasedProduct.definition.id;

            if (ValidateReceipt(args.purchasedProduct.receipt))
            {
                EventManager.Publish(GameConstants.Events.OnIAPPurchased, productId);
                Debug.Log($"[IAPManager] Purchase validated and processed: {productId}");
            }
            else
            {
                Debug.LogWarning($"[IAPManager] Receipt validation failed for: {productId}");
            }

            return PurchaseProcessingResult.Complete;
        }

        /// <summary>
        /// Called when a purchase fails.
        /// </summary>
        public void OnPurchaseFailed(Product product, PurchaseFailureReason failureReason)
        {
            Debug.LogWarning($"[IAPManager] Purchase failed for {product?.definition?.id}: {failureReason}");
        }

        /// <summary>
        /// Validates the purchase receipt locally using CrossPlatformValidator.
        /// Requires GooglePlayTangle and AppleTangle generated by Unity IAP obfuscator.
        /// </summary>
        private bool ValidateReceipt(string receipt)
        {
            if (string.IsNullOrEmpty(receipt)) return false;

#if UNITY_EDITOR
            // Skip validation in editor for testing
            return true;
#else
            try
            {
                var validator = new CrossPlatformValidator(
                    GooglePlayTangle.Data(),
                    AppleTangle.Data(),
                    Application.identifier
                );
                validator.Validate(receipt);
                return true;
            }
            catch (IAPSecurityException ex)
            {
                Debug.LogError($"[IAPManager] Receipt validation exception: {ex.Message}");
                return false;
            }
#endif
        }

#endif

        #endregion
    }
}
