using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using DropTheCat.Core;

namespace DropTheCat.Domain
{
    /// <summary>
    /// Processes cat drops after slides: detects cat-hole overlaps, checks color match,
    /// plays drop animations, and publishes level completion/failure events.
    /// </summary>
    /// <remarks>
    /// Layer: Domain | Genre: Puzzle | Role: Processor | Phase: 2
    /// </remarks>
    public class DropProcessor : Singleton<DropProcessor>
    {
        #region Fields

        [SerializeField] private float dropCheckDelay = 0.1f;
        [SerializeField] private ColorMatcher _colorMatcher;
        [SerializeField] private ScoreCalculator _scoreCalculator;
        [SerializeField] private List<CatController> _cats = new List<CatController>();
        [SerializeField] private List<HoleController> _holes = new List<HoleController>();

        private bool _isDropping;
        private Coroutine _dropCoroutine;

        #endregion

        #region Properties

        public bool IsDropping => _isDropping;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Subscribe<OnSlideComplete>(OnSlideCompleteHandler);
            }
        }

        protected override void OnDestroy()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Unsubscribe<OnSlideComplete>(OnSlideCompleteHandler);
            }

            if (_dropCoroutine != null)
            {
                StopCoroutine(_dropCoroutine);
                _dropCoroutine = null;
            }

            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Scan the grid for cat-hole overlaps and process drops.
        /// Runs as a coroutine to handle animations sequentially.
        /// </summary>
        public void CheckAndProcessDrops()
        {
            if (_isDropping) return;

            if (_dropCoroutine != null)
            {
                StopCoroutine(_dropCoroutine);
            }

            _dropCoroutine = StartCoroutine(ProcessDropsCoroutine());
        }

        /// <summary>
        /// Register a cat for tracking during drop processing.
        /// </summary>
        public void RegisterCat(CatController cat)
        {
            if (cat == null) return;
            if (!_cats.Contains(cat))
            {
                _cats.Add(cat);
                if (_colorMatcher != null) _colorMatcher.RegisterCat(cat);
            }
        }

        /// <summary>
        /// Register a hole for tracking during drop processing.
        /// </summary>
        public void RegisterHole(HoleController hole)
        {
            if (hole == null) return;
            if (!_holes.Contains(hole))
            {
                _holes.Add(hole);
            }
        }

        /// <summary>
        /// Clear all tracked cats and holes.
        /// </summary>
        public void ClearTrackedObjects()
        {
            _cats.Clear();
            _holes.Clear();
            if (_colorMatcher != null) _colorMatcher.ClearTrackedCats();
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Handle OnSlideComplete event by triggering drop checks.
        /// </summary>
        private void OnSlideCompleteHandler(OnSlideComplete evt)
        {
            CheckAndProcessDrops();
        }

        /// <summary>
        /// Coroutine that scans the grid for cat-hole overlaps and processes each drop.
        /// </summary>
        private IEnumerator ProcessDropsCoroutine()
        {
            _isDropping = true;

            // Short delay to let slide animation settle
            yield return new WaitForSeconds(dropCheckDelay);

            if (GridManager.Instance == null)
            {
                _isDropping = false;
                yield break;
            }

            bool anyDropOccurred = false;
            bool levelFailed = false;
            int width = GridManager.Instance.GridWidth;
            int height = GridManager.Instance.GridHeight;

            // Collect all drop candidates first to avoid grid modification during iteration
            var dropCandidates = new List<DropCandidate>();

            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    CellData cell = GridManager.Instance.GetCell(x, y);

                    if (!IsCatHoleOverlap(cell)) continue;

                    dropCandidates.Add(new DropCandidate
                    {
                        position = new Vector2Int(x, y),
                        cell = cell
                    });
                }
            }

            // Process each drop candidate
            for (int i = 0; i < dropCandidates.Count; i++)
            {
                DropCandidate candidate = dropCandidates[i];
                Vector2Int pos = candidate.position;

                // Find CatController and HoleController at this position
                CatController cat = FindCatAtPosition(pos);
                HoleController hole = FindHoleAtPosition(pos);

                if (cat == null || hole == null) continue;
                if (cat.IsCleared || hole.IsMatched) continue;

                // Check color match via ColorMatcher
                MatchResult matchResult = CheckColorMatch(cat, hole);

                switch (matchResult)
                {
                    case MatchResult.Success:
                        yield return ProcessSuccessfulDrop(cat, hole, pos);
                        anyDropOccurred = true;
                        break;

                    case MatchResult.Trap:
                        ProcessTrapDrop(pos);
                        levelFailed = true;
                        break;

                    case MatchResult.Fail:
                        // No match, do nothing
                        break;
                }

                if (levelFailed) break;
            }

            // Check level completion after all drops
            if (!levelFailed && anyDropOccurred)
            {
                CheckLevelCompletion();
            }

            _isDropping = false;
            _dropCoroutine = null;
        }

        /// <summary>
        /// Process a successful color match: animate drop and update grid.
        /// </summary>
        private IEnumerator ProcessSuccessfulDrop(
            CatController cat, HoleController hole, Vector2Int pos)
        {
            Vector3 holeWorldPos = GridManager.Instance != null
                ? GridManager.Instance.GridToWorld(pos.x, pos.y)
                : hole.transform.position;

            bool animComplete = false;

            // Play drop animation on the cat
            cat.PlayDropAnimation(holeWorldPos, () =>
            {
                animComplete = true;
            });

            // Notify hole
            hole.OnCatDropped();

            // Play SFX
            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlaySFX("cat_drop");
            }

            // Wait for animation
            while (!animComplete)
            {
                yield return null;
            }

            // Clear occupant from grid
            if (GridManager.Instance != null)
            {
                GridManager.Instance.SetCellOccupant(pos.x, pos.y, CellOccupant.None);
            }
        }

        /// <summary>
        /// Process a trap drop: play fail SFX and publish level failed event.
        /// </summary>
        private void ProcessTrapDrop(Vector2Int pos)
        {
            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlaySFX("trap_fail");
            }

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnLevelFailed
                {
                    Reason = FailReason.TrapHole
                });
            }
        }

        /// <summary>
        /// Check if all cats are matched after drops, and publish level cleared if so.
        /// </summary>
        private void CheckLevelCompletion()
        {
            if (_colorMatcher == null) return;
            if (!_colorMatcher.IsAllCatsMatched()) return;

            int moveCount = _scoreCalculator != null
                ? _scoreCalculator.GetMoveCount()
                : 0;

            int optimalMoves = 0;
            if (GridManager.Instance != null)
            {
                // Use grid size as a rough optimal move estimate;
                // actual value would come from LevelData
                optimalMoves = Mathf.Max(1,
                    (GridManager.Instance.GridWidth + GridManager.Instance.GridHeight) / 2);
            }

            int stars = _scoreCalculator != null
                ? _scoreCalculator.CalculateStars(moveCount, optimalMoves)
                : 1;

            int coinReward = _scoreCalculator != null
                ? _scoreCalculator.CalculateCoinReward(stars)
                : 10;

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnLevelCleared
                {
                    MoveCount = moveCount,
                    Stars = stars,
                    CoinReward = coinReward
                });
            }
        }

        /// <summary>
        /// Check if a cell has a cat-hole overlap condition.
        /// </summary>
        private bool IsCatHoleOverlap(CellData cell)
        {
            // A drop occurs when a hole tile occupies the same position as a cat.
            // Cats are placed as CellOccupant.Cat, holes slide as tile objects.
            // Overlap detected when CellType.Hole with CellOccupant.Cat.
            return cell.cellType == CellType.Hole && cell.occupantType == CellOccupant.Cat;
        }

        /// <summary>
        /// Check color match between a cat and a hole using ColorMatcher.
        /// Falls back to direct comparison if ColorMatcher is unavailable.
        /// </summary>
        private MatchResult CheckColorMatch(CatController cat, HoleController hole)
        {
            if (_colorMatcher != null)
            {
                return _colorMatcher.CheckMatch(cat, hole);
            }

            // Fallback: direct color comparison
            if (hole.IsRainbow) return MatchResult.Success;
            if (hole.IsTrap && cat.Color != hole.Color) return MatchResult.Trap;
            if (cat.Color == hole.Color) return MatchResult.Success;
            return MatchResult.Fail;
        }

        /// <summary>
        /// Find a CatController at the given grid position from the registered list.
        /// </summary>
        private CatController FindCatAtPosition(Vector2Int pos)
        {
            for (int i = 0; i < _cats.Count; i++)
            {
                if (_cats[i] == null) continue;
                if (_cats[i].GridPosition == pos && !_cats[i].IsCleared)
                {
                    return _cats[i];
                }
            }
            return null;
        }

        /// <summary>
        /// Find a HoleController at the given grid position from the registered list.
        /// </summary>
        private HoleController FindHoleAtPosition(Vector2Int pos)
        {
            for (int i = 0; i < _holes.Count; i++)
            {
                if (_holes[i] == null) continue;
                if (_holes[i].GridPosition == pos && !_holes[i].IsMatched)
                {
                    return _holes[i];
                }
            }
            return null;
        }

        #endregion
    }

    #region Drop Data Types

    /// <summary>
    /// Internal candidate for drop processing.
    /// </summary>
    internal struct DropCandidate
    {
        public Vector2Int position;
        public CellData cell;
    }

    #endregion
}
