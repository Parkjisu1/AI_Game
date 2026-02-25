using System.Collections.Generic;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Manages the grid/layout of all bottles in a level.
    /// Responsible for spawning, positioning, querying, and clearing bottles.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Manager
    /// Phase: 1
    /// </remarks>
    public class BottleCollection : MonoBehaviour
    {
        #region Fields

        [Header("References")]
        [SerializeField] private Transform _bottleParent;
        [SerializeField] private BottleItem _bottlePrefab;

        [Header("Layout")]
        [SerializeField] private float _horizontalSpacing = 1.5f;
        [SerializeField] private float _verticalSpacing = 2.5f;
        [SerializeField] private int _maxPerRow = 5;

        private List<BottleItem> _bottles = new List<BottleItem>();
        private Pool<BottleItem> _pool;

        #endregion

        #region Properties

        /// <summary>Number of active bottles.</summary>
        public int Count => _bottles != null ? _bottles.Count : 0;

        #endregion

        #region Public Methods

        /// <summary>
        /// Initializes the collection from a LevelModel. Spawns all bottles, including empty ones.
        /// </summary>
        /// <param name="model">The level data defining bottles.</param>
        /// <param name="pool">Optional object pool for bottle reuse. Pass null to use Instantiate.</param>
        public void Initialize(LevelModel model, Pool<BottleItem> pool = null)
        {
            if (model == null)
            {
                Debug.LogError("[BottleCollection] Null LevelModel passed to Initialize.");
                return;
            }

            Clear();
            _pool = pool;

            Transform parent = _bottleParent != null ? _bottleParent : transform;

            // Spawn configured bottles
            if (model.Bottles != null)
            {
                for (int i = 0; i < model.Bottles.Count; i++)
                {
                    BottleItem bottle = SpawnBottle(parent);
                    if (bottle != null)
                    {
                        bottle.Initialize(model.Bottles[i]);
                        _bottles.Add(bottle);
                    }
                }
            }

            // Spawn empty bottles
            for (int i = 0; i < model.EmptyBottleCount; i++)
            {
                BottleItem bottle = SpawnBottle(parent);
                if (bottle != null)
                {
                    BottleConfig emptyConfig = new BottleConfig(4, null);
                    bottle.Initialize(emptyConfig);
                    _bottles.Add(bottle);
                }
            }

            ArrangeBottles();
        }

        /// <summary>
        /// Returns a read-only list of all active bottles.
        /// </summary>
        public List<BottleItem> GetAllBottles()
        {
            return _bottles;
        }

        /// <summary>
        /// Returns the bottle at the specified index, or null if out of range.
        /// </summary>
        /// <param name="index">Zero-based bottle index.</param>
        public BottleItem GetBottleAt(int index)
        {
            if (_bottles == null || index < 0 || index >= _bottles.Count)
            {
                return null;
            }
            return _bottles[index];
        }

        /// <summary>
        /// Returns the index of a given bottle, or -1 if not found.
        /// </summary>
        /// <param name="bottle">The bottle to find.</param>
        public int GetBottleIndex(BottleItem bottle)
        {
            if (_bottles == null || bottle == null)
            {
                return -1;
            }
            return _bottles.IndexOf(bottle);
        }

        /// <summary>
        /// Checks if all bottles are either complete (full + monochromatic) or empty.
        /// </summary>
        public bool AreAllBottlesComplete()
        {
            if (_bottles == null || _bottles.Count == 0)
            {
                return false;
            }

            for (int i = 0; i < _bottles.Count; i++)
            {
                if (_bottles[i] == null)
                {
                    continue;
                }

                if (!_bottles[i].IsComplete)
                {
                    return false;
                }
            }

            return true;
        }

        /// <summary>
        /// Checks if any valid pour move exists among all bottles.
        /// </summary>
        public bool HasValidMove()
        {
            if (_bottles == null || _bottles.Count < 2)
            {
                return false;
            }

            for (int i = 0; i < _bottles.Count; i++)
            {
                BottleItem origin = _bottles[i];
                if (origin == null || !origin.CanPourFrom())
                {
                    continue;
                }

                // Skip completed bottles - no need to pour from them
                if (origin.IsComplete)
                {
                    continue;
                }

                WaterColor topColor = origin.GetTopColor();

                for (int j = 0; j < _bottles.Count; j++)
                {
                    if (i == j)
                    {
                        continue;
                    }

                    BottleItem target = _bottles[j];
                    if (target == null)
                    {
                        continue;
                    }

                    if (target.CanReceive(topColor))
                    {
                        // Avoid pointless move: pouring into empty bottle from a monochromatic source
                        if (target.IsEmpty() && origin.IsMonochromatic())
                        {
                            continue;
                        }

                        return true;
                    }
                }
            }

            return false;
        }

        /// <summary>
        /// Clears all bottles, returning them to pool or destroying them.
        /// </summary>
        public void Clear()
        {
            if (_bottles == null)
            {
                return;
            }

            for (int i = 0; i < _bottles.Count; i++)
            {
                if (_bottles[i] == null)
                {
                    continue;
                }

                _bottles[i].Reset();

                if (_pool != null)
                {
                    _pool.Return(_bottles[i]);
                }
                else
                {
                    Destroy(_bottles[i].gameObject);
                }
            }

            _bottles.Clear();
        }

        #endregion

        #region Private Methods

        private BottleItem SpawnBottle(Transform parent)
        {
            if (_pool != null)
            {
                BottleItem pooled = _pool.Get();
                if (pooled != null)
                {
                    pooled.transform.SetParent(parent);
                    return pooled;
                }
            }

            if (_bottlePrefab == null)
            {
                Debug.LogError("[BottleCollection] Bottle prefab is not assigned.");
                return null;
            }

            BottleItem instance = Instantiate(_bottlePrefab, parent);
            return instance;
        }

        /// <summary>
        /// Arranges bottles in a grid layout centered on the parent.
        /// </summary>
        private void ArrangeBottles()
        {
            if (_bottles == null || _bottles.Count == 0)
            {
                return;
            }

            int bottleCount = _bottles.Count;
            int perRow = Mathf.Min(bottleCount, _maxPerRow);
            int rowCount = Mathf.CeilToInt((float)bottleCount / perRow);

            float totalWidth = (perRow - 1) * _horizontalSpacing;
            float totalHeight = (rowCount - 1) * _verticalSpacing;

            float startX = -totalWidth * 0.5f;
            float startY = totalHeight * 0.5f;

            for (int i = 0; i < bottleCount; i++)
            {
                if (_bottles[i] == null)
                {
                    continue;
                }

                int col = i % perRow;
                int row = i / perRow;

                // Center the last row if it has fewer items
                float rowOffset = 0f;
                if (row == rowCount - 1)
                {
                    int itemsInLastRow = bottleCount - (row * perRow);
                    if (itemsInLastRow < perRow)
                    {
                        rowOffset = (perRow - itemsInLastRow) * _horizontalSpacing * 0.5f;
                    }
                }

                float x = startX + (col * _horizontalSpacing) + rowOffset;
                float y = startY - (row * _verticalSpacing);

                _bottles[i].transform.localPosition = new Vector3(x, y, 0f);
                _bottles[i].gameObject.name = $"Bottle_{i}";
            }
        }

        #endregion
    }
}
