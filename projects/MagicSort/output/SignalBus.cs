using System;
using System.Collections.Generic;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Type-safe event bus using struct signals.
    /// Provides decoupled inter-system communication without direct references.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Service
    /// Phase: 0
    /// </remarks>
    public class SignalBus
    {
        #region Fields

        private readonly Dictionary<Type, List<Delegate>> _subscriptions = new Dictionary<Type, List<Delegate>>();

        #endregion

        #region Public Methods

        /// <summary>
        /// Subscribes a callback to a specific signal type.
        /// </summary>
        /// <typeparam name="T">The signal struct type.</typeparam>
        /// <param name="callback">The callback to invoke when the signal is fired.</param>
        public void Subscribe<T>(Action<T> callback) where T : struct
        {
            if (callback == null)
            {
                Debug.LogWarning($"[SignalBus] Cannot subscribe null callback for {typeof(T).Name}.");
                return;
            }

            Type type = typeof(T);
            if (!_subscriptions.TryGetValue(type, out List<Delegate> listeners))
            {
                listeners = new List<Delegate>();
                _subscriptions[type] = listeners;
            }

            if (!listeners.Contains(callback))
            {
                listeners.Add(callback);
            }
        }

        /// <summary>
        /// Unsubscribes a callback from a specific signal type.
        /// </summary>
        /// <typeparam name="T">The signal struct type.</typeparam>
        /// <param name="callback">The callback to remove.</param>
        public void Unsubscribe<T>(Action<T> callback) where T : struct
        {
            if (callback == null) return;

            Type type = typeof(T);
            if (_subscriptions.TryGetValue(type, out List<Delegate> listeners))
            {
                listeners.Remove(callback);

                if (listeners.Count == 0)
                {
                    _subscriptions.Remove(type);
                }
            }
        }

        /// <summary>
        /// Fires a signal, notifying all subscribers of that signal type.
        /// </summary>
        /// <typeparam name="T">The signal struct type.</typeparam>
        /// <param name="signal">The signal data to send.</param>
        public void Fire<T>(T signal) where T : struct
        {
            Type type = typeof(T);
            if (!_subscriptions.TryGetValue(type, out List<Delegate> listeners))
            {
                return;
            }

            // Iterate over a copy to allow safe unsubscription during callbacks
            for (int i = listeners.Count - 1; i >= 0; i--)
            {
                if (i >= listeners.Count) continue;

                try
                {
                    Action<T> callback = listeners[i] as Action<T>;
                    callback?.Invoke(signal);
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[SignalBus] Error firing {typeof(T).Name}: {ex.Message}\n{ex.StackTrace}");
                }
            }
        }

        /// <summary>
        /// Checks if there are any subscribers for a given signal type.
        /// </summary>
        /// <typeparam name="T">The signal struct type.</typeparam>
        /// <returns>True if at least one subscriber exists.</returns>
        public bool HasSubscribers<T>() where T : struct
        {
            Type type = typeof(T);
            return _subscriptions.TryGetValue(type, out List<Delegate> listeners) && listeners.Count > 0;
        }

        /// <summary>
        /// Removes all subscribers for a specific signal type.
        /// </summary>
        /// <typeparam name="T">The signal struct type.</typeparam>
        public void ClearSignal<T>() where T : struct
        {
            _subscriptions.Remove(typeof(T));
        }

        /// <summary>
        /// Removes all subscribers for all signal types.
        /// </summary>
        public void ClearAll()
        {
            _subscriptions.Clear();
        }

        /// <summary>
        /// Gets the number of subscribers for a given signal type. Useful for debugging.
        /// </summary>
        /// <typeparam name="T">The signal struct type.</typeparam>
        /// <returns>The subscriber count.</returns>
        public int GetSubscriberCount<T>() where T : struct
        {
            Type type = typeof(T);
            if (_subscriptions.TryGetValue(type, out List<Delegate> listeners))
            {
                return listeners.Count;
            }
            return 0;
        }

        #endregion
    }
}
