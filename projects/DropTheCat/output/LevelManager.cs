using System;
using System.Collections.Generic;
using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Manages level flow: loading, clearing, failing, retrying, and progress persistence.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Manager | Phase: 2
    /// </remarks>
    public class LevelManager : Singleton<LevelManager>
    {
        #region Enums

        public enum LevelState
        {
            Loading,
            Playing,
            Cleared,
            Failed
        }

        #endregion

        #region Constants

        private const string SAVE_KEY = "LevelProgress";

        #endregion

        #region Fields

        [SerializeField] private LevelDataProvider levelDataProvider;

        private LevelState _currentState;
        private int _currentLevel;
        private int _maxClearedLevel;
        private Dictionary<int, int> _starsByLevel = new Dictionary<int, int>();

        #endregion

        #region Properties

        public int CurrentLevel => _currentLevel;
        public int MaxClearedLevel => _maxClearedLevel;
        public LevelState CurrentState => _currentState;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            LoadProgress();
        }

        private void OnEnable()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Subscribe<OnLevelCleared>(HandleLevelCleared);
                EventManager.Instance.Subscribe<OnLevelFailed>(HandleLevelFailed);
            }
        }

        protected override void OnDestroy()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Unsubscribe<OnLevelCleared>(HandleLevelCleared);
                EventManager.Instance.Unsubscribe<OnLevelFailed>(HandleLevelFailed);
            }

            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Loads the specified level. Fetches data from LevelDataProvider and initializes the grid.
        /// </summary>
        public void LoadLevel(int levelNumber)
        {
            if (levelDataProvider == null)
            {
                Debug.LogError("[LevelManager] LevelDataProvider is not assigned.");
                return;
            }

            if (!levelDataProvider.IsLevelValid(levelNumber))
            {
                Debug.LogWarning($"[LevelManager] Invalid level number: {levelNumber}");
                return;
            }

            _currentState = LevelState.Loading;
            _currentLevel = levelNumber;

            LevelData levelData = levelDataProvider.LoadLevel(levelNumber);
            if (levelData == null)
            {
                Debug.LogError($"[LevelManager] Failed to load level data for level {levelNumber}.");
                return;
            }

            if (GridManager.HasInstance)
            {
                GridManager.Instance.ClearGrid();
                GridManager.Instance.InitGrid(levelData);
            }

            _currentState = LevelState.Playing;

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnLevelLoaded
                {
                    LevelNumber = levelNumber
                });
            }
        }

        /// <summary>
        /// Retries the current level by reloading it.
        /// </summary>
        public void RetryLevel()
        {
            if (_currentLevel <= 0) return;

            LoadLevel(_currentLevel);
        }

        /// <summary>
        /// Advances to and loads the next level.
        /// </summary>
        public void NextLevel()
        {
            int next = _currentLevel + 1;

            if (levelDataProvider != null && !levelDataProvider.IsLevelValid(next))
            {
                Debug.LogWarning($"[LevelManager] No next level available. Current: {_currentLevel}");
                return;
            }

            LoadLevel(next);
        }

        /// <summary>
        /// Returns the star count earned for a specific level. 0 if not cleared.
        /// </summary>
        public int GetStars(int levelNumber)
        {
            if (_starsByLevel.TryGetValue(levelNumber, out int stars))
            {
                return stars;
            }
            return 0;
        }

        /// <summary>
        /// Returns the total stars earned across all levels.
        /// </summary>
        public int GetTotalStars()
        {
            int total = 0;
            foreach (var kvp in _starsByLevel)
            {
                total += kvp.Value;
            }
            return total;
        }

        /// <summary>
        /// Checks if a level is unlocked. Level 1 is always unlocked.
        /// Subsequent levels unlock when the previous level is cleared.
        /// </summary>
        public bool IsLevelUnlocked(int levelNumber)
        {
            if (levelNumber <= 1) return true;
            return levelNumber <= _maxClearedLevel + 1;
        }

        #endregion

        #region Private Methods

        private void HandleLevelCleared(OnLevelCleared eventData)
        {
            _currentState = LevelState.Cleared;

            // Update star record (keep best)
            int previousStars = GetStars(_currentLevel);
            if (eventData.Stars > previousStars)
            {
                _starsByLevel[_currentLevel] = eventData.Stars;
            }

            // Update max cleared level
            if (_currentLevel > _maxClearedLevel)
            {
                _maxClearedLevel = _currentLevel;
            }

            SaveProgress();
            PublishProgressUpdated();
        }

        private void HandleLevelFailed(OnLevelFailed eventData)
        {
            _currentState = LevelState.Failed;
        }

        private void LoadProgress()
        {
            if (!SaveManager.HasInstance) return;

            _maxClearedLevel = SaveManager.Instance.LoadInt("MaxClearedLevel", 0);

            var savedData = SaveManager.Instance.Load<LevelProgressData>(SAVE_KEY);
            if (savedData != null && savedData.levelNumbers != null && savedData.starValues != null)
            {
                int count = Mathf.Min(savedData.levelNumbers.Length, savedData.starValues.Length);
                _starsByLevel.Clear();
                for (int i = 0; i < count; i++)
                {
                    _starsByLevel[savedData.levelNumbers[i]] = savedData.starValues[i];
                }
            }
        }

        private void SaveProgress()
        {
            if (!SaveManager.HasInstance) return;

            SaveManager.Instance.SaveInt("MaxClearedLevel", _maxClearedLevel);

            var saveData = new LevelProgressData();
            int count = _starsByLevel.Count;
            saveData.levelNumbers = new int[count];
            saveData.starValues = new int[count];

            int index = 0;
            foreach (var kvp in _starsByLevel)
            {
                saveData.levelNumbers[index] = kvp.Key;
                saveData.starValues[index] = kvp.Value;
                index++;
            }

            SaveManager.Instance.Save(SAVE_KEY, saveData);
        }

        private void PublishProgressUpdated()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnLevelProgressUpdated
                {
                    MaxClearedLevel = _maxClearedLevel,
                    TotalStars = GetTotalStars()
                });
            }
        }

        #endregion

        #region Save Data

        /// <summary>
        /// Serializable save data for level progress.
        /// Uses parallel arrays because JsonUtility does not support Dictionary.
        /// </summary>
        [Serializable]
        private class LevelProgressData
        {
            public int[] levelNumbers;
            public int[] starValues;
        }

        #endregion
    }
}
