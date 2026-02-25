using System.Collections.Generic;
using UnityEngine;
using DropTheCat.Core;
using DropTheCat.Domain;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Spawns and manages visual GameObjects for the grid based on GridManager data.
    /// Handles tiles, cats, holes, walls, ground, and hole markers.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Handler | Phase: 1
    /// </remarks>
    public class GridVisualizer : MonoBehaviour
    {
        #region Fields

        [Header("Prefab References")]
        [SerializeField] private TileController tilePrefab;
        [SerializeField] private CatController catPrefab;
        [SerializeField] private HoleController holePrefab;
        [SerializeField] private SpriteRenderer groundPrefab;
        [SerializeField] private SpriteRenderer wallPrefab;
        [SerializeField] private SpriteRenderer holeMarkerPrefab;

        [Header("Visual Settings")]
        [SerializeField] private Color groundColor = new Color(0.9f, 0.9f, 0.85f);
        [SerializeField] private Color wallColor = new Color(0.3f, 0.3f, 0.3f);
        [SerializeField] private Color holeMarkerColor = new Color(0.2f, 0.2f, 0.2f);
        [SerializeField] private float holeMarkerScale = 0.6f;
        [SerializeField] private float catScale = 0.7f;

        private bool _isInitialized;

        #endregion

        #region Unity Lifecycle

        private void Start()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Subscribe<OnGridInitialized>(OnGridInitializedHandler);
            }

            // Check if GridManager already has data
            if (GridManager.HasInstance && GridManager.Instance.GridWidth > 0)
            {
                SpawnGrid();
            }
        }

        private void OnDestroy()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Unsubscribe<OnGridInitialized>(OnGridInitializedHandler);
            }
        }

        #endregion

        #region Event Handlers

        /// <summary>
        /// Handle OnGridInitialized event by clearing and spawning visuals.
        /// </summary>
        private void OnGridInitializedHandler(OnGridInitialized evt)
        {
            ClearVisuals();
            SpawnGrid();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Clear all spawned visuals and reset processor states.
        /// </summary>
        public void ClearVisuals()
        {
            if (ObjectPool.HasInstance)
            {
                ObjectPool.Instance.ReleaseAll();
            }

            if (SlideProcessor.HasInstance)
            {
                SlideProcessor.Instance.ClearTileMap();
            }

            if (DropProcessor.HasInstance)
            {
                DropProcessor.Instance.ClearTrackedObjects();
            }

            _isInitialized = false;
        }

        /// <summary>
        /// Spawn visual GameObjects for the entire grid based on GridManager data.
        /// </summary>
        public void SpawnGrid()
        {
            if (!GridManager.HasInstance)
            {
                Debug.LogWarning("[GridVisualizer] GridManager not available.");
                return;
            }

            if (_isInitialized)
            {
                Debug.LogWarning("[GridVisualizer] Grid already spawned. Call ClearVisuals() first.");
                return;
            }

            int width = GridManager.Instance.GridWidth;
            int height = GridManager.Instance.GridHeight;

            if (width <= 0 || height <= 0)
            {
                Debug.LogWarning($"[GridVisualizer] Invalid grid dimensions: {width}x{height}");
                return;
            }

            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    SpawnCellVisuals(x, y);
                }
            }

            _isInitialized = true;
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Spawn visual elements for a single cell based on its type and occupant.
        /// </summary>
        private void SpawnCellVisuals(int x, int y)
        {
            CellData cell = GridManager.Instance.GetCell(x, y);
            Vector3 worldPos = GridManager.Instance.GridToWorld(x, y);
            Vector2Int gridPos = new Vector2Int(x, y);

            // Wall cells
            if (cell.cellType == CellType.Wall)
            {
                SpawnWall(worldPos);
                return;
            }

            // Empty cells (skip)
            if (cell.cellType == CellType.Empty)
            {
                return;
            }

            // Normal, Hole, and other walkable cells
            SpawnGround(worldPos);

            // If cell type is Hole (target destination), spawn hole marker
            if (cell.cellType == CellType.Hole)
            {
                SpawnHoleMarker(worldPos);
            }

            // Spawn occupants (Cat or Hole tiles)
            if (cell.occupantType == CellOccupant.Cat)
            {
                SpawnTileWithCat(worldPos, gridPos, cell.cellType, cell.occupantColor);
            }
            else if (cell.occupantType == CellOccupant.Hole)
            {
                SpawnTileWithHole(worldPos, gridPos, cell.cellType, cell.occupantColor);
            }
        }

        /// <summary>
        /// Spawn ground background sprite.
        /// </summary>
        private void SpawnGround(Vector3 worldPos)
        {
            if (groundPrefab == null || !ObjectPool.HasInstance) return;

            SpriteRenderer ground = ObjectPool.Instance.Get(groundPrefab);
            if (ground == null) return;

            ground.transform.position = worldPos;
            ground.color = groundColor;
        }

        /// <summary>
        /// Spawn wall sprite.
        /// </summary>
        private void SpawnWall(Vector3 worldPos)
        {
            if (wallPrefab == null || !ObjectPool.HasInstance) return;

            SpriteRenderer wall = ObjectPool.Instance.Get(wallPrefab);
            if (wall == null) return;

            wall.transform.position = worldPos;
            wall.color = wallColor;
        }

        /// <summary>
        /// Spawn hole marker sprite (for CellType.Hole destination cells).
        /// </summary>
        private void SpawnHoleMarker(Vector3 worldPos)
        {
            if (holeMarkerPrefab == null || !ObjectPool.HasInstance) return;

            SpriteRenderer marker = ObjectPool.Instance.Get(holeMarkerPrefab);
            if (marker == null) return;

            marker.transform.position = worldPos;
            marker.transform.localScale = Vector3.one * holeMarkerScale;
            marker.color = holeMarkerColor;
        }

        /// <summary>
        /// Spawn a tile with a cat child.
        /// </summary>
        private void SpawnTileWithCat(Vector3 worldPos, Vector2Int gridPos, CellType cellType, CatColor catColor)
        {
            if (tilePrefab == null || catPrefab == null || !ObjectPool.HasInstance) return;

            // Spawn tile
            TileController tile = ObjectPool.Instance.Get(tilePrefab);
            if (tile == null) return;

            tile.transform.position = worldPos;
            tile.Init(cellType, catColor, gridPos);

            // Register tile with SlideProcessor
            if (SlideProcessor.HasInstance)
            {
                SlideProcessor.Instance.RegisterTile(gridPos, tile);
            }

            // Spawn cat as child
            CatController cat = ObjectPool.Instance.Get(catPrefab);
            if (cat == null) return;

            cat.transform.SetParent(tile.transform, false);
            cat.transform.localPosition = Vector3.zero;
            cat.transform.localScale = Vector3.one * catScale;
            cat.Init(catColor, gridPos);

            // Register cat with DropProcessor
            if (DropProcessor.HasInstance)
            {
                DropProcessor.Instance.RegisterCat(cat);
            }
        }

        /// <summary>
        /// Spawn a tile with a hole child.
        /// </summary>
        private void SpawnTileWithHole(Vector3 worldPos, Vector2Int gridPos, CellType cellType, CatColor holeColor)
        {
            if (tilePrefab == null || holePrefab == null || !ObjectPool.HasInstance) return;

            // Spawn tile
            TileController tile = ObjectPool.Instance.Get(tilePrefab);
            if (tile == null) return;

            tile.transform.position = worldPos;
            tile.Init(cellType, holeColor, gridPos);

            // Register tile with SlideProcessor
            if (SlideProcessor.HasInstance)
            {
                SlideProcessor.Instance.RegisterTile(gridPos, tile);
            }

            // Spawn hole as child
            HoleController hole = ObjectPool.Instance.Get(holePrefab);
            if (hole == null) return;

            hole.transform.SetParent(tile.transform, false);
            hole.transform.localPosition = Vector3.zero;
            hole.Init(holeColor, gridPos);

            // Register hole with DropProcessor
            if (DropProcessor.HasInstance)
            {
                DropProcessor.Instance.RegisterHole(hole);
            }
        }

        #endregion
    }
}
