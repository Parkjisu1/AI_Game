using System.Collections.Generic;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Calculates the best available pour move as a hint for the player.
    /// Prioritizes moves that advance bottles toward completion.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Calculator
    /// Phase: 1
    /// </remarks>
    public class HintCalculator
    {
        #region Inner Types

        /// <summary>
        /// Scored move candidate for priority sorting.
        /// </summary>
        private struct MoveCandidate
        {
            public BottleItem From;
            public BottleItem To;
            public int Score;
            public int PourAmount;
        }

        #endregion

        #region Fields

        private readonly PourValidator _pourValidator;

        #endregion

        #region Constructors

        public HintCalculator()
        {
            _pourValidator = new PourValidator();
        }

        public HintCalculator(PourValidator validator)
        {
            _pourValidator = validator ?? new PourValidator();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Finds the best available move in the current board state.
        /// Returns null if no valid move exists.
        /// </summary>
        /// <param name="collection">The bottle collection to analyze.</param>
        /// <returns>A tuple of (from, to) bottles, or null if no move found.</returns>
        public (BottleItem from, BottleItem to)? GetBestMove(BottleCollection collection)
        {
            if (collection == null)
            {
                return null;
            }

            List<BottleItem> bottles = collection.GetAllBottles();
            if (bottles == null || bottles.Count < 2)
            {
                return null;
            }

            List<MoveCandidate> candidates = new List<MoveCandidate>();

            for (int i = 0; i < bottles.Count; i++)
            {
                BottleItem origin = bottles[i];
                if (origin == null || !origin.CanPourFrom() || origin.IsComplete)
                {
                    continue;
                }

                WaterColor topColor = origin.GetTopColor();
                int consecutiveCount = origin.GetTopConsecutiveCount();

                for (int j = 0; j < bottles.Count; j++)
                {
                    if (i == j)
                    {
                        continue;
                    }

                    BottleItem target = bottles[j];
                    if (target == null)
                    {
                        continue;
                    }

                    if (!_pourValidator.CanPour(origin, target))
                    {
                        continue;
                    }

                    int pourAmount = _pourValidator.CalculatePourAmount(origin, target);
                    if (pourAmount <= 0)
                    {
                        continue;
                    }

                    int score = ScoreMove(origin, target, topColor, consecutiveCount, pourAmount);

                    candidates.Add(new MoveCandidate
                    {
                        From = origin,
                        To = target,
                        Score = score,
                        PourAmount = pourAmount
                    });
                }
            }

            if (candidates.Count == 0)
            {
                return null;
            }

            // Sort by score descending
            candidates.Sort((a, b) => b.Score.CompareTo(a.Score));

            MoveCandidate best = candidates[0];
            return (best.From, best.To);
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Scores a potential move. Higher is better.
        /// </summary>
        private int ScoreMove(BottleItem origin, BottleItem target, WaterColor color,
            int consecutiveCount, int pourAmount)
        {
            int score = 0;

            // Priority 1: Move that completes a bottle (fills it to max with same color)
            int targetHeightAfter = target.GetWaterHeight() + pourAmount;
            if (target.IsMonochromatic() && targetHeightAfter == target.MaxHeight)
            {
                score += 100;
            }

            // Priority 2: Move that adds to a monochromatic target (progress toward completion)
            if (!target.IsEmpty() && target.IsMonochromatic() && target.GetTopColor() == color)
            {
                score += 50;
            }

            // Priority 3: Moving more layers at once is better
            score += pourAmount * 10;

            // Priority 4: Emptying a bottle is good (frees up space)
            int originHeightAfter = origin.GetWaterHeight() - pourAmount;
            if (originHeightAfter == 0)
            {
                score += 30;
            }

            // Priority 5: Moving to a partially filled bottle is better than empty
            // (concentrates colors, avoids spreading)
            if (!target.IsEmpty())
            {
                score += 20;
            }

            // Priority 6: If origin becomes monochromatic after pour, that's good
            if (originHeightAfter > 0 && consecutiveCount == pourAmount)
            {
                // Check if remaining would be monochromatic
                // We approximate: if the consecutive count equals the amount we're pouring,
                // the next layer might start a new monochromatic run
                score += 15;
            }

            // Penalty: Moving to empty bottle (less useful unless emptying origin)
            if (target.IsEmpty() && originHeightAfter > 0)
            {
                score -= 5;
            }

            return score;
        }

        #endregion
    }
}
