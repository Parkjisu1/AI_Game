using System.Collections.Generic;
using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Loads and caches level data from JSON resources on demand.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Provider | Phase: 1
    /// LevelData and CellInfo structs are defined in GridManager.cs
    /// </remarks>
    public class LevelDataProvider : MonoBehaviour
    {
        #region Fields

        [SerializeField] private int totalLevelCount = 5;
        [SerializeField] private bool useSampleLevels = true;

        private readonly Dictionary<int, LevelData> _cache = new Dictionary<int, LevelData>();

        private const string LEVEL_PATH_PREFIX = "Levels/Level_";

        #endregion

        #region Properties

        public int TotalLevelCount => totalLevelCount;

        #endregion

        #region Public Methods

        /// <summary>
        /// Loads a level from JSON resource and caches it. Returns the loaded LevelData.
        /// </summary>
        public LevelData LoadLevel(int levelNumber)
        {
            if (!IsLevelValid(levelNumber))
            {
                Debug.LogWarning($"[LevelDataProvider] Invalid level number: {levelNumber}");
                return default;
            }

            if (_cache.TryGetValue(levelNumber, out var cached))
            {
                return cached;
            }

            string path = LEVEL_PATH_PREFIX + levelNumber;
            var textAsset = Resources.Load<TextAsset>(path);

            if (textAsset == null)
            {
                if (useSampleLevels)
                {
                    LevelData sampleLevel = GenerateSampleLevel(levelNumber);
                    if (sampleLevel != null)
                    {
                        _cache[levelNumber] = sampleLevel;
                        return sampleLevel;
                    }
                }
                Debug.LogError($"[LevelDataProvider] Failed to load level resource: {path}");
                return default;
            }

            LevelData levelData;
            try
            {
                levelData = JsonUtility.FromJson<LevelData>(textAsset.text);
            }
            catch (System.Exception e)
            {
                Debug.LogError($"[LevelDataProvider] Failed to parse level {levelNumber}: {e.Message}");
                Resources.UnloadAsset(textAsset);
                return default;
            }

            Resources.UnloadAsset(textAsset);
            _cache[levelNumber] = levelData;

            return levelData;
        }

        /// <summary>
        /// Returns cached LevelData if available, otherwise loads it.
        /// </summary>
        public LevelData GetLevelData(int levelNumber)
        {
            if (_cache.TryGetValue(levelNumber, out var cached))
            {
                return cached;
            }

            return LoadLevel(levelNumber);
        }

        /// <summary>
        /// Returns the total number of levels available.
        /// </summary>
        public int GetTotalLevelCount()
        {
            return totalLevelCount;
        }

        /// <summary>
        /// Checks if the given level number is within valid range.
        /// </summary>
        public bool IsLevelValid(int levelNumber)
        {
            return levelNumber >= 1 && levelNumber <= totalLevelCount;
        }

        /// <summary>
        /// Removes a specific level from the cache.
        /// </summary>
        public void UnloadLevel(int levelNumber)
        {
            _cache.Remove(levelNumber);
        }

        /// <summary>
        /// Clears the entire level cache.
        /// </summary>
        public void ClearCache()
        {
            _cache.Clear();
        }

        #endregion

        #region Sample Levels

        private LevelData GenerateSampleLevel(int levelNumber)
        {
            switch (levelNumber)
            {
                case 1: return CreateLevel1();
                case 2: return CreateLevel2();
                case 3: return CreateLevel3();
                case 4: return CreateLevel4();
                case 5: return CreateLevel5();
                default: return CreateLevel1(); // fallback
            }
        }

        // Level 1: 3x3, one red cat slides down to red hole. Tutorial.
        private LevelData CreateLevel1()
        {
            int w = 3, h = 3;
            var cells = CreateEmptyGrid(w, h);
            SetCat(cells, 1, 2, CatColor.Red);
            SetHole(cells, 1, 0, CatColor.Red);
            return new LevelData { levelNumber = 1, gridWidth = w, gridHeight = h, maxMoves = 5, cells = cells };
        }

        // Level 2: 4x4, two cats (red, blue) slide down to matching holes.
        private LevelData CreateLevel2()
        {
            int w = 4, h = 4;
            var cells = CreateEmptyGrid(w, h);
            SetCat(cells, 1, 3, CatColor.Red);
            SetCat(cells, 2, 3, CatColor.Blue);
            SetHole(cells, 1, 0, CatColor.Red);
            SetHole(cells, 2, 0, CatColor.Blue);
            return new LevelData { levelNumber = 2, gridWidth = w, gridHeight = h, maxMoves = 8, cells = cells };
        }

        // Level 3: 5x5, two cats with wall barriers requiring lateral movement.
        private LevelData CreateLevel3()
        {
            int w = 5, h = 5;
            var cells = CreateEmptyGrid(w, h);
            SetCat(cells, 0, 4, CatColor.Red);
            SetCat(cells, 4, 4, CatColor.Blue);
            SetWall(cells, 2, 3);
            SetWall(cells, 2, 1);
            SetHole(cells, 0, 0, CatColor.Red);
            SetHole(cells, 4, 0, CatColor.Blue);
            return new LevelData { levelNumber = 3, gridWidth = w, gridHeight = h, maxMoves = 10, cells = cells };
        }

        // Level 4: 5x5, three cats, more complex navigation.
        private LevelData CreateLevel4()
        {
            int w = 5, h = 5;
            var cells = CreateEmptyGrid(w, h);
            SetCat(cells, 1, 4, CatColor.Red);
            SetCat(cells, 3, 4, CatColor.Green);
            SetCat(cells, 2, 2, CatColor.Blue);
            SetWall(cells, 0, 2);
            SetWall(cells, 4, 2);
            SetHole(cells, 0, 0, CatColor.Green);
            SetHole(cells, 2, 0, CatColor.Blue);
            SetHole(cells, 4, 0, CatColor.Red);
            return new LevelData { levelNumber = 4, gridWidth = w, gridHeight = h, maxMoves = 12, cells = cells };
        }

        // Level 5: 6x6, three cats with walls forming a maze.
        private LevelData CreateLevel5()
        {
            int w = 6, h = 6;
            var cells = CreateEmptyGrid(w, h);
            SetCat(cells, 0, 5, CatColor.Red);
            SetCat(cells, 5, 5, CatColor.Blue);
            SetCat(cells, 2, 3, CatColor.Yellow);
            SetWall(cells, 1, 4);
            SetWall(cells, 4, 4);
            SetWall(cells, 1, 2);
            SetWall(cells, 4, 2);
            SetHole(cells, 0, 0, CatColor.Blue);
            SetHole(cells, 2, 0, CatColor.Yellow);
            SetHole(cells, 5, 0, CatColor.Red);
            return new LevelData { levelNumber = 5, gridWidth = w, gridHeight = h, maxMoves = 15, cells = cells };
        }

        private CellInfo[][] CreateEmptyGrid(int w, int h)
        {
            var cells = new CellInfo[h][];
            for (int y = 0; y < h; y++)
            {
                cells[y] = new CellInfo[w];
                for (int x = 0; x < w; x++)
                {
                    cells[y][x] = new CellInfo
                    {
                        cellType = CellType.Normal,
                        occupantType = CellOccupant.None,
                        occupantColor = CatColor.Red,
                        isLocked = false
                    };
                }
            }
            return cells;
        }

        private void SetCat(CellInfo[][] cells, int x, int y, CatColor color)
        {
            cells[y][x].occupantType = CellOccupant.Cat;
            cells[y][x].occupantColor = color;
        }

        private void SetHole(CellInfo[][] cells, int x, int y, CatColor color)
        {
            cells[y][x].cellType = CellType.Hole;
            cells[y][x].occupantColor = color;
        }

        private void SetWall(CellInfo[][] cells, int x, int y)
        {
            cells[y][x].cellType = CellType.Wall;
        }

        #endregion
    }
}
