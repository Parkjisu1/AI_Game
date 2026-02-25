using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Data;
using VeilBreaker.Economy;

namespace VeilBreaker.Character
{
    /// <summary>
    /// Hero collection, leveling, star-up, formation, and stat calculation manager.
    /// Central hub for all hero-related operations.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 2
    /// </remarks>
    public class CharacterManager : Singleton<CharacterManager>
    {
        #region Fields

        private List<UserHeroData> _ownedHeroes = new();
        private List<string> _formation = new();

        #endregion

        #region Public Methods - Init

        /// <summary>
        /// Load owned heroes and formation from DataManager.
        /// Must be called after DataManager.Init().
        /// </summary>
        public void Init()
        {
            var allHeroes = DataManager.Instance.GetAllUserHeroes();
            _ownedHeroes = allHeroes?.Values.ToList() ?? new List<UserHeroData>();

            // Load formation from save or use defaults
            // Formation is stored as part of user data
            if (_formation.Count == 0 && _ownedHeroes.Count > 0)
            {
                _formation = _ownedHeroes
                    .Take(GameConstants.Battle.MaxHeroFormation)
                    .Select(h => h.heroId)
                    .ToList();
            }
        }

        #endregion

        #region Public Methods - Hero Queries

        /// <summary>
        /// Get all heroes owned by the player.
        /// </summary>
        public List<UserHeroData> GetOwnedHeroes()
        {
            return _ownedHeroes;
        }

        /// <summary>
        /// Get a specific owned hero by heroId.
        /// </summary>
        public UserHeroData GetHeroData(string heroId)
        {
            if (string.IsNullOrEmpty(heroId)) return null;
            return _ownedHeroes.Find(h => h.heroId == heroId);
        }

        #endregion

        #region Public Methods - Formation

        /// <summary>
        /// Set the battle formation (max 5 heroes).
        /// </summary>
        /// <param name="heroIds">List of heroIds to place in formation.</param>
        public void SetFormation(List<string> heroIds)
        {
            if (heroIds == null) return;

            if (heroIds.Count > GameConstants.Battle.MaxHeroFormation)
            {
                Debug.LogWarning($"[CharacterManager] Formation exceeds max size ({GameConstants.Battle.MaxHeroFormation}). Truncating.");
                heroIds = heroIds.Take(GameConstants.Battle.MaxHeroFormation).ToList();
            }

            // Validate all heroes are owned
            _formation = heroIds.Where(id => GetHeroData(id) != null).ToList();
        }

        /// <summary>
        /// Get the current battle formation hero IDs.
        /// </summary>
        public List<string> GetFormation()
        {
            return new List<string>(_formation);
        }

        #endregion

        #region Public Methods - Hero Growth

        /// <summary>
        /// Level up a hero by 1. Costs gold from UpgradeTable.
        /// </summary>
        /// <returns>True if level up succeeded.</returns>
        public bool LevelUpHero(string heroId)
        {
            var hero = GetHeroData(heroId);
            if (hero == null)
            {
                Debug.LogWarning($"[CharacterManager] Hero '{heroId}' not found.");
                return false;
            }

            if (hero.level >= GameConstants.Hero.MaxLevel)
            {
                Debug.Log($"[CharacterManager] Hero '{heroId}' already at max level.");
                return false;
            }

            long cost = CalculateLevelUpCost(hero.level);

            if (!CurrencyManager.Instance.SpendCurrency(GameConstants.CurrencyType.Gold, cost))
            {
                Debug.Log($"[CharacterManager] Not enough gold for level up. Need: {cost}");
                return false;
            }

            hero.level += 1;
            DataManager.Instance.UpdateUserHero(heroId, hero);

            EventManager.Publish(GameConstants.Events.OnCharacterLevelUp, heroId);

            return true;
        }

        /// <summary>
        /// Star up a hero (requires duplicate heroes or SoulStones).
        /// </summary>
        /// <returns>True if star up succeeded.</returns>
        public bool StarUpHero(string heroId)
        {
            var hero = GetHeroData(heroId);
            if (hero == null) return false;

            if (hero.stars >= GameConstants.Hero.MaxStars)
            {
                Debug.Log($"[CharacterManager] Hero '{heroId}' already at max stars.");
                return false;
            }

            int soulStoneCost = CalculateStarUpCost(hero.stars);

            if (!CurrencyManager.Instance.SpendCurrency(GameConstants.CurrencyType.SoulStone, soulStoneCost))
            {
                Debug.Log($"[CharacterManager] Not enough SoulStones. Need: {soulStoneCost}");
                return false;
            }

            hero.stars += 1;
            DataManager.Instance.UpdateUserHero(heroId, hero);

            EventManager.Publish(GameConstants.Events.OnCharacterStatChanged, heroId);

            return true;
        }

