using System.Collections.Generic;
using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Validates color matching between cats and holes. Pure logic, no visuals.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Validator | Phase: 2
    /// </remarks>
    public class ColorMatcher : MonoBehaviour
    {
        #region Fields

        private readonly List<CatController> _trackedCats = new List<CatController>();

        #endregion

        #region Public Methods

        /// <summary>
        /// Register a cat for tracking. Call when spawning cats during level setup.
        /// </summary>
        public void RegisterCat(CatController cat)
        {
            if (cat == null) return;
            if (!_trackedCats.Contains(cat))
            {
                _trackedCats.Add(cat);
            }
        }

        /// <summary>
        /// Clear all tracked cats. Call on level reset.
        /// </summary>
        public void ClearTrackedCats()
        {
            _trackedCats.Clear();
        }

        /// <summary>
        /// Check if a cat matches a hole by color.
        /// Rainbow hole matches any color. Black (Trap) hole with color mismatch returns Trap.
        /// </summary>
        public MatchResult CheckMatch(CatController cat, HoleController hole)
        {
            if (cat == null || hole == null) return MatchResult.Fail;

            // Rainbow hole matches any cat color
            if (hole.IsRainbow)
            {
                return MatchResult.Success;
            }

            // Trap hole: color mismatch results in Trap
            if (hole.IsTrap)
            {
                return cat.Color == hole.Color ? MatchResult.Success : MatchResult.Trap;
            }

            // Normal matching: compare cat color to hole color
            return cat.Color == hole.Color ? MatchResult.Success : MatchResult.Fail;
        }

        /// <summary>
        /// Check if all tracked cats have been cleared (matched and dropped).
        /// </summary>
        public bool IsAllCatsMatched()
        {
            if (_trackedCats.Count == 0) return false;

            for (int i = 0; i < _trackedCats.Count; i++)
            {
                if (_trackedCats[i] == null) continue;
                if (!_trackedCats[i].IsCleared)
                {
                    return false;
                }
            }

            return true;
        }

        /// <summary>
        /// Get the number of cats that have not yet been cleared.
        /// </summary>
        public int GetRemainingCatCount()
        {
            int count = 0;
            for (int i = 0; i < _trackedCats.Count; i++)
            {
                if (_trackedCats[i] == null) continue;
                if (!_trackedCats[i].IsCleared)
                {
                    count++;
                }
            }
            return count;
        }

        /// <summary>
        /// Get a list of cats that have not yet been cleared.
        /// </summary>
        public List<CatController> GetRemainingCats()
        {
            var remaining = new List<CatController>();
            for (int i = 0; i < _trackedCats.Count; i++)
            {
                if (_trackedCats[i] == null) continue;
                if (!_trackedCats[i].IsCleared)
                {
                    remaining.Add(_trackedCats[i]);
                }
            }
            return remaining;
        }

        #endregion
    }
}
