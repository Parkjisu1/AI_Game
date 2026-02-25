using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Character;

namespace VeilBreaker.Battle
{
    /// <summary>
    /// Individual hero battle controller handling auto-combat AI:
    /// movement, attack, skill usage, damage taking, and death.
    /// Attached to each hero prefab instance in the battle scene.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Controller
    /// Phase: 2
    /// </remarks>
    public class CharacterBattle : MonoBehaviour
    {
        #region Fields

        [SerializeField] private Animator _animator;
        [SerializeField] private Transform _hitPoint;

        private string _heroId;
        private HeroStats _stats;
        private float _currentHp;
        private float _attackTimer;
        private CharacterState _state = CharacterState.Idle;
        private EnemyController _target;
        private bool _isInitialized;

        #endregion

        #region Properties

        /// <summary>
        /// Hero ID associated with this battle instance.
        /// </summary>
        public string HeroId => _heroId;

        /// <summary>
        /// Current battle stats for this hero.
        /// </summary>
        public HeroStats Stats => _stats;

        #endregion

        #region Enums

        private enum CharacterState
        {
            Idle,
            Moving,
            Attacking,
            UsingSkill,
            Dead
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize this battle character with hero data and stats.
        /// </summary>
        /// <param name="heroId">Hero ID from CharacterManager.</param>
        /// <param name="stats">Pre-calculated final stats from CharacterManager.GetFinalStats().</param>
        public void Init(string heroId, HeroStats stats)
        {
            _heroId = heroId;
            _stats = stats;
            _currentHp = stats.hp;
            _attackTimer = 0f;
            _state = CharacterState.Idle;
            _target = null;
            _isInitialized = true;

            if (_animator != null)
            {
                _animator.SetBool("IsAlive", true);
            }
        }

        /// <summary>
        /// Apply damage to this hero.
        /// </summary>
        /// <param name="amount">Damage amount after all calculations.</param>
        public void TakeDamage(int amount)
        {
            if (_state == CharacterState.Dead) return;

            _currentHp -= amount;

            if (_animator != null)
            {
                _animator.SetTrigger("Hit");
            }

            // Spawn hit effect
            if (_hitPoint != null && ObjectPool.HasInstance)
            {
                ObjectPool.Instance.Spawn(
                    GameConstants.PoolTags.HitEffect,
                    _hitPoint.position,
                    Quaternion.identity
                );
            }

            if (_currentHp <= 0f)
            {
                _currentHp = 0f;
                Die();
            }
        }

        /// <summary>
        /// Get current HP.
        /// </summary>
        public int GetCurrentHp()
        {
            return Mathf.CeilToInt(_currentHp);
        }

        /// <summary>
        /// Check if this hero is still alive.
        /// </summary>
        public bool IsAlive()
        {
            return _state != CharacterState.Dead && _currentHp > 0f;
        }

        /// <summary>
        /// Manually set the attack target.
        /// </summary>
        public void SetTarget(EnemyController target)
        {
            _target = target;
        }

        /// <summary>
        /// Handle hero death.
        /// </summary>
        public void Die()
        {
            if (_state == CharacterState.Dead) return;

            _state = CharacterState.Dead;
            _currentHp = 0f;

            if (_animator != null)
            {
                _animator.SetBool("IsAlive", false);
                _animator.SetTrigger("Die");
            }

            EventManager.Publish(GameConstants.Events.OnHeroDie, _heroId);
        }

        /// <summary>
        /// Reset this character for reuse (e.g., next battle).
        /// </summary>
        public void ResetBattle()
        {
            _state = CharacterState.Idle;
            _currentHp = _stats.hp;
            _attackTimer = 0f;
            _target = null;

            if (_animator != null)
            {
                _animator.SetBool("IsAlive", true);
            }
        }

        #endregion

        #region Unity Lifecycle

        private void Update()
        {
            if (!_isInitialized || _state == CharacterState.Dead) return;
            if (_state == CharacterState.UsingSkill) return;

            UpdateCombatAI();
        }

        #endregion

        #region Private Methods - Combat AI

        private void UpdateCombatAI()
        {
            // Find target if none or target is dead
            if (_target == null || !_target.IsAlive())
            {
                _target = FindNearestEnemy();
            }

            if (_target == null)
            {
                SetState(CharacterState.Idle);
                return;
            }

            float distance = Vector3.Distance(transform.position, _target.transform.position);

            if (distance <= _stats.attackRange)
            {
                SetState(CharacterState.Attacking);
                UpdateAttack();
            }
            else
            {
                SetState(CharacterState.Moving);
                MoveToTarget();
            }
        }

        private void MoveToTarget()
        {
            if (_target == null) return;

            Vector3 direction = (_target.transform.position - transform.position).normalized;
            transform.position += direction * _stats.moveSpeed * Time.deltaTime;

            // Face target
            if (direction.x != 0f)
            {
                Vector3 scale = transform.localScale;
                scale.x = direction.x < 0f ? -Mathf.Abs(scale.x) : Mathf.Abs(scale.x);
                transform.localScale = scale;
            }
        }

