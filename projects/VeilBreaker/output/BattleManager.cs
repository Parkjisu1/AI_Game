using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Data;
using VeilBreaker.Character;

namespace VeilBreaker.Battle
{
    /// <summary>
    /// Main battle flow controller managing waves, boss encounters,
    /// hero/enemy lifecycle, speed control, and battle state transitions.
    /// Split into partial classes for maintainability.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 2
    /// </remarks>
    public partial class BattleManager : Singleton<BattleManager>
    {
        #region Fields

        [SerializeField] private EnemySpawner _enemySpawner;
        [SerializeField] private List<Transform> _heroSpawnPoints;
        [SerializeField] private List<Transform> _enemySpawnPoints;

        private StageData _currentStage;
        private GameConstants.BattleState _state = GameConstants.BattleState.Idle;
        private List<CharacterBattle> _heroes = new();
        private float _savedTimeScale = 1f;
        private int _currentWave;
        private int _totalWaves;

        #endregion

        #region Properties

        /// <summary>
        /// Current battle state.
        /// </summary>
        public GameConstants.BattleState State => _state;

        #endregion

        #region Public Methods - Battle Control

        /// <summary>
        /// Initialize and start a battle with the given stage data and hero formation.
        /// </summary>
        /// <param name="stageData">Stage chart data defining enemies and waves.</param>
        /// <param name="heroIds">Hero IDs from CharacterManager formation.</param>
        public void InitBattle(StageData stageData, List<string> heroIds)
        {
            if (stageData == null || heroIds == null || heroIds.Count == 0)
            {
                Debug.LogWarning("[BattleManager] InitBattle called with invalid parameters.");
                return;
            }

            _currentStage = stageData;
            _state = GameConstants.BattleState.Preparing;
            _currentWave = 0;
            _totalWaves = Mathf.Max(1, stageData.enemyCount / 5);

            // Clean up previous battle
            CleanupHeroes();

            // Spawn heroes
            SpawnHeroes(heroIds);

            // Initialize enemy spawner
            if (_enemySpawner != null)
            {
                _enemySpawner.Init(_enemySpawnPoints);
            }

            // Subscribe to events
            EventManager.Subscribe(GameConstants.Events.OnEnemyDie, OnEnemyDied);
            EventManager.Subscribe(GameConstants.Events.OnHeroDie, OnHeroDied);

            EventManager.Publish(GameConstants.Events.OnStageStart, stageData.stageId);

            // Start first wave
            StartCoroutine(StartBattleSequence());
        }

        /// <summary>
        /// Set the battle speed multiplier (1x, 2x, 4x).
        /// </summary>
        public void SetSpeed(float multiplier)
        {
            multiplier = Mathf.Clamp(multiplier, 1f, 4f);
            Time.timeScale = multiplier;
        }

        /// <summary>
        /// Pause the battle.
        /// </summary>
        public void PauseBattle()
        {
            if (_state == GameConstants.BattleState.Idle) return;

            _savedTimeScale = Time.timeScale;
            Time.timeScale = 0f;
        }

        /// <summary>
        /// Resume the battle.
        /// </summary>
        public void ResumeBattle()
        {
            Time.timeScale = _savedTimeScale;
        }

        /// <summary>
        /// Get the current battle state.
        /// </summary>
        public GameConstants.BattleState GetState()
        {
            return _state;
        }

        /// <summary>
        /// Get all alive hero controllers.
        /// </summary>
        public List<CharacterBattle> GetAliveHeroes()
        {
            return _heroes.Where(h => h != null && h.IsAlive()).ToList();
        }

        /// <summary>
        /// Get all alive enemy controllers.
        /// </summary>
        public List<EnemyController> GetAliveEnemies()
        {
            if (_enemySpawner == null) return new List<EnemyController>();
            return _enemySpawner.GetAliveEnemies();
        }

        #endregion

        #region Private Methods - Battle Flow

        private IEnumerator StartBattleSequence()
        {
            // Brief preparation delay
            yield return new WaitForSeconds(0.5f);

            _state = GameConstants.BattleState.Fighting;
            StartNextWave();
        }

        private void StartNextWave()
        {
            _currentWave++;

            if (_currentWave > _totalWaves)
            {
                // All normal waves done, spawn boss
                StartBossPhase();
                return;
            }

            EventManager.Publish(GameConstants.Events.OnWaveStart, _currentWave);

            if (_enemySpawner != null && _currentStage != null)
            {
                var waveData = CreateWaveData(_currentWave);
                _enemySpawner.StartWave(waveData);
            }
        }

