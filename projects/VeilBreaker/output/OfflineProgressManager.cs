using System;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Data;
using VeilBreaker.Economy;

namespace VeilBreaker.Idle
{
    /// <summary>
    /// Calculates and grants offline idle rewards based on elapsed time since last session.
    /// Maximum offline duration is capped at MaxOfflineHours (12h) from GameConstants.
    /// Ad-doubled rewards multiply gold by 2x at claim time.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// System: Offline
    /// Phase: 2
    /// </remarks>
    public class OfflineProgressManager : Singleton<OfflineProgressManager>
    {
        #region Fields

        private OfflineRewardResult _pendingReward;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            _pendingReward = null;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Calculates the offline reward based on elapsed time since the last recorded login.
        /// Caps at GameConstants.Battle.MaxOfflineHours. Stores result as pending.
        /// Publishes OnOfflineRewardCalculated with the result.
        /// </summary>
        public void CalculateOfflineReward()
        {
            if (!DataManager.HasInstance) return;

            UserOfflineData offlineData = DataManager.Instance.GetUserOfflineData();
            if (offlineData == null) return;

            // Step 1: Compute elapsed seconds via UnixTimestamp comparison
            long lastLoginUnix = ParseUnixTimestamp(offlineData.lastLoginTime);
            long nowUnix = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            double offlineSeconds = nowUnix - lastLoginUnix;

            // Step 2: Cap at MaxOfflineHours
            double maxSeconds = GameConstants.Battle.MaxOfflineHours * 3600.0;
            offlineSeconds = Math.Min(offlineSeconds, maxSeconds);
            if (offlineSeconds < 0) offlineSeconds = 0;

            // Step 3: Calculate gold reward (from current stage's offline table)
            double goldPerSec = GetGoldPerSec();
            double pendingGold = goldPerSec * offlineSeconds;

            // Step 4: Calculate exp reward
            double expPerSec = GetExpPerSec();
            double pendingExp = expPerSec * offlineSeconds;

            _pendingReward = new OfflineRewardResult
            {
                gold = (long)pendingGold,
                exp = (long)pendingExp,
                hours = (float)(offlineSeconds / 3600.0)
            };

            // Step 5: Notify UI to show offline reward popup
            EventManager.Publish(
                GameConstants.Events.OnOfflineRewardCalculated,
                (_pendingReward.gold, _pendingReward.exp)
            );
        }

        /// <summary>
        /// Claims the pending offline reward. If withAd is true, gold is doubled.
        /// Clears the pending reward and updates lastLoginTime.
        /// </summary>
        /// <param name="withAd">True to double gold reward via ad watch.</param>
        public void ClaimReward(bool withAd)
        {
            if (_pendingReward == null)
            {
                Debug.LogWarning("[OfflineProgressManager] ClaimReward called but no pending reward.");
                return;
            }

            if (!CurrencyManager.HasInstance || !DataManager.HasInstance) return;

            long gold = _pendingReward.gold;
            long exp = _pendingReward.exp;

            // Step 6: Apply ad multiplier
            if (withAd) gold *= 2;

            // Step 7: Add currencies
            if (gold > 0)
            {
                CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.Gold, gold);
            }

            // Exp is applied to UserInfo level-up logic (no direct CurrencyType for exp)
            ApplyExpReward(exp);

            // Step 8: Reset lastLoginTime and persist
            _pendingReward = null;

            UserOfflineData offlineData = DataManager.Instance.GetUserOfflineData() ?? new UserOfflineData();
            offlineData.lastLoginTime = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString();
            offlineData.pendingGold = 0;
            offlineData.pendingExp = 0;

            DataManager.Instance.UpdateUserOffline(offlineData);
            if (SaveManager.HasInstance) SaveManager.Instance.Save();
        }

        /// <summary>
        /// Returns the currently calculated but unclaimed offline reward.
        /// Returns null if CalculateOfflineReward has not been called yet.
        /// </summary>
        public OfflineRewardResult GetPendingReward()
        {
            return _pendingReward;
        }

        #endregion

        #region Private Methods

        private double GetGoldPerSec()
        {
            if (!DataManager.HasInstance) return 1.0;

            UserStageData stageData = DataManager.Instance.GetUserStageData();
            if (stageData == null) return 1.0;

            // Use max cleared stage's gold reward divided by estimated battle time as base rate
            string stageId = $"{stageData.currentChapter}_{stageData.currentStage}";
            StageData stage = DataManager.Instance.GetStageData(stageId);

            if (stage == null) return 1.0;

            // Approximate idle gold/sec: stage gold reward / 60 seconds per stage
            const double secondsPerStage = 60.0;
            return stage.goldReward / secondsPerStage;
        }

        private double GetExpPerSec()
        {
            if (!DataManager.HasInstance) return 0.5;

            UserStageData stageData = DataManager.Instance.GetUserStageData();
            if (stageData == null) return 0.5;

            string stageId = $"{stageData.currentChapter}_{stageData.currentStage}";
            StageData stage = DataManager.Instance.GetStageData(stageId);

            if (stage == null) return 0.5;

            const double secondsPerStage = 60.0;
            return stage.expReward / secondsPerStage;
        }

        private void ApplyExpReward(long exp)
        {
            if (exp <= 0 || !DataManager.HasInstance) return;

            UserInfo userInfo = DataManager.Instance.GetUserInfo();
            if (userInfo == null) return;

            userInfo.exp += exp;
            DataManager.Instance.UpdateUserInfo(userInfo);
        }

        /// <summary>
        /// Parses either ISO8601 or Unix timestamp string into a Unix timestamp long.
        /// Falls back to current time on parse failure.
        /// </summary>
        private long ParseUnixTimestamp(string raw)
        {
            if (string.IsNullOrEmpty(raw))
            {
                return DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            }

            // Try parsing as Unix timestamp (stored as plain long string)
            if (long.TryParse(raw, out long unix))
            {
                return unix;
            }

            // Fallback: ISO 8601 format from UserOfflineData default constructor
            if (DateTimeOffset.TryParse(raw, out DateTimeOffset dt))
            {
                return dt.ToUnixTimeSeconds();
            }

            Debug.LogWarning($"[OfflineProgressManager] Could not parse lastLoginTime: {raw}. Using current time.");
            return DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        }

        #endregion
    }

    /// <summary>
    /// Result of offline reward calculation.
    /// </summary>
    [Serializable]
    public class OfflineRewardResult
    {
        /// <summary>Gold earned while offline.</summary>
        public long gold;
        /// <summary>Exp earned while offline.</summary>
        public long exp;
        /// <summary>Offline duration in hours (display use).</summary>
        public float hours;
    }
}
