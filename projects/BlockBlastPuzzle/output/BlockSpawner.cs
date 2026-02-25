using System.Collections.Generic;
using UnityEngine;
using BlockBlast.Core;
using BlockBlast.Game;

namespace BlockBlast.Domain
{
    public class BlockSpawner : Singleton<BlockSpawner>
    {
        public const int CANDIDATE_COUNT = 3;
        public const float CANDIDATE_SCALE = 0.55f;

        private List<BlockVisual> _candidates = new List<BlockVisual>();
        private Transform _candidateParent;
        private Vector3 _spawnAreaCenter;

        public List<BlockVisual> Candidates => _candidates;

        public void Init(Vector3 spawnAreaCenter)
        {
            _spawnAreaCenter = spawnAreaCenter;
            _candidateParent = new GameObject("CandidateArea").transform;
            _candidateParent.position = Vector3.zero;
        }

        public void SpawnCandidates()
        {
            ClearCandidates();

            float spacing = 3.0f;
            float startX = _spawnAreaCenter.x - spacing;

            for (int i = 0; i < CANDIDATE_COUNT; i++)
            {
                BlockShape shape = BlockData.GetRandomShape();
                int colorIndex = BlockData.GetRandomColorIndex();

                var blockGo = new GameObject($"Candidate_{i}");
                blockGo.transform.SetParent(_candidateParent);

                var visual = blockGo.AddComponent<BlockVisual>();
                visual.Setup(shape, colorIndex, GameBoard.CELL_SIZE);

                Vector3 pos = new Vector3(startX + i * spacing, _spawnAreaCenter.y, 0);
                visual.SetOriginalPosition(pos);
                visual.SetOriginalScale(Vector3.one * CANDIDATE_SCALE);

                var dragHandler = blockGo.AddComponent<BlockDragHandler>();
                dragHandler.Init(visual);

                _candidates.Add(visual);

                Debug.Log($"[BlockSpawner] Spawned {blockGo.name}: shape={shape.ShapeType}, cells={shape.CellCount}, pos={pos}, scale={CANDIDATE_SCALE}");
            }
        }

        public void RemoveCandidate(BlockVisual block)
        {
            _candidates.Remove(block);

            if (_candidates.Count == 0)
            {
                SpawnCandidates();
            }
        }

        public bool HasAnyValidPlacement()
        {
            foreach (var candidate in _candidates)
            {
                if (candidate != null && GameBoard.Instance.HasValidPlacement(candidate.Shape))
                    return true;
            }
            return false;
        }

        public int RemainingCount => _candidates.Count;

        public void SetDragEnabled(bool enabled)
        {
            foreach (var candidate in _candidates)
            {
                if (candidate != null)
                {
                    var handler = candidate.GetComponent<BlockDragHandler>();
                    if (handler != null) handler.SetEnabled(enabled);
                }
            }
        }

        private void ClearCandidates()
        {
            foreach (var c in _candidates)
            {
                if (c != null) c.DestroySelf();
            }
            _candidates.Clear();
        }
    }
}
