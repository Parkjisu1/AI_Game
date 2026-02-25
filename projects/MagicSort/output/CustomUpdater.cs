using System.Collections.Generic;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Interface for objects that need per-frame updates without MonoBehaviour.
    /// </summary>
    public interface IFrameUpdate
    {
        /// <summary>Called every frame by CustomUpdater.</summary>
        void OnFrameUpdate(float deltaTime);
    }

    /// <summary>
    /// Interface for objects that need once-per-second updates.
    /// </summary>
    public interface ISecondUpdate
    {
        /// <summary>Called approximately once per second by CustomUpdater.</summary>
        void OnSecondUpdate();
    }

    /// <summary>
    /// Centralized update manager that dispatches per-frame and per-second callbacks.
    /// Reduces MonoBehaviour Update overhead by consolidating into a single Update call.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Manager
    /// Phase: 0
    /// </remarks>
    public class CustomUpdater : Singleton<CustomUpdater>
    {
        #region Fields

        private readonly List<IFrameUpdate> _frameListeners = new List<IFrameUpdate>();
        private readonly List<ISecondUpdate> _secondListeners = new List<ISecondUpdate>();

        private readonly List<IFrameUpdate> _pendingFrameAdd = new List<IFrameUpdate>();
        private readonly List<IFrameUpdate> _pendingFrameRemove = new List<IFrameUpdate>();
        private readonly List<ISecondUpdate> _pendingSecondAdd = new List<ISecondUpdate>();
        private readonly List<ISecondUpdate> _pendingSecondRemove = new List<ISecondUpdate>();

        private float _secondTimer;
        private bool _isUpdating;

        #endregion

        #region Properties

        /// <summary>Number of registered frame update listeners.</summary>
        public int FrameListenerCount => _frameListeners.Count;

        /// <summary>Number of registered second update listeners.</summary>
        public int SecondListenerCount => _secondListeners.Count;

        #endregion

        #region Public Methods

        /// <summary>
        /// Registers a listener for per-frame updates.
        /// </summary>
        /// <param name="listener">The listener to register.</param>
        public void RegisterFrameUpdate(IFrameUpdate listener)
        {
            if (listener == null) return;

            if (_isUpdating)
            {
                if (!_pendingFrameAdd.Contains(listener))
                {
                    _pendingFrameAdd.Add(listener);
                }
            }
            else
            {
                if (!_frameListeners.Contains(listener))
                {
                    _frameListeners.Add(listener);
                }
            }
        }

        /// <summary>
        /// Unregisters a listener from per-frame updates.
        /// </summary>
        /// <param name="listener">The listener to unregister.</param>
        public void UnregisterFrameUpdate(IFrameUpdate listener)
        {
            if (listener == null) return;

            if (_isUpdating)
            {
                if (!_pendingFrameRemove.Contains(listener))
                {
                    _pendingFrameRemove.Add(listener);
                }
            }
            else
            {
                _frameListeners.Remove(listener);
            }
        }

        /// <summary>
        /// Registers a listener for once-per-second updates.
        /// </summary>
        /// <param name="listener">The listener to register.</param>
        public void RegisterSecondUpdate(ISecondUpdate listener)
        {
            if (listener == null) return;

            if (_isUpdating)
            {
                if (!_pendingSecondAdd.Contains(listener))
                {
                    _pendingSecondAdd.Add(listener);
                }
            }
            else
            {
                if (!_secondListeners.Contains(listener))
                {
                    _secondListeners.Add(listener);
                }
            }
        }

        /// <summary>
        /// Unregisters a listener from once-per-second updates.
        /// </summary>
        /// <param name="listener">The listener to unregister.</param>
        public void UnregisterSecondUpdate(ISecondUpdate listener)
        {
            if (listener == null) return;

            if (_isUpdating)
            {
                if (!_pendingSecondRemove.Contains(listener))
                {
                    _pendingSecondRemove.Add(listener);
                }
            }
            else
            {
                _secondListeners.Remove(listener);
            }
        }

        #endregion

        #region Unity Lifecycle

        private void Update()
        {
            float deltaTime = Time.deltaTime;

            _isUpdating = true;

            // Frame updates
            for (int i = 0; i < _frameListeners.Count; i++)
            {
                IFrameUpdate listener = _frameListeners[i];
                if (listener != null)
                {
                    listener.OnFrameUpdate(deltaTime);
                }
            }

            // Second updates
            _secondTimer += deltaTime;
            if (_secondTimer >= 1f)
            {
                _secondTimer -= 1f;

                for (int i = 0; i < _secondListeners.Count; i++)
                {
                    ISecondUpdate listener = _secondListeners[i];
                    if (listener != null)
                    {
                        listener.OnSecondUpdate();
                    }
                }
            }

            _isUpdating = false;

            // Process pending additions/removals
            ProcessPendingChanges();
        }

        #endregion

        #region Singleton Lifecycle

        protected override void OnSingletonDestroy()
        {
            _frameListeners.Clear();
            _secondListeners.Clear();
            _pendingFrameAdd.Clear();
            _pendingFrameRemove.Clear();
            _pendingSecondAdd.Clear();
            _pendingSecondRemove.Clear();
        }

        #endregion

        #region Private Methods

        private void ProcessPendingChanges()
        {
            // Process frame listener changes
            for (int i = 0; i < _pendingFrameRemove.Count; i++)
            {
                _frameListeners.Remove(_pendingFrameRemove[i]);
            }
            _pendingFrameRemove.Clear();

            for (int i = 0; i < _pendingFrameAdd.Count; i++)
            {
                if (!_frameListeners.Contains(_pendingFrameAdd[i]))
                {
                    _frameListeners.Add(_pendingFrameAdd[i]);
                }
            }
            _pendingFrameAdd.Clear();

            // Process second listener changes
            for (int i = 0; i < _pendingSecondRemove.Count; i++)
            {
                _secondListeners.Remove(_pendingSecondRemove[i]);
            }
            _pendingSecondRemove.Clear();

            for (int i = 0; i < _pendingSecondAdd.Count; i++)
            {
                if (!_secondListeners.Contains(_pendingSecondAdd[i]))
                {
                    _secondListeners.Add(_pendingSecondAdd[i]);
                }
            }
            _pendingSecondAdd.Clear();
        }

        #endregion
    }
}
