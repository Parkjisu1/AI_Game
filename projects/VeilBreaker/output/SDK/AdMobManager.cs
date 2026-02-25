#if GOOGLE_MOBILE_ADS
using GoogleMobileAds;
using GoogleMobileAds.Api;
#endif

using System;
using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.SDK
{
    /// <summary>
    /// Manages Google AdMob rewarded and interstitial ads with conditional compilation.
    /// In non-SDK environments, all methods fall through to simulation implementations.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Generic
    /// Role: Manager
    /// Phase: 3
    /// System: SDK
    /// </remarks>
    public class AdMobManager : Singleton<AdMobManager>
    {
        #region Fields

#if GOOGLE_MOBILE_ADS
        private RewardedAd      _rewardedAd;
        private InterstitialAd  _interstitialAd;
#endif

        private Action _onRewardComplete;
        private bool   _isInitialized;

        // Ad Unit IDs - replace with real IDs before release
        private const string RewardedAdUnitId      = "ca-app-pub-3940256099942544/5224354917"; // test ID
        private const string InterstitialAdUnitId  = "ca-app-pub-3940256099942544/1033173712"; // test ID

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            // Init is called explicitly from bootstrap; not auto-init here
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialises the AdMob SDK and preloads the rewarded ad.
        /// No-op if already initialised.
        /// </summary>
        public void Init()
        {
            if (_isInitialized) return;
            _isInitialized = true;

#if GOOGLE_MOBILE_ADS
            MobileAds.Initialize(initStatus =>
            {
                Debug.Log("[AdMobManager] SDK initialised.");
                LoadRewardedAd();
                LoadInterstitialAd();
            });
#else
            Debug.Log("[AdMob Sim] Initialised (SDK not present).");
#endif
        }

        /// <summary>
        /// Shows a rewarded ad. In simulation mode, immediately grants the reward.
        /// Publishes OnAdWatched after the reward is granted.
        /// </summary>
        /// <param name="onComplete">Callback invoked when the reward is granted.</param>
        public void ShowRewardedAd(Action onComplete = null)
        {
#if GOOGLE_MOBILE_ADS
            if (!IsRewardedAdReady())
            {
                Debug.LogWarning("[AdMobManager] Rewarded ad not ready. Preloading...");
                LoadRewardedAd();
                return;
            }

            _onRewardComplete = onComplete;
            _rewardedAd.Show(reward =>
            {
                Debug.Log($"[AdMobManager] Reward earned: {reward.Type} x{reward.Amount}");
                _onRewardComplete?.Invoke();
                _onRewardComplete = null;
                EventManager.Publish(GameConstants.Events.OnAdWatched, "rewarded");
                LoadRewardedAd();
            });
#else
            Debug.Log("[AdMob Sim] Rewarded ad completed.");
            onComplete?.Invoke();
            EventManager.Publish(GameConstants.Events.OnAdWatched, "rewarded");
#endif
        }

        /// <summary>
        /// Shows an interstitial ad. In simulation mode, logs and returns immediately.
        /// </summary>
        public void ShowInterstitialAd()
        {
#if GOOGLE_MOBILE_ADS
            if (_interstitialAd == null || !_interstitialAd.CanShowAd())
            {
                Debug.LogWarning("[AdMobManager] Interstitial ad not ready. Preloading...");
                LoadInterstitialAd();
                return;
            }

            _interstitialAd.Show();
            EventManager.Publish(GameConstants.Events.OnAdWatched, "interstitial");
            LoadInterstitialAd();
#else
            Debug.Log("[AdMob Sim] Interstitial ad shown.");
            EventManager.Publish(GameConstants.Events.OnAdWatched, "interstitial");
#endif
        }

        /// <summary>
        /// Returns true if a rewarded ad is loaded and ready to display.
        /// Always returns true in simulation mode.
        /// </summary>
        public bool IsRewardedAdReady()
        {
#if GOOGLE_MOBILE_ADS
            return _rewardedAd != null && _rewardedAd.CanShowAd();
#else
            return true;
#endif
        }

        #endregion

        #region Private Methods

#if GOOGLE_MOBILE_ADS
        private void LoadRewardedAd()
        {
            _rewardedAd?.Destroy();
            _rewardedAd = null;

            var adRequest = new AdRequest();
            RewardedAd.Load(RewardedAdUnitId, adRequest, (ad, error) =>
            {
                if (error != null)
                {
                    Debug.LogError($"[AdMobManager] Rewarded ad load failed: {error.GetMessage()}");
                    return;
                }
                _rewardedAd = ad;
                Debug.Log("[AdMobManager] Rewarded ad loaded.");
            });
        }

        private void LoadInterstitialAd()
        {
            _interstitialAd?.Destroy();
            _interstitialAd = null;

            var adRequest = new AdRequest();
            InterstitialAd.Load(InterstitialAdUnitId, adRequest, (ad, error) =>
            {
                if (error != null)
                {
                    Debug.LogError($"[AdMobManager] Interstitial ad load failed: {error.GetMessage()}");
                    return;
                }
                _interstitialAd = ad;
                Debug.Log("[AdMobManager] Interstitial ad loaded.");
            });
        }
#endif

        #endregion
    }
}
