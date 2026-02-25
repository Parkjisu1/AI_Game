using System.Collections.Generic;
using UnityEngine;

namespace MagicSort.Domain
{
    /// <summary>
    /// Manages undo history by saving and restoring bottle state snapshots.
    /// Each snapshot captures the water stack of every bottle in the collection.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Manager
    /// Phase: 1
    /// </remarks>
    public class UndoManager
    {
        #region Inner Types

        /// <summary>
        /// A snapshot of all bottle states at a single point in time.
        /// </summary>
        private class UndoState
        {
            public Dictionary<BottleItem, List<WaterItem>> BottleStates { get; private set; }

            public UndoState()
            {
                BottleStates = new Dictionary<BottleItem, List<WaterItem>>();
            }

            /// <summary>
            /// Captures the current state of all bottles in the collection.
            /// </summary>
            /// <param name="collection">The bottle collection to snapshot.</param>
            public void Capture(BottleCollection collection)
            {
                BottleStates.Clear();

                if (collection == null)
                {
                    return;
                }

                List<BottleItem> bottles = collection.GetAllBottles();
                if (bottles == null)
                {
                    return;
                }

                for (int i = 0; i < bottles.Count; i++)
                {
                    if (bottles[i] != null)
                    {
                        BottleStates[bottles[i]] = bottles[i].GetWaterStack();
                    }
                }
            }

            /// <summary>
            /// Restores all bottle states from this snapshot.
            /// </summary>
            public void Restore()
            {
                foreach (var kvp in BottleStates)
                {
                    if (kvp.Key != null)
                    {
                        kvp.Key.RestoreState(kvp.Value);
                    }
                }
            }
        }

        #endregion

        #region Fields

        private readonly Stack<UndoState> _undoStack = new Stack<UndoState>();
        private const int MAX_UNDO_STEPS = 50;

        #endregion

        #region Properties

        /// <summary>Whether there are any states to undo.</summary>
        public bool CanUndo => _undoStack.Count > 0;

        /// <summary>Number of undo steps available.</summary>
        public int UndoCount => _undoStack.Count;

        #endregion

        #region Public Methods

        /// <summary>
        /// Captures the current state of all bottles and pushes it onto the undo stack.
        /// Call this BEFORE executing a pour.
        /// </summary>
        /// <param name="collection">The bottle collection to snapshot.</param>
        public void SaveState(BottleCollection collection)
        {
            if (collection == null)
            {
                Debug.LogWarning("[UndoManager] Cannot save state from null collection.");
                return;
            }

            // Enforce max undo steps to prevent unbounded memory growth
            if (_undoStack.Count >= MAX_UNDO_STEPS)
            {
                // Convert to array, rebuild without the oldest entry
                UndoState[] states = _undoStack.ToArray();
                _undoStack.Clear();

                // Stack.ToArray returns top-first, so reverse to rebuild bottom-first
                for (int i = states.Length - 2; i >= 0; i--)
                {
                    _undoStack.Push(states[i]);
                }
            }

            UndoState state = new UndoState();
            state.Capture(collection);
            _undoStack.Push(state);
        }

        /// <summary>
        /// Reverts to the most recent saved state.
        /// Returns true if undo was performed, false if no history.
        /// </summary>
        public bool Undo()
        {
            if (_undoStack.Count == 0)
            {
                Debug.Log("[UndoManager] No undo states available.");
                return false;
            }

            UndoState state = _undoStack.Pop();
            state.Restore();
            return true;
        }

        /// <summary>
        /// Clears all undo history. Call when starting or restarting a level.
        /// </summary>
        public void Clear()
        {
            _undoStack.Clear();
        }

        #endregion
    }
}
