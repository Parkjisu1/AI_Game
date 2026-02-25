using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Economy;

namespace VeilBreaker.Inventory
{
    /// <summary>
    /// Manages the player's consumable item inventory.
    /// Handles item storage, retrieval, usage, and sorting.
    /// Equipment items are managed separately by EquipmentManager.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 2
    /// System: Inventory
    /// </remarks>
    public class InventoryManager : Singleton<InventoryManager>
    {
        #region Enums

        /// <summary>
        /// Item category types for filtering.
        /// </summary>
        public enum ItemType
        {
            All,
            Consumable,
            Material,
            Currency,
            Special
        }

        /// <summary>
        /// Sort criteria for item listing.
        /// </summary>
        public enum SortType
        {
            Default,
            Grade,
            Name,
            Count
        }

        #endregion

        #region Data Structures

        /// <summary>
        /// Represents a stack of items in the inventory.
        /// </summary>
        [System.Serializable]
        public class UserItemData
        {
            public string itemId;
            public int count;
            public ItemType itemType;
            public int grade;
        }

        #endregion

        #region Fields

        // itemId → count mapping for fast lookups
        private Dictionary<string, int> _items = new();

        // Cached metadata: itemId → UserItemData (type/grade from DataManager)
        private Dictionary<string, UserItemData> _itemMeta = new();

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            EventManager.Subscribe(GameConstants.Events.OnDataLoaded, OnDataLoaded);
        }

        protected override void OnDestroy()
        {
            EventManager.Unsubscribe(GameConstants.Events.OnDataLoaded, OnDataLoaded);
            base.OnDestroy();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Returns all items matching the given filter type.
        /// Pass ItemType.All to retrieve every item.
        /// </summary>
        /// <param name="filter">Filter by item category. Default is All.</param>
        public List<UserItemData> GetItems(ItemType filter = ItemType.All)
        {
            if (filter == ItemType.All)
            {
                return BuildUserItemList(_items.Keys);
            }

            var filtered = _items.Keys.Where(id => GetItemType(id) == filter);
            return BuildUserItemList(filtered);
        }

        /// <summary>
        /// Adds the given count of an item to inventory.
        /// Creates a new entry if the item does not exist yet.
        /// </summary>
        /// <param name="itemId">Identifier of the item to add.</param>
        /// <param name="count">Number of items to add (must be > 0).</param>
        public void AddItem(string itemId, int count)
        {
            if (string.IsNullOrEmpty(itemId) || count <= 0)
            {
                Debug.LogWarning($"[InventoryManager] AddItem invalid args: itemId={itemId}, count={count}");
                return;
            }

            if (_items.ContainsKey(itemId))
                _items[itemId] += count;
            else
                _items[itemId] = count;

            SaveInventory();
        }

        /// <summary>
        /// Uses (consumes) the specified count of the given item.
        /// Returns false if the item count is insufficient.
        /// Applies item effects after consumption.
        /// </summary>
        /// <param name="itemId">Identifier of the item to use.</param>
        /// <param name="count">Number of items to consume (must be > 0).</param>
        /// <returns>True if successful; false if insufficient stock.</returns>
        public bool UseItem(string itemId, int count)
        {
            if (string.IsNullOrEmpty(itemId) || count <= 0)
            {
                Debug.LogWarning($"[InventoryManager] UseItem invalid args: itemId={itemId}, count={count}");
                return false;
            }

            if (GetItemCount(itemId) < count)
            {
                Debug.Log($"[InventoryManager] Insufficient item '{itemId}': need {count}, have {GetItemCount(itemId)}");
                return false;
            }

            _items[itemId] -= count;
            if (_items[itemId] <= 0)
                _items.Remove(itemId);

            ApplyItemEffect(itemId, count);
            SaveInventory();
            return true;
        }

        /// <summary>
        /// Returns the current stack count of the given item. Returns 0 if not in inventory.
        /// </summary>
        /// <param name="itemId">Identifier of the item to query.</param>
        public int GetItemCount(string itemId)
        {
            if (string.IsNullOrEmpty(itemId)) return 0;
            return _items.TryGetValue(itemId, out var c) ? c : 0;
        }

        /// <summary>
        /// Returns all items sorted by the specified sort criterion.
        /// </summary>
        /// <param name="sort">Sort order to apply.</param>
        public List<UserItemData> GetSortedItems(SortType sort)
        {
            var all = GetItems();

            return sort switch
            {
                SortType.Grade => all.OrderByDescending(x => x.grade).ToList(),
                SortType.Name  => all.OrderBy(x => x.itemId).ToList(),
                SortType.Count => all.OrderByDescending(x => x.count).ToList(),
                _              => all
            };
        }

        #endregion

        #region Private Methods

        private void OnDataLoaded(object data)
        {
            LoadFromDataManager();
        }

        private void LoadFromDataManager()
        {
            if (!DataManager.HasInstance)
            {
                Debug.LogWarning("[InventoryManager] DataManager not available. Starting with empty inventory.");
                return;
            }

            // Load serialized item dictionary from DataManager's user data
            var userItems = DataManager.Instance.GetUserItems();
            if (userItems == null) return;

            _items.Clear();
            _itemMeta.Clear();

            foreach (var entry in userItems)
            {
                _items[entry.itemId] = entry.count;
                _itemMeta[entry.itemId] = entry;
            }

            Debug.Log($"[InventoryManager] Loaded {_items.Count} item types from DataManager.");
        }

        private void SaveInventory()
        {
            if (!DataManager.HasInstance) return;

            var list = BuildUserItemList(_items.Keys);
            DataManager.Instance.UpdateUserItems(list);
        }

        private void ApplyItemEffect(string itemId, int usedCount)
        {
            if (!DataManager.HasInstance) return;

            var itemData = DataManager.Instance.GetItemData(itemId);
            if (itemData == null) return;

            switch (itemData.effectType)
            {
                case "gold_pouch":
                    if (CurrencyManager.HasInstance)
                        CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.Gold, (long)(itemData.effectValue * usedCount));
                    break;

                case "gem_pouch":
                    if (CurrencyManager.HasInstance)
                        CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.Gold, (long)(itemData.effectValue * usedCount));
                    break;

                case "stage_ticket":
                    if (CurrencyManager.HasInstance)
                        CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.StageTicket, usedCount);
                    break;

