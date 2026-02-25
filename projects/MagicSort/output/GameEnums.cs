namespace MagicSort.Core
{
    /// <summary>
    /// All shared enum definitions for MagicSort.
    /// Centralized to prevent duplication and ensure consistency across systems.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Puzzle
    /// Role: Config
    /// Phase: 0
    /// </remarks>

    /// <summary>
    /// Water colors available in the game, including None for empty slots.
    /// </summary>
    public enum WaterColor
    {
        None = 0,
        Red = 1,
        Blue = 2,
        Green = 3,
        Yellow = 4,
        Purple = 5,
        Orange = 6,
        Pink = 7,
        Cyan = 8,
        Brown = 9,
        White = 10,
        Gray = 11,
        DarkBlue = 12,
        Lime = 13,
        Magenta = 14
    }

    /// <summary>
    /// State of the current level during gameplay.
    /// </summary>
    public enum LevelState
    {
        None = 0,
        Playing,
        Paused,
        Stuck,
        Win,
        Lose,
        Quit
    }

    /// <summary>
    /// Types of blockers that can appear on bottles.
    /// </summary>
    public enum BlockerType
    {
        Ice = 0,
        Frog,
        Duck,
        Tag,
        Ivy,
        Safe,
        MagicSeal,
        Toggle,
        Switch,
        Generator,
        Snitch,
        QuestionMark,
        Carpet,
        Curtain,
        Plaster,
        Clay,
        Woodbox,
        Blob,
        KeyLock
    }

    /// <summary>
    /// Types of boosters the player can use.
    /// </summary>
    public enum BoosterType
    {
        ExtraBottle = 0,
        ColorClear,
        Shuffle,
        Undo,
        Hint
    }

    /// <summary>
    /// Reasons why the player might be stuck.
    /// </summary>
    public enum StuckType
    {
        NoMove = 0,
        TimeIsUp
    }

    /// <summary>
    /// Difficulty rating for levels.
    /// </summary>
    public enum LevelDifficulty
    {
        Easy = 0,
        Medium,
        Hard,
        Expert
    }

    /// <summary>
    /// High-level game state for scene management.
    /// </summary>
    public enum GameState
    {
        Title = 0,
        Home,
        GamePlay
    }

    /// <summary>
    /// Scene name identifiers matching Unity Build Settings.
    /// </summary>
    public enum SceneName
    {
        Title = 0,
        Home,
        GamePlay
    }
}
