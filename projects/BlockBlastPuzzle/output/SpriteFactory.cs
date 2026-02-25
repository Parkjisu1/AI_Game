using UnityEngine;

namespace BlockBlast.Game
{
    public static class SpriteFactory
    {
        private static readonly Color[] _palette =
        {
            HexColor("#FF4444"),
            HexColor("#4488FF"),
            HexColor("#44DD44"),
            HexColor("#FFCC00"),
            HexColor("#BB44FF"),
            HexColor("#FF8800"),
            HexColor("#00CCCC"),
        };

        public static Sprite CreateSquareSprite(int size = 64, Color? color = null)
        {
            Color c = color ?? Color.white;
            var tex = new Texture2D(size, size);
            tex.filterMode = FilterMode.Point;
            var pixels = new Color[size * size];
            for (int i = 0; i < pixels.Length; i++)
                pixels[i] = c;
            tex.SetPixels(pixels);
            tex.Apply();
            return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), size);
        }

        public static Sprite CreateRoundedSprite(int size = 64, Color? color = null, int radius = 8)
        {
            Color c = color ?? Color.white;
            var tex = new Texture2D(size, size);
            tex.filterMode = FilterMode.Bilinear;
            var pixels = new Color[size * size];

            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    bool inside = true;

                    // Check corners for rounding
                    if (x < radius && y < radius)
                        inside = Vector2.Distance(new Vector2(x, y), new Vector2(radius, radius)) <= radius;
                    else if (x >= size - radius && y < radius)
                        inside = Vector2.Distance(new Vector2(x, y), new Vector2(size - radius - 1, radius)) <= radius;
                    else if (x < radius && y >= size - radius)
                        inside = Vector2.Distance(new Vector2(x, y), new Vector2(radius, size - radius - 1)) <= radius;
                    else if (x >= size - radius && y >= size - radius)
                        inside = Vector2.Distance(new Vector2(x, y), new Vector2(size - radius - 1, size - radius - 1)) <= radius;

                    pixels[y * size + x] = inside ? c : Color.clear;
                }
            }

            tex.SetPixels(pixels);
            tex.Apply();
            return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), size);
        }

        public static Sprite CreateCircleSprite(int size = 64, Color? color = null)
        {
            Color c = color ?? Color.white;
            var tex = new Texture2D(size, size);
            tex.filterMode = FilterMode.Bilinear;
            var pixels = new Color[size * size];
            float center = size / 2f;
            float radiusSq = center * center;

            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float dx = x - center + 0.5f;
                    float dy = y - center + 0.5f;
                    pixels[y * size + x] = (dx * dx + dy * dy <= radiusSq) ? c : Color.clear;
                }
            }

            tex.SetPixels(pixels);
            tex.Apply();
            return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), size);
        }

        public static Color GetColorFromIndex(int index)
        {
            return _palette[index % _palette.Length];
        }

        public static int PaletteSize => _palette.Length;

        private static Color HexColor(string hex)
        {
            ColorUtility.TryParseHtmlString(hex, out Color c);
            return c;
        }
    }
}
