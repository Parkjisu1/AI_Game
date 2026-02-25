using System.Collections;
using UnityEngine;
using UnityEngine.SceneManagement;
using VeilBreaker.Core;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Root game manager controlling app lifecycle, scene transitions,
    /// and global game state. Entry point for all initialization sequences.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Generic
    /// Role: Manager
    /// Phase: 3
    /// </remarks>
    public class GameManager : Singleton<GameManager>
    {
        #region Enums

        public enum GameState
        {
            Title,
            Lobby,
            Battle,
            Loading
        }

        #endregion

        #region Fields

        [SerializeField] private float _sceneTransitionDelay = 0.5f;

        private GameState _currentState = GameState.Title;
        private bool _isFirstFocus = true;
        private bool _isLoadingScene;

        #endregion

        #region Properties

        /// <summary>
        /// Current game state.
        /// </summary>
        public GameState CurrentState => _currentState;

        /// <summary>
        /// True while a scene transition is in progress.
        /// </summary>
        public bool IsLoadingScene => _isLoadingScene;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            Application.targetFrameRate = 60;
            Screen.sleepTimeout = SleepTimeout.NeverSleep;
        }

        private void OnApplicationPause(bool pause)
        {
            if (pause)
            {
                SaveGameData();
            }
            else
            {
                if (!_isFirstFocus)
                {
                    CheckOfflineReward();
                }
            }
        }

        private void OnApplicationFocus(bool focus)
        {
            if (focus)
            {
                if (!_isFirstFocus)
                {
                    CheckOfflineReward();
                }
                _isFirstFocus = false;
            }
            else
            {
                SaveGameData();
            }
        }

        protected override void OnApplicationQuit()
        {
            SaveGameData();
            base.OnApplicationQuit();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Get the current game state.
        /// </summary>
        public GameState GetCurrentState()
        {
            return _currentState;
        }

        /// <summary>
        /// Set the game state and publish state change event.
        /// </summary>
        public void SetState(GameState state)
        {
            if (_currentState == state) return;

            _currentState = state;
            EventManager.Publish(GameConstants.Events.OnPageChanged, state.ToString());
        }

        /// <summary>
        /// Load a scene by name with async loading.
        /// </summary>
        public void ChangeScene(string sceneName)
        {
            if (_isLoadingScene)
            {
                Debug.LogWarning("[GameManager] Scene transition already in progress.");
                return;
            }

            if (string.IsNullOrEmpty(sceneName))
            {
                Debug.LogError("[GameManager] ChangeScene called with null/empty sceneName.");
                return;
            }

            StartCoroutine(LoadSceneAsync(sceneName));
        }

        /// <summary>
        /// Convenience: transition to Title scene.
        /// </summary>
        public void GoToTitle()
        {
            SetState(GameState.Title);
            ChangeScene(GameConstants.Scenes.Title);
        }

        /// <summary>
        /// Convenience: transition to Main/Lobby scene.
        /// </summary>
        public void GoToLobby()
        {
            SetState(GameState.Lobby);
            ChangeScene(GameConstants.Scenes.Main);
        }

        /// <summary>
        /// Convenience: transition to GameScene (battle).
        /// </summary>
        public void GoToBattle()
        {
            SetState(GameState.Battle);
            ChangeScene(GameConstants.Scenes.GameScene);
        }

        #endregion

        #region Private Methods

        private IEnumerator LoadSceneAsync(string sceneName)
        {
            _isLoadingScene = true;
            SetState(GameState.Loading);

            SaveGameData();

            if (UISystem.HasInstance)
            {
                UISystem.Instance.CloseAllPopups();
            }

            yield return new WaitForSeconds(_sceneTransitionDelay);

            var asyncOp = SceneManager.LoadSceneAsync(sceneName);
            if (asyncOp == null)
            {
                Debug.LogError($"[GameManager] Failed to load scene: {sceneName}");
                _isLoadingScene = false;
                yield break;
            }

            asyncOp.allowSceneActivation = true;

            while (!asyncOp.isDone)
            {
                yield return null;
            }

            _isLoadingScene = false;
        }

        private void SaveGameData()
        {
            if (VeilBreaker.Data.SaveManager.HasInstance)
            {
                VeilBreaker.Data.SaveManager.Instance.Save();
            }
        }

        private void CheckOfflineReward()
        {
            if (VeilBreaker.Idle.OfflineProgressManager.HasInstance)
            {
                VeilBreaker.Idle.OfflineProgressManager.Instance.CalculateOfflineReward();
            }
        }

        #endregion
    }
}
