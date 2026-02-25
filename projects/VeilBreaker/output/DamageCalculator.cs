using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.Battle
{
    /// <summary>
    /// Static utility class for all combat damage calculations.
    /// Handles base damage, attribute multipliers, and critical hits.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Calculator
    /// Phase: 2
    /// System: Battle
    /// </remarks>
    public static class DamageCalculator
    {
        #region Data Structures

        /// <summary>
        /// Result of a single damage calculation event.
        /// </summary>
        public struct DamageResult
        {
            /// <summary>Final damage amount (minimum 1).</summary>
            public int amount;

            /// <summary>Whether this hit was a critical strike.</summary>
            public bool isCritical;

            /// <summary>Attribute type of the attacking unit.</summary>
            public GameConstants.AttributeType attribute;
        }

        /// <summary>
        /// Attacker stat snapshot used for damage calculation.
        /// </summary>
        public struct HeroStats
        {
            public long atk;
            public float critRate;
            public float critDamage;
            public float armorPenetration;
            public GameConstants.AttributeType attribute;
        }

        /// <summary>
        /// Defender stat snapshot used for damage reduction.
        /// </summary>
        public struct EnemyStats
        {
            public long def;
            public GameConstants.AttributeType attribute;
        }

        #endregion

        #region Attribute Table

        // Attribute advantage lookup: [attackerAttr, defenderAttr] -> multiplier
        // Fire > Earth > Water > Fire (cycle), Light/Dark neutral to cycle, counter each other
        private static readonly float[,] AttributeTable = BuildAttributeTable();

        private static float[,] BuildAttributeTable()
        {
            int count = System.Enum.GetValues(typeof(GameConstants.AttributeType)).Length;
            var table = new float[count, count];

            // Default: neutral (1.0)
            for (int i = 0; i < count; i++)
                for (int j = 0; j < count; j++)
                    table[i, j] = 1.0f;

            int fire  = (int)GameConstants.AttributeType.Fire;
            int water = (int)GameConstants.AttributeType.Water;
            int earth = (int)GameConstants.AttributeType.Earth;
            int light = (int)GameConstants.AttributeType.Light;
            int dark  = (int)GameConstants.AttributeType.Dark;

            // Fire > Earth, Earth > Water, Water > Fire
            table[fire,  earth] = GameConstants.Battle.AttributeAdvantage;
            table[earth, water] = GameConstants.Battle.AttributeAdvantage;
            table[water, fire]  = GameConstants.Battle.AttributeAdvantage;

            // Reverse: disadvantage
            table[earth, fire]  = GameConstants.Battle.AttributeDisadvantage;
            table[water, earth] = GameConstants.Battle.AttributeDisadvantage;
            table[fire,  water] = GameConstants.Battle.AttributeDisadvantage;

            // Light vs Dark: counter each other
            table[light, dark] = GameConstants.Battle.AttributeAdvantage;
            table[dark, light] = GameConstants.Battle.AttributeAdvantage;

            return table;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Calculates standard physical damage from attacker to defender.
        /// Applies armor penetration, attribute multiplier, and critical hit.
        /// </summary>
        /// <param name="attacker">Attacker stats snapshot.</param>
        /// <param name="defender">Defender stats snapshot.</param>
        /// <returns>DamageResult with final amount, crit flag, and attribute.</returns>
        public static DamageResult Calculate(HeroStats attacker, EnemyStats defender)
        {
            float effectiveDef = Mathf.Max(0f, defender.def * (1f - attacker.armorPenetration));
            float baseDamage = Mathf.Max(1f, attacker.atk - effectiveDef);

            float attrMultiplier = GetAttributeMultiplier(attacker.attribute, defender.attribute);
            bool isCrit = IsCritical(attacker.critRate);
            float critMultiplier = isCrit ? attacker.critDamage : 1.0f;

            float variance = 1f + UnityEngine.Random.Range(
                -GameConstants.Battle.BaseDamageVariance,
                 GameConstants.Battle.BaseDamageVariance);

            int finalDamage = Mathf.Max(1, Mathf.RoundToInt(baseDamage * attrMultiplier * critMultiplier * variance));

            return new DamageResult
            {
                amount     = finalDamage,
                isCritical = isCrit,
                attribute  = attacker.attribute
            };
        }

        /// <summary>
        /// Calculates skill-based damage, applying the skill's power multiplier on top of base damage.
        /// </summary>
        /// <param name="attacker">Attacker stats snapshot.</param>
        /// <param name="defender">Defender stats snapshot.</param>
        /// <param name="skill">Skill data containing power multiplier.</param>
        /// <returns>DamageResult for the skill hit.</returns>
        public static DamageResult CalculateSkill(HeroStats attacker, EnemyStats defender, SkillData skill)
        {
            float effectiveDef = Mathf.Max(0f, defender.def * (1f - attacker.armorPenetration));
            float baseDamage = Mathf.Max(1f, attacker.atk - effectiveDef);

            float skillPower = skill?.powerMultiplier ?? 1.0f;
            float attrMultiplier = GetAttributeMultiplier(attacker.attribute, defender.attribute);
            bool isCrit = IsCritical(attacker.critRate);
            float critMultiplier = isCrit ? attacker.critDamage : 1.0f;

            int finalDamage = Mathf.Max(1, Mathf.RoundToInt(baseDamage * skillPower * attrMultiplier * critMultiplier));

            return new DamageResult
            {
                amount     = finalDamage,
                isCritical = isCrit,
                attribute  = attacker.attribute
            };
        }

        /// <summary>
        /// Returns the damage multiplier based on attacker and defender attribute types.
        /// </summary>
        /// <param name="atkAttr">Attacker's attribute.</param>
        /// <param name="defAttr">Defender's attribute.</param>
        /// <returns>Multiplier value (e.g. 1.25f for advantage, 0.8f for disadvantage, 1.0f neutral).</returns>
        public static float GetAttributeMultiplier(GameConstants.AttributeType atkAttr, GameConstants.AttributeType defAttr)
        {
            return AttributeTable[(int)atkAttr, (int)defAttr];
        }

        /// <summary>
        /// Determines whether a hit is a critical strike based on critRate probability.
        /// </summary>
        /// <param name="critRate">Critical rate in range [0, 1].</param>
        /// <returns>True if the hit is critical.</returns>
        public static bool IsCritical(float critRate)
        {
            return UnityEngine.Random.Range(0f, 1f) < Mathf.Clamp01(critRate);
        }

        #endregion
    }

    /// <summary>
    /// Skill data model used in damage calculation.
    /// Full definition lives in DataManager / SkillData chart.
    /// </summary>
    [System.Serializable]
    public class SkillData
    {
        public string skillId;
        public string name;
        public float powerMultiplier = 1.0f;
        public int cooldown;
        public GameConstants.AttributeType attribute;
    }
}
