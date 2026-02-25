using System.Collections;
using UnityEngine;

namespace BlockBlast.Game
{
    public class CellVisual : MonoBehaviour
    {
        private SpriteRenderer _renderer;
        private bool _isOccupied;
        private Color _occupiedColor;
        private Vector2Int _gridPosition;
        private bool _isPreviewing;

        private static readonly Color EMPTY_COLOR = new Color(0.15f, 0.15f, 0.2f, 1f);
        private static readonly Color PREVIEW_VALID_COLOR = new Color(1f, 1f, 1f, 0.3f);
        private static readonly Color PREVIEW_INVALID_COLOR = new Color(1f, 0.3f, 0.3f, 0.3f);
        private static readonly Color GRID_LINE_COLOR = new Color(0.2f, 0.2f, 0.28f, 1f);

        public Vector2Int GridPosition => _gridPosition;
        public bool IsOccupied => _isOccupied;

        public void Init(Vector2Int gridPos, Sprite sprite)
        {
            _gridPosition = gridPos;
            _renderer = GetComponent<SpriteRenderer>();
            if (_renderer == null)
                _renderer = gameObject.AddComponent<SpriteRenderer>();
            _renderer.sprite = sprite;
            _renderer.sortingOrder = 0;
            SetEmpty();
        }

        public void SetOccupied(Color color)
        {
            _isOccupied = true;
            _occupiedColor = color;
            _renderer.color = color;
        }

        public void SetEmpty()
        {
            _isOccupied = false;
            _occupiedColor = EMPTY_COLOR;
            _renderer.color = EMPTY_COLOR;
        }

        public void SetPreview(bool valid)
        {
            if (_isOccupied) return;
            _isPreviewing = true;
            _renderer.color = valid ? PREVIEW_VALID_COLOR : PREVIEW_INVALID_COLOR;
        }

        public void ClearPreview()
        {
            if (!_isPreviewing) return;
            _isPreviewing = false;
            _renderer.color = _isOccupied ? _occupiedColor : EMPTY_COLOR;
        }

        public void PlayClearAnimation()
        {
            StartCoroutine(ClearAnimationCoroutine());
        }

        private IEnumerator ClearAnimationCoroutine()
        {
            float duration = 0.3f;
            float elapsed = 0f;
            Vector3 originalScale = transform.localScale;
            Color startColor = _renderer.color;

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = elapsed / duration;

                // Scale up slightly then down
                float scale = t < 0.3f
                    ? Mathf.Lerp(1f, 1.2f, t / 0.3f)
                    : Mathf.Lerp(1.2f, 0f, (t - 0.3f) / 0.7f);
                transform.localScale = originalScale * scale;

                // Fade out
                Color c = startColor;
                c.a = Mathf.Lerp(1f, 0f, t);
                _renderer.color = c;

                yield return null;
            }

            transform.localScale = originalScale;
            SetEmpty();
        }
    }
}
