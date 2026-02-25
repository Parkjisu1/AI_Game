using UnityEngine;
using UnityEngine.SceneManagement;
using BlockBlast.Core;
using BlockBlast.Domain;

namespace BlockBlast.Game
{
    public enum GameState
    {
        Ready,
        Playing,
        Paused,
        GameOver
    }

    public class GameManager : Singleton<GameManager>
    {
        private GameState _state = GameState.Ready;
        private ScoreCalculator _scoreCalc;
        private int _gamesPlayedSinceAd;
        private const int AD_FREQUENCY = 3;

        public GameState State => _state;
        public int Score => _scoreCalc != null ? _scoreCalc.TotalScore : 0;
        public int Combo => _scoreCalc != null ? _scoreCalc.CurrentCombo : 0;

        protected override void Awake()
        {
            base.Awake();
            _scoreCalc = new ScoreCalculator();
        }

        public void StartGame()
        {
            _state = GameState.Playing;
            _scoreCalc.Reset();

            // Init board at center-upper screen area
            float boardY = 1.5f;
            GameBoard.Instance.InitBoard(new Vector3(0, boardY, 0));
            Debug.Log($"[GameManager] Board initialized at y={boardY}, origin={GameBoard.Instance.BoardOrigin}");

            // Init spawner area below the board
            float spawnerY = boardY - (GameBoard.BOARD_SIZE * GameBoard.TOTAL_CELL / 2f) - 2.0f;
            BlockSpawner.Instance.Init(new Vector3(0, spawnerY, 0));
            BlockSpawner.Instance.SpawnCandidates();
            Debug.Log($"[GameManager] Spawner initialized at y={spawnerY}, candidates={BlockSpawner.Instance.RemainingCount}");

            // Init UI
            UIManager.Instance.UpdateScoreDisplay(0);
            UIManager.Instance.UpdateComboDisplay(0);

            EventManager.Instance.Publish(EventManager.EVT_GAME_START);

            Debug.Log("[GameManager] Game started!");

            #if FIREBASE_ANALYTICS
            SDK.FirebaseManager.Instance.LogEvent("game_start");
            #endif
        }

        public void OnBlockPlaced(int cellCount)
        {
            if (_state != GameState.Playing) return;

            // Placement score
            int placeScore = _scoreCalc.CalculatePlacementScore(cellCount);
            _scoreCalc.AddScore(placeScore);

            // Check and clear lines
            int linesCleared = GameBoard.Instance.CheckAndClearLines();

            if (linesCleared > 0)
            {
                int lineScore = _scoreCalc.CalculateLineClearScore(linesCleared);
                _scoreCalc.AddScore(lineScore);

                UIManager.Instance.UpdateComboDisplay(_scoreCalc.CurrentCombo);

                if (_scoreCalc.CurrentCombo > 1)
                {
                    Vector3 boardCenter = GameBoard.Instance.BoardOrigin +
                        new Vector3(GameBoard.BOARD_SIZE * GameBoard.TOTAL_CELL / 2f,
                                    GameBoard.BOARD_SIZE * GameBoard.TOTAL_CELL / 2f, 0);
                    EffectManager.Instance.PlayComboEffect(_scoreCalc.CurrentCombo, boardCenter);
                }
            }
            else
            {
                _scoreCalc.ResetCombo();
            }

            UIManager.Instance.UpdateScoreDisplay(_scoreCalc.TotalScore);

            // Check game over after a short delay (let new candidates spawn first)
            if (!BlockSpawner.Instance.HasAnyValidPlacement())
            {
                GameOver();
            }
        }

        public void GameOver()
        {
            if (_state == GameState.GameOver) return;
            _state = GameState.GameOver;

            BlockSpawner.Instance.SetDragEnabled(false);

            int score = _scoreCalc.TotalScore;
            int highScore = SaveManager.Instance.GetHighScore();
            bool isNewHigh = SaveManager.Instance.SetHighScore(score);
            if (isNewHigh) highScore = score;

            _gamesPlayedSinceAd++;
            SaveManager.Instance.IncrementGamesPlayed();

            UIManager.Instance.ShowGameOverPopup(score, highScore, isNewHigh);

            // Show interstitial ad every N games
            if (_gamesPlayedSinceAd >= AD_FREQUENCY && !SaveManager.Instance.IsAdsRemoved())
            {
                _gamesPlayedSinceAd = 0;
                #if GOOGLE_MOBILE_ADS
                SDK.AdMobManager.Instance.ShowInterstitial();
                #endif
            }

            EventManager.Instance.Publish(EventManager.EVT_GAME_OVER, score);

            #if FIREBASE_ANALYTICS
            SDK.FirebaseManager.Instance.LogEvent("game_over", "score", score);
            #endif
        }

        public void ContinueWithAdReward()
        {
            _state = GameState.Playing;
            GameBoard.Instance.ClearBottomRows(3);
            BlockSpawner.Instance.SetDragEnabled(true);

            UIManager.Instance.HideAllPopups();

            // Re-check if still game over after clearing
            if (!BlockSpawner.Instance.HasAnyValidPlacement())
            {
                GameOver();
            }
        }

        public void RestartGame()
        {
            UIManager.Instance.HideAllPopups();
            GameBoard.Instance.ClearBoard();
            StartGame();
        }

        public void PauseGame()
        {
            if (_state != GameState.Playing) return;
            _state = GameState.Paused;
            BlockSpawner.Instance.SetDragEnabled(false);
            EventManager.Instance.Publish(EventManager.EVT_GAME_PAUSE, true);
        }

        public void ResumeGame()
        {
            if (_state != GameState.Paused) return;
            _state = GameState.Playing;
            BlockSpawner.Instance.SetDragEnabled(true);
            EventManager.Instance.Publish(EventManager.EVT_GAME_PAUSE, false);
        }

        public void GoToMainMenu()
        {
            _state = GameState.Ready;
            SceneManager.LoadScene("Main");
        }
    }
}