        private void UpdateAttack()
        {
            _attackTimer += Time.deltaTime;

            if (_attackTimer >= 1f / _stats.attackSpeed)
            {
                _attackTimer = 0f;
                DoAttack();
            }
        }

        private void DoAttack()
        {
            if (_target == null || !_target.IsAlive()) return;

            if (_animator != null)
            {
                _animator.SetTrigger("Attack");
            }

            // Calculate damage
            var result = DamageCalculator.Calculate(_stats, _target.GetStats());
            _target.TakeDamage(result.amount);

            // Try skill usage
            TryUseSkill();
        }

        private void TryUseSkill()
        {
            if (!SkillManager.HasInstance) return;

            var skills = SkillManager.Instance.GetHeroSkills(_heroId);
            if (skills == null) return;

            foreach (var skill in skills)
            {
                if (SkillManager.Instance.CanActivate(_heroId, skill.skillId))
                {
                    StartCoroutine(UseSkillRoutine(skill));
                    break;
                }
            }
        }

        private IEnumerator UseSkillRoutine(SkillData skill)
        {
            _state = CharacterState.UsingSkill;

            if (_animator != null)
            {
                _animator.SetTrigger("Skill");
            }

            EventManager.Publish(GameConstants.Events.OnSkillActivated, (_heroId, skill.skillId));

            // Skill damage
            if (_target != null && _target.IsAlive())
            {
                var result = DamageCalculator.CalculateSkill(_stats, _target.GetStats(), skill);
                _target.TakeDamage(result.amount);
            }

            SkillManager.Instance.ResetCooldown(_heroId, skill.skillId);

            // Skill animation duration
            yield return new WaitForSeconds(0.5f);

            if (_state != CharacterState.Dead)
            {
                _state = CharacterState.Idle;
            }
        }

        private EnemyController FindNearestEnemy()
        {
            if (!BattleManager.HasInstance) return null;

            var enemies = BattleManager.Instance.GetAliveEnemies();
            if (enemies == null || enemies.Count == 0) return null;

            EnemyController nearest = null;
            float minDistance = float.MaxValue;

            foreach (var enemy in enemies)
            {
                if (enemy == null || !enemy.IsAlive()) continue;

                float dist = Vector3.Distance(transform.position, enemy.transform.position);
                if (dist < minDistance)
                {
                    minDistance = dist;
                    nearest = enemy;
                }
            }

            return nearest;
        }

        private void SetState(CharacterState newState)
        {
            if (_state == newState || _state == CharacterState.Dead) return;

            _state = newState;

            if (_animator != null)
            {
                _animator.SetBool("IsMoving", _state == CharacterState.Moving);
                _animator.SetBool("IsAttacking", _state == CharacterState.Attacking);
            }
        }

        #endregion
    }

    /// <summary>
    /// Enemy stats structure used by DamageCalculator.
    /// </summary>
    [System.Serializable]
    public struct EnemyStats
    {
        public string enemyId;
        public float atk;
        public float def;
        public float hp;
        public GameConstants.AttributeType attribute;
        public float attackSpeed;
        public float attackRange;
        public float moveSpeed;
    }

    /// <summary>
    /// Result of a damage calculation.
    /// </summary>
    public struct DamageResult
    {
        public int amount;
        public bool isCritical;
        public GameConstants.AttributeType attribute;
    }

    /// <summary>
    /// Static damage calculator (no singleton needed).
    /// </summary>
    public static class DamageCalculator
    {
        /// <summary>
        /// Calculate normal attack damage.
        /// </summary>
        public static DamageResult Calculate(HeroStats attacker, EnemyStats defender)
        {
            float baseDamage = Mathf.Max(1f, attacker.atk - defender.def);

            float attrMult = GetAttributeMultiplier(attacker.attribute, defender.attribute);
            bool isCrit = IsCritical(attacker.critRate);
            float critMult = isCrit ? GameConstants.Battle.CriticalDamageMultiplier : 1f;

            // Apply variance
            float variance = 1f + Random.Range(-GameConstants.Battle.BaseDamageVariance, GameConstants.Battle.BaseDamageVariance);
            float finalDamage = baseDamage * attrMult * critMult * variance;

            return new DamageResult
            {
                amount = Mathf.Max(1, Mathf.RoundToInt(finalDamage)),
                isCritical = isCrit,
                attribute = attacker.attribute
            };
        }

