using System;
using System.Collections;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Executes validated pour operations. Supports both instant and animated execution.
    /// Fires PourCompleteSignal when a pour finishes.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Processor
    /// Phase: 1
    /// </remarks>
    public class PourProcessor : MonoBehaviour
    {
        #region Fields

        [Header("Animation")]
        [SerializeField] private float _pourDuration = 0.4f;
        [SerializeField] private float _liftHeight = 1.5f;
        [SerializeField] private float _tiltAngle = 60f;

        [Inject] private SignalBus _signalBus;

        private bool _isPouring;

        #endregion

        #region Properties

        /// <summary>Whether a pour animation is currently in progress.</summary>
        public bool IsPouring => _isPouring;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            if (ProjectContext.HasInstance)
            {
                ProjectContext.Instance.Inject(this);
            }
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Executes a pour instantly without animation.
        /// Moves water from origin to target and fires PourCompleteSignal.
        /// </summary>
        /// <param name="result">The validated SelectionResult to execute.</param>
        public void ExecutePour(SelectionResult result)
        {
            if (result == null || !result.IsValid())
            {
                Debug.LogWarning("[PourProcessor] Invalid SelectionResult passed to ExecutePour.");
                return;
            }

            // Execute the transfer
            result.Origin.PourOut(result.WaterHeightToMove);
            result.Target.PourIn(result.Color, result.WaterHeightToMove);

            // Update visuals
            result.Origin.UpdateVisuals();
            result.Target.UpdateVisuals();

            // Fire completion signal
            FirePourComplete(result);
        }

        /// <summary>
        /// Executes a pour with a simple lift-tilt-return animation sequence.
        /// </summary>
        /// <param name="result">The validated SelectionResult to execute.</param>
        /// <param name="onComplete">Callback invoked when animation finishes.</param>
        public IEnumerator ExecutePourAnimated(SelectionResult result, Action onComplete = null)
        {
            if (result == null || !result.IsValid())
            {
                Debug.LogWarning("[PourProcessor] Invalid SelectionResult passed to ExecutePourAnimated.");
                onComplete?.Invoke();
                yield break;
            }

            if (_isPouring)
            {
                Debug.LogWarning("[PourProcessor] Already pouring, skipping.");
                onComplete?.Invoke();
                yield break;
            }

            _isPouring = true;

            Transform originTransform = result.Origin.transform;
            Vector3 originalPos = originTransform.localPosition;
            Quaternion originalRot = originTransform.localRotation;

            // Phase 1: Lift origin bottle
            Vector3 liftPos = originalPos + Vector3.up * _liftHeight;
            yield return AnimateTransform(originTransform, originalPos, liftPos, Quaternion.identity, Quaternion.identity, _pourDuration * 0.3f);

            // Phase 2: Tilt to pour
            Quaternion tiltRot = Quaternion.Euler(0f, 0f, _tiltAngle);
            yield return AnimateTransform(originTransform, liftPos, liftPos, Quaternion.identity, tiltRot, _pourDuration * 0.2f);

            // Execute the actual data transfer at the tilt peak
            result.Origin.PourOut(result.WaterHeightToMove);
            result.Target.PourIn(result.Color, result.WaterHeightToMove);
            result.Origin.UpdateVisuals();
            result.Target.UpdateVisuals();

            // Phase 3: Hold briefly
            yield return new WaitForSeconds(_pourDuration * 0.1f);

            // Phase 4: Return to upright
            yield return AnimateTransform(originTransform, liftPos, liftPos, tiltRot, Quaternion.identity, _pourDuration * 0.2f);

            // Phase 5: Lower back to original position
            yield return AnimateTransform(originTransform, liftPos, originalPos, Quaternion.identity, Quaternion.identity, _pourDuration * 0.2f);

            originTransform.localPosition = originalPos;
            originTransform.localRotation = originalRot;

            _isPouring = false;

            // Fire completion signal
            FirePourComplete(result);

            onComplete?.Invoke();
        }

        #endregion

        #region Private Methods

        private void FirePourComplete(SelectionResult result)
        {
            if (_signalBus == null)
            {
                return;
            }

            BottleCollection collection = GetComponentInParent<BottleCollection>();
            int sourceIndex = -1;
            int targetIndex = -1;

            if (collection != null)
            {
                sourceIndex = collection.GetBottleIndex(result.Origin);
                targetIndex = collection.GetBottleIndex(result.Target);
            }

            _signalBus.Fire(new PourCompleteSignal
            {
                SourceIndex = sourceIndex,
                TargetIndex = targetIndex,
                Color = result.Color,
                LayerCount = result.WaterHeightToMove
            });
        }

        private IEnumerator AnimateTransform(Transform target, Vector3 fromPos, Vector3 toPos,
            Quaternion fromRot, Quaternion toRot, float duration)
        {
            if (duration <= 0f)
            {
                target.localPosition = toPos;
                target.localRotation = toRot;
                yield break;
            }

            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = Mathf.Clamp01(elapsed / duration);

                // Smooth ease-in-out
                float smooth = t * t * (3f - 2f * t);

                target.localPosition = Vector3.Lerp(fromPos, toPos, smooth);
                target.localRotation = Quaternion.Slerp(fromRot, toRot, smooth);

                yield return null;
            }

            target.localPosition = toPos;
            target.localRotation = toRot;
        }

        #endregion
    }
}
