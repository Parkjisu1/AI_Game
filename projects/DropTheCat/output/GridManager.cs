using System;
using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Manages the 2D grid system: cell data, coordinate conversion, and grid state.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Manager | Phase: 1
    /// </remarks>
    public class GridManager : Singleton<GridManager>
    {
        #region Fields

        [SerializeField] private float cellSize = 1f;

        private CellData[,] _grid;
        private int _gridWidth;
        private int _gridHeight;
        private Vector3 _gridOriginOffset;

        #endregion

        #region Properties

        public int GridWidth => _gridWidth;
        public int GridHeight => _gridHeight;

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize the grid from level data. Creates the CellData array and
        /// maps each cell's type, occupant, and color from LevelData.
        /// </summary>
        public void InitGrid(LevelData levelData)
        {
            if (levelData == null)
            {
                Debug.LogError("[GridManager] InitGrid called with null LevelData.");
                return;
            }

            _gridWidth = levelData.gridWidth;
            _gridHeight = levelData.gridHeight;

            if (_gridWidth <= 0 || _gridHeight <= 0)
            {
                Debug.LogError($"[GridManager] Invalid grid size: {_gridWidth}x{_gridHeight}");
                return;
            }

            _grid = new CellData[_gridWidth, _gridHeight];

            // Calculate origin offset so the grid is centered horizontally
            _gridOriginOffset = new Vector3(
                -(_gridWidth - 1) * cellSize * 0.5f,
                -(_gridHeight - 1) * cellSize * 0.5f,
                0f
            );

            // Map cell info from level data
            for (int y = 0; y < _gridHeight; y++)
            {
                for (int x = 0; x < _gridWidth; x++)
                {
                    CellData cell = new CellData
                    {
                        x = x,
                        y = y,
                        cellType = CellType.Normal,
                        occupantType = CellOccupant.None,
                        occupantColor = CatColor.Red,
                        isLocked = false,
                        state = CellState.Empty
                    };

                    // Apply level data cell info if available
                    if (levelData.cells != null && y < levelData.cells.Length)
                    {
                        CellInfo[] row = levelData.cells[y];
                        if (row != null && x < row.Length)
                        {
                            CellInfo info = row[x];
                            cell.cellType = info.cellType;
                            cell.occupantType = info.occupantType;
                            cell.occupantColor = info.occupantColor;
                            cell.isLocked = info.isLocked;

                            // Derive initial state from cell type and occupant
                            cell.state = DeriveInitialState(cell.cellType, cell.occupantType);
                        }
                    }

                    _grid[x, y] = cell;
                }
            }

            // Publish grid initialized event
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnGridInitialized
                {
                    Width = _gridWidth,
                    Height = _gridHeight
                });
            }
        }

        /// <summary>
        /// Get cell data at the specified grid position.
        /// Returns default CellData if out of bounds.
        /// </summary>
        public CellData GetCell(int x, int y)
        {
            if (!IsInBounds(x, y)) return default;
            return _grid[x, y];
        }

        /// <summary>
        /// Set the runtime state of a cell at the given position.
        /// Publishes OnCellStateChanged event on change.
        /// </summary>
        public void SetCellState(int x, int y, CellState state)
        {
            if (!IsInBounds(x, y)) return;

            CellState oldState = _grid[x, y].state;
            if (oldState == state) return;

            _grid[x, y].state = state;

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnCellStateChanged
                {
                    X = x,
                    Y = y,
                    OldState = oldState,
                    NewState = state
                });
            }
        }

        /// <summary>
        /// Set the occupant of a cell at the given position.
        /// </summary>
        public void SetCellOccupant(int x, int y, CellOccupant occupant)
        {
            if (!IsInBounds(x, y)) return;

            _grid[x, y].occupantType = occupant;

            // Update state based on occupant
            if (occupant == CellOccupant.None)
            {
                _grid[x, y].state = CellState.Empty;
            }
            else
            {
                _grid[x, y].state = CellState.Occupied;
            }
        }

        /// <summary>
        /// Get the occupant type of a cell at the given position.
        /// Returns CellOccupant.None if out of bounds.
        /// </summary>
        public CellOccupant GetCellOccupant(int x, int y)
        {
            if (!IsInBounds(x, y)) return CellOccupant.None;
            return _grid[x, y].occupantType;
        }

        /// <summary>
        /// Check if the given grid coordinates are within bounds.
        /// </summary>
        public bool IsInBounds(int x, int y)
        {
            if (_grid == null) return false;
            return x >= 0 && x < _gridWidth && y >= 0 && y < _gridHeight;
        }

        /// <summary>
        /// Check if a cell is empty (no occupant and cell type allows placement).
        /// </summary>
        public bool IsEmpty(int x, int y)
        {
            if (!IsInBounds(x, y)) return false;

            CellData cell = _grid[x, y];
            return cell.occupantType == CellOccupant.None
                && cell.state == CellState.Empty
                && cell.cellType != CellType.Wall
                && cell.cellType != CellType.Empty;
        }

        /// <summary>
        /// Check if a cell is walkable (cats can slide through it).
        /// </summary>
        public bool IsWalkable(int x, int y)
        {
            if (!IsInBounds(x, y)) return false;

            CellData cell = _grid[x, y];
            return cell.cellType != CellType.Wall
                && cell.cellType != CellType.Empty
                && cell.cellType != CellType.Obstacle
                && cell.state != CellState.Blocked;
        }

        /// <summary>
        /// Convert grid coordinates to world position.
        /// Grid origin is bottom-left, centered around transform position.
        /// </summary>
        public Vector3 GridToWorld(int x, int y)
        {
            return transform.position + _gridOriginOffset + new Vector3(
                x * cellSize,
                y * cellSize,
                0f
            );
        }

        /// <summary>
        /// Convert world position to grid coordinates.
        /// Returns the nearest grid cell, clamped to grid bounds.
        /// </summary>
        public Vector2Int WorldToGrid(Vector3 worldPos)
        {
            Vector3 local = worldPos - transform.position - _gridOriginOffset;

            int x = Mathf.RoundToInt(local.x / cellSize);
            int y = Mathf.RoundToInt(local.y / cellSize);

            x = Mathf.Clamp(x, 0, Mathf.Max(0, _gridWidth - 1));
            y = Mathf.Clamp(y, 0, Mathf.Max(0, _gridHeight - 1));

            return new Vector2Int(x, y);
        }

        /// <summary>
        /// Clear the entire grid, resetting all cells.
        /// </summary>
        public void ClearGrid()
        {
            if (_grid == null) return;

            for (int y = 0; y < _gridHeight; y++)
            {
                for (int x = 0; x < _gridWidth; x++)
                {
                    _grid[x, y] = new CellData
                    {
                        x = x,
                        y = y,
                        cellType = CellType.Empty,
                        occupantType = CellOccupant.None,
                        occupantColor = CatColor.Red,
                        isLocked = false,
                        state = CellState.Empty
                    };
                }
            }

            _gridWidth = 0;
            _gridHeight = 0;
            _grid = null;
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Derive initial cell state from cell type and occupant.
        /// </summary>
        private CellState DeriveInitialState(CellType cellType, CellOccupant occupant)
        {
            if (cellType == CellType.Wall || cellType == CellType.Empty)
            {
                return CellState.Blocked;
            }

            if (occupant != CellOccupant.None)
            {
                return CellState.Occupied;
            }

            return CellState.Empty;
        }

        #endregion
    }

    #region Data Types

    /// <summary>
    /// Describes a single cell in the grid at runtime.
    /// </summary>
    [Serializable]
    public struct CellData
    {
        public int x;
        public int y;
        public CellType cellType;
        public CellOccupant occupantType;
        public CatColor occupantColor;
        public bool isLocked;
        public CellState state;
    }

    /// <summary>
    /// What occupies a cell.
    /// </summary>
    public enum CellOccupant
    {
        None,
        Cat,
        Hole,
        Obstacle
    }

    /// <summary>
    /// Level configuration data. Defines the grid layout for a single level.
    /// Populated by LevelDataProvider and passed to GridManager.InitGrid().
    /// </summary>
    [Serializable]
    public class LevelData
    {
        public int levelNumber;
        public int gridWidth;
        public int gridHeight;
        public int maxMoves;
        public CellInfo[][] cells;
    }

    /// <summary>
    /// Describes a single cell's initial configuration in level data.
    /// </summary>
    [Serializable]
    public struct CellInfo
    {
        public CellType cellType;
        public CellOccupant occupantType;
        public CatColor occupantColor;
        public bool isLocked;
    }

    #endregion
}
