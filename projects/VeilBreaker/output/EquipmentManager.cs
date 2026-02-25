using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using VeilBreaker.Core;
using VeilBreaker.Data;
using VeilBreaker.Character;

namespace VeilBreaker.Inventory
{
    /// <summary>
    /// Equipment acquisition, enhancement, merge, decompose, and equip/unequip manager.
    /// Handles all equipment lifecycle operations.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 2
    /// </remarks>
    public class EquipmentManager : Singleton<EquipmentManager>
    {
        #region Fields

        private List<UserEquipData> _equipments = new();

        #endregion

        #region Public Methods - Init

        /// <summary>
        /// Load equipment data from SaveManager.
        /// </summary>
        public void Init()
        {
            var saved = SaveManager.Instance.Load<UserEquipCollection>("UserEquipments");
            _equipments = saved?.items ?? new List<UserEquipData>();
        }

        #endregion

        #region Public Methods - Queries

        /// <summary>
        /// Get all owned equipment.
        /// </summary>
        public List<UserEquipData> GetAllEquipments()
        {
            return _equipments;
        }

        /// <summary>
        /// Get equipment filtered by slot type.
        /// </summary>
        public List<UserEquipData> GetEquipmentsForSlot(GameConstants.EquipSlot slot)
        {
            return _equipments.Where(e =>
            {
                var chartData = DataManager.Instance.GetEquipmentData(e.equipId);
                return chartData != null && chartData.slot == slot;
            }).ToList();
        }

        /// <summary>
        /// Get a specific equipment by instanceId.
        /// </summary>
        public UserEquipData GetEquipment(string instanceId)
        {
            if (string.IsNullOrEmpty(instanceId)) return null;
            return _equipments.Find(e => e.instanceId == instanceId);
        }

        /// <summary>
        /// Get all equipment currently equipped on a hero.
        /// </summary>
        public List<UserEquipData> GetHeroEquipments(string heroId)
        {
            if (string.IsNullOrEmpty(heroId)) return new List<UserEquipData>();
            return _equipments.Where(e => e.ownerId == heroId).ToList();
        }

        #endregion

        #region Public Methods - Enhancement

        /// <summary>
        /// Enhance equipment by 1 level. Costs gold.
        /// Max level: GameConstants.Hero.MaxEquipmentLevel (15).
        /// </summary>
        /// <returns>True if enhancement succeeded.</returns>
        public bool EnhanceEquipment(string instanceId)
        {
            var equip = GetEquipment(instanceId);
            if (equip == null)
            {
                Debug.LogWarning($"[EquipmentManager] Equipment '{instanceId}' not found.");
                return false;
            }

            if (equip.level >= GameConstants.Hero.MaxEquipmentLevel)
            {
                Debug.Log("[EquipmentManager] Equipment already at max level.");
                return false;
            }

            long cost = CalculateEnhanceCost(equip.level, equip.grade);

            if (!CurrencyManager.Instance.SpendCurrency(GameConstants.CurrencyType.Gold, cost))
            {
                Debug.Log($"[EquipmentManager] Not enough gold for enhancement. Need: {cost}");
                return false;
            }

            equip.level += 1;
            SaveEquipments();

            EventManager.Publish(GameConstants.Events.OnEquipmentEnhanced, (equip.instanceId, equip.level));
            EventManager.Publish(GameConstants.Events.OnEquipmentChanged);

            return true;
        }

        #endregion

        #region Public Methods - Merge

        /// <summary>
        /// Merge 3 same-grade equipment into 1 higher-grade equipment.
        /// </summary>
        /// <returns>True if merge succeeded.</returns>
        public bool MergeEquipments(List<string> instanceIds)
        {
            if (instanceIds == null || instanceIds.Count != 3)
            {
                Debug.LogWarning("[EquipmentManager] Merge requires exactly 3 equipment instances.");
                return false;
            }

            var targets = new List<UserEquipData>();
            foreach (var id in instanceIds)
            {
                var equip = GetEquipment(id);
                if (equip == null)
                {
                    Debug.LogWarning($"[EquipmentManager] Equipment '{id}' not found for merge.");
                    return false;
                }
                if (!string.IsNullOrEmpty(equip.ownerId))
                {
                    Debug.LogWarning($"[EquipmentManager] Equipment '{id}' is equipped. Unequip first.");
                    return false;
                }
                targets.Add(equip);
            }

            // Validate same grade
            int baseGrade = targets[0].grade;
            if (targets.Any(t => t.grade != baseGrade))
            {
                Debug.LogWarning("[EquipmentManager] All equipment must be the same grade to merge.");
                return false;
            }

            // Remove the 3 source items
            foreach (var target in targets)
            {
                _equipments.Remove(target);
            }

            // Create new equipment with higher grade
            var sourceChart = DataManager.Instance.GetEquipmentData(targets[0].equipId);
            var newEquip = new UserEquipData
            {
                instanceId = Guid.NewGuid().ToString("N")[..8],
                equipId = targets[0].equipId,
                level = 1,
                grade = baseGrade + 1,
                ownerId = ""
            };

            _equipments.Add(newEquip);
            SaveEquipments();

            EventManager.Publish(GameConstants.Events.OnEquipmentChanged);

            return true;
        }

