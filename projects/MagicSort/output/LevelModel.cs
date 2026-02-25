using System;
using System.Collections.Generic;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Complete level definition containing bottle configurations, difficulty, and metadata.
    /// Loaded from LevelDataProvider or generated procedurally.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Config
    /// Phase: 1
    /// </remarks>
    [Serializable]
    public class LevelModel
    {
        #region Fields

        /// <summary>Unique identifier for this level.</summary>
        [SerializeField] private int _levelId;

        /// <summary>Difficulty rating.</summary>
        [SerializeField] private LevelDifficulty _difficulty;

        /// <summary>All bottle configurations for this level.</summary>
        [SerializeField] private List<BottleConfig> _bottles = new List<BottleConfig>();

        /// <summary>Number of empty bottles to add (beyond those in the Bottles list).</summary>
        [SerializeField] private int _emptyBottleCount;

        /// <summary>Par move count (target for star rating).</summary>
        [SerializeField] private int _par;

        /// <summary>Seed string for procedural generation reproducibility.</summary>
        [SerializeField] private string _seedId;

        #endregion

        #region Properties

        /// <summary>Unique level identifier.</summary>
        public int LevelId
        {
            get => _levelId;
            set => _levelId = value;
        }

        /// <summary>Difficulty rating for this level.</summary>
        public LevelDifficulty Difficulty
        {
            get => _difficulty;
            set => _difficulty = value;
        }

        /// <summary>Bottle configurations. Each entry defines a pre-filled or empty bottle.</summary>
        public List<BottleConfig> Bottles
        {
            get => _bottles;
            set => _bottles = value ?? new List<BottleConfig>();
        }

        /// <summary>Additional empty bottles beyond those in the Bottles list.</summary>
        public int EmptyBottleCount
        {
            get => _emptyBottleCount;
            set => _emptyBottleCount = Mathf.Max(0, value);
        }

        /// <summary>Target move count for optimal rating.</summary>
        public int Par
        {
            get => _par;
            set => _par = Mathf.Max(1, value);
        }

        /// <summary>Seed for procedural generation.</summary>
        public string SeedId
        {
            get => _seedId;
            set => _seedId = value ?? string.Empty;
        }

        /// <summary>Total number of bottles (configured + empty).</summary>
        public int TotalBottleCount => (_bottles != null ? _bottles.Count : 0) + _emptyBottleCount;

        #endregion

        #region Constructors

        public LevelModel()
        {
            _levelId = 0;
            _difficulty = LevelDifficulty.Easy;
            _bottles = new List<BottleConfig>();
            _emptyBottleCount = 0;
            _par = 10;
            _seedId = string.Empty;
        }

        public LevelModel(int levelId, LevelDifficulty difficulty, List<BottleConfig> bottles, int emptyBottleCount, int par, string seedId = "")
        {
            _levelId = levelId;
            _difficulty = difficulty;
            _bottles = bottles ?? new List<BottleConfig>();
            _emptyBottleCount = Mathf.Max(0, emptyBottleCount);
            _par = Mathf.Max(1, par);
            _seedId = seedId ?? string.Empty;
        }

        #endregion
    }
}
