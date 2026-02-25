using UnityEngine;
using BlockBlast.Game;

namespace BlockBlast.Domain
{
    public class BlockDragHandler : MonoBehaviour
    {
        private BlockVisual _blockVisual;
        private bool _isDragging;
        private Vector3 _dragOffset;
        private Vector3 _originalPos;
        private Camera _camera;
        private Vector2Int _lastGridPos = new Vector2Int(-1, -1);
        private bool _isEnabled = true;
        private BoxCollider2D _collider;

        private const float DRAG_Y_OFFSET = 2.0f;

        public void Init(BlockVisual visual)
        {
            _blockVisual = visual;
            _camera = Camera.main;

            if (_camera == null)
            {
                Debug.LogError("[BlockDragHandler] Camera.main is null!");
                return;
            }

            // Add collider for touch/click detection
            _collider = gameObject.AddComponent<BoxCollider2D>();
            var size = visual.Shape.GetSize();
            float cellSize = GameBoard.CELL_SIZE;
            _collider.size = new Vector2(size.x * cellSize, size.y * cellSize);
            _collider.offset = new Vector2(
                (size.x - 1) * cellSize / 2f,
                (size.y - 1) * cellSize / 2f
            );

            Debug.Log($"[BlockDragHandler] Init complete: {gameObject.name}, colliderSize={_collider.size}, colliderOffset={_collider.offset}, scale={transform.localScale}");
        }

        public void SetEnabled(bool enabled)
        {
            _isEnabled = enabled;
        }

        private void Update()
        {
            if (!_isEnabled || _camera == null || _blockVisual == null) return;

            if (Input.GetMouseButtonDown(0))
                TryStartDrag();
            else if (Input.GetMouseButton(0) && _isDragging)
                ContinueDrag();
            else if (Input.GetMouseButtonUp(0) && _isDragging)
                EndDrag();
        }

        private void TryStartDrag()
        {
            Vector3 mouseWorld = _camera.ScreenToWorldPoint(Input.mousePosition);
            mouseWorld.z = 0;

            // Use OverlapAll to find our specific collider
            var hits = Physics2D.OverlapPointAll(mouseWorld);
            bool hitSelf = false;
            foreach (var hit in hits)
            {
                if (hit != null && hit.gameObject == gameObject)
                {
                    hitSelf = true;
                    break;
                }
            }

            if (hitSelf)
            {
                _isDragging = true;
                _originalPos = transform.position;
                _dragOffset = transform.position - mouseWorld;
                _blockVisual.SetDragging(true);
                _lastGridPos = new Vector2Int(-1, -1);
                Debug.Log($"[BlockDragHandler] Start drag: {gameObject.name}");
            }
        }

        private void ContinueDrag()
        {
            Vector3 mouseWorld = _camera.ScreenToWorldPoint(Input.mousePosition);
            mouseWorld.z = 0;
            transform.position = mouseWorld + _dragOffset + Vector3.up * DRAG_Y_OFFSET;

            // Calculate grid position for preview
            var board = GameBoard.Instance;
            if (board == null) return;

            Vector3 blockCenter = transform.position;
            Vector2Int gridPos = board.WorldToGrid(blockCenter);

            if (gridPos != _lastGridPos)
            {
                _lastGridPos = gridPos;
                bool canPlace = board.CanPlaceBlock(_blockVisual.Shape, gridPos);
                board.ShowPreview(_blockVisual.Shape, gridPos, canPlace);
            }
        }

        private void EndDrag()
        {
            _isDragging = false;

            var board = GameBoard.Instance;
            if (board == null || _blockVisual == null)
            {
                transform.position = _originalPos;
                _blockVisual?.SetDragging(false);
                return;
            }

            board.ClearPreview();

            Vector3 blockCenter = transform.position;
            Vector2Int gridPos = board.WorldToGrid(blockCenter);

            bool canPlace = board.CanPlaceBlock(_blockVisual.Shape, gridPos);

            if (canPlace)
            {
                Color color = SpriteFactory.GetColorFromIndex(_blockVisual.ColorIndex);
                GameBoard.Instance.PlaceBlock(_blockVisual.Shape, gridPos, color);
                BlockSpawner.Instance.RemoveCandidate(_blockVisual);
                GameManager.Instance.OnBlockPlaced(_blockVisual.Shape.CellCount);
                Debug.Log($"[BlockDragHandler] Placed block at grid ({gridPos.x}, {gridPos.y})");
                _blockVisual.DestroySelf();
            }
            else
            {
                Debug.Log($"[BlockDragHandler] Cannot place at ({gridPos.x}, {gridPos.y}), snapping back");
                _blockVisual.SnapBack();
            }
        }
    }
}
