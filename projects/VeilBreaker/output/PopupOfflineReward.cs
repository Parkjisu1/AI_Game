using UnityEngine;
using UnityEngine.UI;
using TMPro;
using VeilBreaker.Core;
using VeilBreaker.SDK;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Offline reward popup. Auto-opens on OnOfflineRewardCalculated event.
    /// Offers standard claim or ad-doubled claim options.
    /// Falls back to standard claim if ad is not available.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// Phase: 3
    /// System: UI
    /// </remarks>
    public class PopupOfflineReward : PopupBase
    {
        #region Fields

        [SerializeField] private TextMeshProUGUI _offlineHoursText;
        [SerializeField] private TextMeshProUGUI _goldRewardText;
        [SerializeField] private TextMeshProUGUI _expRewardText;
        [SerializeField] private Button          _claimButton;
        [SerializeField] private Button          _adClaimButton;
        [SerializeField] private Button          _closeButton;

        // Cached reward data from the event
        private OfflineRewardResult _pendingReward;

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            EventManager.Subscribe(GameConstants.Events.OnOfflineRewardCalculated, OnOfflineRewardCalculated);
        }

        private void OnDisable()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnOfflineRewardCalculated, OnOfflineRewardCalculated);
        }

        #endregion

        #region PopupBase Overrides

        /// <summary>
        /// Opens the popup. If data is provided as OfflineRewardResult, displays it immediately.
        /// Otherwise waits for OnOfflineRewardCalculated event.
        /// </summary>
        public override void Open(object data = null)
        {
            _pendingReward = data as OfflineRewardResult;

            if (_pendingReward != null)
                RefreshRewardDisplay(_pendingReward);

            RefreshAdButton();

            _claimButton?.onClick.RemoveAllListeners();
            _claimButton?.onClick.AddListener(OnClaimButton);

            _adClaimButton?.onClick.RemoveAllListeners();
            _adClaimButton?.onClick.AddListener(OnAdClaimButton);

            _closeButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.AddListener(CloseThis);
        }

        /// <summary>
        /// Cleans up on close.
        /// </summary>
        public override void Close()
        {
            _pendingReward = null;
            _claimButton?.onClick.RemoveAllListeners();
            _adClaimButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.RemoveAllListeners();
        }

        #endregion

        #region Private Methods

        private void OnOfflineRewardCalculated(object data)
        {
            _pendingReward = data as OfflineRewardResult;
            if (_pendingReward == null) return;

            RefreshRewardDisplay(_pendingReward);
            RefreshAdButton();

            // Auto-open this popup via UISystem if not already open
            if (UISystem.HasInstance && !gameObject.activeInHierarchy)
                UISystem.Instance.OpenPopup<PopupOfflineReward>(_pendingReward);
        }

        private void OnClaimButton()
        {
            ClaimReward(doubleReward: false);
        }

        private void OnAdClaimButton()
        {
            if (AdMobManager.HasInstance && AdMobManager.Instance.IsRewardedAdReady())
            {
                _claimButton?.gameObject.SetActive(false);
                _adClaimButton?.gameObject.SetActive(false);

                AdMobManager.Instance.ShowRewardedAd(ClaimWithAd);
            }
            else
            {
                // Ad not available - fall back to standard claim
                Debug.LogWarning("[PopupOfflineReward] Ad not ready. Claiming standard reward.");
                ClaimReward(doubleReward: false);
            }
        }

        private void ClaimWithAd()
        {
            ClaimReward(doubleReward: true);
        }

        private void ClaimReward(bool doubleReward)
        {
            if (!OfflineProgressManager.HasInstance)
            {
                CloseThis();
                return;
            }

            OfflineProgressManager.Instance.ClaimReward(doubleReward);
            CloseThis();
        }

        private void RefreshRewardDisplay(OfflineRewardResult reward)
        {
            if (reward == null) return;

            if (_offlineHoursText != null)
                _offlineHoursText.text = $"{reward.offlineHours:0.#}h offline";

            if (_goldRewardText != null)
                _goldRewardText.text = FormatNumber((long)reward.gold);

            if (_expRewardText != null)
                _expRewardText.text = FormatNumber((long)reward.exp);
        }

        private void RefreshAdButton()
        {
            bool adReady = AdMobManager.HasInstance && AdMobManager.Instance.IsRewardedAdReady();
            _adClaimButton?.gameObject.SetActive(adReady);
        }

        private static string FormatNumber(long n)
        {
            if (n >= 1_000_000) return $"{n / 1_000_000f:0.#}M";
            if (n >= 1_000)     return $"{n / 1_000f:0.#}K";
            return n.ToString();
        }

        #endregion
    }

    /// <summary>
    /// Payload data for the OnOfflineRewardCalculated event.
    /// Full definition lives in OfflineProgressManager.
    /// </summary>
    [System.Serializable]
    public class OfflineRewardResult
    {
        public double gold;
        public double exp;
        public float  offlineHours;
    }
}
