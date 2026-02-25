using System;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Serializable configuration for a blocker placed on a bottle.
    /// Defines blocker type, position, size, associated color, and hit points.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Config
    /// Phase: 1
    /// </remarks>
    [Serializable]
    public class BlockerConfig
    {
        #region Fields

        /// <summary>The type of blocker.</summary>
        [SerializeField] private BlockerType _type;

        /// <summary>Position index on the bottle (0 = bottom).</summary>
        [SerializeField] private int _position;

        /// <summary>Width in layers the blocker covers.</summary>
        [SerializeField] private int _width = 1;

        /// <summary>Color associated with this blocker (e.g., for color-match removal).</summary>
        [SerializeField] private WaterColor _associatedColor = WaterColor.None;

        /// <summary>Hit points required to break this blocker.</summary>
        [SerializeField] private int _hp = 1;

        #endregion

        #region Properties

        /// <summary>The blocker type.</summary>
        public BlockerType Type
        {
            get => _type;
            set => _type = value;
        }

        /// <summary>Position index on the bottle.</summary>
        public int Position
        {
            get => _position;
            set => _position = Mathf.Max(0, value);
        }

        /// <summary>Number of layers the blocker covers.</summary>
        public int Width
        {
            get => _width;
            set => _width = Mathf.Max(1, value);
        }

        /// <summary>Color associated with removal condition.</summary>
        public WaterColor AssociatedColor
        {
            get => _associatedColor;
            set => _associatedColor = value;
        }

        /// <summary>Hit points to break.</summary>
        public int HP
        {
            get => _hp;
            set => _hp = Mathf.Max(0, value);
        }

        #endregion

        #region Constructors

        public BlockerConfig()
        {
            _type = BlockerType.Ice;
            _position = 0;
            _width = 1;
            _associatedColor = WaterColor.None;
            _hp = 1;
        }

        public BlockerConfig(BlockerType type, int position, int width = 1, WaterColor associatedColor = WaterColor.None, int hp = 1)
        {
            _type = type;
            _position = Mathf.Max(0, position);
            _width = Mathf.Max(1, width);
            _associatedColor = associatedColor;
            _hp = Mathf.Max(0, hp);
        }

        #endregion
    }
}
