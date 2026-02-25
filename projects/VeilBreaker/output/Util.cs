using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace VeilBreaker.Core
{
    /// <summary>
    /// Static utility methods and extension methods used across the project.
    /// Provides number formatting, weighted random, scene loading, and dictionary extensions.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Helper
    /// Phase: 0
    /// </remarks>
    public static class Util
    {
        #region Number Formatting

        /// <summary>
        /// Format a large number with suffix (K, M, B, T).
        /// Example: 1500 -> "1.5K", 2300000 -> "2.3M"
        /// </summary>
        public static string FormatNumber(double value)
        {
            if (value >= 1_000_000_000_000)
                return $"{value / 1_000_000_000_000:F1}T";
            if (value >= 1_000_000_000)
                return $"{value / 1_000_000_000:F1}B";
            if (value >= 1_000_000)
                return $"{value / 1_000_000:F1}M";
            if (value >= 1_000)
                return $"{value / 1_000:F1}K";

            return value.ToString("N0");
        }

        /// <summary>
        /// Format seconds into a human-readable time string.
        /// Example: 3661 -> "1:01:01", 125 -> "2:05"
        /// </summary>
        public static string FormatTime(float seconds)
        {
            if (seconds < 0f) seconds = 0f;

            int totalSeconds = Mathf.FloorToInt(seconds);
            int hours = totalSeconds / 3600;
            int minutes = (totalSeconds % 3600) / 60;
            int secs = totalSeconds % 60;

            if (hours > 0)
                return $"{hours}:{minutes:D2}:{secs:D2}";

            return $"{minutes}:{secs:D2}";
        }

        #endregion

        #region Random

        /// <summary>
        /// Select a random index based on weighted probabilities.
        /// Example: weights [10, 20, 70] -> 70% chance of returning index 2.
        /// </summary>
        /// <param name="weights">List of integer weights. Must not be empty.</param>
        /// <returns>Selected index, or -1 if weights are invalid.</returns>
        public static int WeightedRandom(List<int> weights)
        {
            if (weights == null || weights.Count == 0) return -1;

            int total = 0;
            for (int i = 0; i < weights.Count; i++)
            {
                total += weights[i];
            }

            if (total <= 0) return 0;

            int rand = Random.Range(0, total);
            int cumulative = 0;

            for (int i = 0; i < weights.Count; i++)
            {
                cumulative += weights[i];
                if (rand < cumulative)
                    return i;
            }

            return weights.Count - 1;
        }

        /// <summary>
        /// Roll a percent chance and return whether it succeeds.
        /// Example: IsChanceSuccess(30f) -> 30% chance of returning true.
        /// </summary>
        /// <param name="percent">Chance percentage (0 to 100).</param>
        public static bool IsChanceSuccess(float percent)
        {
            return Random.Range(0f, 100f) < percent;
        }

        #endregion

        #region Scene

        /// <summary>
        /// Load a scene by name using GameConstants.Scenes constants.
        /// </summary>
        public static void LoadScene(string sceneName)
        {
            if (string.IsNullOrEmpty(sceneName))
            {
                Debug.LogWarning("[Util] LoadScene called with null or empty sceneName.");
                return;
            }

            SceneManager.LoadScene(sceneName);
        }

        #endregion

        #region Extension Methods

        /// <summary>
        /// Get or create a value in a dictionary. If the key does not exist, creates a new T() and adds it.
        /// Used by EventManager for listener lists.
        /// </summary>
        public static T GetOrCreate<T>(this Dictionary<string, T> dict, string key) where T : new()
        {
            if (dict.TryGetValue(key, out var value))
                return value;

            value = new T();
            dict[key] = value;
            return value;
        }

        /// <summary>
        /// Shuffle a list in place using Fisher-Yates algorithm.
        /// </summary>
        public static void Shuffle<T>(this IList<T> list)
        {
            for (int i = list.Count - 1; i > 0; i--)
            {
                int j = Random.Range(0, i + 1);
                (list[i], list[j]) = (list[j], list[i]);
            }
        }

        /// <summary>
        /// Safely get a component, logging a warning if not found.
        /// </summary>
        public static T GetComponentSafe<T>(this GameObject obj) where T : Component
        {
            var component = obj.GetComponent<T>();
            if (component == null)
            {
                Debug.LogWarning($"[Util] Component {typeof(T).Name} not found on '{obj.name}'.");
            }
            return component;
        }

        #endregion
    }
}