        /// <summary>
        /// Calculate skill-based damage.
        /// </summary>
        public static DamageResult CalculateSkill(HeroStats attacker, EnemyStats defender, SkillData skill)
        {
            float baseDamage = Mathf.Max(1f, attacker.atk - defender.def);
            float skillMultiplier = skill != null ? skill.damage : 1f;

            float attrMult = GetAttributeMultiplier(attacker.attribute, defender.attribute);
            bool isCrit = IsCritical(attacker.critRate);
            float critMult = isCrit ? GameConstants.Battle.CriticalDamageMultiplier : 1f;

            float finalDamage = baseDamage * skillMultiplier * attrMult * critMult;

            return new DamageResult
            {
                amount = Mathf.Max(1, Mathf.RoundToInt(finalDamage)),
                isCritical = isCrit,
                attribute = attacker.attribute
            };
        }

        /// <summary>
        /// Get attribute advantage/disadvantage multiplier.
        /// Fire > Earth > Water > Fire (triangle), Light/Dark counter each other.
        /// </summary>
        public static float GetAttributeMultiplier(GameConstants.AttributeType atkAttr, GameConstants.AttributeType defAttr)
        {
            if (atkAttr == defAttr) return 1f;

            // Fire > Earth > Water > Fire
            if ((atkAttr == GameConstants.AttributeType.Fire && defAttr == GameConstants.AttributeType.Earth) ||
                (atkAttr == GameConstants.AttributeType.Earth && defAttr == GameConstants.AttributeType.Water) ||
                (atkAttr == GameConstants.AttributeType.Water && defAttr == GameConstants.AttributeType.Fire))
            {
                return GameConstants.Battle.AttributeAdvantage;
            }

            if ((defAttr == GameConstants.AttributeType.Fire && atkAttr == GameConstants.AttributeType.Earth) ||
                (defAttr == GameConstants.AttributeType.Earth && atkAttr == GameConstants.AttributeType.Water) ||
                (defAttr == GameConstants.AttributeType.Water && atkAttr == GameConstants.AttributeType.Fire))
            {
                return GameConstants.Battle.AttributeDisadvantage;
            }

            // Light <-> Dark mutual advantage
            if ((atkAttr == GameConstants.AttributeType.Light && defAttr == GameConstants.AttributeType.Dark) ||
                (atkAttr == GameConstants.AttributeType.Dark && defAttr == GameConstants.AttributeType.Light))
            {
                return GameConstants.Battle.AttributeAdvantage;
            }

            return 1f;
        }

        /// <summary>
        /// Roll critical hit chance.
        /// </summary>
        public static bool IsCritical(float critRate)
        {
            return Random.Range(0f, 1f) < critRate;
        }
    }

    /// <summary>
    /// Placeholder for SkillManager singleton access from Battle namespace.
    /// The actual SkillManager is in a separate file.
    /// </summary>
    public class SkillManager : Singleton<SkillManager>
    {
        public virtual List<SkillData> GetHeroSkills(string heroId) => null;
        public virtual bool CanActivate(string heroId, string skillId) => false;
        public virtual void ResetCooldown(string heroId, string skillId) { }
        public virtual float GetCooldownRemain(string heroId, string skillId) => 0f;
    }

    /// <summary>
    /// Enemy controller interface for battle targets.
    /// Implemented by EnemyController MonoBehaviour.
    /// </summary>
    public class EnemyController : MonoBehaviour
    {
        #region Fields

        [SerializeField] private Animator _animator;
        [SerializeField] private Transform _hitPoint;

        private string _enemyId;
        private EnemyStats _stats;
        private float _currentHp;
        private bool _isAlive = true;

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize enemy with chart data.
        /// </summary>
        public virtual void Init(EnemyData enemyData)
        {
            if (enemyData == null) return;

            _enemyId = enemyData.enemyId;
            _stats = new EnemyStats
            {
                enemyId = enemyData.enemyId,
                atk = enemyData.atk,
                def = enemyData.def,
                hp = enemyData.hp,
                attackSpeed = enemyData.attackSpeed,
                attackRange = enemyData.attackRange,
                moveSpeed = enemyData.moveSpeed
            };
            _currentHp = _stats.hp;
            _isAlive = true;
        }

        /// <summary>
        /// Get current enemy stats.
        /// </summary>
        public EnemyStats GetStats() => _stats;

        /// <summary>
        /// Check if this enemy is alive.
        /// </summary>
        public bool IsAlive() => _isAlive;

        /// <summary>
        /// Apply damage to this enemy.
        /// </summary>
        public virtual void TakeDamage(int amount)
        {
            if (!_isAlive) return;

            _currentHp -= amount;

            if (_animator != null)
            {
                _animator.SetTrigger("Hit");
            }

            if (_currentHp <= 0f)
            {
                _currentHp = 0f;
                Die();
            }
        }

        /// <summary>
        /// Handle enemy death.
        /// </summary>
        protected virtual void Die()
        {
            _isAlive = false;

            if (_animator != null)
            {
                _animator.SetTrigger("Die");
            }

            EventManager.Publish(GameConstants.Events.OnEnemyDie, gameObject);
        }

        #endregion
    }
}
