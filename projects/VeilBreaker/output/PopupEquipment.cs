using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using VeilBreaker.Core;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Equipment management popup. Displays the player's equipment list in a scroll view
    /// and provides enhance, merge, and decompose actions.
    /// Equipment item rows are pooled to avoid repeated Instantiate/Destroy.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// Phase: 3
    /// System: UI
    /// </remarks>
    public class PopupEquipment : PopupBase
    {
        #region Fields

        [SerializeField] private ScrollRect     _equipScrollView;
        [SerializeField] private Transform      _equipListContent;
        [SerializeField] private GameObject     _equipItemPrefab;

        [SerializeField] private Button         _enhanceButton;
        [SerializeField] private Button         _mergeButton;
        [SerializeField] private Button         _decomposeButton;
        [SerializeField] private Button         _closeButton;

        [SerializeField] private TextMeshProUGUI _selectedEquipName;
        [SerializeField] private TextMeshProUGUI _selectedEquipStats;

        private string _selectedEquipId;

        // Row pool: reuse existing rows before instantiating new ones
        private readonly List<GameObject> _rowPool = new();

        #endregion

        #region PopupBase Overrides

        /// <summary>
        /// Opens the popup, loads equipment list, and subscribes to change events.
        /// </summary>
        public override void Open(object data = null)
        {
            _selectedEquipId = null;
            RefreshSelectedPanel();
            RefreshEquipmentList();

            _enhanceButton?.onClick.RemoveAllListeners();
            _enhanceButton?.onClick.AddListener(OnEnhanceButton);

            _mergeButton?.onClick.RemoveAllListeners();
            _mergeButton?.onClick.AddListener(OnMergeButton);

            _decomposeButton?.onClick.RemoveAllListeners();
            _decomposeButton?.onClick.AddListener(OnDecomposeButton);

            _closeButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.AddListener(CloseThis);

            EventManager.Subscribe(GameConstants.Events.OnEquipmentChanged,  OnEquipmentChanged);
            EventManager.Subscribe(GameConstants.Events.OnEquipmentEnhanced, OnEquipmentChanged);
        }

        /// <summary>
        /// Closes the popup and unsubscribes from events.
        /// </summary>
        public override void Close()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnEquipmentChanged,  OnEquipmentChanged);
            EventManager.Unsubscribe(GameConstants.Events.OnEquipmentEnhanced, OnEquipmentChanged);

            _enhanceButton?.onClick.RemoveAllListeners();
            _mergeButton?.onClick.RemoveAllListeners();
            _decomposeButton?.onClick.RemoveAllListeners();
            _closeButton?.onClick.RemoveAllListeners();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Refreshes the equipment scroll list from EquipmentManager.
        /// Reuses pooled rows where possible.
        /// </summary>
        public void RefreshEquipmentList()
        {
            if (_equipListContent == null) return;

            // Hide all pooled rows first
            foreach (var row in _rowPool)
                row?.SetActive(false);

            if (!EquipmentManager.HasInstance) return;

            var equipList = EquipmentManager.Instance.GetAllEquipments();
            if (equipList == null) return;

            int poolIndex = 0;
            foreach (var equip in equipList)
            {
                GameObject row;
                if (poolIndex < _rowPool.Count)
                {
                    row = _rowPool[poolIndex];
                    row.SetActive(true);
                }
                else
                {
                    if (_equipItemPrefab == null) break;
                    row = Instantiate(_equipItemPrefab, _equipListContent);
                    _rowPool.Add(row);
                }

                var rowView = row.GetComponent<EquipmentRowView>();
                if (rowView != null)
                    rowView.Bind(equip, OnRowSelected);

                poolIndex++;
            }
        }

        #endregion

        #region Private Methods

        private void OnEnhanceButton()
        {
            if (string.IsNullOrEmpty(_selectedEquipId)) return;
            if (!EquipmentManager.HasInstance) return;

            EquipmentManager.Instance.EnhanceEquipment(_selectedEquipId);
        }

        private void OnMergeButton()
        {
            if (string.IsNullOrEmpty(_selectedEquipId)) return;
            if (!EquipmentManager.HasInstance) return;

            EquipmentManager.Instance.MergeEquipment(_selectedEquipId);
        }

        private void OnDecomposeButton()
        {
            if (string.IsNullOrEmpty(_selectedEquipId)) return;
            if (!EquipmentManager.HasInstance) return;

            EquipmentManager.Instance.DecomposeEquipment(_selectedEquipId);
            _selectedEquipId = null;
            RefreshSelectedPanel();
        }

        private void OnRowSelected(string equipId)
        {
            _selectedEquipId = equipId;
            RefreshSelectedPanel();
        }

        private void RefreshSelectedPanel()
        {
            bool hasSelection = !string.IsNullOrEmpty(_selectedEquipId);

            _enhanceButton?.gameObject.SetActive(hasSelection);
            _mergeButton?.gameObject.SetActive(hasSelection);
            _decomposeButton?.gameObject.SetActive(hasSelection);

            if (_selectedEquipName != null)
                _selectedEquipName.text = hasSelection ? _selectedEquipId : string.Empty;

            if (_selectedEquipStats != null)
                _selectedEquipStats.text = string.Empty;
        }

        private void OnEquipmentChanged(object data)
        {
            RefreshEquipmentList();
        }

        #endregion
    }

    /// <summary>
    /// View component for a single equipment row in the scroll list.
    /// Attach to the equipment item prefab.
    /// </summary>
    public class EquipmentRowView : MonoBehaviour
    {
        [SerializeField] private TextMeshProUGUI _nameText;
        [SerializeField] private TextMeshProUGUI _levelText;
        [SerializeField] private Button          _selectButton;

        private System.Action<string> _onSelected;
        private string _equipId;

        /// <summary>
        /// Binds equipment data and selection callback to this row.
        /// </summary>
        public void Bind(UserEquipmentData equip, System.Action<string> onSelected)
        {
            _equipId    = equip?.equipId;
            _onSelected = onSelected;

            if (_nameText  != null) _nameText.text  = equip?.equipId ?? string.Empty;
            if (_levelText != null) _levelText.text = $"+{equip?.level ?? 0}";

            _selectButton?.onClick.RemoveAllListeners();
            _selectButton?.onClick.AddListener(() => _onSelected?.Invoke(_equipId));
        }
    }

    /// <summary>
    /// Equipment runtime data model. Full definition lives in EquipmentManager.
    /// </summary>
    [System.Serializable]
    public class UserEquipmentData
    {
        public string equipId;
        public int    level;
        public string slotType;
        public int    grade;
    }
}