                case "dungeon_ticket":
                    if (CurrencyManager.HasInstance)
                        CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.DungeonTicket, usedCount);
                    break;

                default:
                    Debug.LogWarning($"[InventoryManager] Unknown effectType '{itemData.effectType}' for item '{itemId}'");
                    break;
            }
        }

        private ItemType GetItemType(string itemId)
        {
            if (_itemMeta.TryGetValue(itemId, out var meta))
                return meta.itemType;

            if (!DataManager.HasInstance) return ItemType.Consumable;

            var itemData = DataManager.Instance.GetItemData(itemId);
            if (itemData == null) return ItemType.Consumable;

            var type = ParseItemType(itemData.itemType);
            if (!_itemMeta.ContainsKey(itemId))
            {
                _itemMeta[itemId] = new UserItemData
                {
                    itemId   = itemId,
                    count    = GetItemCount(itemId),
                    itemType = type,
                    grade    = itemData.grade
                };
            }
            return type;
        }

        private static ItemType ParseItemType(string raw)
        {
            return raw?.ToLower() switch
            {
                "consumable" => ItemType.Consumable,
                "material"   => ItemType.Material,
                "currency"   => ItemType.Currency,
                "special"    => ItemType.Special,
                _            => ItemType.Consumable
            };
        }

        private List<UserItemData> BuildUserItemList(IEnumerable<string> keys)
        {
            var result = new List<UserItemData>();
            foreach (var id in keys)
            {
                if (!_items.TryGetValue(id, out var cnt)) continue;

                if (_itemMeta.TryGetValue(id, out var meta))
                {
                    meta.count = cnt;
                    result.Add(meta);
                }
                else
                {
                    result.Add(new UserItemData { itemId = id, count = cnt, itemType = ItemType.Consumable, grade = 1 });
                }
            }
            return result;
        }

        #endregion
    }

    /// <summary>
    /// Item chart data model. Full definition lives in DataManager.
    /// </summary>
    [System.Serializable]
    public class ItemData
    {
        public string itemId;
        public string itemType;
        public int grade;
        public string effectType;
        public float effectValue;
    }
}
