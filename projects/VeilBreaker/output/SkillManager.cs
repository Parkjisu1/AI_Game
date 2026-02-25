using System.Collections.Generic;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Data;
using VeilBreaker.Economy;

namespace VeilBreaker.Character
{
    /// <summary>
    /// Manages hero skill state: equipment into slots, level-up, and cooldown tracking.
    /// Cooldown is ticked externally via UpdateCooldowns() to keep it decoupled from Update().
    /// Damage computation is delegated to DamageCalculator, not handled here.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// System: Skill
    /// Phase: 2
    /// </remarks>
    public class SkillManager : Singleton<SkillManager>
    {
        #region Constants

        private const int MaxSkillSlots = 3;

        #endregion

        #region Fields

        // heroId -> float[] where index = slot, value = remaining cooldown seconds
        private readonly Dictionary<string, float[]> _cooldowns = new();

        // heroId -> List<string> equipped skillIds per slot (index = slot)
        private readonly Dictionary<string, List<string>> _equippedSkills = new();

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            _cooldowns.Clear();
            _equippedSkills.Clear();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Returns all skills available to the hero from their chart data (not just equipped).
        /// Returns empty list if hero or skill data is missing.
        /// </summary>
        /// <param name="heroId">Hero ID to query.</param>
        public List<SkillData> GetHeroSkills(string heroId)
        {
            var result = new List<SkillData>();

            if (string.IsNullOrEmpty(heroId) || !DataManager.HasInstance) return result;

            HeroData heroData = DataManager.Instance.GetHeroData(heroId);
            if (heroData?.skillIds == null) return result;

            foreach (string skillId in heroData.skillIds)
            {
                SkillData skill = DataManager.Instance.GetSkillData(skillId);
                if (skill != null)
                {
                    result.Add(skill);
                }
            }

            return result;
        }

        /// <summary>
        /// Levels up the specified skill by spending SkillStone currency.
        /// Validates max level (10) and currency balance before proceeding.
        /// </summary>
        /// <param name="heroId">Hero owning the skill.</param>
        /// <param name="skillId">Skill to level up.</param>
        /// <returns>True if level-up succeeded.</returns>
        public bool LevelUpSkill(string heroId, string skillId)
        {
            if (string.IsNullOrEmpty(heroId) || string.IsNullOrEmpty(skillId)) return false;
            if (!DataManager.HasInstance || !CurrencyManager.HasInstance) return false;

            UserHeroData userHero = DataManager.Instance.GetUserHeroData(heroId);
            if (userHero == null)
            {
                Debug.LogWarning($"[SkillManager] UserHeroData not found for heroId: {heroId}");
                return false;
            }

            SkillData skillData = DataManager.Instance.GetSkillData(skillId);
            if (skillData == null)
            {
                Debug.LogWarning($"[SkillManager] SkillData not found for skillId: {skillId}");
                return false;
            }

            // Step 1: Validate max level
            int slotIndex = GetSkillSlotIndex(userHero, skillId);
            int currentLevel = GetSkillLevel(userHero, slotIndex);

            if (currentLevel >= GameConstants.Hero.MaxSkillLevel)
            {
                Debug.Log($"[SkillManager] Skill {skillId} is already at max level {GameConstants.Hero.MaxSkillLevel}.");
                return false;
            }

            // Skill stone cost scales with current level
            long cost = GetLevelUpCost(currentLevel);

            // Step 2: Spend SkillStone (mapped to DungeonTicket as placeholder; project uses skillStone in UserCurrency)
            if (!SpendSkillStone(cost)) return false;

            // Step 3: Increment skill level in user data
            SetSkillLevel(userHero, slotIndex, currentLevel + 1);
            DataManager.Instance.UpdateUserHero(heroId, userHero);

            EventManager.Publish(GameConstants.Events.OnCharacterStatChanged, heroId);
            return true;
        }

        /// <summary>
        /// Equips a skill into the specified slot for the hero.
        /// Slots are 0-indexed. If the slot is occupied, the existing skill is replaced.
        /// Maximum 3 slots. If slot >= 3, the oldest skill (slot 0) is evicted.
        /// </summary>
        /// <param name="heroId">Hero to equip the skill on.</param>
        /// <param name="skillId">Skill to equip.</param>
        /// <param name="slot">Target slot index (0-2).</param>
        /// <returns>True if equip succeeded.</returns>
        public bool EquipSkill(string heroId, string skillId, int slot)
        {
            if (string.IsNullOrEmpty(heroId) || string.IsNullOrEmpty(skillId)) return false;

            int targetSlot = slot >= MaxSkillSlots ? 0 : slot;

            if (!_equippedSkills.TryGetValue(heroId, out List<string> slots))
            {
                slots = new List<string>(new string[MaxSkillSlots]);
                _equippedSkills[heroId] = slots;
            }

            // Ensure list is padded to MaxSkillSlots
            while (slots.Count < MaxSkillSlots) slots.Add(null);

            slots[targetSlot] = skillId;

            // Reset cooldown for the newly equipped slot
            EnsureCooldownArray(heroId);
            _cooldowns[heroId][targetSlot] = 0f;

            EventManager.Publish(GameConstants.Events.OnCharacterStatChanged, heroId);
            return true;
        }

