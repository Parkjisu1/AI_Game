using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Singleton manager that controls level lifecycle: start, play, pause, win, stuck, quit.
    /// Wires up all domain subsystems and manages the LevelState FSM.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Manager
    /// Phase: 1
    /// </remarks>
    public class LevelManager : Singleton<LevelManager>
    {
        #region Fields

        [Header("Scene References")]
        [SerializeField] private BottleCollection _bottleCollection;
        [SerializeField] private SelectionManager _selectionManager;
        [SerializeField] private PourProcessor _pourProcessor;

        private SignalBus _signalBus;
        private StateMachine<LevelState> _fsm;
        private LevelDataProvider _levelDataProvider;
        private PourValidator _pourValidator;
        private CompletionChecker _completionChecker;
        private UndoManager _undoManager;

        private LevelModel _currentLevel;
        private int _moveCount;
        private int _currentLevelId;

        // Cached state references for configuration
        private StuckState _stuckState;

        #endregion

        #region Properties

        /// <summary>The currently loaded level model.</summary>
        public LevelModel CurrentLevel => _currentLevel;

        /// <summary>Current move count this attempt.</summary>
        public int MoveCount => _moveCount;

        /// <summary>Active level ID.</summary>
        public int CurrentLevelId => _currentLevelId;

        /// <summary>Current FSM state.</summary>
        public LevelState CurrentState => _fsm != null ? _fsm.CurrentStateId : LevelState.None;

        #endregion

        #region Singleton Lifecycle

        protected override void OnSingletonAwake()
        {
            InitializeSystems();
            InitializeFSM();
            SubscribeSignals();
        }

        protected override void OnSingletonDestroy()
        {
            UnsubscribeSignals();
        }

        #endregion

        #region Unity Lifecycle

        private void Update()
        {
            _fsm?.Update();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Loads and starts a level by ID.
        /// </summary>
        /// <param name="levelId">1-based level ID.</param>
        public void StartLevel(int levelId)
        {
            _currentLevelId = levelId;
            _moveCount = 0;

            _currentLevel = _levelDataProvider.GetLevel(levelId);
            if (_currentLevel == null)
            {
                Debug.LogError($"[LevelManager] Failed to load level {levelId}.");
                return;
            }

            // Initialize subsystems
            _undoManager.Clear();
            _bottleCollection.Initialize(_currentLevel);
            _completionChecker.SetCurrentLevel(levelId);

            // Fire level start signal
            if (_signalBus != null)
            {
                _signalBus.Fire(new LevelStartSignal
                {
                    LevelNumber = levelId,
                    Difficulty = _currentLevel.Difficulty
                });
            }

            // Transition to Playing
            _fsm.ChangeState(LevelState.Playing);

            Debug.Log($"[LevelManager] Started level {levelId} ({_currentLevel.Difficulty}).");
        }

        /// <summary>
        /// Restarts the current level.
        /// </summary>
        public void RestartLevel()
        {
            if (_currentLevelId > 0)
            {
                StartLevel(_currentLevelId);
            }
        }

        /// <summary>
        /// Called when the level is won. Transitions to Win state.
        /// </summary>
        public void WinLevel()
        {
            if (_fsm.CurrentStateId == LevelState.Win)
            {
                return;
            }

            // Save progress
            SaveProgress();

            _fsm.ChangeState(LevelState.Win);
            Debug.Log($"[LevelManager] Level {_currentLevelId} won in {_moveCount} moves.");
        }

        /// <summary>
        /// Called when the player is stuck. Transitions to Stuck state.
        /// </summary>
        /// <param name="type">The reason for being stuck.</param>
        public void StuckLevel(StuckType type)
        {
            if (_fsm.CurrentStateId == LevelState.Stuck)
            {
                return;
            }

            if (_stuckState != null)
            {
                _stuckState.SetStuckType(type);
            }

            _fsm.ChangeState(LevelState.Stuck);
            Debug.Log($"[LevelManager] Level {_currentLevelId} stuck: {type}.");
        }

        /// <summary>
        /// Pauses the level. Disables input.
        /// </summary>
        public void PauseLevel()
        {
            if (_fsm.CurrentStateId == LevelState.Playing)
            {
                _fsm.ChangeState(LevelState.Paused);
            }
        }

        /// <summary>
        /// Resumes from paused state.
        /// </summary>
        public void ResumeLevel()
        {
            if (_fsm.CurrentStateId == LevelState.Paused)
            {
                _fsm.ChangeState(LevelState.Playing);
            }
        }

        /// <summary>
        /// Quits the current level. Cleans up and transitions to Quit state.
        /// </summary>
        public void QuitLevel()
        {
            _bottleCollection.Clear();
            _undoManager.Clear();
            _currentLevel = null;

            if (_fsm.HasState(LevelState.Quit))
            {
                _fsm.ChangeState(LevelState.Quit);
            }
        }

        /// <summary>
        /// Returns the current move count.
        /// </summary>
        public int GetMoveCount()
        {
            return _moveCount;
        }

        /// <summary>
        /// Returns the current FSM state.
        /// </summary>
        public LevelState GetCurrentState()
        {
            return _fsm != null ? _fsm.CurrentStateId : LevelState.None;
        }

        /// <summary>
        /// Performs an undo operation if available.
        /// </summary>
        public void Undo()
        {
            if (_fsm.CurrentStateId != LevelState.Playing)
            {
                return;
            }

            if (_undoManager.Undo())
            {
                _moveCount = Mathf.Max(0, _moveCount - 1);
                Debug.Log($"[LevelManager] Undo performed. Moves: {_moveCount}.");
            }
        }

        #endregion

        #region Private Methods

        private void InitializeSystems()
        {
            // Resolve SignalBus from DI
            if (ProjectContext.HasInstance)
            {
                _signalBus = ProjectContext.Instance.Resolve<SignalBus>();
            }

            // Create non-MonoBehaviour systems
            _levelDataProvider = new LevelDataProvider();
            _pourValidator = new PourValidator();
            _undoManager = new UndoManager();

            // Create CompletionChecker
            _completionChecker = new CompletionChecker(_bottleCollection, _signalBus);

            // Initialize SelectionManager with dependencies
            if (_selectionManager != null)
            {
                _selectionManager.Initialize(_pourValidator, _pourProcessor, _bottleCollection, _undoManager);
            }
        }

        private void InitializeFSM()
        {
            _fsm = new StateMachine<LevelState>();

            var playingState = new PlayingState(_selectionManager);
            var pausedState = new PausedState(_selectionManager);
            var winState = new WinState(_selectionManager, OnWinStateEntered);
            _stuckState = new StuckState(_selectionManager, OnStuckStateEntered);
            var loseState = new LoseState(_selectionManager);

            _fsm.AddState(playingState);
            _fsm.AddState(pausedState);
            _fsm.AddState(winState);
            _fsm.AddState(_stuckState);
            _fsm.AddState(loseState);

            _fsm.OnStateChanged += OnStateChanged;
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
        }

        #endregion

        #region Signal Handlers

        private void OnPourComplete(PourCompleteSignal signal)
        {
            if (_fsm.CurrentStateId != LevelState.Playing)
            {
                return;
            }

            _moveCount++;

            // Check completion after each pour
            _completionChecker.CheckAndNotify(_moveCount);
        }

        private void OnLevelComplete(LevelCompleteSignal signal)
        {
            WinLevel();
        }

        private void OnLevelFail(LevelFailSignal signal)
        {
            StuckLevel(signal.Reason);
        }

        #endregion

        #region State Callbacks

        private void OnStateChanged(LevelState previous, LevelState next)
        {
            Debug.Log($"[LevelManager] State: {previous} -> {next}");
        }

        private void OnWinStateEntered()
        {
            if (SoundManager.HasInstance)
            {
                // Win SFX would be played here via SoundManager
                // SoundManager.Instance.PlaySFX(winClip);
            }
        }

        private void OnStuckStateEntered(StuckType type)
        {
            // Show stuck popup or UI notification
            Debug.Log($"[LevelManager] Stuck popup should appear. Reason: {type}");
        }

        #endregion

        #region Save/Load

        private void SaveProgress()
        {
            if (!SaveManager.HasInstance)
            {
                return;
            }

            // Save highest completed level
            int currentBest = SaveManager.Instance.LoadInt("HighestLevel", 0);
            if (_currentLevelId > currentBest)
            {
                SaveManager.Instance.SaveInt("HighestLevel", _currentLevelId);
            }

            // Save star rating
            int stars = CalculateStars();
            string starKey = $"Level_{_currentLevelId}_Stars";
            int existingStars = SaveManager.Instance.LoadInt(starKey, 0);
            if (stars > existingStars)
            {
                SaveManager.Instance.SaveInt(starKey, stars);
            }
        }

        private int CalculateStars()
        {
            if (_currentLevel == null)
            {
                return 1;
            }

            int par = _currentLevel.Par;
            if (_moveCount <= par)
            {
                return 3;
            }
            if (_moveCount <= par * 1.5f)
            {
                return 2;
            }
            return 1;
        }

        #endregion
    }
}
