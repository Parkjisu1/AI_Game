using System;
using System.Collections.Generic;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Serializable configuration data for a single bottle in a level.
    /// Defines max height, initial water arrangement, and blockers.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Config
    /// Phase: 1
    /// </remarks>
    [Serializable]
    public class BottleConfig
    {
        #region Fields

        /// <summary>Maximum number of water layers this bottle can hold.</summary>
        [SerializeField] private int _maxHeight = 4;

        /// <summary>Initial water colors from bottom to top.</summary>
        [SerializeField] private List<WaterColor> _initialWaters = new List<WaterColor>();

        /// <summary>Blocker configurations applied to this bottle.</summary>
        [SerializeField] private List<BlockerConfig> _blockers = new List<BlockerConfig>();

        #endregion

        #region Properties

        /// <summary>Maximum water layer count for this bottle.</summary>
        public int MaxHeight
        {
            get => _maxHeight;
            set => _maxHeight = Mathf.Max(1, value);
        }

        /// <summary>Initial water colors from bottom (index 0) to top.</summary>
        public List<WaterColor> InitialWaters
        {
            get => _initialWaters;
            set => _initialWaters = value ?? new List<WaterColor>();
        }

        /// <summary>Blockers attached to this bottle.</summary>
        public List<BlockerConfig> Blockers
        {
            get => _blockers;
            set => _blockers = value ?? new List<BlockerConfig>();
        }

        /// <summary>Whether this bottle starts empty (no initial waters).</summary>
        public bool IsEmpty => _initialWaters == null || _initialWaters.Count == 0;

        #endregion

        #region Constructors

        public BottleConfig()
        {
            _maxHeight = 4;
            _initialWaters = new List<WaterColor>();
            _blockers = new List<BlockerConfig>();
        }

        public BottleConfig(int maxHeight, List<WaterColor> initialWaters, List<BlockerConfig> blockers = null)
        {
            _maxHeight = Mathf.Max(1, maxHeight);
            _initialWaters = initialWaters ?? new List<WaterColor>();
            _blockers = blockers ?? new List<BlockerConfig>();
        }

        #endregion
    }
}
