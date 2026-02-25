using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Controls individual hole behavior: initialization, match detection, and match effects.
    /// Holes are children of tiles and move with them.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Controller | Phase: 1
    /// </remarks>
    public class HoleController : MonoBehaviour
    {
        #region Enums

        public enum HoleState
        {
            Active,
            Matched
        }

        #endregion

        #region Fields

        [SerializeField] private SpriteRenderer spriteRenderer;
        [SerializeField] private ParticleSystem matchEffect;

        private CatColor _color;

        #endregion

        #region Properties

        public CatColor Color => _color;
        public Vector2Int GridPosition { get; set; }
        public HoleState CurrentState { get; private set; } = HoleState.Active;
        public bool IsMatched => CurrentState == HoleState.Matched;
        public bool IsRainbow => _color == CatColor.Rainbow;
        public bool IsTrap => _color == CatColor.Black;

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize hole with color and grid position.
        /// </summary>
        public void Init(CatColor color, Vector2Int gridPos)
        {
            _color = color;
            GridPosition = gridPos;
            CurrentState = HoleState.Active;

            if (spriteRenderer != null)
            {
                spriteRenderer.color = GetColorFromCatColor(color);
            }
        }

        /// <summary>
        /// Called when a cat is dropped into this hole. Transitions to Matched state.
        /// </summary>
        public void OnCatDropped()
        {
            if (CurrentState == HoleState.Matched)
            {
                return;
            }

            CurrentState = HoleState.Matched;
            PlayMatchEffect();

            if (EventManager.Instance != null)
            {
                EventManager.Instance.Publish(new OnCatDropped
                {
                    CatColor = _color,
                    Position = GridPosition
                });
            }
        }

        /// <summary>
        /// Play particle match effect.
        /// </summary>
        public void PlayMatchEffect()
        {
            if (matchEffect == null)
            {
                return;
            }

            var main = matchEffect.main;
            main.startColor = GetColorFromCatColor(_color);
            matchEffect.Play();
        }

        #endregion

        #region Private Methods

        private Color GetColorFromCatColor(CatColor catColor)
        {
            switch (catColor)
            {
                case CatColor.Red:     return new Color(0.9f, 0.3f, 0.3f);
                case CatColor.Blue:    return new Color(0.3f, 0.5f, 0.9f);
                case CatColor.Green:   return new Color(0.3f, 0.8f, 0.4f);
                case CatColor.Yellow:  return new Color(0.95f, 0.85f, 0.3f);
                case CatColor.Purple:  return new Color(0.7f, 0.3f, 0.9f);
                case CatColor.Orange:  return new Color(0.95f, 0.6f, 0.2f);
                case CatColor.Pink:    return new Color(0.95f, 0.5f, 0.7f);
                case CatColor.White:   return UnityEngine.Color.white;
                case CatColor.Black:   return new Color(0.3f, 0.3f, 0.3f);
                case CatColor.Rainbow: return UnityEngine.Color.white;
                default:               return UnityEngine.Color.gray;
            }
        }

        #endregion
    }
}
