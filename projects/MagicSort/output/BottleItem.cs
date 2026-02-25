using System.Collections.Generic;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Core bottle behaviour. Manages a stack of WaterItems, handles pour in/out,
    /// completion checks, and visual updates via child SpriteRenderers.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Controller
    /// Phase: 1
    /// </remarks>
    public class BottleItem : MonoBehaviour
    {
        #region Fields

        [Header("Visuals")]
        [SerializeField] private SpriteRenderer _bottleSprite;
        [SerializeField] private SpriteRenderer _bottleFront;
        [SerializeField] private SpriteRenderer _bottleBack;
        [SerializeField] private Transform _waterContainer;

        [Header("Selection")]
        [SerializeField] private Color _selectedTint = new Color(1f, 1f, 0.7f, 1f);
        [SerializeField] private float _selectedLiftY = 0.3f;

        private List<WaterItem> _waters = new List<WaterItem>();
        private int _maxHeight = 4;
        private bool _isComplete;
        private bool _isSelected;
        private Vector3 _originalPosition;

        // Cached child renderers for water layer visualization
        private SpriteRenderer[] _waterRenderers;

        #endregion

        #region Properties

        /// <summary>Whether this bottle is fully sorted (all same color and full, or empty).</summary>
        public bool IsComplete => _isComplete;

        /// <summary>Maximum water layers this bottle can hold.</summary>
        public int MaxHeight => _maxHeight;

        /// <summary>Current water count.</summary>
        public int WaterCount => _waters != null ? _waters.Count : 0;

        /// <summary>Current selection state.</summary>
        public bool IsSelected => _isSelected;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            _originalPosition = transform.localPosition;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initializes the bottle from a BottleConfig. Creates water items from bottom to top.
        /// </summary>
        /// <param name="config">The bottle configuration data.</param>
        public void Initialize(BottleConfig config)
        {
            if (config == null)
            {
                Debug.LogError($"[BottleItem] Null config passed to Initialize on {gameObject.name}.");
                return;
            }

            _maxHeight = config.MaxHeight;
            _waters.Clear();
            _isComplete = false;
            _isSelected = false;

            if (config.InitialWaters != null)
            {
                for (int i = 0; i < config.InitialWaters.Count && i < _maxHeight; i++)
                {
                    WaterColor color = config.InitialWaters[i];
                    if (color != WaterColor.None)
                    {
                        _waters.Add(new WaterItem(color, i, true));
                    }
                }
            }

            CacheWaterRenderers();
            UpdateVisuals();
            CheckCompletion();
        }

        /// <summary>
        /// Returns the color of the topmost water layer, or None if empty.
        /// </summary>
        public WaterColor GetTopColor()
        {
            if (_waters == null || _waters.Count == 0)
            {
                return WaterColor.None;
            }
            return _waters[_waters.Count - 1].Color;
        }

        /// <summary>
        /// Returns the current number of water layers in this bottle.
        /// </summary>
        public int GetWaterHeight()
        {
            return _waters != null ? _waters.Count : 0;
        }

        /// <summary>
        /// Returns how many more water layers can fit.
        /// </summary>
        public int GetEmptySpace()
        {
            return _maxHeight - GetWaterHeight();
        }

        /// <summary>
        /// Checks whether water can be poured from this bottle.
        /// Returns false if empty.
        /// </summary>
        public bool CanPourFrom()
        {
            return _waters != null && _waters.Count > 0;
        }

        /// <summary>
        /// Checks whether this bottle can receive water of the given color.
        /// Valid if: not full, AND (empty OR top color matches).
        /// </summary>
        /// <param name="color">The color to check.</param>
        public bool CanReceive(WaterColor color)
        {
            if (color == WaterColor.None)
            {
                return false;
            }

            int currentHeight = GetWaterHeight();
            if (currentHeight >= _maxHeight)
            {
                return false;
            }

            // Empty bottle accepts any color
            if (currentHeight == 0)
            {
                return true;
            }

            return GetTopColor() == color;
        }

        /// <summary>
        /// Removes the specified number of water layers from the top and returns the removed item template.
        /// </summary>
        /// <param name="count">Number of layers to remove.</param>
        /// <returns>A WaterItem representing the removed color, or null if invalid.</returns>
        public WaterItem PourOut(int count)
        {
            if (_waters == null || _waters.Count == 0 || count <= 0)
            {
                return null;
            }

            count = Mathf.Min(count, _waters.Count);
            WaterColor pourColor = GetTopColor();

            for (int i = 0; i < count; i++)
            {
                if (_waters.Count > 0)
                {
                    _waters.RemoveAt(_waters.Count - 1);
                }
            }

            UpdateVisuals();
            CheckCompletion();

            return new WaterItem(pourColor, 0);
        }

        /// <summary>
        /// Adds water layers of the given color to the top of this bottle.
        /// </summary>
        /// <param name="color">The color to add.</param>
        /// <param name="count">Number of layers to add.</param>
        public void PourIn(WaterColor color, int count)
        {
            if (color == WaterColor.None || count <= 0)
            {
                return;
            }

            int available = GetEmptySpace();
            int toAdd = Mathf.Min(count, available);

            for (int i = 0; i < toAdd; i++)
            {
                int height = GetWaterHeight();
                _waters.Add(new WaterItem(color, height, true));
            }

            UpdateVisuals();
            CheckCompletion();
        }

        /// <summary>
        /// Returns true if all water layers are the same color.
        /// Returns true for empty bottles as well.
        /// </summary>
        public bool IsMonochromatic()
        {
            if (_waters == null || _waters.Count <= 1)
            {
                return true;
            }

            WaterColor firstColor = _waters[0].Color;
            for (int i = 1; i < _waters.Count; i++)
            {
                if (_waters[i].Color != firstColor)
                {
                    return false;
                }
            }

            return true;
        }

        /// <summary>
        /// Returns true if this bottle has no water.
        /// </summary>
        public bool IsEmpty()
        {
            return _waters == null || _waters.Count == 0;
        }

        /// <summary>
        /// Returns true if this bottle is at max capacity.
        /// </summary>
        public bool IsFull()
        {
            return GetWaterHeight() >= _maxHeight;
        }

        /// <summary>
        /// Sets visual selection state. Lifts the bottle and applies a tint.
        /// </summary>
        /// <param name="selected">True to select, false to deselect.</param>
        public void SetSelected(bool selected)
        {
            _isSelected = selected;

            if (selected)
            {
                transform.localPosition = _originalPosition + Vector3.up * _selectedLiftY;

                if (_bottleSprite != null)
                {
                    _bottleSprite.color = _selectedTint;
                }
            }
            else
            {
                transform.localPosition = _originalPosition;

                if (_bottleSprite != null)
                {
                    _bottleSprite.color = Color.white;
                }
            }
        }

        /// <summary>
        /// Updates the visual representation of water layers using child SpriteRenderers.
        /// Each child under _waterContainer represents one layer slot.
        /// Active layers get the water color; empty layers are hidden.
        /// </summary>
        public void UpdateVisuals()
        {
            if (_waterRenderers == null || _waterRenderers.Length == 0)
            {
                CacheWaterRenderers();
            }

            if (_waterRenderers == null)
            {
                return;
            }

            for (int i = 0; i < _waterRenderers.Length; i++)
            {
                if (_waterRenderers[i] == null)
                {
                    continue;
                }

                if (i < _waters.Count)
                {
                    _waterRenderers[i].gameObject.SetActive(true);
                    _waterRenderers[i].color = GetColorForWater(_waters[i].Color);
                }
                else
                {
                    _waterRenderers[i].gameObject.SetActive(false);
                }
            }
        }

        /// <summary>
        /// Returns a copy of the current water stack for undo snapshots.
        /// </summary>
        public List<WaterItem> GetWaterStack()
        {
            List<WaterItem> snapshot = new List<WaterItem>(_waters.Count);
            for (int i = 0; i < _waters.Count; i++)
            {
                snapshot.Add(_waters[i].Clone());
            }
            return snapshot;
        }

        /// <summary>
        /// Restores the water stack from a previously saved state (undo).
        /// </summary>
        /// <param name="state">The water list snapshot to restore.</param>
        public void RestoreState(List<WaterItem> state)
        {
            _waters.Clear();

            if (state != null)
            {
                for (int i = 0; i < state.Count; i++)
                {
                    _waters.Add(state[i].Clone());
                }
            }

            UpdateVisuals();
            CheckCompletion();
        }

        /// <summary>
        /// Returns the number of consecutive same-color layers from the top.
        /// Used to calculate how many layers can be poured at once.
        /// </summary>
        public int GetTopConsecutiveCount()
        {
            if (_waters == null || _waters.Count == 0)
            {
                return 0;
            }

            WaterColor topColor = GetTopColor();
            int count = 0;

            for (int i = _waters.Count - 1; i >= 0; i--)
            {
                if (_waters[i].Color == topColor)
                {
                    count++;
                }
                else
                {
                    break;
                }
            }

            return count;
        }

        /// <summary>
        /// Resets the bottle to an uninitialized state.
        /// </summary>
        public void Reset()
        {
            _waters.Clear();
            _isComplete = false;
            _isSelected = false;
            transform.localPosition = _originalPosition;

            if (_bottleSprite != null)
            {
                _bottleSprite.color = Color.white;
            }

            UpdateVisuals();
        }

        #endregion

        #region Private Methods

        private void CacheWaterRenderers()
        {
            if (_waterContainer == null)
            {
                return;
            }

            _waterRenderers = new SpriteRenderer[_maxHeight];
            for (int i = 0; i < _waterContainer.childCount && i < _maxHeight; i++)
            {
                SpriteRenderer sr = _waterContainer.GetChild(i).GetComponent<SpriteRenderer>();
                if (sr != null)
                {
                    _waterRenderers[i] = sr;
                }
            }
        }

        private void CheckCompletion()
        {
            // A bottle is complete if: full and monochromatic, OR empty
            if (IsEmpty())
            {
                _isComplete = true;
                return;
            }

            _isComplete = IsFull() && IsMonochromatic();
        }

        /// <summary>
        /// Maps a WaterColor enum to a Unity Color for rendering.
        /// </summary>
        private Color GetColorForWater(WaterColor waterColor)
        {
            switch (waterColor)
            {
                case WaterColor.Red:      return new Color(0.90f, 0.20f, 0.20f, 1f);
                case WaterColor.Blue:     return new Color(0.20f, 0.40f, 0.90f, 1f);
                case WaterColor.Green:    return new Color(0.20f, 0.80f, 0.30f, 1f);
                case WaterColor.Yellow:   return new Color(0.95f, 0.85f, 0.15f, 1f);
                case WaterColor.Purple:   return new Color(0.60f, 0.20f, 0.80f, 1f);
                case WaterColor.Orange:   return new Color(0.95f, 0.55f, 0.10f, 1f);
                case WaterColor.Pink:     return new Color(0.95f, 0.50f, 0.70f, 1f);
                case WaterColor.Cyan:     return new Color(0.20f, 0.85f, 0.85f, 1f);
                case WaterColor.Brown:    return new Color(0.55f, 0.35f, 0.15f, 1f);
                case WaterColor.White:    return new Color(0.95f, 0.95f, 0.95f, 1f);
                case WaterColor.Gray:     return new Color(0.55f, 0.55f, 0.55f, 1f);
                case WaterColor.DarkBlue: return new Color(0.10f, 0.15f, 0.55f, 1f);
                case WaterColor.Lime:     return new Color(0.50f, 0.95f, 0.10f, 1f);
                case WaterColor.Magenta:  return new Color(0.85f, 0.15f, 0.55f, 1f);
                case WaterColor.None:
                default:
                    return new Color(0f, 0f, 0f, 0f);
            }
        }

        #endregion
    }
}
