using System;
using UnityEngine;
using DG.Tweening;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Controls individual cat behavior: initialization, idle animation, and drop animation.
    /// Cats are stationary; holes move toward them.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Controller | Phase: 1
    /// </remarks>
    public class CatController : MonoBehaviour
    {
        #region Enums

        public enum CatState
        {
            Idle,
            Dropping,
            Cleared
        }

        #endregion

        #region Fields

        [SerializeField] private SpriteRenderer spriteRenderer;
        [SerializeField] private float idleBobAmount = 0.05f;
        [SerializeField] private float idleBobDuration = 1.0f;
        [SerializeField] private float dropDuration = 0.3f;

        private Sequence _idleSequence;
        private Sequence _dropSequence;
        private Vector3 _basePosition;

        #endregion

        #region Properties

        public CatColor Color { get; private set; }
        public Vector2Int GridPosition { get; private set; }
        public CatState CurrentState { get; private set; } = CatState.Idle;
        public bool IsCleared => CurrentState == CatState.Cleared;

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize cat with color and grid position.
        /// </summary>
        public void Init(CatColor color, Vector2Int gridPos)
        {
            Color = color;
            GridPosition = gridPos;
            CurrentState = CatState.Idle;

            if (spriteRenderer != null)
            {
                spriteRenderer.color = GetColorFromCatColor(color);
            }

            if (GridManager.Instance != null)
            {
                transform.position = GridManager.Instance.GridToWorld(gridPos.x, gridPos.y);
            }

            _basePosition = transform.position;

            PlayIdleAnimation();
        }

        /// <summary>
        /// Play idle bobbing animation (subtle up/down movement, looping).
        /// </summary>
        public void PlayIdleAnimation()
        {
            StopAnimation();

            _idleSequence = DOTween.Sequence();
            _idleSequence.Append(
                transform.DOMoveY(_basePosition.y + idleBobAmount, idleBobDuration * 0.5f)
                    .SetEase(Ease.InOutSine)
            );
            _idleSequence.Append(
                transform.DOMoveY(_basePosition.y, idleBobDuration * 0.5f)
                    .SetEase(Ease.InOutSine)
            );
            _idleSequence.SetLoops(-1, LoopType.Restart);
        }

        /// <summary>
        /// Play drop animation: shrink and move toward hole, then mark as cleared.
        /// </summary>
        public void PlayDropAnimation(Vector3 holeWorldPos, Action onComplete)
        {
            if (CurrentState == CatState.Cleared)
            {
                return;
            }

            StopAnimation();
            CurrentState = CatState.Dropping;

            _dropSequence = DOTween.Sequence();
            _dropSequence.Append(
                transform.DOScale(Vector3.zero, dropDuration)
                    .SetEase(Ease.InBack)
            );
            _dropSequence.Join(
                transform.DOMove(holeWorldPos, dropDuration)
                    .SetEase(Ease.InQuad)
            );
            _dropSequence.OnComplete(() =>
            {
                CurrentState = CatState.Cleared;
                gameObject.SetActive(false);
                onComplete?.Invoke();
            });
        }

        /// <summary>
        /// Stop all running animations and kill tweens.
        /// </summary>
        public void StopAnimation()
        {
            _idleSequence?.Kill();
            _idleSequence = null;

            _dropSequence?.Kill();
            _dropSequence = null;
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

        private void OnDisable()
        {
            StopAnimation();
        }

        private void OnDestroy()
        {
            StopAnimation();
        }

        #endregion
    }
}
