using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.Data
{
    /// <summary>
    /// Central data manager with dual-structure: Chart (read-only tables) + User (save/load).
    /// Chart data is loaded once from Resources JSON. User data syncs with SaveManager.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 1
    /// </remarks>
    public class DataManager : Singleton<DataManager>
    {
        #region Fields

        private bool _isReady;

        // Chart caches (read-only, loaded from Resources/Data/)
        private Dictionary<string, HeroData> _heroCache = new();
        private Dictionary<string, StageData> _stageCache = new();
        private Dictionary<string, EnemyData> _enemyCache = new();
        private Dictionary<string, EquipmentData> _equipmentCache = new();
        private Dictionary<string, SkillData> _skillCache = new();
        private Dictionary<string, GachaData> _gachaCache = new();
        private Dictionary<string, QuestData> _questCache = new();
        private Dictionary<string, DungeonData> _dungeonCache = new();
        private Dictionary<int, TowerData> _towerCache = new();
        private Dictionary<string, ItemData> _itemCache = new();

        // User data caches (read-write, synced with SaveManager)
        private UserInfo _userInfo;
        private UserCurrency _userCurrency;
        private Dictionary<string, UserHeroData> _userHeroCache = new();
        private UserStageData _userStageData;
        private UserQuestData _userQuestData;
        private UserTowerData _userTowerData;
        private UserDungeonData _userDungeonData;
        private UserSettingsData _userSettingsData;
        private UserOfflineData _userOfflineData;
        private UserGachaData _userGachaData;
        private UserInventoryData _userInventoryData;
        private UserSkillSaveData _userSkillData;
        private UserQuestSaveData _userQuestSaveData;
        private UserDungeonSaveData _userDungeonSaveData;

        #endregion

        #region Properties

        /// <summary>
        /// Returns true when all chart and user data has been loaded.
        /// </summary>
        public bool IsReady => _isReady;

        #endregion

        #region Public Methods - Init

        /// <summary>
        /// Initialize all chart data from Resources and user data from SaveManager.
        /// Must be called after SaveManager.Init().
        /// </summary>
        public void Init()
        {
            _isReady = false;

            LoadAllCharts();
            LoadAllUserData();

            _isReady = true;
        }

        #endregion

        #region Public Methods - Chart Getters

        /// <summary>
        /// Get hero chart data by heroId.
        /// </summary>
        public HeroData GetHeroData(string heroId)
        {
            if (string.IsNullOrEmpty(heroId)) return null;
            _heroCache.TryGetValue(heroId, out var data);
            return data;
        }

        /// <summary>
        /// Get all hero chart data.
        /// </summary>
        public IReadOnlyDictionary<string, HeroData> GetAllHeroData() => _heroCache;

        /// <summary>
        /// Get stage chart data by stageId.
        /// </summary>
        public StageData GetStageData(string stageId)
        {
            if (string.IsNullOrEmpty(stageId)) return null;
            _stageCache.TryGetValue(stageId, out var data);
            return data;
        }

        /// <summary>
        /// Get enemy chart data by enemyId.
        /// </summary>
        public EnemyData GetEnemyData(string enemyId)
        {
            if (string.IsNullOrEmpty(enemyId)) return null;
            _enemyCache.TryGetValue(enemyId, out var data);
            return data;
        }

        /// <summary>
        /// Get equipment chart data by equipId.
        /// </summary>
        public EquipmentData GetEquipmentData(string equipId)
        {
            if (string.IsNullOrEmpty(equipId)) return null;
            _equipmentCache.TryGetValue(equipId, out var data);
            return data;
        }

        /// <summary>
        /// Get skill chart data by skillId.
        /// </summary>
        public SkillData GetSkillData(string skillId)
        {
            if (string.IsNullOrEmpty(skillId)) return null;
            _skillCache.TryGetValue(skillId, out var data);
            return data;
        }

        /// <summary>
        /// Get gacha banner data by bannerId.
        /// </summary>
        public GachaData GetGachaData(string bannerId)
        {
            if (string.IsNullOrEmpty(bannerId)) return null;
            _gachaCache.TryGetValue(bannerId, out var data);
            return data;
        }

        /// <summary>
        /// Get quest chart data by questId.
        /// </summary>
        public QuestData GetQuestData(string questId)
        {
            if (string.IsNullOrEmpty(questId)) return null;
            _questCache.TryGetValue(questId, out var data);
            return data;
        }

        /// <summary>
        /// Get dungeon chart data by dungeonId.
        /// </summary>
        public DungeonData GetDungeonData(string dungeonId)
        {
            if (string.IsNullOrEmpty(dungeonId)) return null;
            _dungeonCache.TryGetValue(dungeonId, out var data);
            return data;
        }

        /// <summary>
        /// Get tower chart data by floor number.
        /// </summary>
        public TowerData GetTowerData(int floor)
        {
            _towerCache.TryGetValue(floor, out var data);
            return data;
        }

        /// <summary>
        /// Get item chart data by itemId.
        /// </summary>
        public ItemData GetItemData(string itemId)
        {
            if (string.IsNullOrEmpty(itemId)) return null;
            _itemCache.TryGetValue(itemId, out var data);
            return data;
        }

        /// <summary>
        /// Get all dungeon chart data as a list.
        /// </summary>
        public List<DungeonData> GetDungeonList()
        {
            return _dungeonCache.Values.ToList();
        }

        /// <summary>
        /// Get all skill chart data as a list.
        /// </summary>
        public List<SkillData> GetSkillList()
        {
            return _skillCache.Values.ToList();
        }

        /// <summary>
        /// Get all stage chart data as a list.
        /// </summary>
        public List<StageData> GetStageList()
        {
            return _stageCache.Values.ToList();
        }

        /// <summary>
        /// Get all quest chart data as a list.
        /// </summary>
        public List<QuestData> GetQuestList()
        {
            return _questCache.Values.ToList();
        }

        /// <summary>
        /// Get all tower chart data as a list.
        /// </summary>
        public List<TowerData> GetTowerList()
        {
            return _towerCache.Values.ToList();
        }

        #endregion

        #region Public Methods - User Data Getters

        /// <summary>
        /// Get user info (level, exp, nickname etc).
        /// </summary>
        public UserInfo GetUserInfo() => _userInfo;

        /// <summary>
        /// Get user currency data.
        /// </summary>
        public UserCurrency GetUserCurrency() => _userCurrency;

        /// <summary>
        /// Get user hero data by heroId.
        /// </summary>
        public UserHeroData GetUserHeroData(string heroId)
        {
            if (string.IsNullOrEmpty(heroId)) return null;
            _userHeroCache.TryGetValue(heroId, out var data);
            return data;
        }

        /// <summary>
        /// Get all user-owned heroes.
        /// </summary>
        public IReadOnlyDictionary<string, UserHeroData> GetAllUserHeroes() => _userHeroCache;

        /// <summary>
        /// Get user stage progress data.
        /// </summary>
        public UserStageData GetUserStageData() => _userStageData;

        /// <summary>
        /// Get user settings data.
        /// </summary>
        public UserSettingsData GetUserSettingsData() => _userSettingsData;

        /// <summary>
        /// Get user offline progress data.
        /// </summary>
        public UserOfflineData GetUserOfflineData() => _userOfflineData;

        /// <summary>
        /// Get user gacha pity data.
        /// </summary>
        public UserGachaData GetUserGachaData() => _userGachaData;

        /// <summary>
        /// Get user inventory data.
        /// </summary>
        public UserInventoryData GetUserInventoryData() => _userInventoryData;

        /// <summary>
        /// Get user inventory items as a list (convenience for InventoryManager).
        /// </summary>
        public List<UserInventoryEntry> GetUserItems()
        {
            return _userInventoryData?.items ?? new List<UserInventoryEntry>();
        }

        /// <summary>
        /// Get user quest save data (progress tracking).
        /// </summary>
        public UserQuestSaveData GetUserQuestSaveData() => _userQuestSaveData;

        /// <summary>
        /// Get user dungeon save data (entry tracking).
        /// </summary>
        public UserDungeonSaveData GetUserDungeonSaveData() => _userDungeonSaveData;

        /// <summary>
        /// Get user skill save data (equipped skills, cooldowns).
        /// </summary>
        public UserSkillSaveData GetUserSkillData() => _userSkillData;

        /// <summary>
        /// Get user tower progress data.
        /// </summary>
        public UserTowerData GetUserTowerData() => _userTowerData;

        #endregion

        #region Public Methods - User Data Setters

        /// <summary>
        /// Update user info and persist to SaveManager.
        /// </summary>
        public void UpdateUserInfo(UserInfo info)
        {
            _userInfo = info;
            SaveUserData(GameConstants.Save.UserInfoKey, _userInfo);
        }

        /// <summary>
        /// Update user currency and persist to SaveManager. Publishes OnCurrencyChanged.
        /// </summary>
        public void UpdateUserCurrency(UserCurrency currency)
        {
            _userCurrency = currency;
            SaveUserData(GameConstants.Save.UserCurrencyKey, _userCurrency);
            EventManager.Publish(GameConstants.Events.OnCurrencyChanged);
        }

        /// <summary>
        /// Update a specific user hero and persist.
        /// </summary>
        public void UpdateUserHero(string heroId, UserHeroData heroData)
        {
            if (string.IsNullOrEmpty(heroId)) return;
            _userHeroCache[heroId] = heroData;
            SaveUserData(GameConstants.Save.UserHeroesKey, new UserHeroCollection(_userHeroCache));
        }

        /// <summary>
        /// Update user stage progress and persist.
        /// </summary>
        public void UpdateUserStage(UserStageData stageData)
        {
            _userStageData = stageData;
            SaveUserData(GameConstants.Save.UserStageKey, _userStageData);
        }

        /// <summary>
        /// Update user settings and persist.
        /// </summary>
        public void UpdateUserSettings(UserSettingsData settings)
        {
            _userSettingsData = settings;
            SaveUserData(GameConstants.Save.SettingsKey, _userSettingsData);
        }

        /// <summary>
        /// Update user offline data and persist.
        /// </summary>
        public void UpdateUserOffline(UserOfflineData offlineData)
        {
            _userOfflineData = offlineData;
            SaveUserData("UserOffline", _userOfflineData);
        }

        /// <summary>
        /// Update user gacha data and persist.
        /// </summary>
        public void UpdateUserGacha(UserGachaData gachaData)
        {
            _userGachaData = gachaData;
            SaveUserData("UserGacha", _userGachaData);
        }

        /// <summary>
        /// Update user inventory data and persist.
        /// </summary>
        public void UpdateUserInventory(UserInventoryData inventoryData)
        {
            _userInventoryData = inventoryData;
            SaveUserData("UserInventory", _userInventoryData);
        }

        /// <summary>
        /// Update user items list and persist (convenience for InventoryManager).
        /// </summary>
        public void UpdateUserItems(List<UserInventoryEntry> items)
        {
            if (_userInventoryData == null)
                _userInventoryData = new UserInventoryData();
            _userInventoryData.items = items ?? new List<UserInventoryEntry>();
            SaveUserData("UserInventory", _userInventoryData);
        }

        /// <summary>
        /// Update user quest save data and persist.
        /// </summary>
        public void UpdateUserQuestSaveData(UserQuestSaveData questSaveData)
        {
            _userQuestSaveData = questSaveData;
            SaveUserData("UserQuestSave", _userQuestSaveData);
        }

        /// <summary>
        /// Update user dungeon save data and persist.
        /// </summary>
        public void UpdateUserDungeonSaveData(UserDungeonSaveData dungeonSaveData)
        {
            _userDungeonSaveData = dungeonSaveData;
            SaveUserData("UserDungeonSave", _userDungeonSaveData);
        }

        /// <summary>
        /// Update user skill save data and persist.
        /// </summary>
        public void UpdateUserSkillData(UserSkillSaveData skillData)
        {
            _userSkillData = skillData;
            SaveUserData("UserSkillSave", _userSkillData);
        }

        /// <summary>
        /// Update user stage data and persist (alias for UpdateUserStage).
        /// </summary>
        public void UpdateUserStageData(UserStageData stageData)
        {
            UpdateUserStage(stageData);
        }

        /// <summary>
        /// Update user tower data and persist.
        /// </summary>
        public void UpdateUserTowerData(UserTowerData towerData)
        {
            _userTowerData = towerData;
            SaveUserData("UserTower", _userTowerData);
        }

        /// <summary>
        /// Update user gacha save data and persist (alias for UpdateUserGacha).
        /// </summary>
        public void UpdateUserGachaData(UserGachaData gachaData)
        {
            UpdateUserGacha(gachaData);
        }

        /// <summary>
        /// Update user offline data and persist (alias for UpdateUserOffline).
        /// </summary>
        public void UpdateUserOfflineData(UserOfflineData offlineData)
        {
            UpdateUserOffline(offlineData);
        }

        #endregion

        #region Private Methods - Chart Loading

        private void LoadAllCharts()
        {
            LoadChart<HeroDataCollection>("HeroTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.heroId))
                        _heroCache[item.heroId] = item;
                }
            });

            LoadChart<StageDataCollection>("StageTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.stageId))
                        _stageCache[item.stageId] = item;
                }
            });

            LoadChart<EnemyDataCollection>("EnemyTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.enemyId))
                        _enemyCache[item.enemyId] = item;
                }
            });

            LoadChart<EquipmentDataCollection>("EquipmentTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.equipId))
                        _equipmentCache[item.equipId] = item;
                }
            });

            LoadChart<SkillDataCollection>("SkillTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.skillId))
                        _skillCache[item.skillId] = item;
                }
            });

            LoadChart<GachaDataCollection>("GachaTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.bannerId))
                        _gachaCache[item.bannerId] = item;
                }
            });

            LoadChart<QuestDataCollection>("QuestTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.questId))
                        _questCache[item.questId] = item;
                }
            });

            LoadChart<DungeonDataCollection>("DungeonTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.dungeonId))
                        _dungeonCache[item.dungeonId] = item;
                }
            });

            LoadChart<TowerDataCollection>("TowerTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    _towerCache[item.floor] = item;
                }
            });

            LoadChart<ItemDataCollection>("ItemTable", col =>
            {
                if (col?.items == null) return;
                foreach (var item in col.items)
                {
                    if (!string.IsNullOrEmpty(item.itemId))
                        _itemCache[item.itemId] = item;
                }
            });
        }

        private void LoadChart<T>(string tableName, Action<T> onLoaded)
        {
            var textAsset = Resources.Load<TextAsset>($"Data/{tableName}");

            if (textAsset == null)
            {
                Debug.LogWarning($"[DataManager] Chart '{tableName}' not found in Resources/Data/.");
                return;
            }

            try
            {
                var data = JsonUtility.FromJson<T>(textAsset.text);
                onLoaded?.Invoke(data);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[DataManager] Failed to parse chart '{tableName}': {ex.Message}");
            }
        }

        #endregion

        #region Private Methods - User Data

        private void LoadAllUserData()
        {
            if (!SaveManager.HasInstance)
            {
                Debug.LogError("[DataManager] SaveManager not initialized. Call SaveManager.Init() first.");
                return;
            }

            _userInfo = SaveManager.Instance.Load<UserInfo>(GameConstants.Save.UserInfoKey);
            _userCurrency = SaveManager.Instance.Load<UserCurrency>(GameConstants.Save.UserCurrencyKey);
            _userStageData = SaveManager.Instance.Load<UserStageData>(GameConstants.Save.UserStageKey);
            _userSettingsData = SaveManager.Instance.Load<UserSettingsData>(GameConstants.Save.SettingsKey);
            _userOfflineData = SaveManager.Instance.Load<UserOfflineData>("UserOffline");
            _userGachaData = SaveManager.Instance.Load<UserGachaData>("UserGacha");
            _userInventoryData = SaveManager.Instance.Load<UserInventoryData>("UserInventory");
            _userSkillData = SaveManager.Instance.Load<UserSkillSaveData>("UserSkillSave");
            _userQuestSaveData = SaveManager.Instance.Load<UserQuestSaveData>("UserQuestSave");
            _userDungeonSaveData = SaveManager.Instance.Load<UserDungeonSaveData>("UserDungeonSave");
            _userTowerData = SaveManager.Instance.Load<UserTowerData>("UserTower");

            var heroCollection = SaveManager.Instance.Load<UserHeroCollection>(GameConstants.Save.UserHeroesKey);
            _userHeroCache = heroCollection?.ToDictionary() ?? new Dictionary<string, UserHeroData>();
        }

        private void SaveUserData<T>(string key, T data)
        {
            if (!SaveManager.HasInstance) return;

            SaveManager.Instance.Save(key, data);
        }

        #endregion
    }

    #region Chart Data Models

    /// <summary>
    /// Hero chart data from HeroTable.json.
    /// </summary>
    [Serializable]
    public class HeroData
    {
        public string heroId;
        public string name;
        public int grade;
        public GameConstants.AttributeType attribute;
        public string role;
        public float baseAtk;
        public float baseDef;
        public float baseHp;
        public float growthAtk;
        public float growthDef;
        public float growthHp;
        public List<string> skillIds;
    }

    [Serializable]
    public class HeroDataCollection
    {
        public List<HeroData> items;
    }

    /// <summary>
    /// Skill chart data from SkillTable.json.
    /// </summary>
    [Serializable]
    public class SkillData
    {
        public string skillId;
        public string name;
        public string description;
        public string type;
        public float cooldown;
        public float damage;
        public string effect;
        public string targetType;
    }

    [Serializable]
    public class SkillDataCollection
    {
        public List<SkillData> items;
    }

    /// <summary>
    /// Stage chart data from StageTable.json.
    /// </summary>
    [Serializable]
    public class StageData
    {
        public string stageId;
        public int chapter;
        public int stageNum;
        public List<string> enemyIds;
        public int enemyCount;
        public string bossId;
        public double goldReward;
        public double expReward;
        public int difficulty;
    }

    [Serializable]
    public class StageDataCollection
    {
        public List<StageData> items;
    }

    /// <summary>
    /// Enemy chart data from EnemyTable.json.
    /// </summary>
    [Serializable]
    public class EnemyData
    {
        public string enemyId;
        public string name;
        public float hp;
        public float atk;
        public float def;
        public float moveSpeed;
        public float attackRange;
        public float attackSpeed;
        public List<string> dropItems;
    }

    [Serializable]
    public class EnemyDataCollection
    {
        public List<EnemyData> items;
    }

    /// <summary>
    /// Equipment chart data from EquipmentTable.json.
    /// </summary>
    [Serializable]
    public class EquipmentData
    {
        public string equipId;
        public string name;
        public GameConstants.EquipSlot slot;
        public int grade;
        public float baseAtk;
        public float baseDef;
        public float baseHp;
        public List<string> skills;
    }

    [Serializable]
    public class EquipmentDataCollection
    {
        public List<EquipmentData> items;
    }

    /// <summary>
    /// Gacha banner data from GachaTable.json.
    /// </summary>
    [Serializable]
    public class GachaData
    {
        public string bannerId;
        public string name;
        public string type;
        public List<float> rates;
        public int pity;
        public List<string> pool;
    }

    [Serializable]
    public class GachaDataCollection
    {
        public List<GachaData> items;
    }

    /// <summary>
    /// Quest chart data from QuestTable.json.
    /// </summary>
    [Serializable]
    public class QuestData
    {
        public string questId;
        public string type;
        public string title;
        public string description;
        public string condition;
        public int targetCount;
        public List<string> rewards;
    }

    [Serializable]
    public class QuestDataCollection
    {
        public List<QuestData> items;
    }

    /// <summary>
    /// Dungeon chart data from DungeonTable.json.
    /// </summary>
    [Serializable]
    public class DungeonData
    {
        public string dungeonId;
        public string name;
        public string type;
        public int difficulty;
        public int energyCost;
        public List<string> rewards;
    }

    [Serializable]
    public class DungeonDataCollection
    {
        public List<DungeonData> items;
    }

    /// <summary>
    /// Tower chart data from TowerTable.json.
    /// </summary>
    [Serializable]
    public class TowerData
    {
        public int floor;
        public List<string> enemyIds;
        public float enemyMultiplier;
        public List<string> rewards;
    }

    [Serializable]
    public class TowerDataCollection
    {
        public List<TowerData> items;
    }

    #endregion

    #region User Data Models

    /// <summary>
    /// User profile information.
    /// </summary>
    [Serializable]
    public class UserInfo
    {
        public string userId;
        public string nickname;
        public int level;
        public double exp;
        public string createdAt;
        public string lastLoginAt;

        public UserInfo()
        {
            userId = Guid.NewGuid().ToString("N")[..8];
            nickname = "Player";
            level = 1;
            exp = 0;
            createdAt = DateTime.UtcNow.ToString("o");
            lastLoginAt = DateTime.UtcNow.ToString("o");
        }
    }

    /// <summary>
    /// User currency balances.
    /// </summary>
    [Serializable]
    public class UserCurrency
    {
        public double gold;
        public int gem;
        public int soulStone;
        public int skillStone;
        public int dungeonKey;

        public UserCurrency()
        {
            gold = 0;
            gem = 0;
            soulStone = 0;
            skillStone = 0;
            dungeonKey = 3;
        }
    }

    /// <summary>
    /// User-owned hero instance data.
    /// </summary>
    [Serializable]
    public class UserHeroData
    {
        public string heroId;
        public int level;
        public int stars;
        public double exp;
        public List<string> equippedItems;
        public List<int> skills;

        public UserHeroData()
        {
            heroId = "";
            level = 1;
            stars = 1;
            exp = 0;
            equippedItems = new List<string>();
            skills = new List<int>();
        }
    }

    /// <summary>
    /// Serializable wrapper for the user hero dictionary.
    /// </summary>
    [Serializable]
    public class UserHeroCollection
    {
        public List<UserHeroData> heroes = new();

        public UserHeroCollection() { }

        public UserHeroCollection(Dictionary<string, UserHeroData> dict)
        {
            foreach (var kvp in dict)
            {
                heroes.Add(kvp.Value);
            }
        }

        public Dictionary<string, UserHeroData> ToDictionary()
        {
            var dict = new Dictionary<string, UserHeroData>();
            if (heroes == null) return dict;

            foreach (var hero in heroes)
            {
                if (!string.IsNullOrEmpty(hero?.heroId))
                {
                    dict[hero.heroId] = hero;
                }
            }
            return dict;
        }
    }

    /// <summary>
    /// User stage progress data.
    /// </summary>
    [Serializable]
    public class UserStageData
    {
        public int currentChapter;
        public int currentStage;
        public int maxClearedStage;
        public int difficulty;
        public int stars;

        public UserStageData()
        {
            currentChapter = 1;
            currentStage = 1;
            maxClearedStage = 0;
            difficulty = 1;
            stars = 0;
        }
    }

    /// <summary>
    /// User quest progress data.
    /// </summary>
    [Serializable]
    public class UserQuestData
    {
        public List<UserQuestEntry> quests = new();
    }

    [Serializable]
    public class UserQuestEntry
    {
        public string questId;
        public int progress;
        public bool isComplete;
        public bool isClaimed;
        public string refreshedAt;
    }

    /// <summary>
    /// User tower progress data.
    /// </summary>
    [Serializable]
    public class UserTowerData
    {
        public int maxFloor;
        public int currentFloor;
        public string lastAttemptAt;

        public UserTowerData()
        {
            maxFloor = 0;
            currentFloor = 1;
            lastAttemptAt = "";
        }
    }

    /// <summary>
    /// User dungeon progress data.
    /// </summary>
    [Serializable]
    public class UserDungeonData
    {
        public List<UserDungeonEntry> dungeons = new();
    }

    [Serializable]
    public class UserDungeonEntry
    {
        public string dungeonId;
        public int remainEntries;
        public string lastResetAt;
        public int bestRecord;
    }

    /// <summary>
    /// User settings data.
    /// </summary>
    [Serializable]
    public class UserSettingsData
    {
        public bool soundOn;
        public bool bgmOn;
        public bool notificationOn;
        public string language;

        public UserSettingsData()
        {
            soundOn = true;
            bgmOn = true;
            notificationOn = true;
            language = "ko";
        }
    }

    /// <summary>
    /// User offline progress data.
    /// </summary>
    [Serializable]
    public class UserOfflineData
    {
        public string lastLoginTime;
        public double pendingGold;
        public double pendingExp;

        public UserOfflineData()
        {
            lastLoginTime = DateTime.UtcNow.ToString("o");
            pendingGold = 0;
            pendingExp = 0;
        }
    }

    /// <summary>
    /// User gacha pity tracking data.
    /// </summary>
    [Serializable]
    public class UserGachaData
    {
        public List<UserGachaEntry> banners = new();
    }

    [Serializable]
    public class UserGachaEntry
    {
        public string bannerId;
        public int pityCount;
        public int totalPulls;
        public bool isSoftPity;
    }

    /// <summary>
    /// User inventory data.
    /// </summary>
    [Serializable]
    public class UserInventoryData
    {
        public List<UserInventoryEntry> items = new();
    }

    [Serializable]
    public class UserInventoryEntry
    {
        public string itemId;
        public int count;
    }

    #endregion

    #region Additional Chart Data Models

    /// <summary>
    /// Item chart data from ItemTable.json.
    /// </summary>
    [Serializable]
    public class ItemData
    {
        public string itemId;
        public string name;
        public string type;
        public string description;
        public string effectType;
        public int effectValue;
        public int maxStack;
        public int grade;
    }

    [Serializable]
    public class ItemDataCollection
    {
        public List<ItemData> items;
    }

    #endregion

    #region Additional User Save Data Models

    /// <summary>
    /// User skill save data (equipped skills per hero, cooldown states).
    /// </summary>
    [Serializable]
    public class UserSkillSaveData
    {
        public List<UserHeroSkillEntry> heroSkills = new();
    }

    [Serializable]
    public class UserHeroSkillEntry
    {
        public string heroId;
        public List<string> equippedSkillIds = new();
        public List<int> skillLevels = new();
    }

    /// <summary>
    /// User quest save data (progress, completion, claim status per quest).
    /// </summary>
    [Serializable]
    public class UserQuestSaveData
    {
        public List<UserQuestSaveEntry> quests = new();
    }

    [Serializable]
    public class UserQuestSaveEntry
    {
        public string questId;
        public int progress;
        public bool isComplete;
        public bool isClaimed;
        public string refreshedAt;
    }

    /// <summary>
    /// User dungeon save data (remaining entries, best records per dungeon).
    /// </summary>
    [Serializable]
    public class UserDungeonSaveData
    {
        public List<UserDungeonSaveEntry> dungeons = new();
    }

    [Serializable]
    public class UserDungeonSaveEntry
    {
        public string dungeonId;
        public int remainEntries;
        public string lastResetAt;
        public int bestRecord;
    }

    #endregion
}
