using UnityEngine;
using UnityEngine.UI;
using TMPro;
using VeilBreaker.Core;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Tower challenge popup. Displays current and max tower floor,
    /// provides a challenge button, and updates on floor completion events.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// Phase: 3
    /// System: UI
    /// </remarks>
    public class PopupTower : PopupBase
    {
        #region Fields

        [SerializeField] private TextMeshProUGUI _maxFloorText;
        [SerializeField] private TextMeshProUGUI _nextFloorText;
        [SerializeField] private Button          _challengeButton;
        [SerializeField] private Button          _closeButton;
        [SerializeField] private Transform       _rewardPreviewContent;

        #endregion

        #region PopupBase Overrides

        /// <summary>
        /// Opens the tower popup and populates floor information.
        /// </summary>
        public override void Open(object data = null)
        {
            RefreshFloorDisplay();

            _challengeButton?.onClick.RemoveAllListeners();
            _challengeButton?.onClick.AddListener(OnChallengeButton);

            _closeButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.AddListener(CloseThis);

            EventManager.Subscribe(GameConstants.Events.OnTowerFloorComplete, OnTowerFloorComplete);
        }

        /// <summary>
        /// Cleans up on close.
        /// </summary>
        public override void Close()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnTowerFloorComplete, OnTowerFloorComplete);
            _challengeButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.RemoveAllListeners();
        }

        #endregion

        #region Private Methods

        private void OnChallengeButton()
        {
            if (!TowerManager.HasInstance) return;

            int nextFloor = TowerManager.Instance.GetNextFloor();
            TowerManager.Instance.StartTower(nextFloor);

            // Close popup before battle starts to prevent UI overlap
            CloseThis();
        }

        private void OnTowerFloorComplete(object data)
        {
            RefreshFloorDisplay();
        }

        private void RefreshFloorDisplay()
        {
            if (!TowerManager.HasInstance) return;

            int maxFloor  = TowerManager.Instance.GetMaxFloor();
            int nextFloor = TowerManager.Instance.GetNextFloor();

            if (_maxFloorText  != null) _maxFloorText.text  = $"Max Floor: {maxFloor}";
            if (_nextFloorText != null) _nextFloorText.text = $"Next: Floor {nextFloor}";

            // Disable challenge button if tower is at cap
            if (_challengeButton != null)
                _challengeButton.interactable = nextFloor <= TowerManager.MaxFloor;
        }

        #endregion
    }
}
