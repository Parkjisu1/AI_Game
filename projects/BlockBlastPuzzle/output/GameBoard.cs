using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using BlockBlast.Core;

namespace BlockBlast.Domain
{
    public class GameBoard : Singleton<GameBoard>
    {
        public const int BOARD_SIZE = 8;
        public const float CELL_SIZE = 0.9f;
        public const float CELL_GAP = 0.1f;
        public const float TOTAL_CELL = CELL_SIZE + CELL_GAP;

        private Game.CellVisual[,] _cells;
        private bool[,] _occupied;
        private Transform _boardParent;
        private Vector3 _boardOrigin;

        public Vector3 BoardOrigin => _boardOrigin;

        public void InitBoard(Vector3 centerPosition)
        {
            _cells = new Game.CellVisual[BOARD_SIZE, BOARD_SIZE];
            _occupied = new bool[BOARD_SIZE, BOARD_SIZE];

            float boardWidth = BOARD_SIZE * TOTAL_CELL - CELL_GAP;
            _boardOrigin = centerPosition - new Vector3(boardWidth / 2f, boardWidth / 2f, 0);

            Debug.Log($"[GameBoard] InitBoard: center={centerPosition}, origin={_boardOrigin}, boardWidth={boardWidth}");

            _boardParent = new GameObject("Board").transform;
            _boardParent.position = Vector3.zero;

            // Create background panel
            var bgGo = new GameObject("BoardBackground");
            bgGo.transform.SetParent(_boardParent);
            var bgSr = bgGo.AddComponent<SpriteRenderer>();
            bgSr.sprite = Game.SpriteFactory.CreateSquareSprite(64, new Color(0.1f, 0.1f, 0.15f, 1f));
            float bgSize = boardWidth + 0.4f;
            bgGo.transform.localScale = new Vector3(bgSize, bgSize, 1f);
            bgGo.transform.position = centerPosition;
            bgSr.sortingOrder = -1;

            Sprite cellSprite = Game.SpriteFactory.CreateRoundedSprite(64, Color.white, 8);

            for (int y = 0; y < BOARD_SIZE; y++)
            {
                for (int x = 0; x < BOARD_SIZE; x++)
                {
                    var cellGo = new GameObject($"Cell_{x}_{y}");
                    cellGo.transform.SetParent(_boardParent);
                    cellGo.transform.position = GridToWorld(new Vector2Int(x, y));
                    cellGo.transform.localScale = Vector3.one * CELL_SIZE;

                    var cell = cellGo.AddComponent<Game.CellVisual>();
                    cell.Init(new Vector2Int(x, y), cellSprite);

                    _cells[x, y] = cell;
                    _occupied[x, y] = false;
                }
            }
        }

        public bool CanPlaceBlock(BlockShape shape, Vector2Int gridPos)
        {
            if (shape == null || _occupied == null) return false;
            foreach (var cell in shape.Cells)
            {
                int gx = gridPos.x + cell.x;
                int gy = gridPos.y + cell.y;
                if (gx < 0 || gx >= BOARD_SIZE || gy < 0 || gy >= BOARD_SIZE)
                    return false;
                if (_occupied[gx, gy])
                    return false;
            }
            return true;
        }

        public bool PlaceBlock(BlockShape shape, Vector2Int gridPos, Color color)
        {
            if (_occupied == null || !CanPlaceBlock(shape, gridPos)) return false;

            foreach (var cell in shape.Cells)
            {
                int gx = gridPos.x + cell.x;
                int gy = gridPos.y + cell.y;
                _occupied[gx, gy] = true;
                _cells[gx, gy].SetOccupied(color);
            }

            EventManager.Instance.Publish(EventManager.EVT_BLOCK_PLACED);
            return true;
        }