        private WaveData CreateWaveData(int waveIndex)
        {
            var waveData = new WaveData
            {
                waveIndex = waveIndex,
                enemyIds = _currentStage.enemyIds ?? new List<string>(),
                enemyCount = Mathf.Max(1, _currentStage.enemyCount / _totalWaves),
                spawnInterval = 0.5f
            };

            return waveData;
        }

        #endregion

        #region Private Methods - Hero Management

        private void SpawnHeroes(List<string> heroIds)
        {
            for (int i = 0; i < heroIds.Count && i < _heroSpawnPoints.Count; i++)
            {
                var heroId = heroIds[i];
                if (!CharacterManager.HasInstance) continue;

                var stats = CharacterManager.Instance.GetFinalStats(heroId);
                var spawnPoint = _heroSpawnPoints[i];

                // CharacterBattle should be pre-placed on hero prefabs or spawned via pool
                // For now, expect them to exist in the scene
                var heroBattle = spawnPoint.GetComponentInChildren<CharacterBattle>();
                if (heroBattle != null)
                {
                    heroBattle.Init(heroId, stats);
                    _heroes.Add(heroBattle);
                }
            }
        }

        private void CleanupHeroes()
        {
            foreach (var hero in _heroes)
            {
                if (hero != null)
                {
                    hero.ResetBattle();
                }
            }
            _heroes.Clear();
        }

        #endregion

        #region Private Methods - Event Handlers

        private void OnEnemyDied(object data)
        {
            if (_state != GameConstants.BattleState.Fighting &&
                _state != GameConstants.BattleState.BossPhase)
                return;

            int aliveCount = _enemySpawner != null ? _enemySpawner.GetAliveEnemyCount() : 0;

            if (aliveCount <= 0)
            {
                if (_state == GameConstants.BattleState.BossPhase)
                {
                    OnBossDefeated();
                }
                else
                {
                    OnWaveCleared();
                }
            }
        }

        private void OnHeroDied(object data)
        {
            var aliveHeroes = GetAliveHeroes();
            if (aliveHeroes.Count <= 0)
            {
                OnBattleFailed();
            }
        }

        private void OnWaveCleared()
        {
            EventManager.Publish(GameConstants.Events.OnWaveComplete, _currentWave);

            // Delay before next wave
            StartCoroutine(DelayedNextWave());
        }

        private IEnumerator DelayedNextWave()
        {
            yield return new WaitForSeconds(1f);
            StartNextWave();
        }

        #endregion

        #region Private Methods - Boss Phase

        private void StartBossPhase()
        {
            if (_currentStage == null || string.IsNullOrEmpty(_currentStage.bossId))
            {
                // No boss, just complete
                OnBattleVictory();
                return;
            }

            _state = GameConstants.BattleState.BossPhase;
            EventManager.Publish(GameConstants.Events.OnBossSpawn);

            if (_enemySpawner != null && _enemySpawnPoints.Count > 0)
            {
                _enemySpawner.SpawnBoss(_currentStage.bossId, _enemySpawnPoints[0]);
            }
        }

        private void OnBossDefeated()
        {
            OnBattleVictory();
        }

        #endregion

        #region Private Methods - Battle End

        private void OnBattleVictory()
        {
            _state = GameConstants.BattleState.Victory;
            Time.timeScale = 1f;

            CalculateRewards();

            EventManager.Publish(GameConstants.Events.OnStageComplete, _currentStage?.stageId);

            Cleanup();
        }

        private void OnBattleFailed()
        {
            _state = GameConstants.BattleState.Defeat;
            Time.timeScale = 1f;

            if (_enemySpawner != null)
            {
                _enemySpawner.StopSpawning();
            }

            EventManager.Publish(GameConstants.Events.OnStageFail, _currentStage?.stageId);

            Cleanup();
        }

