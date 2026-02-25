using System;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Represents a single unit of water inside a bottle.
    /// Contains color, height (layer index), and visibility state.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Config
    /// Phase: 1
    /// </remarks>
    [Serializable]
    public class WaterItem
    {
        #region Fields

        [SerializeField] private WaterColor _color;
        [SerializeField] private int _height;
        [SerializeField] private bool _isVisible;

        #endregion

        #region Properties

        /// <summary>The color of this water unit.</summary>
        public WaterColor Color => _color;

        /// <summary>The layer index (0 = bottom) of this water in its bottle.</summary>
        public int Height => _height;

        /// <summary>Whether this water unit is currently visible (not hidden by a blocker).</summary>
        public bool IsVisible => _isVisible;

        #endregion

        #region Constructors

        public WaterItem()
        {
            _color = WaterColor.None;
            _height = 0;
            _isVisible = true;
        }

        public WaterItem(WaterColor color, int height, bool isVisible = true)
        {
            _color = color;
            _height = height;
            _isVisible = isVisible;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Sets the water color.
        /// </summary>
        /// <param name="color">The new color to assign.</param>
        public void SetColor(WaterColor color)
        {
            _color = color;
        }

        /// <summary>
        /// Sets the layer height index.
        /// </summary>
        /// <param name="height">The new height index (0 = bottom).</param>
        public void SetHeight(int height)
        {
            _height = Mathf.Max(0, height);
        }

        /// <summary>
        /// Sets visibility state (e.g., hidden by blocker).
        /// </summary>
        /// <param name="visible">True if visible.</param>
        public void SetVisible(bool visible)
        {
            _isVisible = visible;
        }

        /// <summary>
        /// Creates a deep copy of this WaterItem.
        /// </summary>
        /// <returns>A new WaterItem with identical values.</returns>
        public WaterItem Clone()
        {
            return new WaterItem(_color, _height, _isVisible);
        }

        public override string ToString()
        {
            return $"[Water: {_color}, H:{_height}, Vis:{_isVisible}]";
        }

        #endregion
    }
}