        /// <summary>
        /// Returns true if the specified skill can be activated (cooldown <= 0).
        /// </summary>
        /// <param name="heroId">Hero ID.</param>
        /// <param name="skillId">Skill ID to check.</param>
        public bool CanActivate(string heroId, string skillId)
        {
            if (string.IsNullOrEmpty(heroId) || string.IsNullOrEmpty(skillId)) return false;

            int slotIndex = GetEquippedSlot(heroId, skillId);
            if (slotIndex < 0) return false;

            float remain = GetCooldownRemain(heroId, skillId);
            return remain <= 0f;
        }

        /// <summary>
        /// Resets the cooldown of the specified skill to its full cooldown duration.
        /// Called by BattleManager after skill activation.
        /// </summary>
        /// <param name="heroId">Hero ID.</param>
        /// <param name="skillId">Skill ID to reset.</param>
        public void ResetCooldown(string heroId, string skillId)
        {
            if (string.IsNullOrEmpty(heroId) || string.IsNullOrEmpty(skillId)) return;

            SkillData skillData = DataManager.HasInstance ? DataManager.Instance.GetSkillData(skillId) : null;
            float cooldownDuration = skillData?.cooldown ?? 0f;

            int slotIndex = GetEquippedSlot(heroId, skillId);
            if (slotIndex < 0) return;

            EnsureCooldownArray(heroId);
            _cooldowns[heroId][slotIndex] = cooldownDuration;
        }

        /// <summary>
        /// Returns remaining cooldown seconds for the specified hero/skill pair.
        /// Returns 0 if the skill is not equipped or cooldown array does not exist.
        /// </summary>
        /// <param name="heroId">Hero ID.</param>
        /// <param name="skillId">Skill ID.</param>
        public float GetCooldownRemain(string heroId, string skillId)
        {
            if (string.IsNullOrEmpty(heroId) || string.IsNullOrEmpty(skillId)) return 0f;

            int slotIndex = GetEquippedSlot(heroId, skillId);
            if (slotIndex < 0) return 0f;

            if (!_cooldowns.TryGetValue(heroId, out float[] cooldownArr)) return 0f;
            if (slotIndex >= cooldownArr.Length) return 0f;

            return Mathf.Max(0f, cooldownArr[slotIndex]);
        }

        /// <summary>
        /// Ticks down all active cooldowns by deltaTime.
        /// Called by BattleManager each Update frame during combat.
        /// </summary>
        /// <param name="deltaTime">Elapsed time since last call (Time.deltaTime).</param>
        public void UpdateCooldowns(float deltaTime)
        {
            foreach (var kvp in _cooldowns)
            {
                float[] arr = kvp.Value;
                for (int i = 0; i < arr.Length; i++)
                {
                    if (arr[i] > 0f)
                    {
                        arr[i] -= deltaTime;
                        if (arr[i] <= 0f)
                        {
                            arr[i] = 0f;
                            NotifyCooldownComplete(kvp.Key, i);
                        }
                    }
                }
            }
        }

        #endregion

        #region Private Methods

        private void EnsureCooldownArray(string heroId)
        {
            if (!_cooldowns.ContainsKey(heroId))
            {
                _cooldowns[heroId] = new float[MaxSkillSlots];
            }
        }

        private int GetEquippedSlot(string heroId, string skillId)
        {
            if (!_equippedSkills.TryGetValue(heroId, out List<string> slots)) return -1;

            for (int i = 0; i < slots.Count; i++)
            {
                if (slots[i] == skillId) return i;
            }
            return -1;
        }

        private int GetSkillSlotIndex(UserHeroData userHero, string skillId)
        {
            if (userHero?.skills == null) return -1;
            // skills list stores skillId hashes by slot; use enumeration index as slot
            if (!DataManager.HasInstance) return 0;
            var heroSkills = GetHeroSkills(userHero.heroId);
            for (int i = 0; i < heroSkills.Count; i++)
            {
                if (heroSkills[i].skillId == skillId) return i;
            }
            return 0;
        }

        private int GetSkillLevel(UserHeroData userHero, int slotIndex)
        {
            if (userHero?.skills == null || slotIndex < 0 || slotIndex >= userHero.skills.Count) return 1;
            return Mathf.Max(1, userHero.skills[slotIndex]);
        }

        private void SetSkillLevel(UserHeroData userHero, int slotIndex, int newLevel)
        {
            if (userHero?.skills == null) return;
            while (userHero.skills.Count <= slotIndex) userHero.skills.Add(1);
            userHero.skills[slotIndex] = newLevel;
        }

        private long GetLevelUpCost(int currentLevel)
        {
            // Cost scales: level 1=10, 2=20 ... n=n*10
            return (currentLevel + 1) * 10L;
        }

        private bool SpendSkillStone(long cost)
        {
            // SkillStone uses DungeonTicket key in CurrencyType mapping
            // (UserCurrency.skillStone is stored but CurrencyManager uses CurrencyType enum)
            // Use DungeonTicket as the SkillStone currency representation
            return CurrencyManager.Instance.SpendCurrency(GameConstants.CurrencyType.DungeonTicket, cost);
        }

        private void NotifyCooldownComplete(string heroId, int slotIndex)
        {
            if (!_equippedSkills.TryGetValue(heroId, out List<string> slots)) return;
            if (slotIndex >= slots.Count || string.IsNullOrEmpty(slots[slotIndex])) return;

            EventManager.Publish(
                GameConstants.Events.OnSkillCooldownComplete,
                (heroId, slots[slotIndex])
            );
        }

        #endregion
    }
}
