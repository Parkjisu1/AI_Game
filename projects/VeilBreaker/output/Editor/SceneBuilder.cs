#if UNITY_EDITOR
using UnityEngine;
using UnityEngine.UI;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.EventSystems;
using VeilBreaker.Core;
using VeilBreaker.Battle;
using VeilBreaker.Character;
using VeilBreaker.Economy;
using VeilBreaker.Data;
using VeilBreaker.Idle;
using VeilBreaker.Gacha;
using VeilBreaker.Quest;
using VeilBreaker.Content;
using VeilBreaker.Inventory;

namespace VeilBreaker.Editor
{
    /// <summary>
    /// Editor-only utility that auto-generates the three required scenes (Title, Main, GameScene)
    /// on first load via [InitializeOnLoad]. Uses EditorPrefs to prevent repeated execution.
    /// Output: Assets/Scenes/*.unity
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Generic
    /// Role: Builder
    /// System: Editor
    /// Phase: 3
    /// IMPORTANT: Must be placed in Assets/Editor/, NOT Assets/Scripts/
    /// </remarks>
    [InitializeOnLoad]
    public static class SceneBuilder
    {
        #region Constants

        private const string EditorPrefsKey = "VeilBreaker_SceneBuilt";
        private const string SceneFolderPath = "Assets/Scenes";
        private const string TitleScenePath = "Assets/Scenes/Title.unity";
        private const string MainScenePath = "Assets/Scenes/Main.unity";
        private const string GameScenePath = "Assets/Scenes/GameScene.unity";

        // Canvas reference resolution
        private const float CanvasWidth = 1080f;
        private const float CanvasHeight = 1920f;

        #endregion

        #region Static Constructor (InitializeOnLoad entry point)

        static SceneBuilder()
        {
            EditorApplication.delayCall += BuildScenesDelayed;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Manually trigger scene build (available via menu).
        /// Resets the EditorPrefs flag before building.
        /// </summary>
        [MenuItem("VeilBreaker/Build Scenes")]
        public static void BuildScenes()
        {
            EnsureSceneFolder();
            BuildTitleScene();
            BuildMainScene();
            BuildGameScene();
            AddScenesToBuildSettings();
            Debug.Log("[SceneBuilder] All scenes built successfully.");
        }

        /// <summary>
        /// Resets the EditorPrefs flag so scenes will be rebuilt on next Unity load.
        /// </summary>
        [MenuItem("VeilBreaker/Reset Scene Build Flag")]
        public static void ResetBuildFlag()
        {
            EditorPrefs.DeleteKey(EditorPrefsKey);
            Debug.Log("[SceneBuilder] Scene build flag reset. Reload Unity to rebuild scenes.");
        }

        #endregion

        #region Private Methods - Entry

        private static void BuildScenesDelayed()
        {
            // Step 3: Check EditorPrefs to prevent duplicate builds
            if (EditorPrefs.GetBool(EditorPrefsKey, false)) return;

            // Step 4-6: Build all scenes
            BuildScenes();

            // Step 7: Mark as built
            EditorPrefs.SetBool(EditorPrefsKey, true);
        }

        private static void EnsureSceneFolder()
        {
            if (!AssetDatabase.IsValidFolder(SceneFolderPath))
            {
                AssetDatabase.CreateFolder("Assets", "Scenes");
                AssetDatabase.Refresh();
            }
        }

        #endregion

        #region Build: Title Scene

        /// <summary>
        /// Builds Title.unity - splash screen with loading bar and logo.
        /// Contains TitleManager MonoBehaviour for initialization sequencing.
        /// </summary>
        private static void BuildTitleScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);

            // Camera
            SetupMainCamera();

            // Canvas
            GameObject canvas = CreateCanvas("Canvas");
            CreateEventSystem();

            // Loading bar placeholder (user connects in Inspector)
            var loadingBarGo = new GameObject("LoadingBar");
            loadingBarGo.transform.SetParent(canvas.transform, false);
            loadingBarGo.AddComponent<Slider>();