        /// <summary>
        /// Add a new hero to the player's collection.
        /// If already owned, converts to SoulStones instead.
        /// </summary>
        /// <returns>True if hero was added (false if converted to SoulStones).</returns>
        public bool AddHero(string heroId)
        {
            if (string.IsNullOrEmpty(heroId)) return false;

            var existing = GetHeroData(heroId);
            if (existing != null)
            {
                // Duplicate: convert to SoulStones
                var chartData = DataManager.Instance.GetHeroData(heroId);
                int soulStones = chartData != null ? GetDuplicateSoulStones(chartData.grade) : 10;
                CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.SoulStone, soulStones);
                return false;
            }

            var newHero = new UserHeroData
            {
                heroId = heroId,
                level = 1,
                stars = 1,
                exp = 0,
                equippedItems = new List<string>(),
                skills = new List<int>()
            };

            _ownedHeroes.Add(newHero);
            DataManager.Instance.UpdateUserHero(heroId, newHero);

            return true;
        }

        #endregion

        #region Public Methods - Stats

        /// <summary>
        /// Calculate the final combined stats for a hero (base + growth + equipment).
        /// </summary>
        public HeroStats GetFinalStats(string heroId)
        {
            var hero = GetHeroData(heroId);
            if (hero == null) return new HeroStats();

            var chartData = DataManager.Instance.GetHeroData(heroId);
            if (chartData == null) return new HeroStats();

            float levelMultiplier = hero.level - 1;
            float starMultiplier = 1f + (hero.stars - 1) * 0.1f;

            float atk = (chartData.baseAtk + chartData.growthAtk * levelMultiplier) * starMultiplier;
            float def = (chartData.baseDef + chartData.growthDef * levelMultiplier) * starMultiplier;
            float hp = (chartData.baseHp + chartData.growthHp * levelMultiplier) * starMultiplier;

            // Add equipment stats
            float equipAtk = 0f, equipDef = 0f, equipHp = 0f;
            if (hero.equippedItems != null)
            {
                foreach (var equipId in hero.equippedItems)
                {
                    var equipData = DataManager.Instance.GetEquipmentData(equipId);
                    if (equipData != null)
                    {
                        equipAtk += equipData.baseAtk;
                        equipDef += equipData.baseDef;
                        equipHp += equipData.baseHp;
                    }
                }
            }

            return new HeroStats
            {
                heroId = heroId,
                atk = atk + equipAtk,
                def = def + equipDef,
                hp = hp + equipHp,
                attribute = chartData.attribute,
                critRate = 0.05f + (hero.stars - 1) * 0.02f,
                attackSpeed = 1f,
                attackRange = 2f,
                moveSpeed = 3f
            };
        }

        #endregion

        #region Private Methods

        private long CalculateLevelUpCost(int currentLevel)
        {
            // Base cost * level multiplier
            return (long)(100 * currentLevel * (1f + currentLevel * 0.1f));
        }

        private int CalculateStarUpCost(int currentStars)
        {
            // Exponential SoulStone cost per star
            return currentStars switch
            {
                1 => 10,
                2 => 30,
                3 => 80,
                4 => 150,
                _ => 300
            };
        }

        private int GetDuplicateSoulStones(int grade)
        {
            return grade switch
            {
                5 => 50,  // Legendary
                4 => 30,  // Epic
                3 => 15,  // Rare
                2 => 8,   // Uncommon
                _ => 5    // Common
            };
        }

        #endregion
    }

    /// <summary>
    /// Calculated hero stats combining base, growth, stars, and equipment.
    /// Used by battle system for damage calculations.
    /// </summary>
    [Serializable]
    public struct HeroStats
    {
        public string heroId;
        public float atk;
        public float def;
        public float hp;
        public GameConstants.AttributeType attribute;
        public float critRate;
        public float attackSpeed;
        public float attackRange;
        public float moveSpeed;
    }

}
