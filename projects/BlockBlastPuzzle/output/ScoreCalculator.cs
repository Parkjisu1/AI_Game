using UnityEngine;
using BlockBlast.Core;

namespace BlockBlast.Domain
{
    public class ScoreCalculator
    {
        public const int BASE_SCORE_PER_CELL = 10;
        public const int LINE_CLEAR_BONUS = 100;
        public const int MULTI_LINE_2 = 300;
        public const int MULTI_LINE_3 = 600;
        public const int MULTI_LINE_4 = 1000;
        public const int MULTI_LINE_5_PLUS = 2000;

        private int _currentCombo;
        private int _totalScore;

        public int TotalScore => _totalScore;
        public int CurrentCombo => _currentCombo;

        public int CalculatePlacementScore(int cellCount)
        {
            return cellCount * BASE_SCORE_PER_CELL;
        }

        public int CalculateLineClearScore(int lineCount)
        {
            if (lineCount <= 0) return 0;

            _currentCombo++;

            int score = lineCount * LINE_CLEAR_BONUS;

            // Multi-line bonus
            switch (lineCount)
            {
                case 2: score += MULTI_LINE_2; break;
                case 3: score += MULTI_LINE_3; break;
                case 4: score += MULTI_LINE_4; break;
                default:
                    if (lineCount >= 5) score += MULTI_LINE_5_PLUS;
                    break;
            }

            // Combo multiplier
            float multiplier = GetComboMultiplier();
            score = Mathf.RoundToInt(score * multiplier);

            return score;
        }

        public float GetComboMultiplier()
        {
            switch (_currentCombo)
            {
                case 0:
                case 1: return 1.0f;
                case 2: return 1.5f;
                case 3: return 2.0f;
                case 4: return 3.0f;
                default: return 4.0f;
            }
        }

        public void AddScore(int points)
        {
            _totalScore += points;
            EventManager.Instance.Publish(EventManager.EVT_SCORE_CHANGED, _totalScore);
        }

        public void ResetCombo()
        {
            _currentCombo = 0;
            EventManager.Instance.Publish(EventManager.EVT_COMBO_CHANGED, 0);
        }

        public void Reset()
        {
            _totalScore = 0;
            _currentCombo = 0;
        }
    }
}
