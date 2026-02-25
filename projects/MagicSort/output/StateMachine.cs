using System;
using System.Collections.Generic;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Interface for state implementations used by StateMachine.
    /// </summary>
    /// <typeparam name="TState">The enum type representing states.</typeparam>
    public interface IState<TState> where TState : Enum
    {
        /// <summary>The enum value identifying this state.</summary>
        TState StateId { get; }

        /// <summary>Called when entering this state.</summary>
        void OnEnter();

        /// <summary>Called every frame while in this state.</summary>
        void OnUpdate();

        /// <summary>Called when exiting this state.</summary>
        void OnExit();
    }

    /// <summary>
    /// Generic Finite State Machine supporting enum-based states.
    /// Manages state transitions with Enter/Update/Exit lifecycle.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: State
    /// Phase: 0
    /// </remarks>
    /// <typeparam name="TState">The enum type representing states.</typeparam>
    public class StateMachine<TState> where TState : Enum
    {
        #region Fields

        private readonly Dictionary<TState, IState<TState>> _states = new Dictionary<TState, IState<TState>>();
        private IState<TState> _currentState;
        private TState _currentStateId;
        private TState _previousStateId;
        private bool _isTransitioning;

        #endregion

        #region Properties

        /// <summary>
        /// The currently active state identifier.
        /// </summary>
        public TState CurrentStateId => _currentStateId;

        /// <summary>
        /// The previously active state identifier.
        /// </summary>
        public TState PreviousStateId => _previousStateId;

        /// <summary>
        /// Whether the state machine is currently transitioning between states.
        /// </summary>
        public bool IsTransitioning => _isTransitioning;

        /// <summary>
        /// The currently active state instance. May be null if no state is set.
        /// </summary>
        public IState<TState> CurrentState => _currentState;

        #endregion

        #region Events

        /// <summary>
        /// Invoked when a state transition occurs. Parameters: (previousState, newState).
        /// </summary>
        public event Action<TState, TState> OnStateChanged;

        #endregion

        #region Public Methods

        /// <summary>
        /// Registers a state implementation.
        /// </summary>
        /// <param name="state">The state to register.</param>
        public void AddState(IState<TState> state)
        {
            if (state == null)
            {
                Debug.LogError("[StateMachine] Cannot add null state.");
                return;
            }

            TState id = state.StateId;
            if (_states.ContainsKey(id))
            {
                Debug.LogWarning($"[StateMachine] State {id} already registered. Overwriting.");
            }

            _states[id] = state;
        }

        /// <summary>
        /// Removes a registered state. Cannot remove the currently active state.
        /// </summary>
        /// <param name="stateId">The state to remove.</param>
        public void RemoveState(TState stateId)
        {
            if (_currentState != null && _currentStateId.Equals(stateId))
            {
                Debug.LogWarning($"[StateMachine] Cannot remove currently active state {stateId}.");
                return;
            }

            _states.Remove(stateId);
        }

        /// <summary>
        /// Transitions to a new state. Calls OnExit on current and OnEnter on new.
        /// </summary>
        /// <param name="newStateId">The state to transition to.</param>
        public void ChangeState(TState newStateId)
        {
            if (_isTransitioning)
            {
                Debug.LogWarning($"[StateMachine] Cannot change state to {newStateId} during an active transition.");
                return;
            }

            if (!_states.TryGetValue(newStateId, out IState<TState> newState))
            {
                Debug.LogError($"[StateMachine] State {newStateId} not registered.");
                return;
            }

            _isTransitioning = true;

            // Exit current state
            if (_currentState != null)
            {
                _previousStateId = _currentStateId;

                try
                {
                    _currentState.OnExit();
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[StateMachine] Error in OnExit for state {_currentStateId}: {ex.Message}");
                }
            }

            // Enter new state
            _currentStateId = newStateId;
            _currentState = newState;

            try
            {
                _currentState.OnEnter();
            }
            catch (Exception ex)
            {
                Debug.LogError($"[StateMachine] Error in OnEnter for state {_currentStateId}: {ex.Message}");
            }

            _isTransitioning = false;

            OnStateChanged?.Invoke(_previousStateId, _currentStateId);
        }

        /// <summary>
        /// Calls OnUpdate on the current state. Should be called from a MonoBehaviour Update.
        /// </summary>
        public void Update()
        {
            if (_currentState == null || _isTransitioning) return;

            try
            {
                _currentState.OnUpdate();
            }
            catch (Exception ex)
            {
                Debug.LogError($"[StateMachine] Error in OnUpdate for state {_currentStateId}: {ex.Message}");
            }
        }

        /// <summary>
        /// Checks if a given state is registered.
        /// </summary>
        /// <param name="stateId">The state identifier to check.</param>
        /// <returns>True if the state is registered.</returns>
        public bool HasState(TState stateId)
        {
            return _states.ContainsKey(stateId);
        }

        /// <summary>
        /// Checks if the current state matches the given state identifier.
        /// </summary>
        /// <param name="stateId">The state to compare against.</param>
        /// <returns>True if currently in the given state.</returns>
        public bool IsInState(TState stateId)
        {
            return _currentState != null && _currentStateId.Equals(stateId);
        }

        #endregion
    }
}
