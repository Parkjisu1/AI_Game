using System;
using System.Collections.Generic;
using UnityEngine;

namespace DropTheCat.Core
{
    /// <summary>
    /// Type-safe global event publish/subscribe system.
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

        private readonly Dictionary<Type, List<Delegate>> _eventDict = new Dictionary<Type, List<Delegate>>();

        #endregion

        #region Public Methods

        /// <summary>
        /// Subscribe to an event of type T.
        /// </summary>
        public void Subscribe<T>(Action<T> callback)
        {
            if (callback == null) return;

            var type = typeof(T);
            if (!_eventDict.TryGetValue(type, out var list))
            {
                list = new List<Delegate>();
                _eventDict[type] = list;
            }

            if (!list.Contains(callback))
            {
                list.Add(callback);
            }
        }

        /// <summary>
        /// Unsubscribe from an event of type T.
        /// </summary>
        public void Unsubscribe<T>(Action<T> callback)
        {
            if (callback == null) return;

            var type = typeof(T);
            if (_eventDict.TryGetValue(type, out var list))
            {
                list.Remove(callback);
                if (list.Count == 0)
                {
                    _eventDict.Remove(type);
                }
            }
        }

        /// <summary>
        /// Publish an event of type T to all subscribers.
        /// </summary>
        public void Publish<T>(T eventData)
        {
            var type = typeof(T);
            if (!_eventDict.TryGetValue(type, out var list)) return;
            if (list.Count == 0) return;

            // Copy to avoid modification during iteration
            var snapshot = new List<Delegate>(list);
            foreach (var callback in snapshot)
            {
                try
                {
                    ((Action<T>)callback)?.Invoke(eventData);
                }
                catch (Exception e)
                {
                    Debug.LogError($"[EventManager] Error publishing {type.Name}: {e}");
                }
            }
        }

        /// <summary>
        /// Clear all event subscriptions.
        /// </summary>
        public void Clear()
        {
            _eventDict.Clear();
        }

        /// <summary>
        /// Clear subscriptions for a specific event type.
        /// </summary>
        public void Clear<T>()
        {
            _eventDict.Remove(typeof(T));
        }

        #endregion

        #region Unity Lifecycle

        protected override void OnDestroy()
        {
            Clear();
            base.OnDestroy();
        }

        #endregion
    }

    #region Event Data Classes

    // ===== Grid Events =====
    public struct OnGridInitialized
    {
        public int Width;
        public int Height;
    }

    public struct OnCellStateChanged
    {
        public int X;
        public int Y;
        public CellState OldState;
        public CellState NewState;
    }

    // ===== Slide Events =====
    public struct OnSlideComplete
    {
        public int TileId;
        public Vector2Int FromPos;
        public Vector2Int ToPos;
        public SlideDirection Direction;
    }

    public struct OnMovePerformed { }

    // ===== Drop Events =====
    public struct OnCatDropped
    {
        public CatColor CatColor;
        public Vector2Int Position;
    }

    public struct OnLevelCleared
    {
        public int MoveCount;
        public int Stars;
        public int CoinReward;
    }

    public struct OnLevelFailed
    {
        public FailReason Reason;
    }

    // ===== Level Events =====
    public struct OnLevelLoaded
    {
        public int LevelNumber;
    }

    public struct OnLevelProgressUpdated
    {
        public int MaxClearedLevel;
        public int TotalStars;
    }

    // ===== Currency Events =====
    public struct OnCoinChanged
    {
        public int Balance;
        public int Delta;
    }

    // ===== Score Events =====
    public struct OnMoveCountChanged
    {
        public int MoveCount;
    }

    // ===== Booster Events =====
    public struct OnBoosterUsed
    {
        public BoosterType BoosterType;
    }

    public struct OnBoosterCountChanged
    {
        public BoosterType BoosterType;
        public int Count;
    }

    // ===== Obstacle Events =====
    public struct OnObstacleStateChanged
    {
        public int X;
        public int Y;
        public ObstacleType ObstacleType;
        public int NewState;
    }

    public struct OnTileUnlocked
    {
        public int X;
        public int Y;
    }

    // ===== Game State Events =====
    public struct OnGameStateChanged
    {
        public GameState NewState;
    }

    #endregion

    #region Enums

    public enum CatColor
    {
        Red,
        Blue,
        Green,
        Yellow,
        Purple,
        Orange,
        Pink,
        White,
        Black,
        Rainbow
    }

    public enum CellType
    {
        Empty,
        Normal,
        Hole,
        Wall,
        Obstacle,
        Portal,
        Ice,
        Lock
    }

    public enum SlideDirection
    {
        Up,
        Down,
        Left,
        Right
    }

    public enum ObstacleType
    {
        None,
        Wall,
        Ice,
        Lock,
        Portal,
        Switch,
        OneWay
    }

    public enum GameState
    {
        Title,
        Main,
        Loading,
        Playing,
        Paused,
        Result
    }

    public enum BoosterType
    {
        Hint,
        Undo,
        Magnet,
        Shuffle
    }

    public enum FailReason
    {
        TrapHole,
        OutOfMoves,
        PlayerQuit
    }

    public enum MatchResult
    {
        Success,
        Fail,
        Trap
    }

    public enum CellState
    {
        Empty,
        Occupied,
        Blocked
    }

    #endregion
}
