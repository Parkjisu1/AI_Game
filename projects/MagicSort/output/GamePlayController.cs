using UnityEngine;
using UnityEngine.UI;
using TMPro;
using MagicSort.Core;
using MagicSort.Domain;

namespace MagicSort.Game
{
    /// <summary>
    /// Controls the GamePlay HUD: level info, move counter, booster buttons, and pause.
    /// Subscribes to game signals and updates UI accordingly.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Puzzle
    /// Role: Controller
    /// Phase: 1
    /// </remarks>
    public class GamePlayController : MonoBehaviour
    {
        #region Fields

        [Header("Scene References")]
        [SerializeField] private LevelManager levelManager;
        [SerializeField] private BottleCollection bottleCollection;

        [Header("HUD - Top")]
        [SerializeField] private TMP_Text levelText;
        [SerializeField] private TMP_Text moveCountText;

        [Header("HUD - Buttons")]
        [SerializeField] private Button undoButton;
        [SerializeField] private Button hintButton;
        [SerializeField] private Button extraBottleButton;
        [SerializeField] private Button shuffleButton;
        [SerializeField] private Button pauseButton;

        private SignalBus _signalBus;
        private HintCalculator _hintCalculator;
        private int _currentLevelId;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            if (ProjectContext.HasInstance)
            {
                _signalBus = ProjectContext.Instance.Resolve<SignalBus>();
            }

            _hintCalculator = new HintCalculator();
        }

        private void Start()
        {
            SetupButtons();
            SubscribeSignals();
            StartCurrentLevel();
        }

        private void OnDestroy()
        {
            UnsubscribeSignals();
            RemoveButtonListeners();
        }

        #endregion

        #region Private Methods - Setup

        private void SetupButtons()
        {
            if (undoButton != null)
            {
                undoButton.onClick.AddListener(OnUndoClicked);
            }

            if (hintButton != null)
            {
                hintButton.onClick.AddListener(OnHintClicked);
            }

            if (extraBottleButton != null)
            {
                extraBottleButton.onClick.AddListener(OnExtraBottleClicked);
            }

            if (shuffleButton != null)
            {
                shuffleButton.onClick.AddListener(OnShuffleClicked);
            }

            if (pauseButton != null)
            {
                pauseButton.onClick.AddListener(OnPauseClicked);
            }
        }

        private void RemoveButtonListeners()
        {
            if (undoButton != null) undoButton.onClick.RemoveListener(OnUndoClicked);
            if (hintButton != null) hintButton.onClick.RemoveListener(OnHintClicked);
            if (extraBottleButton != null) extraBottleButton.onClick.RemoveListener(OnExtraBottleClicked);
            if (shuffleButton != null) shuffleButton.onClick.RemoveListener(OnShuffleClicked);
            if (pauseButton != null) pauseButton.onClick.RemoveListener(OnPauseClicked);
        }

        private void StartCurrentLevel()
        {
            // Load current level from save data
            if (SaveManager.HasInstance)
            {
                _currentLevelId = SaveManager.Instance.LoadInt("HighestLevel", 0) + 1;
            }
            else
            {
                _currentLevelId = 1;
            }

            if (levelManager != null)
            {
                levelManager.StartLevel(_currentLevelId);
            }

            UpdateHUD();
        }

        private void SubscribeSignals()
        {
            if (_signalBus == null)
            {
                return;
            }

            _signalBus.Subscribe<PourCompleteSignal>(OnPourComplete);
            _signalBus.Subscribe<LevelCompleteSignal>(OnLevelComplete);
            _signalBus.Subscribe<LevelFailSignal>(OnLevelFail);
            _signalBus.Subscribe<LevelStartSignal>(OnLevelStart);
        }

        private void UnsubscribeSignals()
        {
            if (_signalBus == null)
            {
                return;
            }

            _signalBus.Unsubscribe<PourCompleteSignal>(OnPourComplete);
            _signalBus.Unsubscribe<LevelCompleteSignal>(OnLevelComplete);
            _signalBus.Unsubscribe<LevelFailSignal>(OnLevelFail);
            _signalBus.Unsubscribe<LevelStartSignal>(OnLevelStart);
        }

        #endregion

        #region Private Methods - UI

        private void UpdateHUD()
        {
            if (levelText != null)
            {
                levelText.text = $"Level {_currentLevelId}";
            }

            if (moveCountText != null && levelManager != null)
            {
                moveCountText.text = $"Moves: {levelManager.MoveCount}";
            }
        }

        #endregion

        #region Signal Handlers

        private void OnPourComplete(PourCompleteSignal signal)
        {
            UpdateHUD();
        }

        private void OnLevelStart(LevelStartSignal signal)
        {
            _currentLevelId = signal.LevelNumber;
            UpdateHUD();
        }

        private void OnLevelComplete(LevelCompleteSignal signal)
        {
            Debug.Log($"[GamePlayController] Level {signal.LevelNumber} complete! Stars: {signal.StarRating}");

            // Show win popup
            if (PopUpService.HasInstance)
            {
                PopUpService.Instance.ShowPopup("LevelComplete");
            }
        }

        private void OnLevelFail(LevelFailSignal signal)
        {
            Debug.Log($"[GamePlayController] Level {signal.LevelNumber} failed. Reason: {signal.Reason}");

            // Show fail/stuck popup
            if (PopUpService.HasInstance)
            {
                PopUpService.Instance.ShowPopup("LevelFail");
            }
        }

        #endregion

        #region Button Handlers

        private void OnUndoClicked()
        {
            if (levelManager != null)
            {
                levelManager.Undo();
                UpdateHUD();
            }
        }

        private void OnHintClicked()
        {
            if (bottleCollection == null)
            {
                return;
            }

            var bestMove = _hintCalculator.GetBestMove(bottleCollection);
            if (bestMove.HasValue)
            {
                // Visual hint: highlight the from and to bottles
                bestMove.Value.from.SetSelected(true);

                Debug.Log($"[GamePlayController] Hint: Pour from {bestMove.Value.from.name} to {bestMove.Value.to.name}");
            }
            else
            {
                Debug.Log("[GamePlayController] No valid moves available for hint.");
            }
        }

        private void OnExtraBottleClicked()
        {
            // Extra bottle booster - to be implemented with booster system
            Debug.Log("[GamePlayController] Extra bottle booster used.");

            if (_signalBus != null)
            {
                _signalBus.Fire(new BoosterUsedSignal
                {
                    Type = BoosterType.ExtraBottle,
                    RemainingCount = 0
                });
            }
        }

        private void OnShuffleClicked()
        {
            // Shuffle booster - to be implemented with booster system
            Debug.Log("[GamePlayController] Shuffle booster used.");

            if (_signalBus != null)
            {
                _signalBus.Fire(new BoosterUsedSignal
                {
                    Type = BoosterType.Shuffle,
                    RemainingCount = 0
                });
            }
        }

        private void OnPauseClicked()
        {
            if (levelManager != null)
            {
                levelManager.PauseLevel();
            }

            // Show pause popup
            if (PopUpService.HasInstance)
            {
                PopUpService.Instance.ShowPopup("Pause");
            }
        }

        #endregion
    }
}
