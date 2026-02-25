using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Result of validating a pour selection from one bottle to another.
    /// Contains all data needed to execute or animate the pour.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Config
    /// Phase: 1
    /// </remarks>
    public class SelectionResult
    {
        #region Properties

        /// <summary>The source bottle being poured from.</summary>
        public BottleItem Origin { get; set; }

        /// <summary>The target bottle being poured into.</summary>
        public BottleItem Target { get; set; }

        /// <summary>The color of water being transferred.</summary>
        public WaterColor Color { get; set; }

        /// <summary>Number of water layers to move.</summary>
        public int WaterHeightToMove { get; set; }

        /// <summary>Water height of origin after the pour.</summary>
        public int OriginNewHeight { get; set; }

        /// <summary>Water height of target after the pour.</summary>
        public int TargetNewHeight { get; set; }

        #endregion

        #region Constructors

        public SelectionResult()
        {
            Origin = null;
            Target = null;
            Color = WaterColor.None;
            WaterHeightToMove = 0;
            OriginNewHeight = 0;
            TargetNewHeight = 0;
        }

        public SelectionResult(BottleItem origin, BottleItem target, WaterColor color,
            int waterHeightToMove, int originNewHeight, int targetNewHeight)
        {
            Origin = origin;
            Target = target;
            Color = color;
            WaterHeightToMove = waterHeightToMove;
            OriginNewHeight = originNewHeight;
            TargetNewHeight = targetNewHeight;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Returns true if this result represents a valid pour operation.
        /// </summary>
        public bool IsValid()
        {
            return Origin != null
                && Target != null
                && Color != WaterColor.None
                && WaterHeightToMove > 0;
        }

        public override string ToString()
        {
            return $"[Pour: {Color} x{WaterHeightToMove} from {Origin?.name ?? "null"} to {Target?.name ?? "null"}]";
        }

        #endregion
    }
}
