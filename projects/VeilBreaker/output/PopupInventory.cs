using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using VeilBreaker.Core;
using VeilBreaker.UI;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Inventory popup with filter tabs. Displays all owned items using a pooled scroll list.
    /// Item rows are returned to ObjectPool and re-spawned on filter change or refresh.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// System: UI
    /// Phase: 3
    /// </remarks>
    public class PopupInventory : PopupBase
    {
        #region Fields

        [SerializeField] private ScrollRect _itemScrollView;
        [SerializeField] private Transform _itemContent;
        [SerializeField] private GameObject _itemPrefab;
        [SerializeField] private Toggle[] _filterToggles;
        [SerializeField] private Button _closeButton;

        private InventoryManager.ItemType _currentFilter = InventoryManager.ItemType.All;
        private readonly List<InventoryItemUI> _activeItems = new();

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            _closeButton?.onClick.AddListener(OnCloseClicked);

            if (_filterToggles != null)
            {
                for (int i = 0; i < _filterToggles.Length; i++)
                {
                    int filterIndex = i;
                    _filterToggles[i]?.onValueChanged.AddListener(on =>
                    {
                        if (on) OnFilterChanged(filterIndex);
                    });
                }
            }
        }

        private void OnDisable()
        {
            _closeButton?.onClick.RemoveListener(OnCloseClicked);
            if (_filterToggles != null)
                foreach (var t in _filterToggles)
                    t?.onValueChanged.RemoveAllListeners();
        }

        #endregion

        #region Public Methods (PopupBase override)

        /// <summary>
        /// Opens the inventory popup, defaulting to All filter.
        /// </summary>
        public override void Open(object data = null)
        {
            _currentFilter = InventoryManager.ItemType.All;
            if (_filterToggles?.Length > 0)
                _filterToggles[0].isOn = true;

            RefreshItemList();
        }

        /// <summary>
        /// Returns all active item rows to the pool on close.
        /// </summary>
        public override void Close()
        {
            ClearItemList();
        }

        /// <summary>
        /// Clears and re-populates the item list with the current filter.
        /// </summary>
        public void RefreshItemList()
        {
            if (!InventoryManager.HasInstance) return;

            List<InventoryManager.UserItemData> items =
                InventoryManager.Instance.GetItems(_currentFilter);

            ClearItemList();

            if (items == null) return;

            foreach (var itemData in items)
            {
                if (itemData == null) continue;

                InventoryItemUI row = SpawnItemRow();
                row?.SetItem(itemData, this);
            }

            // Reset scroll position to top
            if (_itemScrollView != null)
                _itemScrollView.verticalNormalizedPosition = 1f;
        }

        #endregion

        #region Private Methods

        private void OnFilterChanged(int filterIndex)
        {
            _currentFilter = (InventoryManager.ItemType)filterIndex;
            RefreshItemList();
        }

        private InventoryItemUI SpawnItemRow()
        {
            if (_itemContent == null || _itemPrefab == null) return null;

            GameObject go;
            if (ObjectPool.HasInstance)
            {
                go = ObjectPool.Instance.Spawn("InventoryItem", _itemContent.position, Quaternion.identity);
                if (go != null) go.transform.SetParent(_itemContent, false);
            }
            else
            {
                go = Object.Instantiate(_itemPrefab, _itemContent);
            }

            if (go == null) return null;

            var row = go.GetComponent<InventoryItemUI>() ?? go.AddComponent<InventoryItemUI>();
            _activeItems.Add(row);
            return row;
        }

        private void ClearItemList()
        {
            foreach (InventoryItemUI row in _activeItems)
            {
                if (row == null) continue;
                if (ObjectPool.HasInstance)
                    ObjectPool.Instance.Despawn(row.gameObject);
                else
                    Destroy(row.gameObject);
            }
            _activeItems.Clear();
        }

        private void OnCloseClicked()
        {
            CloseThis();
        }

        #endregion
    }

    /// <summary>
    /// A single item row in PopupInventory.
    /// User connects TextMeshProUGUI and Button fields via Inspector.
    /// </summary>
    public class InventoryItemUI : MonoBehaviour
    {
        #region Fields

        [SerializeField] private TextMeshProUGUI _itemNameText;
        [SerializeField] private TextMeshProUGUI _countText;
        [SerializeField] private Button _useButton;

        private InventoryManager.UserItemData _itemData;
        private PopupInventory _parentPopup;

        #endregion

        #region Public Methods

        /// <summary>
        /// Populates this row with item data.
        /// </summary>
        public void SetItem(InventoryManager.UserItemData itemData, PopupInventory parent)
        {
            _itemData = itemData;
            _parentPopup = parent;

            if (_itemNameText != null) _itemNameText.text = itemData?.itemId ?? "";
            if (_countText != null) _countText.text = $"x{itemData?.count ?? 0}";

            _useButton?.onClick.RemoveAllListeners();
            _useButton?.onClick.AddListener(OnUseClicked);

            if (_useButton != null)
                _useButton.interactable = (itemData?.count ?? 0) > 0;
        }

        #endregion

        #region Private Methods

        private void OnUseClicked()
        {
            if (_itemData == null || !InventoryManager.HasInstance) return;

            InventoryManager.Instance.UseItem(_itemData.itemId, 1);
            _parentPopup?.RefreshItemList();
        }

        #endregion
    }
}
