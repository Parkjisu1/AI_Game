using UnityEngine;
using UnityEngine.SceneManagement;
using DropTheCat.Core;
using DropTheCat.Domain;

namespace DropTheCat.Game
{
    /// <summary>
    /// Controls overall game flow: state machine, scene transitions, level lifecycle,
    /// and coordination between domain systems. Does not implement game logic directly.
    /// </summary>
    /// <remarks>
    /// Layer: Game | Genre: Puzzle | Role: Manager | Phase: 3
    /// </remarks>
    public class GameManager : Singleton<GameManager>
    {
        #region Constants

        private const string SCENE_TITLE = "Title";
        private const string SCENE_MAIN = "Main";
        private const string SCENE_GAME = "GameScene";
        private const string BGM_TITLE = "bgm_title";
        private const string BGM_MAIN = "bgm_main";
        private const string BGM_GAME = "bgm_game";
        private const int INTERSTITIAL_AD_INTERVAL = 3;

        #endregion

        #region Fields

        [SerializeField] private ScoreCalculator scoreCalculator;

        private GameState _currentState;
        private bool _isPaused;
        private int _clearCountSinceAd;

        #endregion

        #region Properties

        public GameState CurrentState => _currentState;
        public bool IsPaused => _isPaused;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            _currentState = GameState.Title;
            _isPaused = false;
            _clearCountSinceAd = 0;
        }

        private void OnEnable()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Subscribe<OnLevelCleared>(HandleLevelCleared);
                EventManager.Instance.Subscribe<OnLevelFailed>(HandleLevelFailed);
            }
        }

        protected override void OnDestroy()
        {
            if (EventManager.HasInstance)
            {
                EventManager.Instance.Unsubscribe<OnLevelCleared>(HandleLevelCleared);
                EventManager.Instance.Unsubscribe<OnLevelFailed>(HandleLevelFailed);
            }

            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Start a level: transition to Loading state, delegate to LevelManager,
        /// reset per-level systems, then transition to Playing state.
        /// </summary>
        public void StartLevel(int levelNumber)
        {
            if (_currentState == GameState.Loading) return;

            ChangeState(GameState.Loading);

            // Reset per-level systems
            if (scoreCalculator != null)
            {
                scoreCalculator.Reset();
            }

            if (BoosterManager.HasInstance)
            {
                BoosterManager.Instance.ResetLevelUsage();
            }

            if (SlideProcessor.HasInstance)
            {
                SlideProcessor.Instance.ClearHistory();
            }

            // Load level via LevelManager
            if (LevelManager.HasInstance)
            {
                LevelManager.Instance.LoadLevel(levelNumber);
            }

            // Ensure we are in the game scene
            if (SceneManager.GetActiveScene().name != SCENE_GAME)
            {
                SceneManager.LoadScene(SCENE_GAME);
            }

            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlayBGM(BGM_GAME);
            }

            _isPaused = false;
            Time.timeScale = 1f;
            ChangeState(GameState.Playing);
        }

        /// <summary>
        /// Retry the current level by reloading it through LevelManager.
        /// </summary>
        public void RetryLevel()
        {
            if (!LevelManager.HasInstance) return;

            int currentLevel = LevelManager.Instance.CurrentLevel;
            if (currentLevel <= 0) return;

            StartLevel(currentLevel);
        }

        /// <summary>
        /// Return to the main menu: clean up game state, load main scene.
        /// </summary>
        public void GoToMain()
        {
            // Ensure time is running
            _isPaused = false;
            Time.timeScale = 1f;

            // Clean up game systems
            CleanupGameSystems();

            ChangeState(GameState.Main);

            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlayBGM(BGM_MAIN);
            }

            SceneManager.LoadScene(SCENE_MAIN);
        }

        /// <summary>
        /// Pause the game by freezing time. Only works during Playing state.
        /// </summary>
        public void PauseGame()
        {
            if (_currentState != GameState.Playing) return;
            if (_isPaused) return;

            _isPaused = true;
            Time.timeScale = 0f;
            ChangeState(GameState.Paused);
        }

        /// <summary>
        /// Resume the game by restoring time. Only works during Paused state.
        /// </summary>
        public void ResumeGame()
        {
            if (_currentState != GameState.Paused) return;
            if (!_isPaused) return;

            _isPaused = false;
            Time.timeScale = 1f;
            ChangeState(GameState.Playing);
        }

        /// <summary>
        /// Quit the game. On editor stops play mode, on device quits application.
        /// </summary>
        public void QuitGame()
        {
#if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
#else
            Application.Quit();
#endif
        }

        /// <summary>
        /// Transition from Title to Main state. Called after title screen loading completes.
        /// </summary>
        public void OnTitleComplete()
        {
            ChangeState(GameState.Main);

            if (SoundManager.HasInstance)
            {
                SoundManager.Instance.PlayBGM(BGM_MAIN);
            }

            SceneManager.LoadScene(SCENE_MAIN);
        }

        #endregion

        #region Private Methods

        private void HandleLevelCleared(OnLevelCleared eventData)
        {
            if (_currentState != GameState.Playing) return;

            // Award coins
            if (CurrencyManager.HasInstance && eventData.CoinReward > 0)
            {
                CurrencyManager.Instance.AddCoins(eventData.CoinReward);
            }

            // Track interstitial ad interval
            _clearCountSinceAd++;

            ChangeState(GameState.Result);
        }

        private void HandleLevelFailed(OnLevelFailed eventData)
        {
            if (_currentState != GameState.Playing) return;

            ChangeState(GameState.Result);
        }

        /// <summary>
        /// Clean up game systems when leaving a level.
        /// </summary>
        private void CleanupGameSystems()
        {
            if (GridManager.HasInstance)
            {
                GridManager.Instance.ClearGrid();
            }

            if (SlideProcessor.HasInstance)
            {
                SlideProcessor.Instance.ClearHistory();
                SlideProcessor.Instance.ClearTileMap();
            }

            if (DropProcessor.HasInstance)
            {
                DropProcessor.Instance.ClearTrackedObjects();
            }
        }

        /// <summary>
        /// Change game state and publish event.
        /// </summary>
        private void ChangeState(GameState newState)
        {
            if (_currentState == newState) return;

            _currentState = newState;

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Publish(new OnGameStateChanged
                {
                    NewState = newState
                });
            }
        }

        /// <summary>
        /// Check if an interstitial ad should be shown (every N level clears).
        /// </summary>
        public bool ShouldShowInterstitialAd()
        {
            return _clearCountSinceAd >= INTERSTITIAL_AD_INTERVAL;
        }

        /// <summary>
        /// Reset the interstitial ad counter. Call after showing an ad.
        /// </summary>
        public void ResetAdCounter()
        {
            _clearCountSinceAd = 0;
        }

        #endregion
    }
}
