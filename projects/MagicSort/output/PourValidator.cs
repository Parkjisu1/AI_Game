using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Validates whether a pour from one bottle to another is legal.
    /// Calculates the exact amount that can be transferred and builds a SelectionResult.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Validator
    /// Phase: 1
    /// </remarks>
    public class PourValidator
    {
        #region Public Methods

        /// <summary>
        /// Checks all conditions to determine if pouring from origin to target is valid.
        /// </summary>
        /// <param name="origin">Source bottle.</param>
        /// <param name="target">Destination bottle.</param>
        /// <returns>True if the pour is allowed.</returns>
        public bool CanPour(BottleItem origin, BottleItem target)
        {
            if (origin == null || target == null)
            {
                return false;
            }

            // Cannot pour to self
            if (origin == target)
            {
                return false;
            }

            // Origin must have water
            if (!origin.CanPourFrom())
            {
                return false;
            }

            // Target must accept the origin's top color
            WaterColor topColor = origin.GetTopColor();
            if (!target.CanReceive(topColor))
            {
                return false;
            }

            // Avoid pointless move: pouring monochromatic source into empty target
            if (target.IsEmpty() && origin.IsMonochromatic())
            {
                return false;
            }

            // Must have at least 1 unit to pour
            int pourAmount = CalculatePourAmount(origin, target);
            return pourAmount > 0;
        }

        /// <summary>
        /// Calculates how many consecutive same-color layers can be poured from origin to target.
        /// Limited by origin's top consecutive count and target's empty space.
        /// </summary>
        /// <param name="origin">Source bottle.</param>
        /// <param name="target">Destination bottle.</param>
        /// <returns>Number of layers that can be transferred.</returns>
        public int CalculatePourAmount(BottleItem origin, BottleItem target)
        {
            if (origin == null || target == null)
            {
                return 0;
            }

            if (!origin.CanPourFrom())
            {
                return 0;
            }

            WaterColor topColor = origin.GetTopColor();
            if (!target.CanReceive(topColor))
            {
                return 0;
            }

            int consecutiveCount = origin.GetTopConsecutiveCount();
            int emptySpace = target.GetEmptySpace();

            return Mathf.Min(consecutiveCount, emptySpace);
        }

        /// <summary>
        /// Builds a complete SelectionResult describing the pour operation.
        /// Returns null if the pour is not valid.
        /// </summary>
        /// <param name="origin">Source bottle.</param>
        /// <param name="target">Destination bottle.</param>
        /// <returns>A SelectionResult, or null if invalid.</returns>
        public SelectionResult CreateResult(BottleItem origin, BottleItem target)
        {
            if (!CanPour(origin, target))
            {
                return null;
            }

            int pourAmount = CalculatePourAmount(origin, target);
            WaterColor color = origin.GetTopColor();

            int originCurrentHeight = origin.GetWaterHeight();
            int targetCurrentHeight = target.GetWaterHeight();

            return new SelectionResult(
                origin: origin,
                target: target,
                color: color,
                waterHeightToMove: pourAmount,
                originNewHeight: originCurrentHeight - pourAmount,
                targetNewHeight: targetCurrentHeight + pourAmount
            );
        }

        #endregion
    }
}
