namespace VeilBreaker.Core
{
    /// <summary>
    /// Central repository for all game constants, event keys, scene names,
    /// save keys, and gameplay parameters.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Config
    /// Phase: 0
    /// </remarks>
    public static class GameConstants
    {
        #region Events

        /// <summary>
        /// Event key constants for EventManager.Subscribe / Publish.
        /// All inter-system communication must use these constants.
        /// </summary>
        public static class Events
        {
            // Stage / Battle Flow
            public const string OnStageStart = "OnStageStart";
            public const string OnStageComplete = "OnStageComplete";
            public const string OnStageFail = "OnStageFail";
            public const string OnBossSpawn = "OnBossSpawn";
            public const string OnWaveStart = "OnWaveStart";
            public const string OnWaveComplete = "OnWaveComplete";

            // Character / Hero
            public const string OnHeroDie = "OnHeroDie";
            public const string OnEnemyDie = "OnEnemyDie";
            public const string OnCharacterLevelUp = "OnCharacterLevelUp";
            public const string OnCharacterStatChanged = "OnCharacterStatChanged";

            // Skill
            public const string OnSkillActivated = "OnSkillActivated";
            public const string OnSkillCooldownComplete = "OnSkillCooldownComplete";

            // Equipment
            public const string OnEquipmentChanged = "OnEquipmentChanged";
            public const string OnEquipmentEnhanced = "OnEquipmentEnhanced";

            // Currency / Economy
            public const string OnCurrencyChanged = "OnCurrencyChanged";
            public const string OnGachaResult = "OnGachaResult";

            // Quest
            public const string OnQuestProgress = "OnQuestProgress";
            public const string OnQuestComplete = "OnQuestComplete";

            // Content
            public const string OnTowerFloorComplete = "OnTowerFloorComplete";
            public const string OnDungeonComplete = "OnDungeonComplete";

            // Data / Save
            public const string OnDataLoaded = "OnDataLoaded";
            public const string OnGameSaved = "OnGameSaved";
            public const string OnOfflineRewardCalculated = "OnOfflineRewardCalculated";

            // Monetization
            public const string OnAdWatched = "OnAdWatched";
            public const string OnIAPPurchased = "OnIAPPurchased";

            // UI
            public const string OnPopupOpened = "OnPopupOpened";
            public const string OnPopupClosed = "OnPopupClosed";
            public const string OnPageChanged = "OnPageChanged";
        }

        #endregion

        #region Scenes

        /// <summary>
        /// Scene name constants for SceneManager.LoadScene.
        /// </summary>
        public static class Scenes
        {
            public const string Title = "Title";
            public const string Main = "Main";
            public const string GameScene = "GameScene";
        }

        #endregion

        #region Save Keys

        /// <summary>
        /// PlayerPrefs / save system key constants.
        /// </summary>
        public static class Save
        {
            public const string UserInfoKey = "UserInfo";
            public const string UserCurrencyKey = "UserCurrency";
            public const string UserHeroesKey = "UserHeroes";
            public const string UserStageKey = "UserStage";
            public const string LastLoginKey = "LastLogin";
            public const string SettingsKey = "Settings";
        }

        #endregion

        #region Battle

        /// <summary>
        /// Battle system numerical constants.
        /// </summary>
        public static class Battle
        {
            public const float AutoSaveInterval = 30f;
            public const float MaxOfflineHours = 12f;
            public const int MaxHeroFormation = 5;
            public const float CriticalDamageMultiplier = 1.5f;
            public const float AttributeAdvantage = 1.25f;
            public const float AttributeDisadvantage = 0.8f;
            public const float BaseDamageVariance = 0.05f;
        }

        #endregion

        #region Hero

        /// <summary>
        /// Hero system numerical constants.
        /// </summary>
        public static class Hero
        {
            public const int MaxLevel = 100;
            public const int MaxStars = 5;
            public const int MaxSkillLevel = 10;
            public const int EquipmentSlots = 6;
            public const int MaxEquipmentLevel = 15;
        }

        #endregion

        #region Gacha

        /// <summary>
        /// Gacha system pity constants.
        /// </summary>
        public static class Gacha
        {
            public const int SoftPity = 80;
            public const int HardPity = 100;
        }

        #endregion

        #region Pool Tags

        /// <summary>
        /// ObjectPool tag constants for consistent pool identification.
        /// </summary>
        public static class PoolTags
        {
            public const string DamageText = "DamageText";
            public const string HitEffect = "HitEffect";
            public const string Projectile = "Projectile";
            public const string Enemy = "Enemy";
            public const string DropItem = "DropItem";
        }

        #endregion

        #region Enums

        /// <summary>
        /// Character attribute types for rock-paper-scissors advantage system.
        /// </summary>
        public enum AttributeType
        {
            Fire,
            Water,
            Earth,
            Light,
            Dark
        }

        /// <summary>
        /// Hero rarity tiers.
        /// </summary>
        public enum Rarity
        {
            Common,
            Uncommon,
            Rare,
            Epic,
            Legendary
        }

        /// <summary>
        /// Currency types in the economy system.
        /// </summary>
        public enum CurrencyType
        {
            Gold,
            Gem,
            StageTicket,
            DungeonTicket,
            TowerTicket
        }

        /// <summary>
        /// Equipment slots on a hero.
        /// </summary>
        public enum EquipSlot
        {
            Weapon,
            Armor,
            Helmet,
            Boots,
            Ring,
            Necklace
        }

        /// <summary>
        /// Battle states for the stage/battle flow.
        /// </summary>
        public enum BattleState
        {
            Idle,
            Preparing,
            Fighting,
            BossPhase,
            Victory,
            Defeat
        }

        /// <summary>
        /// Game content modes.
        /// </summary>
        public enum GameMode
        {
            MainStage,
            Tower,
            Dungeon,
            Arena
        }

        #endregion
    }
}
