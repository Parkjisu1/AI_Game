using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace VeilBreaker.Core
{
    /// <summary>
    /// Global event bus for decoupled inter-system communication.
    /// Uses string keys (from GameConstants.Events) with Action callbacks.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Manager
    /// Phase: 0
    /// </remarks>
    public class EventManager : Singleton<EventManager>
    {
        #region Fields

        private readonly Dictionary<string, List<Action<object>>> _listeners = new();

        #endregion

        #region Public Methods

        /// <summary>
        /// Subscribe a callback to the specified event key.
        /// </summary>
        /// <param name="eventKey">Event key constant from GameConstants.Events.</param>
        /// <param name="callback">Callback to invoke when event is published.</param>
        public static void Subscribe(string eventKey, Action<object> callback)
        {
            if (Instance == null) return;

            if (string.IsNullOrEmpty(eventKey))
            {
                Debug.LogWarning("[EventManager] Subscribe called with null or empty eventKey.");
                return;
            }

            if (callback == null)
            {
                Debug.LogWarning($"[EventManager] Subscribe called with null callback for '{eventKey}'.");
                return;
            }

            if (!Instance._listeners.ContainsKey(eventKey))
            {
                Instance._listeners[eventKey] = new List<Action<object>>();
            }

            Instance._listeners[eventKey].Add(callback);
        }

        /// <summary>
        /// Unsubscribe a callback from the specified event key.
        /// </summary>
        /// <param name="eventKey">Event key constant from GameConstants.Events.</param>
        /// <param name="callback">Previously registered callback to remove.</param>
        public static void Unsubscribe(string eventKey, Action<object> callback)
        {
            if (Instance == null) return;

            if (string.IsNullOrEmpty(eventKey) || callback == null) return;

            if (Instance._listeners.TryGetValue(eventKey, out var list))
            {
                list.Remove(callback);

                if (list.Count == 0)
                {
                    Instance._listeners.Remove(eventKey);
                }
            }
        }

        /// <summary>
        /// Publish an event, invoking all registered callbacks for the key.
        /// Uses ToList() snapshot to prevent collection-modified-during-enumeration errors.
        /// </summary>
        /// <param name="eventKey">Event key constant from GameConstants.Events.</param>
        /// <param name="data">Optional data payload to pass to callbacks.</param>
        public static void Publish(string eventKey, object data = null)
        {
            if (Instance == null) return;

            if (string.IsNullOrEmpty(eventKey)) return;

            if (!Instance._listeners.TryGetValue(eventKey, out var list)) return;

            foreach (var callback in list.ToList())
            {
                try
                {
                    callback?.Invoke(data);
                }
                catch (Exception ex)
                {
                    Debug.LogError($"[EventManager] Error in callback for '{eventKey}': {ex.Message}\n{ex.StackTrace}");
                }
            }
        }

        /// <summary>
        /// Remove all registered listeners. Call on scene transitions to prevent memory leaks.
        /// </summary>
        public static void Clear()
        {
            if (Instance == null) return;

            Instance._listeners.Clear();
        }

        /// <summary>
        /// Remove all listeners for a specific event key.
        /// </summary>
        /// <param name="eventKey">Event key to clear.</param>
        public static void ClearEvent(string eventKey)
        {
            if (Instance == null) return;

            if (!string.IsNullOrEmpty(eventKey))
            {
                Instance._listeners.Remove(eventKey);
            }
        }

        /// <summary>
        /// Returns the number of listeners registered for a specific event key.
        /// </summary>
        public static int GetListenerCount(string eventKey)
        {
            if (Instance == null) return 0;

            if (Instance._listeners.TryGetValue(eventKey, out var list))
            {
                return list.Count;
            }

            return 0;
        }

        #endregion
    }
}