        #endregion

        #region Public Methods - Decompose

        /// <summary>
        /// Decompose equipment into enhancement materials.
        /// Equipment must not be equipped.
        /// </summary>
        public void DecomposeEquipment(string instanceId)
        {
            var equip = GetEquipment(instanceId);
            if (equip == null)
            {
                Debug.LogWarning($"[EquipmentManager] Equipment '{instanceId}' not found.");
                return;
            }

            if (!string.IsNullOrEmpty(equip.ownerId))
            {
                Debug.LogWarning($"[EquipmentManager] Equipment is equipped on hero '{equip.ownerId}'. Unequip first.");
                return;
            }

            int materialAmount = CalculateDecomposeReward(equip.grade, equip.level);
            _equipments.Remove(equip);
            SaveEquipments();

            // Return materials via currency (Gold) or InventoryManager
            CurrencyManager.Instance.AddCurrency(GameConstants.CurrencyType.Gold, materialAmount);

            EventManager.Publish(GameConstants.Events.OnEquipmentChanged);
        }

        #endregion

        #region Public Methods - Equip / Unequip

        /// <summary>
        /// Equip an item to a hero in the specified slot.
        /// Auto-unequips any existing item in that slot.
        /// </summary>
        /// <returns>True if equip succeeded.</returns>
        public bool EquipToHero(string instanceId, string heroId, GameConstants.EquipSlot slot)
        {
            var equip = GetEquipment(instanceId);
            if (equip == null) return false;

            var chartData = DataManager.Instance.GetEquipmentData(equip.equipId);
            if (chartData == null) return false;

            if (chartData.slot != slot)
            {
                Debug.LogWarning($"[EquipmentManager] Equipment slot mismatch. Expected: {chartData.slot}, Got: {slot}");
                return false;
            }

            // Unequip existing item in same slot
            UnequipFromHero(heroId, slot);

            // Unequip from previous owner if any
            if (!string.IsNullOrEmpty(equip.ownerId) && equip.ownerId != heroId)
            {
                equip.ownerId = "";
            }

            equip.ownerId = heroId;
            SaveEquipments();

            EventManager.Publish(GameConstants.Events.OnEquipmentChanged, heroId);

            return true;
        }

        /// <summary>
        /// Unequip an item from a hero's slot.
        /// </summary>
        public void UnequipFromHero(string heroId, GameConstants.EquipSlot slot)
        {
            if (string.IsNullOrEmpty(heroId)) return;

            var equipped = _equipments.Find(e =>
            {
                if (e.ownerId != heroId) return false;
                var chart = DataManager.Instance.GetEquipmentData(e.equipId);
                return chart != null && chart.slot == slot;
            });

            if (equipped != null)
            {
                equipped.ownerId = "";
                SaveEquipments();
            }
        }

        #endregion

        #region Public Methods - Equipment Creation

        /// <summary>
        /// Create a new equipment instance from a chart equipId.
        /// Called by gacha, dungeon rewards, etc.
        /// </summary>
        public UserEquipData CreateEquipment(string equipId)
        {
            var chartData = DataManager.Instance.GetEquipmentData(equipId);
            if (chartData == null)
            {
                Debug.LogWarning($"[EquipmentManager] Chart data for '{equipId}' not found.");
                return null;
            }

            var newEquip = new UserEquipData
            {
                instanceId = Guid.NewGuid().ToString("N")[..8],
                equipId = equipId,
                level = 1,
                grade = chartData.grade,
                ownerId = ""
            };

            _equipments.Add(newEquip);
            SaveEquipments();

            return newEquip;
        }

        #endregion

        #region Private Methods

        private void SaveEquipments()
        {
            if (!SaveManager.HasInstance) return;
            SaveManager.Instance.Save("UserEquipments", new UserEquipCollection { items = _equipments });
        }

        private long CalculateEnhanceCost(int currentLevel, int grade)
        {
            return (long)(50 * (currentLevel + 1) * (1f + grade * 0.5f));
        }

        private int CalculateDecomposeReward(int grade, int level)
        {
            return (grade + 1) * 100 + level * 50;
        }

        #endregion
    }

    #region Data Models

    /// <summary>
    /// User-owned equipment instance.
    /// </summary>
    [Serializable]
    public class UserEquipData
    {
        public string instanceId;
        public string equipId;
        public int level;
        public int grade;
        public string ownerId;
    }

    /// <summary>
    /// Serializable collection wrapper for equipment list.
    /// </summary>
    [Serializable]
    public class UserEquipCollection
    {
        public List<UserEquipData> items = new();
    }

    #endregion
}
