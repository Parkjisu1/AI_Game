using System;
using System.Collections.Generic;

namespace BlockBlast.Core
{
    public class EventManager : Singleton<EventManager>
    {
        private readonly Dictionary<string, Delegate> _events = new Dictionary<string, Delegate>();

        // Event name constants
        public const string EVT_SCORE_CHANGED = "OnScoreChanged";
        public const string EVT_COMBO_CHANGED = "OnComboChanged";
        public const string EVT_LINE_CLEAR = "OnLineClear";
        public const string EVT_BLOCK_PLACED = "OnBlockPlaced";
        public const string EVT_GAME_OVER = "OnGameOver";
        public const string EVT_GAME_START = "OnGameStart";
        public const string EVT_GAME_PAUSE = "OnGamePause";

        public void Subscribe(string eventName, Action callback)
        {
            if (_events.TryGetValue(eventName, out var existing))
                _events[eventName] = Delegate.Combine(existing, callback);
            else
                _events[eventName] = callback;
        }

        public void Subscribe<T>(string eventName, Action<T> callback)
        {
            if (_events.TryGetValue(eventName, out var existing))
                _events[eventName] = Delegate.Combine(existing, callback);
            else
                _events[eventName] = callback;
        }

        public void Unsubscribe(string eventName, Action callback)
        {
            if (_events.TryGetValue(eventName, out var existing))
            {
                var result = Delegate.Remove(existing, callback);
                if (result == null)
                    _events.Remove(eventName);
                else
                    _events[eventName] = result;
            }
        }

        public void Unsubscribe<T>(string eventName, Action<T> callback)
        {
            if (_events.TryGetValue(eventName, out var existing))
            {
                var result = Delegate.Remove(existing, callback);
                if (result == null)
                    _events.Remove(eventName);
                else
                    _events[eventName] = result;
            }
        }

        public void Publish(string eventName)
        {
            if (_events.TryGetValue(eventName, out var d))
                (d as Action)?.Invoke();
        }

        public void Publish<T>(string eventName, T data)
        {
            if (_events.TryGetValue(eventName, out var d))
                (d as Action<T>)?.Invoke(data);
        }

        public void Clear()
        {
            _events.Clear();
        }
    }
}
