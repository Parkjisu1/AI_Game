using System;
using System.Collections.Generic;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Provides a unique daily level generated from the current date as seed.
    /// Tracks completion state so each daily level can only be completed once per day.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Provider
    /// Phase: 1
    /// </remarks>
    public class DailyLevelProvider
    {
        #region Fields

        private const string SAVE_KEY_DAILY_COMPLETED = "Daily_Completed_";
        private const int DAILY_LEVEL_ID = -1; // Special ID for daily levels
        private const int DEFAULT_MAX_HEIGHT = 4;

        private readonly LevelDataProvider _levelDataProvider;

        #endregion

        #region Constructors

        public DailyLevelProvider()
        {
            _levelDataProvider = new LevelDataProvider();
        }

        public DailyLevelProvider(LevelDataProvider levelDataProvider)
        {
            _levelDataProvider = levelDataProvider ?? new LevelDataProvider();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Returns today's daily level. The level is deterministically generated
        /// from the current date, ensuring the same puzzle for all players on the same day.
        /// </summary>
        /// <returns>A LevelModel for today's daily challenge.</returns>
        public LevelModel GetTodayLevel()
        {
            DateTime today = DateTime.Now.Date;
            string seedString = GetDateSeed(today);
            int seed = seedString.GetHashCode();

            // Daily levels are medium-to-hard difficulty
            int dayOfYear = today.DayOfYear;
            LevelDifficulty difficulty = GetDailyDifficulty(dayOfYear);
            int colorCount = GetDailyColorCount(difficulty);
            int emptyBottles = 2;

            LevelModel level = GenerateDailyLevel(seed, colorCount, emptyBottles, difficulty);
            if (level != null)
            {
                level.LevelId = DAILY_LEVEL_ID;
                level.SeedId = seedString;
            }

            return level;
        }

        /// <summary>
        /// Checks whether today's daily level has already been completed.
        /// </summary>
        public bool IsCompleted()
        {
            if (!SaveManager.HasInstance)
            {
                return false;
            }

            string key = GetTodaySaveKey();
            return SaveManager.Instance.LoadInt(key, 0) == 1;
        }

        /// <summary>
        /// Marks today's daily level as completed and saves the state.
        /// </summary>
        public void MarkCompleted()
        {
            if (!SaveManager.HasInstance)
            {
                return;
            }

            string key = GetTodaySaveKey();
            SaveManager.Instance.SaveInt(key, 1);
        }

        /// <summary>
        /// Returns the number of consecutive days the player has completed daily levels.
        /// Checks backwards from today.
        /// </summary>
        public int GetStreak()
        {
            if (!SaveManager.HasInstance)
            {
                return 0;
            }

            int streak = 0;
            DateTime checkDate = DateTime.Now.Date;

            for (int i = 0; i < 365; i++)
            {
                string key = SAVE_KEY_DAILY_COMPLETED + GetDateSeed(checkDate);
                if (SaveManager.Instance.LoadInt(key, 0) == 1)
                {
                    streak++;
                    checkDate = checkDate.AddDays(-1);
                }
                else
                {
                    break;
                }
            }

            return streak;
        }

        #endregion

        #region Private Methods

        private string GetDateSeed(DateTime date)
        {
            return date.ToString("yyyyMMdd");
        }

        private string GetTodaySaveKey()
        {
            return SAVE_KEY_DAILY_COMPLETED + GetDateSeed(DateTime.Now.Date);
        }

        private LevelDifficulty GetDailyDifficulty(int dayOfYear)
        {
            // Cycle through difficulties based on day of year
            int cycle = dayOfYear % 7;

            if (cycle < 2) return LevelDifficulty.Medium;
            if (cycle < 5) return LevelDifficulty.Hard;
            return LevelDifficulty.Expert;
        }

        private int GetDailyColorCount(LevelDifficulty difficulty)
        {
            switch (difficulty)
            {
                case LevelDifficulty.Easy:    return 4;
                case LevelDifficulty.Medium:  return 5;
                case LevelDifficulty.Hard:    return 7;
                case LevelDifficulty.Expert:  return 9;
                default:                      return 5;
            }
        }

        private LevelModel GenerateDailyLevel(int seed, int colorCount, int emptyBottles, LevelDifficulty difficulty)
        {
            System.Random rng = new System.Random(seed);

            // Select colors deterministically from the seed
            WaterColor[] allColors = new WaterColor[]
            {
                WaterColor.Red, WaterColor.Blue, WaterColor.Green, WaterColor.Yellow,
                WaterColor.Purple, WaterColor.Orange, WaterColor.Pink, WaterColor.Cyan,
                WaterColor.Brown, WaterColor.White, WaterColor.Gray, WaterColor.DarkBlue,
                WaterColor.Lime, WaterColor.Magenta
            };

            if (colorCount > allColors.Length)
            {
                colorCount = allColors.Length;
            }

            // Shuffle all colors with the seed, then take first N
            for (int i = allColors.Length - 1; i > 0; i--)
            {
                int j = rng.Next(i + 1);
                WaterColor temp = allColors[i];
                allColors[i] = allColors[j];
                allColors[j] = temp;
            }

            WaterColor[] selectedColors = new WaterColor[colorCount];
            Array.Copy(allColors, selectedColors, colorCount);

            // Build water pool (4 of each color)
            List<WaterColor> waterPool = new List<WaterColor>();
            for (int i = 0; i < colorCount; i++)
            {
                for (int j = 0; j < DEFAULT_MAX_HEIGHT; j++)
                {
                    waterPool.Add(selectedColors[i]);
                }
            }

            // Shuffle water pool
            for (int i = waterPool.Count - 1; i > 0; i--)
            {
                int j = rng.Next(i + 1);
                WaterColor temp = waterPool[i];
                waterPool[i] = waterPool[j];
                waterPool[j] = temp;
            }

            // Distribute into bottles
            List<BottleConfig> bottles = new List<BottleConfig>();
            int idx = 0;

            for (int b = 0; b < colorCount; b++)
            {
                List<WaterColor> bottleWaters = new List<WaterColor>();
                for (int w = 0; w < DEFAULT_MAX_HEIGHT && idx < waterPool.Count; w++)
                {
                    bottleWaters.Add(waterPool[idx]);
                    idx++;
                }
                bottles.Add(new BottleConfig(DEFAULT_MAX_HEIGHT, bottleWaters));
            }

            // Verify not trivially solved
            bool trivial = true;
            for (int i = 0; i < bottles.Count; i++)
            {
                List<WaterColor> waters = bottles[i].InitialWaters;
                if (waters != null && waters.Count > 1)
                {
                    for (int w = 1; w < waters.Count; w++)
                    {
                        if (waters[w] != waters[0])
                        {
                            trivial = false;
                            break;
                        }
                    }
                }
                if (!trivial) break;
            }

            if (trivial)
            {
                // Re-shuffle with different offset
                return GenerateDailyLevel(seed + 7919, colorCount, emptyBottles, difficulty);
            }

            int par = colorCount * 3 + (difficulty == LevelDifficulty.Expert ? 0 : 3);

            return new LevelModel(DAILY_LEVEL_ID, difficulty, bottles, emptyBottles, par,
                $"daily_{GetDateSeed(DateTime.Now.Date)}");
        }

        #endregion
    }
}
