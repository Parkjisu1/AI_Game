using System.Collections.Generic;
using UnityEngine;

namespace BlockBlast.Domain
{
    public enum BlockShapeType
    {
        Single, H2, V2, H3, V3, L2x2, L2x2_R, Square2, T3,
        H4, V4, L3x2, L3x2_R, Square3, H5, V5, Z3, S3
    }

    [System.Serializable]
    public class BlockShape
    {
        public BlockShapeType ShapeType;
        public Vector2Int[] Cells;
        public int Weight;

        public BlockShape(BlockShapeType type, Vector2Int[] cells, int weight)
        {
            ShapeType = type;
            Cells = cells;
            Weight = weight;
        }

        public int CellCount => Cells.Length;

        public Vector2Int GetSize()
        {
            int maxX = 0, maxY = 0;
            foreach (var c in Cells)
            {
                if (c.x > maxX) maxX = c.x;
                if (c.y > maxY) maxY = c.y;
            }
            return new Vector2Int(maxX + 1, maxY + 1);
        }
    }

    public static class BlockData
    {
        private static List<BlockShape> _allShapes;
        private static int _totalWeight;

        public static List<BlockShape> GetAllShapes()
        {
            if (_allShapes != null) return _allShapes;

            _allShapes = new List<BlockShape>
            {
                new BlockShape(BlockShapeType.Single, new[] { V(0,0) }, 5),
                new BlockShape(BlockShapeType.H2, new[] { V(0,0), V(1,0) }, 8),
                new BlockShape(BlockShapeType.V2, new[] { V(0,0), V(0,1) }, 8),
                new BlockShape(BlockShapeType.H3, new[] { V(0,0), V(1,0), V(2,0) }, 10),
                new BlockShape(BlockShapeType.V3, new[] { V(0,0), V(0,1), V(0,2) }, 10),
                new BlockShape(BlockShapeType.L2x2, new[] { V(0,0), V(1,0), V(0,1) }, 12),
                new BlockShape(BlockShapeType.L2x2_R, new[] { V(0,0), V(1,0), V(1,1) }, 12),
                new BlockShape(BlockShapeType.Square2, new[] { V(0,0), V(1,0), V(0,1), V(1,1) }, 10),
                new BlockShape(BlockShapeType.T3, new[] { V(0,0), V(1,0), V(2,0), V(1,1) }, 8),
                new BlockShape(BlockShapeType.H4, new[] { V(0,0), V(1,0), V(2,0), V(3,0) }, 6),
                new BlockShape(BlockShapeType.V4, new[] { V(0,0), V(0,1), V(0,2), V(0,3) }, 6),
                new BlockShape(BlockShapeType.L3x2, new[] { V(0,0), V(1,0), V(2,0), V(0,1) }, 7),
                new BlockShape(BlockShapeType.L3x2_R, new[] { V(0,0), V(1,0), V(2,0), V(2,1) }, 7),
                new BlockShape(BlockShapeType.Square3, new[] { V(0,0), V(1,0), V(2,0), V(0,1), V(1,1), V(2,1), V(0,2), V(1,2), V(2,2) }, 3),
                new BlockShape(BlockShapeType.H5, new[] { V(0,0), V(1,0), V(2,0), V(3,0), V(4,0) }, 3),
                new BlockShape(BlockShapeType.V5, new[] { V(0,0), V(0,1), V(0,2), V(0,3), V(0,4) }, 3),
                new BlockShape(BlockShapeType.Z3, new[] { V(0,0), V(1,0), V(1,1), V(2,1) }, 6),
                new BlockShape(BlockShapeType.S3, new[] { V(1,0), V(2,0), V(0,1), V(1,1) }, 6),
            };

            _totalWeight = 0;
            foreach (var s in _allShapes) _totalWeight += s.Weight;

            return _allShapes;
        }

        public static BlockShape GetRandomShape()
        {
            var shapes = GetAllShapes();
            int roll = Random.Range(0, _totalWeight);
            int cumulative = 0;
            foreach (var s in shapes)
            {
                cumulative += s.Weight;
                if (roll < cumulative) return s;
            }
            return shapes[shapes.Count - 1];
        }

        private static Vector2Int V(int x, int y) => new Vector2Int(x, y);

        // Color palette
        private static readonly Color[] _colors =
        {
            HexColor("#FF4444"), // Red
            HexColor("#4488FF"), // Blue
            HexColor("#44DD44"), // Green
            HexColor("#FFCC00"), // Yellow
            HexColor("#BB44FF"), // Purple
            HexColor("#FF8800"), // Orange
            HexColor("#00CCCC"), // Cyan
        };

        public static Color GetColor(int index)
        {
            return _colors[index % _colors.Length];
        }

        public static int GetRandomColorIndex()
        {
            return Random.Range(0, _colors.Length);
        }

        public static int ColorCount => _colors.Length;

        private static Color HexColor(string hex)
        {
            ColorUtility.TryParseHtmlString(hex, out Color c);
            return c;
        }
    }
}
