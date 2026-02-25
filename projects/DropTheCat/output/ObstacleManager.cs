using System;
using System.Collections.Generic;
using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Manages obstacle state, portal pairs, switch links, ice durability, and arrow directions.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Manager | Phase: 2
    /// </remarks>
    public class ObstacleManager : Singleton<ObstacleManager>
    {
        #region Fields

        private readonly Dictionary<Vector2Int, ObstacleData> _obstacleMap =
            new Dictionary<Vector2Int, ObstacleData>();

        private readonly Dictionary<Vector2Int, Vector2Int> _portalPairs =
            new Dictionary<Vector2Int, Vector2Int>();

        private readonly Dictionary<Vector2Int, List<Vector2Int>> _switchLinks =
            new Dictionary<Vector2Int, List<Vector2Int>>();

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Subscribe<OnCatDropped>(OnCatDroppedHandler);
            }
        }

        protected override void OnDestroy()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Unsubscribe<OnCatDropped>(OnCatDroppedHandler);
            }
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize obstacles from level data. Scans cells and builds obstacle map,
        /// portal pairs, and switch links.
        /// </summary>
        public void InitObstacles(LevelData levelData)
        {
            ClearObstacles();

            if (levelData == null || levelData.cells == null) return;
            if (GridManager.Instance == null) return;

            for (int y = 0; y < levelData.gridHeight; y++)
            {
                if (y >= levelData.cells.Length) break;
                CellInfo[] row = levelData.cells[y];
                if (row == null) continue;

                for (int x = 0; x < levelData.gridWidth; x++)
                {
                    if (x >= row.Length) break;

                    CellInfo info = row[x];
                    ObstacleType obsType = CellTypeToObstacleType(info.cellType);
                    if (obsType == ObstacleType.None) continue;

                    Vector2Int pos = new Vector2Int(x, y);
                    ObstacleData data = new ObstacleData
                    {
                        type = obsType,
                        durability = GetDefaultDurability(obsType),
                        arrowDirection = null,
                        position = pos
                    };

                    _obstacleMap[pos] = data;
                }
            }

            // Build portal pairs from obstacle map
            BuildPortalPairs();
        }

        /// <summary>
        /// Check if a tile can slide through the given position in the given direction.
        /// Walls always block. Ice allows passage. Lock blocks if locked.
        /// OneWay checks arrow direction.
        /// </summary>
        public bool CanSlideThrough(int x, int y, SlideDirection direction)
        {
            Vector2Int pos = new Vector2Int(x, y);

            if (!_obstacleMap.TryGetValue(pos, out ObstacleData obstacle))
            {
                return true;
            }

            switch (obstacle.type)
            {
                case ObstacleType.Wall:
                    return false;

                case ObstacleType.Ice:
                    return true;

                case ObstacleType.Lock:
                    return obstacle.durability <= 0;

                case ObstacleType.OneWay:
                    if (obstacle.arrowDirection.HasValue)
                    {
                        return obstacle.arrowDirection.Value == direction;
                    }
                    return true;

                case ObstacleType.Portal:
                    return true;

                case ObstacleType.Switch:
                    return true;

                default:
                    return true;
            }
        }

        /// <summary>
        /// Called when a tile passes over a position. Handles ice durability and switch activation.
        /// </summary>
        public void OnTilePassedOver(int x, int y)
        {
            Vector2Int pos = new Vector2Int(x, y);

            if (!_obstacleMap.TryGetValue(pos, out ObstacleData obstacle)) return;

            switch (obstacle.type)
            {
                case ObstacleType.Ice:
                    HandleIceDamage(pos, obstacle);
                    break;

                case ObstacleType.Switch:
                    HandleSwitchActivation(pos);
                    break;
            }
        }

        /// <summary>
        /// Get obstacle data at the given position.
        /// Returns default ObstacleData (type=None) if no obstacle exists.
        /// </summary>
        public ObstacleData GetObstacle(int x, int y)
        {
            Vector2Int pos = new Vector2Int(x, y);
            if (_obstacleMap.TryGetValue(pos, out ObstacleData data))
            {
                return data;
            }
            return default;
        }

        /// <summary>
        /// Check if an obstacle exists at the given position.
        /// </summary>
        public bool HasObstacle(int x, int y)
        {
            return _obstacleMap.ContainsKey(new Vector2Int(x, y));
        }

        /// <summary>
        /// Get the linked portal position for the given portal.
        /// Returns a list containing the paired portal position, or empty list if not a portal.
        /// </summary>
        public List<Vector2Int> GetPortalPair(Vector2Int portalPos)
        {
            var result = new List<Vector2Int>();
            if (_portalPairs.TryGetValue(portalPos, out Vector2Int paired))
            {
                result.Add(paired);
            }
            return result;
        }

        /// <summary>
        /// Get the arrow direction at the given position, if it's a OneWay obstacle.
        /// Returns null if no arrow exists.
        /// </summary>
        public SlideDirection? GetArrowDirection(int x, int y)
        {
            Vector2Int pos = new Vector2Int(x, y);
            if (_obstacleMap.TryGetValue(pos, out ObstacleData data))
            {
                return data.arrowDirection;
            }
            return null;
        }

        /// <summary>
        /// Clear all obstacle data.
        /// </summary>
        public void ClearObstacles()
        {
            _obstacleMap.Clear();
            _portalPairs.Clear();
            _switchLinks.Clear();
        }

        /// <summary>
        /// Register a portal pair (bidirectional).
        /// </summary>
        public void RegisterPortalPair(Vector2Int portalA, Vector2Int portalB)
        {
            _portalPairs[portalA] = portalB;
            _portalPairs[portalB] = portalA;
        }

        /// <summary>
        /// Register a switch-to-targets link.
        /// </summary>
        public void RegisterSwitchLink(Vector2Int switchPos, List<Vector2Int> targets)
        {
            if (targets == null || targets.Count == 0) return;
            _switchLinks[switchPos] = new List<Vector2Int>(targets);
        }

        /// <summary>
        /// Set the arrow direction for a OneWay obstacle.
        /// </summary>
        public void SetArrowDirection(int x, int y, SlideDirection direction)
        {
            Vector2Int pos = new Vector2Int(x, y);
            if (!_obstacleMap.TryGetValue(pos, out ObstacleData data)) return;

            data.arrowDirection = direction;
            _obstacleMap[pos] = data;
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Handle ice tile damage: reduce durability, destroy if zero.
        /// </summary>
        private void HandleIceDamage(Vector2Int pos, ObstacleData obstacle)
        {
            obstacle.durability--;
            _obstacleMap[pos] = obstacle;

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnObstacleStateChanged
                {
                    X = pos.x,
                    Y = pos.y,
                    ObstacleType = ObstacleType.Ice,
                    NewState = obstacle.durability
                });
            }

            if (obstacle.durability <= 0)
            {
                _obstacleMap.Remove(pos);

                if (GridManager.HasInstance)
                {
                    GridManager.Instance.SetCellState(pos.x, pos.y, CellState.Empty);
                }
            }
        }

        /// <summary>
        /// Handle switch activation: toggle linked locks/blockers.
        /// </summary>
        private void HandleSwitchActivation(Vector2Int switchPos)
        {
            if (!_switchLinks.TryGetValue(switchPos, out List<Vector2Int> targets)) return;

            for (int i = 0; i < targets.Count; i++)
            {
                Vector2Int targetPos = targets[i];
                if (!_obstacleMap.TryGetValue(targetPos, out ObstacleData targetObs)) continue;

                if (targetObs.type == ObstacleType.Lock)
                {
                    targetObs.durability = 0;
                    _obstacleMap[targetPos] = targetObs;

                    if (GridManager.HasInstance)
                    {
                        GridManager.Instance.SetCellState(targetPos.x, targetPos.y, CellState.Empty);
                    }

                    if (EventManager.HasInstance)
                    {
                        EventManager.Instance.Publish(new OnTileUnlocked
                        {
                            X = targetPos.x,
                            Y = targetPos.y
                        });
                    }
                }
            }
        }

        /// <summary>
        /// Handle cat drop event: check if adjacent locked tiles should unlock.
        /// </summary>
        private void OnCatDroppedHandler(OnCatDropped evt)
        {
            CheckAdjacentLocks(evt.Position);
        }

        /// <summary>
        /// Check four-directional neighbors for lock obstacles and unlock them
        /// if their durability reaches zero.
        /// </summary>
        private void CheckAdjacentLocks(Vector2Int center)
        {
            Vector2Int[] neighbors = new Vector2Int[]
            {
                center + Vector2Int.up,
                center + Vector2Int.down,
                center + Vector2Int.left,
                center + Vector2Int.right
            };

            for (int i = 0; i < neighbors.Length; i++)
            {
                Vector2Int pos = neighbors[i];
                if (!_obstacleMap.TryGetValue(pos, out ObstacleData obs)) continue;
                if (obs.type != ObstacleType.Lock) continue;

                obs.durability--;
                _obstacleMap[pos] = obs;

                if (obs.durability <= 0)
                {
                    _obstacleMap.Remove(pos);

                    if (GridManager.HasInstance)
                    {
                        GridManager.Instance.SetCellState(pos.x, pos.y, CellState.Empty);
                    }

                    if (EventManager.HasInstance)
                    {
                        EventManager.Instance.Publish(new OnTileUnlocked
                        {
                            X = pos.x,
                            Y = pos.y
                        });
                    }
                }
                else
                {
                    if (EventManager.HasInstance)
                    {
                        EventManager.Instance.Publish(new OnObstacleStateChanged
                        {
                            X = pos.x,
                            Y = pos.y,
                            ObstacleType = ObstacleType.Lock,
                            NewState = obs.durability
                        });
                    }
                }
            }
        }

        /// <summary>
        /// Build portal pairs by scanning obstacle map for portal-type obstacles.
        /// Portals are paired in the order they are found.
        /// </summary>
        private void BuildPortalPairs()
        {
            var portalList = new List<Vector2Int>();
            foreach (var kvp in _obstacleMap)
            {
                if (kvp.Value.type == ObstacleType.Portal)
                {
                    portalList.Add(kvp.Key);
                }
            }

            // Pair portals sequentially (0-1, 2-3, ...)
            for (int i = 0; i + 1 < portalList.Count; i += 2)
            {
                RegisterPortalPair(portalList[i], portalList[i + 1]);
            }
        }

        /// <summary>
        /// Convert CellType to ObstacleType. Returns None for non-obstacle cell types.
        /// </summary>
        private ObstacleType CellTypeToObstacleType(CellType cellType)
        {
            switch (cellType)
            {
                case CellType.Wall:     return ObstacleType.Wall;
                case CellType.Ice:      return ObstacleType.Ice;
                case CellType.Lock:     return ObstacleType.Lock;
                case CellType.Portal:   return ObstacleType.Portal;
                case CellType.Obstacle: return ObstacleType.Wall;
                default:                return ObstacleType.None;
            }
        }

        /// <summary>
        /// Get default durability for an obstacle type.
        /// </summary>
        private int GetDefaultDurability(ObstacleType type)
        {
            switch (type)
            {
                case ObstacleType.Ice:  return 2;
                case ObstacleType.Lock: return 1;
                default:                return 0;
            }
        }

        #endregion
    }

    #region Obstacle Data Types

    /// <summary>
    /// Runtime data for a single obstacle on the grid.
    /// </summary>
    [Serializable]
    public struct ObstacleData
    {
        public ObstacleType type;
        public int durability;
        public SlideDirection? arrowDirection;
        public Vector2Int position;
    }

    #endregion
}
