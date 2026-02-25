using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Checks win and stuck conditions after each pour.
    /// Fires LevelCompleteSignal or LevelFailSignal as appropriate.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Validator
    /// Phase: 1
    /// </remarks>
    public class CompletionChecker
    {
        #region Fields

        private BottleCollection _bottleCollection;
        private SignalBus _signalBus;
        private int _currentLevelNumber;

        #endregion

        #region Constructors

        public CompletionChecker(BottleCollection bottleCollection, SignalBus signalBus)
        {
            _bottleCollection = bottleCollection;
            _signalBus = signalBus;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Sets the current level number for signal metadata.
        /// </summary>
        /// <param name="levelNumber">The active level ID.</param>
        public void SetCurrentLevel(int levelNumber)
        {
            _currentLevelNumber = levelNumber;
        }

        /// <summary>
        /// Returns true if every bottle is complete (full+monochromatic) or empty.
        /// </summary>
        public bool CheckWin()
        {
            if (_bottleCollection == null)
            {
                return false;
            }

            return _bottleCollection.AreAllBottlesComplete();
        }

        /// <summary>
        /// Returns true if no valid pour moves remain and the level is not won.
        /// </summary>
        public bool CheckStuck()
        {
            if (_bottleCollection == null)
            {
                return false;
            }

            // If already won, not stuck
            if (_bottleCollection.AreAllBottlesComplete())
            {
                return false;
            }

            return !_bottleCollection.HasValidMove();
        }

        /// <summary>
        /// Performs both win and stuck checks, firing appropriate signals.
        /// Call this after each pour completes.
        /// </summary>
        /// <param name="moveCount">Current move count for rating calculation.</param>
        /// <returns>True if the level ended (win or stuck).</returns>
        public bool CheckAndNotify(int moveCount = 0)
        {
            if (CheckWin())
            {
                NotifyWin(moveCount);
                return true;
            }

            if (CheckStuck())
            {
                NotifyStuck();
                return true;
            }

            return false;
        }

        #endregion

        #region Private Methods

        private void NotifyWin(int moveCount)
        {
            if (_signalBus == null)
            {
                return;
            }

            // Calculate star rating: 3 stars if at or under par, 2 for up to 50% over, 1 otherwise
            int starRating = 3;
            // Star rating logic would reference par from LevelModel, using moveCount as proxy
            // For now, default to 3 since par is managed by LevelManager

            _signalBus.Fire(new LevelCompleteSignal
            {
                LevelNumber = _currentLevelNumber,
                StarRating = starRating,
                MoveCount = moveCount
            });
        }

        private void NotifyStuck()
        {
            if (_signalBus == null)
            {
                return;
            }

            _signalBus.Fire(new LevelFailSignal
            {
                LevelNumber = _currentLevelNumber,
                Reason = StuckType.NoMove
            });
        }

        #endregion
    }
}
