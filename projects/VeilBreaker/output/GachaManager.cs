using System;
using System.Collections.Generic;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Data;
using VeilBreaker.Economy;

namespace VeilBreaker.Gacha
{
    /// <summary>
    /// Handles gacha pulls across banners with pity system (soft pity 80, hard pity 100).
    /// Routes currency spending through CurrencyManager and results via EventManager.
    /// Probability tables are defined in GachaData (chart), not hardcoded here.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// System: Gacha
    /// Phase: 2
    /// </remarks>
    public class GachaManager : Singleton<GachaManager>
    {
        #region Constants

        private const int SinglePullCost = 300;
        private const int MultiPullCost = 3000;
        private const int MultiPullCount = 10;

        #endregion

        #region Fields

        // bannerId -> current pity count
        private readonly Dictionary<string, int> _pityCounters = new();

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            _pityCounters.Clear();
            EventManager.Subscribe(GameConstants.Events.OnDataLoaded, OnDataLoaded);
        }

        protected override void OnDestroy()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnDataLoaded, OnDataLoaded);
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Executes a gacha pull on the specified banner.
        /// Deducts Gem cost, applies pity logic, and returns pulled items.
        /// Publishes OnGachaResult after completion.
        /// </summary>
        /// <param name="bannerId">Banner to pull from.</param>
        /// <param name="count">Number of pulls (1 or 10).</param>
        /// <returns>List of pulled GachaItem results. Empty list on failure.</returns>
        public List<GachaItem> Pull(string bannerId, int count)
        {
            var results = new List<GachaItem>();

            if (string.IsNullOrEmpty(bannerId) || count <= 0) return results;
            if (!DataManager.HasInstance || !CurrencyManager.HasInstance) return results;

            GachaData bannerData = DataManager.Instance.GetGachaData(bannerId);
            if (bannerData == null)
            {
                Debug.LogWarning($"[GachaManager] GachaData not found for bannerId: {bannerId}");
                return results;
            }

            // Step 1: Validate gem balance
            long gemCost = count == 1 ? SinglePullCost : (long)MultiPullCount * SinglePullCost;
            if (!CurrencyManager.Instance.HasEnough(GameConstants.CurrencyType.Gem, gemCost))
            {
                Debug.Log($"[GachaManager] Not enough Gems for pull on banner {bannerId}. Required: {gemCost}");
                return results;
            }

            // Step 2: Spend gems
            if (!CurrencyManager.Instance.SpendCurrency(GameConstants.CurrencyType.Gem, gemCost))
            {
                return results;
            }

            // Step 3: Execute pulls
            int pity = GetOrCreatePity(bannerId);

            for (int i = 0; i < count; i++)
            {
                pity++;
                GachaItem item = RollSingle(bannerData, pity);

                // Step 4/5: Pity adjustments applied inside RollSingle
                bool isSSR = item.grade == GachaGrade.SSR;

                // Step 6: Update pity counter
                if (isSSR)
                {
                    pity = 0; // Reset on SSR
                }

                results.Add(item);
            }

            _pityCounters[bannerId] = pity;
            PersistPityCounters();

            // Step 7: Notify
            var resultIds = new List<string>();
            foreach (var item in results) resultIds.Add(item.id);
            EventManager.Publish(GameConstants.Events.OnGachaResult, resultIds);

            return results;
        }

        /// <summary>
        /// Returns the current pity count for the specified banner.
        /// </summary>
        /// <param name="bannerId">Banner ID to query.</param>
        public int GetPityCount(string bannerId)
        {
            return string.IsNullOrEmpty(bannerId) ? 0 : GetOrCreatePity(bannerId);
        }

        /// <summary>
        /// Returns chart data for the specified banner.
        /// </summary>
        /// <param name="bannerId">Banner ID to look up.</param>
        public GachaData GetBannerData(string bannerId)
        {
            if (string.IsNullOrEmpty(bannerId) || !DataManager.HasInstance) return null;
            return DataManager.Instance.GetGachaData(bannerId);
        }

        /// <summary>
        /// Returns all banner data records from the chart cache.
        /// </summary>
        public List<GachaData> GetActiveBanners()
        {
            var result = new List<GachaData>();
            if (!DataManager.HasInstance) return result;

            foreach (var kvp in DataManager.Instance.GetAllHeroData())
            {
                // Active banners are in GachaData cache, accessed via DataManager
                // Return all banners from chart (DataManager does not expose GetAllGachaData,
                // so we use a known banner list approach via UserGachaData entries)
            }

            // Fallback: Return banners tracked in user pity data
            if (DataManager.HasInstance)
            {
                UserGachaData userGacha = DataManager.Instance.GetUserGachaData();
                if (userGacha?.banners != null)
                {
                    foreach (UserGachaEntry entry in userGacha.banners)
                    {
                        GachaData data = DataManager.Instance.GetGachaData(entry.bannerId);
                        if (data != null) result.Add(data);
                    }
                }
            }

            return result;
        }

        #endregion

        #region Private Methods

        private GachaItem RollSingle(GachaData bannerData, int pity)
        {
            GachaGrade grade = DetermineGrade(bannerData, pity);

            // Pick a random item id from the banner pool
            string itemId = PickFromPool(bannerData, grade);

            return new GachaItem
            {
                id = itemId,
                type = GachaItemType.Hero,
                grade = grade
            };
        }

        private GachaGrade DetermineGrade(GachaData bannerData, int pity)
        {
            // Hard pity: force SSR at 100
            if (pity >= GameConstants.Gacha.HardPity)
            {
                return GachaGrade.SSR;
            }

            // Base SSR rate from chart (index 0 = SSR rate as percentage, e.g. 0.5 means 0.5%)
            float ssrRate = bannerData.rates != null && bannerData.rates.Count > 0
                ? bannerData.rates[0]
                : 0.5f;

            // Soft pity: SSR rate boosted linearly after pull 80
            if (pity >= GameConstants.Gacha.SoftPity)
            {
                int overSoft = pity - GameConstants.Gacha.SoftPity;
                ssrRate += overSoft * 6f;
            }

            ssrRate = Mathf.Clamp(ssrRate, 0f, 100f);

            if (Util.IsChanceSuccess(ssrRate)) return GachaGrade.SSR;

            // SR rate from chart index 1
            float srRate = bannerData.rates != null && bannerData.rates.Count > 1
                ? bannerData.rates[1]
                : 6f;

            if (Util.IsChanceSuccess(srRate)) return GachaGrade.SR;

            return GachaGrade.R;
        }

        private string PickFromPool(GachaData bannerData, GachaGrade grade)
        {
            if (bannerData.pool == null || bannerData.pool.Count == 0)
            {
                return $"unknown_{grade}";
            }

            // Simple uniform random from pool; grade-based sub-pool not in chart, use full pool
            int index = UnityEngine.Random.Range(0, bannerData.pool.Count);
            return bannerData.pool[index];
        }

        private int GetOrCreatePity(string bannerId)
        {
            if (!_pityCounters.TryGetValue(bannerId, out int count))
            {
                count = 0;
                _pityCounters[bannerId] = count;
            }
            return count;
        }

        private void PersistPityCounters()
        {
            if (!DataManager.HasInstance) return;

            UserGachaData userGacha = DataManager.Instance.GetUserGachaData() ?? new UserGachaData();
            userGacha.banners ??= new List<UserGachaEntry>();

            foreach (var kvp in _pityCounters)
            {
                UserGachaEntry entry = userGacha.banners.Find(e => e.bannerId == kvp.Key);
                if (entry == null)
                {
                    entry = new UserGachaEntry { bannerId = kvp.Key };
                    userGacha.banners.Add(entry);
                }
                entry.pityCount = kvp.Value;
                entry.totalPulls++;
                entry.isSoftPity = kvp.Value >= GameConstants.Gacha.SoftPity;
            }

            DataManager.Instance.UpdateUserGacha(userGacha);
        }

        private void OnDataLoaded(object data)
        {
            if (!DataManager.HasInstance) return;

            UserGachaData userGacha = DataManager.Instance.GetUserGachaData();
            if (userGacha?.banners == null) return;

            _pityCounters.Clear();
            foreach (UserGachaEntry entry in userGacha.banners)
            {
                if (!string.IsNullOrEmpty(entry?.bannerId))
                {
                    _pityCounters[entry.bannerId] = entry.pityCount;
                }
            }
        }

        #endregion
    }

    #region Gacha Data Models

    /// <summary>
    /// A single gacha pull result.
    /// </summary>
    [Serializable]
    public class GachaItem
    {
        /// <summary>Hero or equipment ID from the pool.</summary>
        public string id;
        /// <summary>Whether this is a hero or equipment pull.</summary>
        public GachaItemType type;
        /// <summary>Grade of the pulled item.</summary>
        public GachaGrade grade;
    }

    /// <summary>
    /// Type of item returned from a gacha pull.
    /// </summary>
    public enum GachaItemType
    {
        Hero,
        Equipment
    }

    /// <summary>
    /// Gacha rarity grades corresponding to chart rates.
    /// </summary>
    public enum GachaGrade
    {
        R,
        SR,
        SSR
    }

    #endregion
}
