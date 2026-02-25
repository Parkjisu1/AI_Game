using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.Battle
{
    /// <summary>
    /// Manages enemy spawning and wave lifecycle.
    /// Owned and referenced directly by BattleManager (no Singleton - one per battle scene).
    /// Uses ObjectPool for enemy instantiation and despawn.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 2
    /// System: Battle
    /// </remarks>
    public class EnemySpawner : MonoBehaviour
    {
        #region Data Structures

        /// <summary>
        /// Descriptor for a single enemy entry within a wave.
        /// </summary>
        [System.Serializable]
        public struct WaveEnemyEntry
        {
            public string enemyId;
            public int spawnPointIndex;
        }

        /// <summary>
        /// Full wave configuration passed in from BattleManager.
        /// </summary>
        [System.Serializable]
        public class WaveData
        {
            public int waveIndex;
            public List<WaveEnemyEntry> enemies;
            public float spawnInterval;
        }

        #endregion

        #region Fields

        [SerializeField] private float _defaultSpawnInterval = 0.5f;

        private List<Transform>         _spawnPoints  = new();
        private List<EnemyController>   _aliveEnemies = new();
        private Coroutine               _spawnRoutine;
        private bool                    _isSpawning;
        private WaveData                _currentWave;

        #endregion

        #region Unity Lifecycle

        private void OnDisable()
        {
            StopSpawning();
            EventManager.Unsubscribe(GameConstants.Events.OnEnemyDie, OnEnemyDie);
        }

        private void OnEnable()
        {
            EventManager.Subscribe(GameConstants.Events.OnEnemyDie, OnEnemyDie);
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialises the spawner with scene spawn point transforms.
        /// Must be called before StartWave.
        /// </summary>
        /// <param name="spawnPoints">List of world-space spawn transforms.</param>
        public void Init(List<Transform> spawnPoints)
        {
            _spawnPoints = spawnPoints ?? new List<Transform>();
            _aliveEnemies.Clear();
            _isSpawning = false;
            Debug.Log($"[EnemySpawner] Initialised with {_spawnPoints.Count} spawn points.");
        }

        /// <summary>
        /// Starts sequential enemy spawning for the given wave.
        /// Previous spawn routine is stopped before starting a new one.
        /// </summary>
        /// <param name="waveData">Wave configuration including enemy list and intervals.</param>
        public void StartWave(WaveData waveData)
        {
            if (waveData == null)
            {
                Debug.LogWarning("[EnemySpawner] StartWave called with null waveData.");
                return;
            }

            StopSpawning();
            _currentWave = waveData;
            _aliveEnemies.Clear();
            _isSpawning = true;

            EventManager.Publish(GameConstants.Events.OnWaveStart, waveData.waveIndex);
            _spawnRoutine = StartCoroutine(SpawnRoutine(waveData));
        }

        /// <summary>
        /// Spawns a boss enemy at the given spawn point immediately (no coroutine delay).
        /// </summary>
        /// <param name="bossId">Enemy pool tag / ID for the boss.</param>
        /// <param name="spawnPoint">World-space transform to spawn at.</param>
        public void SpawnBoss(string bossId, Transform spawnPoint)
        {
            if (string.IsNullOrEmpty(bossId) || spawnPoint == null)
            {
                Debug.LogWarning("[EnemySpawner] SpawnBoss called with invalid args.");
                return;
            }

            SpawnEnemy(bossId, spawnPoint);
            EventManager.Publish(GameConstants.Events.OnBossSpawn, null);
        }

        /// <summary>
        /// Stops any active spawn coroutine immediately.
        /// Alive enemies remain in scene until explicitly despawned.
        /// </summary>
        public void StopSpawning()
        {
            _isSpawning = false;
            if (_spawnRoutine != null)
            {
                StopCoroutine(_spawnRoutine);
                _spawnRoutine = null;
            }
        }

        /// <summary>
        /// Returns the number of enemies currently alive in the wave.
        /// </summary>
        public int GetAliveEnemyCount() => _aliveEnemies?.Count ?? 0;

        /// <summary>
        /// Returns a copy of the currently alive enemy list.
        /// </summary>
        public List<EnemyController> GetAliveEnemies() => new List<EnemyController>(_aliveEnemies);

        #endregion

        #region Private Methods

        private IEnumerator SpawnRoutine(WaveData wave)
        {
            if (wave.enemies == null || wave.enemies.Count == 0)
            {
                NotifyWaveComplete(wave.waveIndex);
                yield break;
            }

            float interval = wave.spawnInterval > 0f ? wave.spawnInterval : _defaultSpawnInterval;

            foreach (var entry in wave.enemies)
            {
                if (!_isSpawning) yield break;

                var point = GetSpawnPoint(entry.spawnPointIndex);
                if (point != null)
                    SpawnEnemy(entry.enemyId, point);

                yield return new WaitForSeconds(interval);
            }

            _isSpawning = false;

            // Wave complete check deferred to OnEnemyDie listener
            // In case there are 0 enemies, signal immediately
            if (_aliveEnemies.Count == 0)
                NotifyWaveComplete(wave.waveIndex);
        }

        private void SpawnEnemy(string enemyId, Transform spawnPoint)
        {
            if (!ObjectPool.HasInstance)
            {
                Debug.LogWarning("[EnemySpawner] ObjectPool not available.");
                return;
            }

            var obj = ObjectPool.Instance.Spawn(enemyId, spawnPoint.position, Quaternion.identity);
            if (obj == null)
            {
                Debug.LogWarning($"[EnemySpawner] Failed to spawn enemy '{enemyId}' from pool.");
                return;
            }

            var controller = obj.GetComponent<EnemyController>();
            if (controller == null)
            {
                Debug.LogWarning($"[EnemySpawner] No EnemyController on spawned object '{enemyId}'.");
                return;
            }

            if (DataManager.HasInstance)
            {
                var enemyData = DataManager.Instance.GetEnemyData(enemyId);
                controller.Init(enemyData);
            }

            _aliveEnemies.Add(controller);
        }

        private Transform GetSpawnPoint(int index)
        {
            if (_spawnPoints == null || _spawnPoints.Count == 0) return null;
            int safeIndex = Mathf.Clamp(index, 0, _spawnPoints.Count - 1);
            return _spawnPoints[safeIndex];
        }

        private void OnEnemyDie(object data)
        {
            if (data is EnemyController enemy)
            {
                _aliveEnemies.Remove(enemy);
            }
            else
            {
                // Fallback: remove first dead entry
                _aliveEnemies.RemoveAll(e => e == null);
            }

            if (_aliveEnemies.Count == 0 && !_isSpawning && _currentWave != null)
            {
                NotifyWaveComplete(_currentWave.waveIndex);
            }
        }

        private void NotifyWaveComplete(int waveIndex)
        {
            EventManager.Publish(GameConstants.Events.OnWaveComplete, waveIndex);
            Debug.Log($"[EnemySpawner] Wave {waveIndex} complete.");
        }

        #endregion
    }

    /// <summary>
    /// Placeholder for EnemyController. Full definition lives in Battle namespace.
    /// </summary>
    public class EnemyController : MonoBehaviour
    {
        /// <summary>Initialises this enemy from chart data.</summary>
        public virtual void Init(EnemyData data) { }
    }

    /// <summary>
    /// Enemy chart data model. Full definition lives in DataManager.
    /// </summary>
    [System.Serializable]
    public class EnemyData
    {
        public string enemyId;
        public string name;
        public long hp;
        public long atk;
        public long def;
        public GameConstants.AttributeType attribute;
    }
}
