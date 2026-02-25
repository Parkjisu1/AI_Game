using System;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// FSM states for LevelManager. Each state controls what systems are active
    /// during that phase of level gameplay.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: State
    /// Phase: 1
    /// </remarks>

    /// <summary>
    /// Active gameplay state. Input is enabled and player can interact with bottles.
    /// </summary>
    public class PlayingState : IState<LevelState>
    {
        #region Fields

        private readonly SelectionManager _selectionManager;
        private readonly Action _onEnterCallback;
        private readonly Action _onExitCallback;

        #endregion

        #region Properties

        public LevelState StateId => LevelState.Playing;

        #endregion

        #region Constructors

        public PlayingState(SelectionManager selectionManager, Action onEnterCallback = null, Action onExitCallback = null)
        {
            _selectionManager = selectionManager;
            _onEnterCallback = onEnterCallback;
            _onExitCallback = onExitCallback;
        }

        #endregion

        #region IState Implementation

        public void OnEnter()
        {
            if (_selectionManager != null)
            {
                _selectionManager.Enable();
            }

            _onEnterCallback?.Invoke();
        }

        public void OnUpdate()
        {
            // Update logic handled by SelectionManager's own Update
        }

        public void OnExit()
        {
            if (_selectionManager != null)
            {
                _selectionManager.Disable();
            }

            _onExitCallback?.Invoke();
        }

        #endregion
    }

    /// <summary>
    /// Paused state. Input is disabled. Resume returns to Playing.
    /// </summary>
    public class PausedState : IState<LevelState>
    {
        #region Fields

        private readonly SelectionManager _selectionManager;
        private readonly Action _onEnterCallback;

        #endregion

        #region Properties

        public LevelState StateId => LevelState.Paused;

        #endregion

        #region Constructors

        public PausedState(SelectionManager selectionManager, Action onEnterCallback = null)
        {
            _selectionManager = selectionManager;
            _onEnterCallback = onEnterCallback;
        }

        #endregion

        #region IState Implementation

        public void OnEnter()
        {
            if (_selectionManager != null)
            {
                _selectionManager.Disable();
            }

            Time.timeScale = 0f;
            _onEnterCallback?.Invoke();
        }

        public void OnUpdate() { }

        public void OnExit()
        {
            Time.timeScale = 1f;
        }

        #endregion
    }

    /// <summary>
    /// Win state. Fires when all bottles are sorted. Disables input.
    /// </summary>
    public class WinState : IState<LevelState>
    {
        #region Fields

        private readonly SelectionManager _selectionManager;
        private readonly Action _onWinCallback;

        #endregion

        #region Properties

        public LevelState StateId => LevelState.Win;

        #endregion

        #region Constructors

        public WinState(SelectionManager selectionManager, Action onWinCallback = null)
        {
            _selectionManager = selectionManager;
            _onWinCallback = onWinCallback;
        }

        #endregion

        #region IState Implementation

        public void OnEnter()
        {
            if (_selectionManager != null)
            {
                _selectionManager.Disable();
            }

            _onWinCallback?.Invoke();
        }

        public void OnUpdate() { }
        public void OnExit() { }

        #endregion
    }

    /// <summary>
    /// Stuck state. No valid moves remaining. Presents options to use boosters or restart.
    /// </summary>
    public class StuckState : IState<LevelState>
    {
        #region Fields

        private readonly SelectionManager _selectionManager;
        private readonly Action<StuckType> _onStuckCallback;
        private StuckType _stuckType;

        #endregion

        #region Properties

        public LevelState StateId => LevelState.Stuck;

        /// <summary>The reason the player is stuck.</summary>
        public StuckType StuckType => _stuckType;

        #endregion

        #region Constructors

        public StuckState(SelectionManager selectionManager, Action<StuckType> onStuckCallback = null)
        {
            _selectionManager = selectionManager;
            _onStuckCallback = onStuckCallback;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Sets the stuck reason before transitioning to this state.
        /// </summary>
        /// <param name="type">The reason for being stuck.</param>
        public void SetStuckType(StuckType type)
        {
            _stuckType = type;
        }

        #endregion

        #region IState Implementation

        public void OnEnter()
        {
            if (_selectionManager != null)
            {
                _selectionManager.Disable();
            }

            _onStuckCallback?.Invoke(_stuckType);
        }

        public void OnUpdate() { }
        public void OnExit() { }

        #endregion
    }

    /// <summary>
    /// Lose state. Terminal state for failed levels.
    /// </summary>
    public class LoseState : IState<LevelState>
    {
        #region Fields

        private readonly SelectionManager _selectionManager;
        private readonly Action _onLoseCallback;

        #endregion

        #region Properties

        public LevelState StateId => LevelState.Lose;

        #endregion

        #region Constructors

        public LoseState(SelectionManager selectionManager, Action onLoseCallback = null)
        {
            _selectionManager = selectionManager;
            _onLoseCallback = onLoseCallback;
        }

        #endregion

        #region IState Implementation

        public void OnEnter()
        {
            if (_selectionManager != null)
            {
                _selectionManager.Disable();
            }

            _onLoseCallback?.Invoke();
        }

        public void OnUpdate() { }
        public void OnExit() { }

        #endregion
    }
}
