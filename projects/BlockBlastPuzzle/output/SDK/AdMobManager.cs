#if GOOGLE_MOBILE_ADS
using GoogleMobileAds.Api;
#endif
using System;
using UnityEngine;
using BlockBlast.Core;

namespace BlockBlast.SDK
{
    public class AdMobManager : Singleton<AdMobManager>
    {
#if GOOGLE_MOBILE_ADS
        // Test Ad Unit IDs (replace with real ones for production)
        private const string BANNER_ID = "ca-app-pub-3940256099942544/6300978111";
        private const string INTERSTITIAL_ID = "ca-app-pub-3940256099942544/1033173712";
        private const string REWARDED_ID = "ca-app-pub-3940256099942544/5224354917";

        private BannerView _bannerView;
        private InterstitialAd _interstitialAd;
        private RewardedAd _rewardedAd;
        private Action<bool> _rewardedCallback;

        protected override void Awake()
        {
            base.Awake();
            MobileAds.Initialize(status =>
            {
                Debug.Log("[AdMob] Initialized");
                LoadInterstitial();
                LoadRewarded();
            });
        }

        public void ShowBanner()
        {
            if (_bannerView != null)
            {
                _bannerView.Destroy();
            }

            _bannerView = new BannerView(BANNER_ID, AdSize.Banner, AdPosition.Bottom);
            var request = new AdRequest();
            _bannerView.LoadAd(request);
        }

        public void HideBanner()
        {
            _bannerView?.Hide();
        }

        public void ShowInterstitial()
        {
            if (_interstitialAd != null && _interstitialAd.CanShowAd())
            {
                _interstitialAd.Show();
            }
            else
            {
                Debug.Log("[AdMob] Interstitial not ready");
                LoadInterstitial();
            }
        }

        private void LoadInterstitial()
        {
            if (_interstitialAd != null)
            {
                _interstitialAd.Destroy();
                _interstitialAd = null;
            }

            var request = new AdRequest();
            InterstitialAd.Load(INTERSTITIAL_ID, request, (InterstitialAd ad, LoadAdError error) =>
            {
                if (error != null)
                {
                    Debug.LogError($"[AdMob] Interstitial load error: {error}");
                    return;
                }
                _interstitialAd = ad;
                _interstitialAd.OnAdFullScreenContentClosed += () =>
                {
                    LoadInterstitial();
                };
            });
        }

        public void ShowRewarded(Action<bool> callback)
        {
            _rewardedCallback = callback;

            if (_rewardedAd != null && _rewardedAd.CanShowAd())
            {
                _rewardedAd.Show((Reward reward) =>
                {
                    Debug.Log($"[AdMob] Rewarded: {reward.Type} x{reward.Amount}");
                    _rewardedCallback?.Invoke(true);
                    _rewardedCallback = null;
                });
            }
            else
            {
                Debug.Log("[AdMob] Rewarded not ready");
                _rewardedCallback?.Invoke(false);
                _rewardedCallback = null;
                LoadRewarded();
            }
        }

        private void LoadRewarded()
        {
            if (_rewardedAd != null)
            {
                _rewardedAd.Destroy();
                _rewardedAd = null;
            }

            var request = new AdRequest();
            RewardedAd.Load(REWARDED_ID, request, (RewardedAd ad, LoadAdError error) =>
            {
                if (error != null)
                {
                    Debug.LogError($"[AdMob] Rewarded load error: {error}");
                    return;
                }
                _rewardedAd = ad;
                _rewardedAd.OnAdFullScreenContentClosed += () =>
                {
                    LoadRewarded();
                };
            });
        }

        private void OnDestroy()
        {
            _bannerView?.Destroy();
            _interstitialAd?.Destroy();
            _rewardedAd?.Destroy();
        }
#else
        // ===== Simulation Mode =====
        protected override void Awake()
        {
            base.Awake();
            Debug.Log("[AdMob Sim] Initialized (simulation mode)");
        }

        public void ShowBanner()
        {
            Debug.Log("[AdMob Sim] Banner shown");
        }

        public void HideBanner()
        {
            Debug.Log("[AdMob Sim] Banner hidden");
        }

        public void ShowInterstitial()
        {
            Debug.Log("[AdMob Sim] Interstitial shown");
        }

        public void ShowRewarded(Action<bool> callback)
        {
            Debug.Log("[AdMob Sim] Rewarded shown (simulating success)");
            callback?.Invoke(true);
        }
#endif
    }
}
