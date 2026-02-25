using System;
using UnityEngine;
using DG.Tweening;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Controls individual tile behavior: initialization, sliding movement, and state management.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Controller | Phase: 1
    /// </remarks>
    public class TileController : MonoBehaviour
    {
        #region Enums

        public enum TileState
        {
            Idle,
            Sliding,
            Locked,
            Frozen
        }

        #endregion

        #region Fields

        [SerializeField] private SpriteRenderer spriteRenderer;
        [SerializeField] private float slideDuration = 0.25f;

        private Tween _slideTween;

        #endregion

        #region Properties

        public TileState CurrentState { get; private set; } = TileState.Idle;
        public CellType CellType { get; private set; }
        public CatColor HoleColor { get; private set; }
        public Vector2Int GridPosition { get; set; }
        public bool IsSliding => CurrentState == TileState.Sliding;
        public bool CanSlide => CurrentState == TileState.Idle;

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize tile with cell type, color, and grid position.
        /// </summary>
        public void Init(CellType cellType, CatColor color, Vector2Int gridPos)
        {
            CellType = cellType;
            HoleColor = color;
            GridPosition = gridPos;
            CurrentState = TileState.Idle;

            if (spriteRenderer != null)
            {
                spriteRenderer.color = GetColorFromCatColor(color);
            }

            if (GridManager.Instance != null)
            {
                transform.position = GridManager.Instance.GridToWorld(gridPos.x, gridPos.y);
            }
        }

        /// <summary>
        /// Slide tile to target world position with DOTween animation.
        /// </summary>
        public void SlideTo(Vector3 targetWorldPos, Action onComplete)
        {
            if (!CanSlide)
            {
                return;
            }

            SetState(TileState.Sliding);

            _slideTween?.Kill();
            _slideTween = transform.DOMove(targetWorldPos, slideDuration)
                .SetEase(Ease.OutQuad)
                .OnComplete(() =>
                {
                    if (GridManager.Instance != null)
                    {
                        Vector2Int newGridPos = GridManager.Instance.WorldToGrid(targetWorldPos);
                        GridPosition = newGridPos;
                    }

                    SetState(TileState.Idle);
                    onComplete?.Invoke();
                });
        }

        /// <summary>
        /// Set tile state directly.
        /// </summary>
        public void SetState(TileState state)
        {
            CurrentState = state;
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

        #region Unity Lifecycle

        private void OnDestroy()
        {
            _slideTween?.Kill();
        }

        #endregion
    }
}
