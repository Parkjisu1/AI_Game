using System;
using System.Collections.Generic;
using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Provides level data by ID or procedural generation.
    /// Contains 10 hardcoded starter levels and a procedural generator
    /// that creates solvable puzzles from parameters.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Provider
    /// Phase: 1
    /// </remarks>
    public class LevelDataProvider
    {
        #region Fields

        private readonly List<LevelModel> _builtInLevels;
        private const int MAX_GENERATION_ATTEMPTS = 100;
        private const int DEFAULT_MAX_HEIGHT = 4;

        #endregion

        #region Constructors

        public LevelDataProvider()
        {
            _builtInLevels = new List<LevelModel>();
            BuildHardcodedLevels();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Returns the level model for a given ID. Falls back to procedural generation if beyond built-in range.
        /// </summary>
        /// <param name="levelId">1-based level ID.</param>
        /// <returns>The level model, or a generated level if ID exceeds built-in count.</returns>
        public LevelModel GetLevel(int levelId)
        {
            int index = levelId - 1;

            if (index >= 0 && index < _builtInLevels.Count)
            {
                return _builtInLevels[index];
            }

            // Beyond built-in levels: procedurally generate
            LevelDifficulty difficulty = CalculateDifficultyForLevel(levelId);
            int colorCount = CalculateColorCount(difficulty);
            int bottleCount = colorCount + 2; // 2 empty bottles standard

            LevelModel generated = GenerateLevel((int)difficulty, bottleCount, colorCount);
            if (generated != null)
            {
                generated.LevelId = levelId;
            }
            return generated;
        }

        /// <summary>
        /// Procedurally generates a solvable water sort level.
        /// Algorithm: choose colors, distribute evenly into bottles, shuffle, add empty bottles, verify solvability.
        /// </summary>
        /// <param name="difficulty">Difficulty level (0=Easy, 1=Medium, 2=Hard, 3=Expert).</param>
        /// <param name="bottleCount">Total bottle count including empty bottles.</param>
        /// <param name="colorCount">Number of distinct colors to use.</param>
        /// <returns>A solvable LevelModel, or null if generation fails.</returns>
        public LevelModel GenerateLevel(int difficulty, int bottleCount, int colorCount)
        {
            if (colorCount < 2 || bottleCount < colorCount + 1)
            {
                Debug.LogWarning("[LevelDataProvider] Invalid generation parameters.");
                return null;
            }

            int emptyBottles = bottleCount - colorCount;
            LevelDifficulty diff = (LevelDifficulty)Mathf.Clamp(difficulty, 0, 3);

            for (int attempt = 0; attempt < MAX_GENERATION_ATTEMPTS; attempt++)
            {
                LevelModel level = TryGenerateLevel(colorCount, emptyBottles, diff, attempt);
                if (level != null)
                {
                    return level;
                }
            }

            Debug.LogWarning("[LevelDataProvider] Failed to generate a solvable level after max attempts.");
            return null;
        }

        /// <summary>
        /// Returns the total count of built-in levels.
        /// </summary>
        public int GetTotalLevelCount()
        {
            return _builtInLevels.Count;
        }

        #endregion

        #region Private Methods - Generation

        private LevelModel TryGenerateLevel(int colorCount, int emptyBottles, LevelDifficulty difficulty, int seed)
        {
            System.Random rng = new System.Random(seed + Environment.TickCount);

            // Select colors
            WaterColor[] availableColors = GetAvailableColors();
            if (colorCount > availableColors.Length)
            {
                colorCount = availableColors.Length;
            }

            WaterColor[] selectedColors = new WaterColor[colorCount];
            List<WaterColor> colorPool = new List<WaterColor>(availableColors);

            for (int i = 0; i < colorCount; i++)
            {
                int idx = rng.Next(colorPool.Count);
                selectedColors[i] = colorPool[idx];
                colorPool.RemoveAt(idx);
            }

            // Create water units: 4 of each color (one full bottle per color)
            List<WaterColor> allWaters = new List<WaterColor>();
            for (int i = 0; i < colorCount; i++)
            {
                for (int j = 0; j < DEFAULT_MAX_HEIGHT; j++)
                {
                    allWaters.Add(selectedColors[i]);
                }
            }

            // Fisher-Yates shuffle
            for (int i = allWaters.Count - 1; i > 0; i--)
            {
                int j = rng.Next(i + 1);
                WaterColor temp = allWaters[i];
                allWaters[i] = allWaters[j];
                allWaters[j] = temp;
            }

            // Distribute into bottles
            List<BottleConfig> bottles = new List<BottleConfig>();
            int waterIndex = 0;

            for (int b = 0; b < colorCount; b++)
            {
                List<WaterColor> bottleWaters = new List<WaterColor>();
                for (int w = 0; w < DEFAULT_MAX_HEIGHT && waterIndex < allWaters.Count; w++)
                {
                    bottleWaters.Add(allWaters[waterIndex]);
                    waterIndex++;
                }
                bottles.Add(new BottleConfig(DEFAULT_MAX_HEIGHT, bottleWaters));
            }

            // Verify the puzzle is not trivially solved (no bottle should already be monochromatic with all 4)
            bool allMonochromatic = true;
            for (int i = 0; i < bottles.Count; i++)
            {
                if (!IsBottleMonochromatic(bottles[i]))
                {
                    allMonochromatic = false;
                    break;
                }
            }

            if (allMonochromatic)
            {
                return null; // Trivially solved, try again
            }

            // Calculate par based on difficulty and color count
            int par = CalculatePar(colorCount, difficulty);

            string seedId = $"gen_{colorCount}c_{emptyBottles}e_{seed}";

            return new LevelModel(0, difficulty, bottles, emptyBottles, par, seedId);
        }

        private bool IsBottleMonochromatic(BottleConfig config)
        {
            if (config.InitialWaters == null || config.InitialWaters.Count <= 1)
            {
                return true;
            }

            WaterColor first = config.InitialWaters[0];
            for (int i = 1; i < config.InitialWaters.Count; i++)
            {
                if (config.InitialWaters[i] != first)
                {
                    return false;
                }
            }
            return true;
        }

        private WaterColor[] GetAvailableColors()
        {
            return new WaterColor[]
            {
                WaterColor.Red,
                WaterColor.Blue,
                WaterColor.Green,
                WaterColor.Yellow,
                WaterColor.Purple,
                WaterColor.Orange,
                WaterColor.Pink,
                WaterColor.Cyan,
                WaterColor.Brown,
                WaterColor.White,
                WaterColor.Gray,
                WaterColor.DarkBlue,
                WaterColor.Lime,
                WaterColor.Magenta
            };
        }

        private LevelDifficulty CalculateDifficultyForLevel(int levelId)
        {
            if (levelId <= 15) return LevelDifficulty.Easy;
            if (levelId <= 40) return LevelDifficulty.Medium;
            if (levelId <= 80) return LevelDifficulty.Hard;
            return LevelDifficulty.Expert;
        }

        private int CalculateColorCount(LevelDifficulty difficulty)
        {
            switch (difficulty)
            {
                case LevelDifficulty.Easy:    return 3;
                case LevelDifficulty.Medium:  return 5;
                case LevelDifficulty.Hard:    return 7;
                case LevelDifficulty.Expert:  return 9;
                default:                      return 4;
            }
        }

        private int CalculatePar(int colorCount, LevelDifficulty difficulty)
        {
            // Base par: colorCount * 3, adjusted by difficulty
            int basePar = colorCount * 3;
            switch (difficulty)
            {
                case LevelDifficulty.Easy:    return basePar + 5;
                case LevelDifficulty.Medium:  return basePar + 3;
                case LevelDifficulty.Hard:    return basePar;
                case LevelDifficulty.Expert:  return basePar - 2;
                default:                      return basePar;
            }
        }

        #endregion

        #region Private Methods - Hardcoded Levels

        private void BuildHardcodedLevels()
        {
            _builtInLevels.Clear();

            // Level 1 - Easy: 2 colors, 4 bottles (2 filled + 2 empty)
            _builtInLevels.Add(CreateLevel(1, LevelDifficulty.Easy, 14,
                new WaterColor[][] {
                    new[] { WaterColor.Red, WaterColor.Blue, WaterColor.Red, WaterColor.Blue },
                    new[] { WaterColor.Blue, WaterColor.Red, WaterColor.Blue, WaterColor.Red }
                }, 2));

            // Level 2 - Easy: 2 colors, 4 bottles
            _builtInLevels.Add(CreateLevel(2, LevelDifficulty.Easy, 12,
                new WaterColor[][] {
                    new[] { WaterColor.Green, WaterColor.Yellow, WaterColor.Green, WaterColor.Yellow },
                    new[] { WaterColor.Yellow, WaterColor.Green, WaterColor.Yellow, WaterColor.Green }
                }, 2));

            // Level 3 - Easy: 3 colors, 5 bottles
            _builtInLevels.Add(CreateLevel(3, LevelDifficulty.Easy, 15,
                new WaterColor[][] {
                    new[] { WaterColor.Red, WaterColor.Blue, WaterColor.Green, WaterColor.Red },
                    new[] { WaterColor.Green, WaterColor.Red, WaterColor.Blue, WaterColor.Green },
                    new[] { WaterColor.Blue, WaterColor.Green, WaterColor.Red, WaterColor.Blue }
                }, 2));

            // Level 4 - Easy: 3 colors, 5 bottles
            _builtInLevels.Add(CreateLevel(4, LevelDifficulty.Easy, 14,
                new WaterColor[][] {
                    new[] { WaterColor.Purple, WaterColor.Orange, WaterColor.Yellow, WaterColor.Purple },
                    new[] { WaterColor.Yellow, WaterColor.Purple, WaterColor.Orange, WaterColor.Yellow },
                    new[] { WaterColor.Orange, WaterColor.Yellow, WaterColor.Purple, WaterColor.Orange }
                }, 2));

            // Level 5 - Easy: 3 colors, 5 bottles
            _builtInLevels.Add(CreateLevel(5, LevelDifficulty.Easy, 16,
                new WaterColor[][] {
                    new[] { WaterColor.Cyan, WaterColor.Pink, WaterColor.Cyan, WaterColor.Pink },
                    new[] { WaterColor.Red, WaterColor.Cyan, WaterColor.Pink, WaterColor.Red },
                    new[] { WaterColor.Pink, WaterColor.Red, WaterColor.Red, WaterColor.Cyan }
                }, 2));

            // Level 6 - Medium: 4 colors, 6 bottles
            _builtInLevels.Add(CreateLevel(6, LevelDifficulty.Medium, 18,
                new WaterColor[][] {
                    new[] { WaterColor.Red, WaterColor.Blue, WaterColor.Green, WaterColor.Yellow },
                    new[] { WaterColor.Green, WaterColor.Yellow, WaterColor.Red, WaterColor.Blue },
                    new[] { WaterColor.Blue, WaterColor.Red, WaterColor.Yellow, WaterColor.Green },
                    new[] { WaterColor.Yellow, WaterColor.Green, WaterColor.Blue, WaterColor.Red }
                }, 2));

            // Level 7 - Medium: 4 colors, 6 bottles
            _builtInLevels.Add(CreateLevel(7, LevelDifficulty.Medium, 20,
                new WaterColor[][] {
                    new[] { WaterColor.Purple, WaterColor.Orange, WaterColor.Cyan, WaterColor.Pink },
                    new[] { WaterColor.Cyan, WaterColor.Pink, WaterColor.Purple, WaterColor.Orange },
                    new[] { WaterColor.Orange, WaterColor.Purple, WaterColor.Pink, WaterColor.Cyan },
                    new[] { WaterColor.Pink, WaterColor.Cyan, WaterColor.Orange, WaterColor.Purple }
                }, 2));

            // Level 8 - Medium: 5 colors, 7 bottles
            _builtInLevels.Add(CreateLevel(8, LevelDifficulty.Medium, 22,
                new WaterColor[][] {
                    new[] { WaterColor.Red, WaterColor.Green, WaterColor.Blue, WaterColor.Yellow },
                    new[] { WaterColor.Purple, WaterColor.Red, WaterColor.Green, WaterColor.Blue },
                    new[] { WaterColor.Yellow, WaterColor.Purple, WaterColor.Red, WaterColor.Green },
                    new[] { WaterColor.Blue, WaterColor.Yellow, WaterColor.Purple, WaterColor.Red },
                    new[] { WaterColor.Green, WaterColor.Blue, WaterColor.Yellow, WaterColor.Purple }
                }, 2));

            // Level 9 - Hard: 5 colors, 7 bottles
            _builtInLevels.Add(CreateLevel(9, LevelDifficulty.Hard, 20,
                new WaterColor[][] {
                    new[] { WaterColor.Orange, WaterColor.Cyan, WaterColor.Pink, WaterColor.Brown },
                    new[] { WaterColor.White, WaterColor.Orange, WaterColor.Cyan, WaterColor.Pink },
                    new[] { WaterColor.Brown, WaterColor.White, WaterColor.Orange, WaterColor.Cyan },
                    new[] { WaterColor.Pink, WaterColor.Brown, WaterColor.White, WaterColor.Orange },
                    new[] { WaterColor.Cyan, WaterColor.Pink, WaterColor.Brown, WaterColor.White }
                }, 2));

            // Level 10 - Hard: 6 colors, 8 bottles
            _builtInLevels.Add(CreateLevel(10, LevelDifficulty.Hard, 25,
                new WaterColor[][] {
                    new[] { WaterColor.Red, WaterColor.Blue, WaterColor.Green, WaterColor.Yellow },
                    new[] { WaterColor.Purple, WaterColor.Orange, WaterColor.Red, WaterColor.Blue },
                    new[] { WaterColor.Green, WaterColor.Yellow, WaterColor.Purple, WaterColor.Orange },
                    new[] { WaterColor.Orange, WaterColor.Purple, WaterColor.Yellow, WaterColor.Green },
                    new[] { WaterColor.Blue, WaterColor.Red, WaterColor.Orange, WaterColor.Purple },
                    new[] { WaterColor.Yellow, WaterColor.Green, WaterColor.Blue, WaterColor.Red }
                }, 2));
        }

        private LevelModel CreateLevel(int id, LevelDifficulty difficulty, int par,
            WaterColor[][] bottleWaters, int emptyBottleCount)
        {
            List<BottleConfig> bottles = new List<BottleConfig>();

            for (int i = 0; i < bottleWaters.Length; i++)
            {
                List<WaterColor> waters = new List<WaterColor>(bottleWaters[i]);
                bottles.Add(new BottleConfig(DEFAULT_MAX_HEIGHT, waters));
            }

            return new LevelModel(id, difficulty, bottles, emptyBottleCount, par, $"builtin_{id}");
        }

        #endregion
    }
}
