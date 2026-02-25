using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Data;

namespace VeilBreaker.Idle
{
    /// <summary>
    /// Manages stage progression: starting, retrying, chapter/difficulty tracking,
    /// and clearing records. Communicates with BattleManager exclusively via events.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// System: Stage
    /// Phase: 2
    /// </remarks>
    public class StageManager : Singleton<StageManager>
    {
        #region Fields

        private StageState _state = StageState.Idle;
        private string _currentStageId;

        #endregion

        #region Properties

        /// <summary>
        /// Current stage flow state.
        /// </summary>
        public StageState State => _state;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            EventManager.Subscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            EventManager.Subscribe(GameConstants.Events.OnStageFail, OnStageFail);
        }

        protected override void OnDestroy()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnStageComplete, OnStageComplete);
            EventManager.Unsubscribe(GameConstants.Events.OnStageFail, OnStageFail);
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Start the specified stage. Validates unlock state before transitioning.
        /// Publishes OnStageStart on success.
        /// </summary>
        /// <param name="stageId">Stage ID in the format "{chapter}_{stage}", e.g. "1_1".</param>
        public void StartStage(string stageId)
        {
            if (string.IsNullOrEmpty(stageId))
            {
                Debug.LogWarning("[StageManager] StartStage called with null or empty stageId.");
                return;
            }

            // Step 1: Get stage data
            if (!DataManager.HasInstance)
            {
                Debug.LogError("[StageManager] DataManager not available.");
                return;
            }

            StageData stageData = DataManager.Instance.GetStageData(stageId);
            if (stageData == null)
            {
                Debug.LogWarning($"[StageManager] StageData not found for id: {stageId}");
                return;
            }

            // Step 2: Validate unlock
            if (!IsStageUnlocked(stageId))
            {
                Debug.LogWarning($"[StageManager] Stage {stageId} is not yet unlocked.");
                return;
            }

            // Step 3: Transition state
            _currentStageId = stageId;
            _state = StageState.InProgress;

            // Step 4: Notify
            EventManager.Publish(GameConstants.Events.OnStageStart, stageId);
        }

        /// <summary>
        /// Retry the current stage. Re-calls StartStage with the same stageId.
        /// No-op if no stage is currently active.
        /// </summary>
        public void RetryStage()
        {
            if (string.IsNullOrEmpty(_currentStageId))
            {
                Debug.LogWarning("[StageManager] RetryStage called but no current stage set.");
                return;
            }

            _state = StageState.Idle;
            StartStage(_currentStageId);
        }

        /// <summary>
        /// Returns the currently active stageId, or null if no stage is in progress.
        /// </summary>
        public string GetCurrentStageId()
        {
            return _currentStageId;
        }

        /// <summary>
        /// Returns user stage progress data from DataManager.
        /// </summary>
        public UserStageData GetUserStageData()
        {
            return DataManager.HasInstance ? DataManager.Instance.GetUserStageData() : null;
        }

        /// <summary>
        /// Returns the highest cleared stage index (linear).
        /// </summary>
        public int GetMaxClearedStage()
        {
            return GetUserStageData()?.maxClearedStage ?? 0;
        }

        /// <summary>
        /// Returns true if the given stageId is accessible based on maxClearedStage.
        /// Stage "1_1" is always unlocked. Subsequent stages require the previous to be cleared.
        /// </summary>
        /// <param name="stageId">Stage ID in format "{chapter}_{stage}".</param>
        public bool IsStageUnlocked(string stageId)
        {
            if (string.IsNullOrEmpty(stageId)) return false;

            // Parse chapter and stage number
            if (!TryParseStageId(stageId, out int chapter, out int stageNum)) return false;

            // Stage 1_1 always unlocked
            if (chapter == 1 && stageNum == 1) return true;

            int linearIndex = ToLinearIndex(chapter, stageNum);
            return linearIndex <= GetMaxClearedStage() + 1;
        }

        #endregion

        #region Private Methods

        private void OnStageComplete(object data)
        {
            // Step 5: Record clear
            _state = StageState.Idle;

            if (!DataManager.HasInstance || string.IsNullOrEmpty(_currentStageId)) return;

            UserStageData userStage = DataManager.Instance.GetUserStageData();
            if (userStage == null) return;

            if (!TryParseStageId(_currentStageId, out int chapter, out int stageNum)) return;

            int linearIndex = ToLinearIndex(chapter, stageNum);

            // Step 6: Update max cleared, unlock next
            if (linearIndex > userStage.maxClearedStage)
            {
                userStage.maxClearedStage = linearIndex;
                userStage.currentChapter = chapter;
                userStage.currentStage = stageNum;
            }

            // Step 7: Persist
            DataManager.Instance.UpdateUserStage(userStage);
            if (SaveManager.HasInstance) SaveManager.Instance.Save();
        }

        private void OnStageFail(object data)
        {
            _state = StageState.Idle;
        }

        /// <summary>
        /// Parses a stageId string into chapter and stage number.
        /// Expected format: "{chapter}_{stageNum}".
        /// </summary>
        private bool TryParseStageId(string stageId, out int chapter, out int stageNum)
        {
            chapter = 0;
            stageNum = 0;

            string[] parts = stageId.Split('_');
            if (parts.Length < 2) return false;
            if (!int.TryParse(parts[0], out chapter)) return false;
            if (!int.TryParse(parts[1], out stageNum)) return false;
            return true;
        }

        /// <summary>
        /// Converts chapter/stageNum to a linear index.
        /// Assumes 10 stages per chapter for unlock comparison.
        /// </summary>
        private int ToLinearIndex(int chapter, int stageNum)
        {
            return (chapter - 1) * 10 + stageNum;
        }

        #endregion
    }

    /// <summary>
    /// Stage flow states for StageManager.
    /// </summary>
    public enum StageState
    {
        Idle,
        InProgress,
        Paused
    }
}
