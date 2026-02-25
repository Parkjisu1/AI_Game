using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using BlockBlast.Domain;

namespace BlockBlast.Game
{
    public class BlockVisual : MonoBehaviour
    {
        private BlockShape _shape;
        private Color _color;
        private int _colorIndex;
        private List<GameObject> _cellObjects = new List<GameObject>();
        private Vector3 _originalPosition;
        private Vector3 _originalScale;
        private BlockDragHandler _dragHandler;

        public BlockShape Shape => _shape;
        public int ColorIndex => _colorIndex;

        public void Setup(BlockShape shape, int colorIndex, float cellSize = 0.9f)
        {
            _shape = shape;
            _colorIndex = colorIndex;
            _color = SpriteFactory.GetColorFromIndex(colorIndex);

            Sprite cellSprite = SpriteFactory.CreateRoundedSprite(64, _color, 10);

            foreach (var cell in shape.Cells)
            {
                var cellGo = new GameObject($"Cell_{cell.x}_{cell.y}");
                cellGo.transform.SetParent(transform);
                cellGo.transform.localPosition = new Vector3(cell.x * cellSize, cell.y * cellSize, 0);

                var sr = cellGo.AddComponent<SpriteRenderer>();
                sr.sprite = cellSprite;
                sr.sortingOrder = 10;
                cellGo.transform.localScale = Vector3.one * cellSize;

                _cellObjects.Add(cellGo);
            }

            _originalPosition = transform.position;
            _originalScale = transform.localScale;
        }

        public void SetDragging(bool dragging)
        {
            if (dragging)
            {
                transform.localScale = Vector3.one;
                foreach (var cell in _cellObjects)
                {
                    var sr = cell.GetComponent<SpriteRenderer>();
                    if (sr != null) sr.sortingOrder = 20;
                }
            }
            else
            {
                transform.localScale = _originalScale;
                foreach (var cell in _cellObjects)
                {
                    var sr = cell.GetComponent<SpriteRenderer>();
                    if (sr != null) sr.sortingOrder = 10;
                }
            }
        }

        public void SnapBack()
        {
            StartCoroutine(SnapBackCoroutine());
        }

        private IEnumerator SnapBackCoroutine()
        {
            float duration = 0.2f;
            float elapsed = 0f;
            Vector3 start = transform.position;

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = Mathf.SmoothStep(0f, 1f, elapsed / duration);
                transform.position = Vector3.Lerp(start, _originalPosition, t);
                yield return null;
            }

            transform.position = _originalPosition;
            SetDragging(false);
        }

        public void SetOriginalPosition(Vector3 pos)
        {
            _originalPosition = pos;
            transform.position = pos;
        }

        public void SetOriginalScale(Vector3 scale)
        {
            _originalScale = scale;
            transform.localScale = scale;
        }

        public void DestroySelf()
        {
            foreach (var cell in _cellObjects)
            {
                if (cell != null) Destroy(cell);
            }
            _cellObjects.Clear();
            Destroy(gameObject);
        }
    }
}
