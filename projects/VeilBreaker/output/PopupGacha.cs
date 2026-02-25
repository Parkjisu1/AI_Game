using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using VeilBreaker.Core;
using VeilBreaker.Economy;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Gacha pull popup. Handles single and 10x pulls with sequential card reveal animation.
    /// Disables pull buttons during animation to prevent duplicate inputs.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// Phase: 3
    /// System: UI
    /// </remarks>
    public class PopupGacha : PopupBase
    {
        #region Constants

        private const float CardRevealInterval = 0.15f;

        #endregion

        #region Fields

        [SerializeField] private Transform          _resultContainer;
        [SerializeField] private GameObject         _gachaCardPrefab;
        [SerializeField] private TextMeshProUGUI    _pityText;
        [SerializeField] private Button             _singlePullButton;
        [SerializeField] private Button             _tenPullButton;
        [SerializeField] private Button             _closeButton;
        [SerializeField] private GameObject         _pullBlocker; // overlay to block input during animation

        private string _currentBannerId;
        private bool   _isAnimating;

        // Card pool for result display
        private readonly List<GameObject> _cardPool = new();

        #endregion

        #region PopupBase Overrides

        /// <summary>
        /// Opens the popup for the given banner. Expects data as string bannerId.
        /// </summary>
        public override void Open(object data = null)
        {
            _currentBannerId = data as string ?? string.Empty;
            _isAnimating     = false;

            SetPullButtonsInteractable(true);
            HideBlocker();
            ClearResultCards();
            RefreshPityDisplay();

            _singlePullButton?.onClick.RemoveAllListeners();
            _singlePullButton?.onClick.AddListener(OnSinglePull);

            _tenPullButton?.onClick.RemoveAllListeners();
            _tenPullButton?.onClick.AddListener(OnTenPull);

            _closeButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.AddListener(CloseThis);
        }

        /// <summary>
        /// Cleans up on close.
        /// </summary>
        public override void Close()
        {
            StopAllCoroutines();
            _singlePullButton?.onClick.RemoveAllListeners();
            _tenPullButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.RemoveAllListeners();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Displays the gacha result cards with a sequential reveal animation.
        /// </summary>
        /// <param name="results">List of gacha result items to reveal.</param>
        public void ShowGachaResult(List<GachaItem> results)
        {
            if (results == null || results.Count == 0) return;
            StartCoroutine(ShowResultAnimation(results));
        }

        #endregion

        #region Private Methods

        private void OnSinglePull()
        {
            if (_isAnimating) return;
            ExecutePull(1);
        }

        private void OnTenPull()
        {
            if (_isAnimating) return;
            ExecutePull(10);
        }

        private void ExecutePull(int count)
        {
            if (!GachaManager.HasInstance) return;

            SetPullButtonsInteractable(false);
            var results = GachaManager.Instance.Pull(_currentBannerId, count);
            if (results == null || results.Count == 0)
            {
                SetPullButtonsInteractable(true);
                return;
            }

            RefreshPityDisplay();
            ShowGachaResult(results);
        }

        private IEnumerator ShowResultAnimation(List<GachaItem> items)
        {
            _isAnimating = true;
            ShowBlocker();
            ClearResultCards();

            foreach (var item in items)
            {
                var card = GetOrCreateCard();
                if (card != null)
                {
                    var cardView = card.GetComponent<GachaCardView>();
                    cardView?.Bind(item);
                }
                yield return new WaitForSeconds(CardRevealInterval);
            }

            _isAnimating = false;
            HideBlocker();
            SetPullButtonsInteractable(true);
        }

        private GameObject GetOrCreateCard()
        {
            // Find inactive card in pool
            foreach (var c in _cardPool)
            {
                if (c != null && !c.activeInHierarchy)
                {
                    c.SetActive(true);
                    return c;
                }
            }

            // Create new card
            if (_gachaCardPrefab == null || _resultContainer == null) return null;
            var newCard = Instantiate(_gachaCardPrefab, _resultContainer);
            _cardPool.Add(newCard);
            return newCard;
        }

        private void ClearResultCards()
        {
            foreach (var c in _cardPool)
                c?.SetActive(false);
        }

        private void RefreshPityDisplay()
        {
            if (_pityText == null) return;
            if (!GachaManager.HasInstance) return;

            int pity = GachaManager.Instance.GetPityCount(_currentBannerId);
            _pityText.text = $"Pity: {pity}/{GameConstants.Gacha.HardPity}";
        }

        private void SetPullButtonsInteractable(bool interactable)
        {
            if (_singlePullButton != null) _singlePullButton.interactable = interactable;
            if (_tenPullButton    != null) _tenPullButton.interactable    = interactable;
        }

        private void ShowBlocker()
        {
            _pullBlocker?.SetActive(true);
        }

        private void HideBlocker()
        {
            _pullBlocker?.SetActive(false);
        }

        #endregion
    }

    /// <summary>
    /// Single gacha result item data.
    /// </summary>
    [System.Serializable]
    public class GachaItem
    {
        public string heroId;
        public GameConstants.Rarity rarity;
    }

    /// <summary>
    /// View component attached to the gacha card prefab.
    /// </summary>
    public class GachaCardView : MonoBehaviour
    {
        [SerializeField] private TextMeshProUGUI _heroNameText;
        [SerializeField] private Image           _cardBackground;

        private static readonly Color[] RarityColors =
        {
            new Color(0.7f, 0.7f, 0.7f),   // Common  - grey
            new Color(0.3f, 0.8f, 0.3f),   // Uncommon - green
            new Color(0.2f, 0.5f, 1.0f),   // Rare    - blue
            new Color(0.6f, 0.2f, 0.9f),   // Epic    - purple
            new Color(1.0f, 0.8f, 0.1f),   // Legendary - gold
        };

        /// <summary>
        /// Binds gacha result data to this card view.
        /// </summary>
        public void Bind(GachaItem item)
        {
            if (item == null) return;

            if (_heroNameText != null)
                _heroNameText.text = item.heroId;

            if (_cardBackground != null)
            {
                int colorIndex = Mathf.Clamp((int)item.rarity, 0, RarityColors.Length - 1);
                _cardBackground.color = RarityColors[colorIndex];
            }
        }
    }
}