        private void Cleanup()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnEnemyDie, OnEnemyDied);
            EventManager.Unsubscribe(GameConstants.Events.OnHeroDie, OnHeroDied);
        }

        #endregion

        #region Private Methods - Rewards

        private void CalculateRewards()
        {
            if (_currentStage == null) return;

            double goldReward = _currentStage.goldReward;
            double expReward = _currentStage.expReward;

            // Apply rewards
            if (CurrencyManager.Instance != null)
            {
                CurrencyManager.Instance.AddCurrency(
                    GameConstants.CurrencyType.Gold,
                    (long)goldReward
                );
            }
        }

        #endregion

        #region Unity Lifecycle

        protected override void OnDestroy()
        {
            Cleanup();
            Time.timeScale = 1f;
            base.OnDestroy();
        }

        #endregion
    }

    /// <summary>
    /// Wave data structure for EnemySpawner.
    /// </summary>
    [System.Serializable]
    public class WaveData
    {
        public int waveIndex;
        public List<string> enemyIds;
        public int enemyCount;
        public float spawnInterval;
    }

    /// <summary>
    /// Enemy spawner component that handles wave-based enemy instantiation.
    /// Managed by BattleManager, uses ObjectPool for efficient spawning.
    /// </summary>
    public class EnemySpawner : MonoBehaviour
    {
        #region Fields

        private List<Transform> _spawnPoints = new();
        private List<EnemyController> _aliveEnemies = new();
        private Coroutine _spawnCoroutine;
        private bool _isSpawning;

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize with spawn point transforms.
        /// </summary>
        public void Init(List<Transform> spawnPoints)
        {
            _spawnPoints = spawnPoints ?? new List<Transform>();
        }

        /// <summary>
        /// Start spawning enemies for a wave.
        /// </summary>
        public void StartWave(WaveData waveData)
        {
            if (waveData == null) return;

            StopSpawning();
            _spawnCoroutine = StartCoroutine(SpawnRoutine(waveData));
        }

        /// <summary>
        /// Spawn a boss enemy at the specified point.
        /// </summary>
        public void SpawnBoss(string bossId, Transform spawnPoint)
        {
            if (string.IsNullOrEmpty(bossId) || spawnPoint == null) return;

            var enemyData = DataManager.Instance?.GetEnemyData(bossId);
            if (enemyData == null) return;

            // Boss has multiplied stats
            var bossData = new EnemyData
            {
                enemyId = enemyData.enemyId,
                name = enemyData.name,
                hp = enemyData.hp * 5f,
                atk = enemyData.atk * 2f,
                def = enemyData.def * 2f,
                moveSpeed = enemyData.moveSpeed * 0.8f,
                attackRange = enemyData.attackRange,
                attackSpeed = enemyData.attackSpeed * 0.8f,
                dropItems = enemyData.dropItems
            };

            SpawnEnemy(bossData, spawnPoint);
        }

        /// <summary>
        /// Stop all spawning coroutines.
        /// </summary>
        public void StopSpawning()
        {
            _isSpawning = false;
            if (_spawnCoroutine != null)
            {
                StopCoroutine(_spawnCoroutine);
                _spawnCoroutine = null;
            }
        }

        /// <summary>
        /// Get count of currently alive enemies.
        /// </summary>
        public int GetAliveEnemyCount()
        {
            _aliveEnemies.RemoveAll(e => e == null || !e.IsAlive());
            return _aliveEnemies.Count;
        }

        /// <summary>
        /// Get list of alive enemy controllers.
        /// </summary>
        public List<EnemyController> GetAliveEnemies()
        {
            _aliveEnemies.RemoveAll(e => e == null || !e.IsAlive());
            return new List<EnemyController>(_aliveEnemies);
        }

        #endregion

        #region Private Methods

        private IEnumerator SpawnRoutine(WaveData waveData)
        {
            _isSpawning = true;
            var wait = new WaitForSeconds(waveData.spawnInterval);

            int spawned = 0;
            while (spawned < waveData.enemyCount && _isSpawning)
            {
                string enemyId = null;
                if (waveData.enemyIds != null && waveData.enemyIds.Count > 0)
                {
                    enemyId = waveData.enemyIds[spawned % waveData.enemyIds.Count];
                }

                if (!string.IsNullOrEmpty(enemyId))
                {
                    var enemyData = DataManager.Instance?.GetEnemyData(enemyId);
                    if (enemyData != null)
                    {
                        var spawnPoint = _spawnPoints.Count > 0
                            ? _spawnPoints[spawned % _spawnPoints.Count]
                            : transform;

                        SpawnEnemy(enemyData, spawnPoint);
                    }
                }

                spawned++;
                yield return wait;
            }

            _isSpawning = false;
        }

        private void SpawnEnemy(EnemyData enemyData, Transform spawnPoint)
        {
            if (!ObjectPool.HasInstance) return;

            var obj = ObjectPool.Instance.Spawn(
                GameConstants.PoolTags.Enemy,
                spawnPoint.position,
                Quaternion.identity
            );

            if (obj == null) return;

            var controller = obj.GetComponent<EnemyController>();
            if (controller != null)
            {
                controller.Init(enemyData);
                _aliveEnemies.Add(controller);
            }
        }

        #endregion
    }
}
