using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Tracks move count and calculates stars, score, and coin rewards.
    /// Subscribes to OnMovePerformed and publishes OnMoveCountChanged.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Calculator | Phase: 2
    /// </remarks>
    public class ScoreCalculator : MonoBehaviour
    {
        #region Constants

        private const int BASE_SCORE = 1000;
        private const int COIN_REWARD_3_STARS = 50;
        private const int COIN_REWARD_2_STARS = 20;
        private const int COIN_REWARD_1_STAR = 10;
        private const int STAR_2_EXTRA_MOVES = 2;

        #endregion

        #region Fields

        private int _moveCount;

        #endregion

        #region Properties

        public int MoveCount => _moveCount;

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            if (EventManager.Instance != null)
            {
                EventManager.Instance.Subscribe<OnMovePerformed>(OnMovePerformedHandler);
            }
        }

        private void OnDestroy()
        {
            if (EventManager.Instance != null)
            {
                EventManager.Instance.Unsubscribe<OnMovePerformed>(OnMovePerformedHandler);
            }
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Increment the move counter by one and publish OnMoveCountChanged.
        /// </summary>
        public void IncrementMove()
        {
            _moveCount++;

            if (EventManager.Instance != null)
            {
                EventManager.Instance.Publish(new OnMoveCountChanged
                {
                    MoveCount = _moveCount
                });
            }
        }

        /// <summary>
        /// Get the current move count.
        /// </summary>
        public int GetMoveCount()
        {
            return _moveCount;
        }

        /// <summary>
        /// Calculate star rating based on move count and optimal moves.
        /// 3 stars: moveCount &lt;= optimalMoves
        /// 2 stars: moveCount &lt;= optimalMoves + 2
        /// 1 star: everything else
        /// </summary>
        public int CalculateStars(int moveCount, int optimalMoves)
        {
            if (optimalMoves <= 0) return 1;

            if (moveCount <= optimalMoves)
            {
                return 3;
            }

            if (moveCount <= optimalMoves + STAR_2_EXTRA_MOVES)
            {
                return 2;
            }

            return 1;
        }

        /// <summary>
        /// Calculate score based on move count, optimal moves, and star rating.
        /// Score = baseScore * starMultiplier * efficiencyBonus
        /// </summary>
        public int CalculateScore(int moveCount, int optimalMoves, int stars)
        {
            if (optimalMoves <= 0 || moveCount <= 0) return 0;

            float starMultiplier;
            switch (stars)
            {
                case 3:  starMultiplier = 3.0f; break;
                case 2:  starMultiplier = 2.0f; break;
                default: starMultiplier = 1.0f; break;
            }

            float efficiencyBonus = Mathf.Clamp01((float)optimalMoves / moveCount);

            return Mathf.RoundToInt(BASE_SCORE * starMultiplier * efficiencyBonus);
        }

        /// <summary>
        /// Calculate coin reward based on star rating.
        /// 3 stars = 50, 2 stars = 20, 1 star = 10
        /// </summary>
        public int CalculateCoinReward(int stars)
        {
            switch (stars)
            {
                case 3:  return COIN_REWARD_3_STARS;
                case 2:  return COIN_REWARD_2_STARS;
                default: return COIN_REWARD_1_STAR;
            }
        }

        /// <summary>
        /// Reset the move counter. Call at the start of a new level.
        /// </summary>
        public void Reset()
        {
            _moveCount = 0;
        }

        #endregion

        #region Private Methods

        private void OnMovePerformedHandler(OnMovePerformed evt)
        {
            IncrementMove();
        }

        #endregion
    }
}
