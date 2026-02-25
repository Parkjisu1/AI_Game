namespace MagicSort.Core
{
    /// <summary>
    /// Signal structs for the SignalBus event system.
    /// All inter-system communication uses these typed signals.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Puzzle
    /// Role: Config
    /// Phase: 0
    /// </remarks>

    /// <summary>
    /// Fired when a level starts. Contains the level number and difficulty.
    /// </summary>
    public struct LevelStartSignal
    {
        public int LevelNumber;
        public LevelDifficulty Difficulty;
    }

    /// <summary>
    /// Fired when the player completes a level successfully.
    /// </summary>
    public struct LevelCompleteSignal
    {
        public int LevelNumber;
        public int StarRating;
        public int MoveCount;
    }

    /// <summary>
    /// Fired when the player fails a level.
    /// </summary>
    public struct LevelFailSignal
    {
        public int LevelNumber;
        public StuckType Reason;
    }

    /// <summary>
    /// Fired when the player selects a bottle.
    /// </summary>
    public struct BottleSelectedSignal
    {
        public int BottleIndex;
        public bool IsSource;
    }

    /// <summary>
    /// Fired when a pour action completes (water transferred between bottles).
    /// </summary>
    public struct PourCompleteSignal
    {
        public int SourceIndex;
        public int TargetIndex;
        public WaterColor Color;
        public int LayerCount;
    }

    /// <summary>
    /// Fired when a blocker is broken/removed from a bottle.
    /// </summary>
    public struct BlockerBrokenSignal
    {
        public int BottleIndex;
        public BlockerType Type;
    }

    /// <summary>
    /// Fired when the player uses a booster.
    /// </summary>
    public struct BoosterUsedSignal
    {
        public BoosterType Type;
        public int RemainingCount;
    }

    /// <summary>
    /// Fired when a scene finishes loading.
    /// </summary>
    public struct SceneLoadedSignal
    {
        public SceneName SceneName;
    }

    /// <summary>
    /// Fired when any currency amount changes.
    /// </summary>
    public struct CurrencyChangedSignal
    {
        public string CurrencyId;
        public int OldAmount;
        public int NewAmount;
    }
}