            // Title Manager
            var titleManagerGo = new GameObject("TitleManager");
            titleManagerGo.AddComponent<TitleManager>();

            EditorSceneManager.SaveScene(scene, TitleScenePath);
            Debug.Log($"[SceneBuilder] Title scene saved to {TitleScenePath}");
        }

        #endregion

        #region Build: Main Scene

        /// <summary>
        /// Builds Main.unity - main menu with Play/Settings buttons.
        /// </summary>
        private static void BuildMainScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);

            SetupMainCamera();
            GameObject canvas = CreateCanvas("Canvas");
            CreateEventSystem();

            // Play button placeholder
            var playBtnGo = new GameObject("PlayButton");
            playBtnGo.transform.SetParent(canvas.transform, false);
            playBtnGo.AddComponent<Button>();

            // Settings button placeholder
            var settingsBtnGo = new GameObject("SettingsButton");
            settingsBtnGo.transform.SetParent(canvas.transform, false);
            settingsBtnGo.AddComponent<Button>();

            EditorSceneManager.SaveScene(scene, MainScenePath);
            Debug.Log($"[SceneBuilder] Main scene saved to {MainScenePath}");
        }

        #endregion

        #region Build: GameScene

        /// <summary>
        /// Builds GameScene.unity - main gameplay scene with Managers object,
        /// Canvas, Camera, and EventSystem. All Manager singletons are attached
        /// to the "Managers" GameObject.
        /// </summary>
        private static void BuildGameScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);

            SetupMainCamera();
            CreateCanvas("Canvas");
            CreateEventSystem();

            // "Managers" GameObject - all singleton Managers attached here
            // (DontDestroyOnLoad applied automatically by Singleton<T> base)
            var managersGo = new GameObject("Managers");

            managersGo.AddComponent<EventManager>();
            managersGo.AddComponent<ObjectPool>();
            managersGo.AddComponent<SaveManager>();
            managersGo.AddComponent<DataManager>();
            managersGo.AddComponent<ResourceContainer>();

            managersGo.AddComponent<CurrencyManager>();
            managersGo.AddComponent<CharacterManager>();
            managersGo.AddComponent<SkillManager>();
            managersGo.AddComponent<StageManager>();
            managersGo.AddComponent<GachaManager>();
            managersGo.AddComponent<QuestManager>();
            managersGo.AddComponent<TowerManager>();
            managersGo.AddComponent<DungeonManager>();
            managersGo.AddComponent<OfflineProgressManager>();
            managersGo.AddComponent<InventoryManager>();
            managersGo.AddComponent<EquipmentManager>();
            managersGo.AddComponent<BattleManager>();

            EditorSceneManager.SaveScene(scene, GameScenePath);
            Debug.Log($"[SceneBuilder] GameScene saved to {GameScenePath}");
        }

        #endregion

        #region Build Settings

        private static void AddScenesToBuildSettings()
        {
            var scenes = new EditorBuildSettingsScene[]
            {
                new EditorBuildSettingsScene(TitleScenePath, true),
                new EditorBuildSettingsScene(MainScenePath, true),
                new EditorBuildSettingsScene(GameScenePath, true),
            };

            EditorBuildSettings.scenes = scenes;
            Debug.Log("[SceneBuilder] Build settings updated with 3 scenes.");
        }

        #endregion

        #region Scene Utilities

        private static void SetupMainCamera()
        {
            var cameraGo = new GameObject("Main Camera");
            cameraGo.tag = "MainCamera";
            var cam = cameraGo.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Color.black;
        }

        private static GameObject CreateCanvas(string name)
        {
            var canvasGo = new GameObject(name);
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(CanvasWidth, CanvasHeight);
            scaler.matchWidthOrHeight = 0.5f;

            canvasGo.AddComponent<GraphicRaycaster>();
            return canvasGo;
        }

        private static void CreateEventSystem()
        {
            var eventSystemGo = new GameObject("EventSystem");
            eventSystemGo.AddComponent<EventSystem>();
            eventSystemGo.AddComponent<StandaloneInputModule>();
        }

        #endregion
    }
}
#endif