        public int CheckAndClearLines()
        {
            List<int> fullRows = new List<int>();
            List<int> fullCols = new List<int>();

            // Check rows
            for (int y = 0; y < BOARD_SIZE; y++)
            {
                bool full = true;
                for (int x = 0; x < BOARD_SIZE; x++)
                {
                    if (!_occupied[x, y]) { full = false; break; }
                }
                if (full) fullRows.Add(y);
            }

            // Check columns
            for (int x = 0; x < BOARD_SIZE; x++)
            {
                bool full = true;
                for (int y = 0; y < BOARD_SIZE; y++)
                {
                    if (!_occupied[x, y]) { full = false; break; }
                }
                if (full) fullCols.Add(x);
            }

            int totalLines = fullRows.Count + fullCols.Count;

            if (totalLines > 0)
            {
                // Collect positions for effects
                List<Vector3> clearPositions = new List<Vector3>();

                foreach (int y in fullRows)
                {
                    for (int x = 0; x < BOARD_SIZE; x++)
                    {
                        clearPositions.Add(GridToWorld(new Vector2Int(x, y)));
                        _cells[x, y].PlayClearAnimation();
                        _occupied[x, y] = false;
                    }
                }

                foreach (int x in fullCols)
                {
                    for (int y = 0; y < BOARD_SIZE; y++)
                    {
                        if (!fullRows.Contains(y)) // Avoid double-clearing
                        {
                            clearPositions.Add(GridToWorld(new Vector2Int(x, y)));
                            _cells[x, y].PlayClearAnimation();
                        }
                        _occupied[x, y] = false;
                    }
                }

                // Reset cells that were in cleared columns but not cleared rows
                foreach (int x in fullCols)
                {
                    for (int y = 0; y < BOARD_SIZE; y++)
                    {
                        if (fullRows.Contains(y)) continue;
                        // Already handled above
                    }
                }

                Game.EffectManager.Instance.PlayLineClearEffect(clearPositions);
                EventManager.Instance.Publish(EventManager.EVT_LINE_CLEAR, totalLines);
            }

            return totalLines;
        }

        public void ShowPreview(BlockShape shape, Vector2Int gridPos, bool valid)
        {
            ClearPreview();
            if (shape == null || _cells == null) return;

            foreach (var cell in shape.Cells)
            {
                int gx = gridPos.x + cell.x;
                int gy = gridPos.y + cell.y;
                if (gx >= 0 && gx < BOARD_SIZE && gy >= 0 && gy < BOARD_SIZE)
                {
                    _cells[gx, gy].SetPreview(valid);
                }
            }
        }

        public void ClearPreview()
        {
            if (_cells == null) return;
            for (int y = 0; y < BOARD_SIZE; y++)
                for (int x = 0; x < BOARD_SIZE; x++)
                    _cells[x, y].ClearPreview();
        }

        public Vector2Int WorldToGrid(Vector3 worldPos)
        {
            Vector3 local = worldPos - _boardOrigin;
            int gx = Mathf.FloorToInt(local.x / TOTAL_CELL);
            int gy = Mathf.FloorToInt(local.y / TOTAL_CELL);
            return new Vector2Int(gx, gy);
        }

        public Vector3 GridToWorld(Vector2Int gridPos)
        {
            return _boardOrigin + new Vector3(
                gridPos.x * TOTAL_CELL + CELL_SIZE / 2f,
                gridPos.y * TOTAL_CELL + CELL_SIZE / 2f,
                0
            );
        }

        public bool HasValidPlacement(BlockShape shape)
        {
            if (_occupied == null) return false;
            for (int y = 0; y < BOARD_SIZE; y++)
                for (int x = 0; x < BOARD_SIZE; x++)
                    if (CanPlaceBlock(shape, new Vector2Int(x, y)))
                        return true;
            return false;
        }

        public void ClearBoard()
        {
            if (_cells == null) return;
            for (int y = 0; y < BOARD_SIZE; y++)
            {
                for (int x = 0; x < BOARD_SIZE; x++)
                {
                    _occupied[x, y] = false;
                    _cells[x, y].SetEmpty();
                }
            }
        }

        public void ClearBottomRows(int rowCount)
        {
            for (int y = 0; y < Mathf.Min(rowCount, BOARD_SIZE); y++)
            {
                for (int x = 0; x < BOARD_SIZE; x++)
                {
                    _occupied[x, y] = false;
                    if (_cells[x, y].IsOccupied)
                        _cells[x, y].PlayClearAnimation();
                }
            }
        }

        public bool IsOccupied(int x, int y)
        {
            if (_occupied == null || x < 0 || x >= BOARD_SIZE || y < 0 || y >= BOARD_SIZE) return true;
            return _occupied[x, y];
        }
    }
}
