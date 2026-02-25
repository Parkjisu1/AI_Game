using System;
using System.Collections.Generic;
using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Processes tile slide logic: calculates target positions, animates slides via TileController,
    /// tracks move history for undo, and notifies obstacles of passage.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Processor | Phase: 2
    /// </remarks>
    public class SlideProcessor : Singleton<SlideProcessor>
    {
        #region Fields

        private readonly Stack<SlideRecord> _moveHistory = new Stack<SlideRecord>();
        private readonly Dictionary<Vector2Int, TileController> _tileMap =
            new Dictionary<Vector2Int, TileController>();
        private bool _isProcessing;

        #endregion

        #region Properties

        public bool IsProcessing => _isProcessing;

        #endregion

        #region Public Methods

        /// <summary>
        /// Register a tile at a grid position for lookup during slide processing.
        /// </summary>
        public void RegisterTile(Vector2Int gridPos, TileController tile)
        {
            if (tile == null) return;
            _tileMap[gridPos] = tile;
        }

        /// <summary>
        /// Unregister a tile from the grid position map.
        /// </summary>
        public void UnregisterTile(Vector2Int gridPos)
        {
            _tileMap.Remove(gridPos);
        }

        /// <summary>
        /// Clear all registered tiles.
        /// </summary>
        public void ClearTileMap()
        {
            _tileMap.Clear();
        }

        /// <summary>
        /// Process a slide from tileGridPos in the given direction.
        /// Validates the slide, calculates target, updates grid, animates via TileController,
        /// and publishes events on completion.
        /// </summary>
        public void ProcessSlide(Vector2Int tileGridPos, SlideDirection direction)
        {
            if (_isProcessing) return;
            if (GridManager.Instance == null) return;

            if (!CanSlide(tileGridPos, direction)) return;

            Vector2Int targetPos = CalculateSlideTarget(tileGridPos, direction);

            // No movement: target is same as start
            if (targetPos == tileGridPos) return;

            _isProcessing = true;

            // Get the tile controller at the current position
            CellData fromCell = GridManager.Instance.GetCell(tileGridPos.x, tileGridPos.y);
            int tileId = tileGridPos.x + tileGridPos.y * GridManager.Instance.GridWidth;

            // Record for undo
            SlideRecord record = new SlideRecord
            {
                tileId = tileId,
                fromPos = tileGridPos,
                toPos = targetPos,
                direction = direction,
                occupantType = fromCell.occupantType,
                occupantColor = fromCell.occupantColor
            };
            _moveHistory.Push(record);

            // Update grid state: clear source, occupy target
            GridManager.Instance.SetCellOccupant(tileGridPos.x, tileGridPos.y, CellOccupant.None);
            GridManager.Instance.SetCellOccupant(targetPos.x, targetPos.y, fromCell.occupantType);

            // Update tile map registration
            TileController tile = null;
            _tileMap.TryGetValue(tileGridPos, out tile);
            if (tile != null)
            {
                _tileMap.Remove(tileGridPos);
                _tileMap[targetPos] = tile;
            }

            // Calculate world position for animation
            Vector3 targetWorldPos = GridManager.Instance.GridToWorld(targetPos.x, targetPos.y);

            // Notify obstacles along the path
            NotifyObstaclesAlongPath(tileGridPos, targetPos, direction);

            // Play SFX
            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlaySFX("tile_slide");
            }

            // Animate via TileController
            if (tile != null && tile.CanSlide)
            {
                tile.SlideTo(targetWorldPos, () => OnSlideAnimationComplete(record));
            }
            else
            {
                // No tile controller available, complete immediately
                OnSlideAnimationComplete(record);
            }
        }

        /// <summary>
        /// Check if a tile at the given position can slide in the given direction.
        /// </summary>
        public bool CanSlide(Vector2Int tileGridPos, SlideDirection direction)
        {
            if (GridManager.Instance == null) return false;
            if (!GridManager.Instance.IsInBounds(tileGridPos.x, tileGridPos.y)) return false;

            CellData cell = GridManager.Instance.GetCell(tileGridPos.x, tileGridPos.y);

            // Must have a slideable occupant (Hole type tiles slide)
            if (cell.cellType == CellType.Wall || cell.cellType == CellType.Empty) return false;
            if (cell.state == CellState.Blocked) return false;
            if (cell.isLocked) return false;

            // Check TileController state if registered
            if (_tileMap.TryGetValue(tileGridPos, out TileController tile))
            {
                if (!tile.CanSlide) return false;
            }

            // Check arrow direction restriction
            if (ObstacleManager.HasInstance)
            {
                SlideDirection? arrow = ObstacleManager.Instance.GetArrowDirection(
                    tileGridPos.x, tileGridPos.y);
                if (arrow.HasValue && arrow.Value != direction) return false;
            }

            // Check if there's at least one cell to slide into
            Vector2Int nextPos = tileGridPos + GetDirectionVector(direction);
            if (!GridManager.Instance.IsInBounds(nextPos.x, nextPos.y)) return false;
            if (!GridManager.Instance.IsWalkable(nextPos.x, nextPos.y)) return false;

            // Check obstacle at next position
            if (ObstacleManager.HasInstance)
            {
                if (!ObstacleManager.Instance.CanSlideThrough(nextPos.x, nextPos.y, direction))
                {
                    return false;
                }
            }

            return true;
        }

        /// <summary>
        /// Calculate the target position for a slide from fromPos in the given direction.
        /// Advances cell by cell until hitting a wall, occupied cell, obstacle, or grid boundary.
        /// </summary>
        public Vector2Int CalculateSlideTarget(Vector2Int fromPos, SlideDirection direction)
        {
            if (GridManager.Instance == null) return fromPos;

            Vector2Int dirVec = GetDirectionVector(direction);
            Vector2Int current = fromPos;
            Vector2Int next = current + dirVec;

            while (GridManager.Instance.IsInBounds(next.x, next.y))
            {
                // Check if next cell is walkable
                if (!GridManager.Instance.IsWalkable(next.x, next.y)) break;

                // Check if next cell is empty (no occupant)
                if (!GridManager.Instance.IsEmpty(next.x, next.y)) break;

                // Check obstacle passability
                if (ObstacleManager.HasInstance)
                {
                    if (!ObstacleManager.Instance.CanSlideThrough(next.x, next.y, direction))
                    {
                        break;
                    }
                }

                current = next;
                next = current + dirVec;
            }

            return current;
        }

        /// <summary>
        /// Undo the last slide by reversing grid state, restoring occupants,
        /// and moving the tile back via TileController.
        /// </summary>
        public void UndoLastSlide()
        {
            if (_moveHistory.Count == 0) return;
            if (_isProcessing) return;
            if (GridManager.Instance == null) return;

            _isProcessing = true;

            SlideRecord record = _moveHistory.Pop();

            // Reverse grid state: clear target, restore source
            GridManager.Instance.SetCellOccupant(record.toPos.x, record.toPos.y, CellOccupant.None);
            GridManager.Instance.SetCellOccupant(
                record.fromPos.x, record.fromPos.y, record.occupantType);

            // Update tile map registration
            TileController tile = null;
            _tileMap.TryGetValue(record.toPos, out tile);
            if (tile != null)
            {
                _tileMap.Remove(record.toPos);
                _tileMap[record.fromPos] = tile;

                Vector3 fromWorldPos = GridManager.Instance.GridToWorld(
                    record.fromPos.x, record.fromPos.y);
                tile.SlideTo(fromWorldPos, () => { _isProcessing = false; });
            }
            else
            {
                _isProcessing = false;
            }

            // Play undo SFX
            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlaySFX("tile_undo");
            }
        }

        /// <summary>
        /// Get the move history as a list (most recent first).
        /// </summary>
        public List<SlideRecord> GetMoveHistory()
        {
            return new List<SlideRecord>(_moveHistory);
        }

        /// <summary>
        /// Clear the move history.
        /// </summary>
        public void ClearHistory()
        {
            _moveHistory.Clear();
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Called when slide animation completes. Publishes events.
        /// </summary>
        private void OnSlideAnimationComplete(SlideRecord record)
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnSlideComplete
                {
                    TileId = record.tileId,
                    FromPos = record.fromPos,
                    ToPos = record.toPos,
                    Direction = record.direction
                });

                EventManager.Instance.Publish(new OnMovePerformed());
            }

            _isProcessing = false;
        }

        /// <summary>
        /// Notify ObstacleManager for each cell along the slide path.
        /// </summary>
        private void NotifyObstaclesAlongPath(
            Vector2Int from, Vector2Int to, SlideDirection direction)
        {
            if (!ObstacleManager.HasInstance) return;

            Vector2Int dirVec = GetDirectionVector(direction);
            Vector2Int current = from + dirVec;

            int maxSteps = GridManager.Instance != null
                ? GridManager.Instance.GridWidth + GridManager.Instance.GridHeight
                : 100;
            int steps = 0;

            while (current != to && steps < maxSteps)
            {
                ObstacleManager.Instance.OnTilePassedOver(current.x, current.y);
                current += dirVec;
                steps++;
            }

            // Also notify the destination cell
            ObstacleManager.Instance.OnTilePassedOver(to.x, to.y);
        }

        /// <summary>
        /// Convert SlideDirection to a Vector2Int direction vector.
        /// </summary>
        private Vector2Int GetDirectionVector(SlideDirection direction)
        {
            switch (direction)
            {
                case SlideDirection.Up:    return Vector2Int.up;
                case SlideDirection.Down:  return Vector2Int.down;
                case SlideDirection.Left:  return Vector2Int.left;
                case SlideDirection.Right: return Vector2Int.right;
                default:                   return Vector2Int.zero;
            }
        }

        #endregion
    }

    #region Slide Data Types

    /// <summary>
    /// Records a single slide move for undo support.
    /// </summary>
    [Serializable]
    public struct SlideRecord
    {
        public int tileId;
        public Vector2Int fromPos;
        public Vector2Int toPos;
        public SlideDirection direction;
        public CellOccupant occupantType;
        public CatColor occupantColor;
    }

    #endregion
}
