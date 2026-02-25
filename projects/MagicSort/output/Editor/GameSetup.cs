using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using Core = MagicSort.Core;
using Domain = MagicSort.Domain;
using Game = MagicSort.Game;

namespace MagicSort.Editor
{
    /// <summary>
    /// EditorWindow that sets up the entire MagicSort game:
    /// 3 scenes, prefabs, hierarchy objects, components, and SerializeField wiring.
    /// Menu: MagicSort > Setup Game
    /// </summary>
    public class GameSetup : EditorWindow
    {
        #region Constants

        private const string PREFS_KEY = "MagicSort_GameSetup_Done";
        private const string SCENES_PATH = "Assets/Scenes";
        private const string PREFABS_PATH = "Assets/Prefabs";

        // Scene names matching the SceneName enum
        private const string TITLE_SCENE = "Title";
        private const string HOME_SCENE = "Home";
        private const string GAMEPLAY_SCENE = "GamePlay";

        // Camera background color: deep purple #1A0A2E
        private static readonly Color BG_COLOR = new Color(0.102f, 0.039f, 0.180f, 1f);

        // Canvas reference resolution
        private static readonly Vector2 CANVAS_REF_RESOLUTION = new Vector2(1080f, 1920f);

        #endregion

        #region Menu Item

        [MenuItem("MagicSort/Setup Game")]
        public static void ShowWindow()
        {
            GetWindow<GameSetup>("MagicSort Setup");
        }

        #endregion

        #region EditorWindow

        private Vector2 _scrollPos;
        private bool _forceRebuild;

        private void OnGUI()
        {
            _scrollPos = EditorGUILayout.BeginScrollView(_scrollPos);

            EditorGUILayout.LabelField("MagicSort Game Setup", EditorStyles.boldLabel);
            EditorGUILayout.Space(10);

            bool alreadyRun = EditorPrefs.GetBool(PREFS_KEY, false);
            if (alreadyRun)
            {
                EditorGUILayout.HelpBox("Setup has already been run. Check 'Force Rebuild' to run again.", MessageType.Info);
                _forceRebuild = EditorGUILayout.Toggle("Force Rebuild", _forceRebuild);
            }

            EditorGUILayout.Space(10);

            GUI.enabled = !alreadyRun || _forceRebuild;
            if (GUILayout.Button("Run Full Setup", GUILayout.Height(40)))
            {
                RunFullSetup();
            }
            GUI.enabled = true;

            EditorGUILayout.Space(20);
            EditorGUILayout.LabelField("Individual Steps", EditorStyles.boldLabel);

            if (GUILayout.Button("1. Create Scenes Only"))
            {
                CreateAllScenes();
                RegisterScenesInBuildSettings();
            }

            if (GUILayout.Button("2. Create Prefabs Only"))
            {
                CreateAllPrefabs();
            }

            if (GUILayout.Button("3. Setup Title Scene"))
            {
                SetupTitleScene();
            }

            if (GUILayout.Button("4. Setup Home Scene"))
            {
                SetupHomeScene();
            }

            if (GUILayout.Button("5. Setup GamePlay Scene"))
            {
                SetupGamePlayScene();
            }

            EditorGUILayout.Space(10);

            if (GUILayout.Button("Reset Setup Flag"))
            {
                EditorPrefs.DeleteKey(PREFS_KEY);
                Debug.Log("[GameSetup] Setup flag reset.");
            }

            EditorGUILayout.EndScrollView();
        }

        #endregion

        #region Full Setup

        private void RunFullSetup()
        {
            Debug.Log("[GameSetup] Starting full game setup...");

            EnsureDirectories();
            CreateAllPrefabs();
            CreateAllScenes();
            RegisterScenesInBuildSettings();

            SetupTitleScene();
            SetupHomeScene();
            SetupGamePlayScene();

            EditorPrefs.SetBool(PREFS_KEY, true);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            Debug.Log("[GameSetup] Full setup complete! Open Title scene and press Play.");
            EditorUtility.DisplayDialog("MagicSort Setup", "Setup complete!\n\n- 3 scenes created\n- Prefabs created\n- All scenes configured\n\nOpen Title scene and press Play.", "OK");
        }

        #endregion

        #region Directory Setup

        private static void EnsureDirectories()
        {
            EnsureFolder("Assets", "Scenes");
            EnsureFolder("Assets", "Prefabs");
        }

        private static void EnsureFolder(string parent, string folderName)
        {
            string fullPath = $"{parent}/{folderName}";
            if (!AssetDatabase.IsValidFolder(fullPath))
            {
                AssetDatabase.CreateFolder(parent, folderName);
            }
        }

        #endregion

        #region Scene Creation

        private static void CreateAllScenes()
        {
            EnsureDirectories();
            CreateEmptyScene(TITLE_SCENE);
            CreateEmptyScene(HOME_SCENE);
            CreateEmptyScene(GAMEPLAY_SCENE);
            Debug.Log("[GameSetup] All 3 scenes created.");
        }

        private static string CreateEmptyScene(string sceneName)
        {
            string path = $"{SCENES_PATH}/{sceneName}.unity";

            // Create a new scene with default objects (Camera + Directional Light)
            var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);

            // Remove the directional light (we don't need it for 2D)
            var lights = Object.FindObjectsOfType<Light>();
            foreach (var light in lights)
            {
                Object.DestroyImmediate(light.gameObject);
            }

            EditorSceneManager.SaveScene(scene, path);
            Debug.Log($"[GameSetup] Scene created: {path}");
            return path;
        }

        private static void RegisterScenesInBuildSettings()
        {
            EditorBuildSettingsScene[] buildScenes = new EditorBuildSettingsScene[]
            {
                new EditorBuildSettingsScene($"{SCENES_PATH}/{TITLE_SCENE}.unity", true),
                new EditorBuildSettingsScene($"{SCENES_PATH}/{HOME_SCENE}.unity", true),
                new EditorBuildSettingsScene($"{SCENES_PATH}/{GAMEPLAY_SCENE}.unity", true)
            };

            EditorBuildSettings.scenes = buildScenes;
            Debug.Log("[GameSetup] Build settings updated: Title(0), Home(1), GamePlay(2).");
        }

        #endregion

        #region Prefab Creation

        private static void CreateAllPrefabs()
        {
            EnsureDirectories();
            CreateBottlePrefab();
            CreateWaterSlotPrefab();
            CreatePopupBasePrefab();
            Debug.Log("[GameSetup] All prefabs created.");
        }

        private static GameObject CreateBottlePrefab()
        {
            string path = $"{PREFABS_PATH}/BottlePrefab.prefab";

            // Root: BottleItem
            GameObject root = new GameObject("BottlePrefab");

            // Add BottleItem component (will be wired after save)
            var bottleItem = root.AddComponent<Domain.BottleItem>();

            // Add BoxCollider2D for touch detection
            var collider = root.AddComponent<BoxCollider2D>();
            collider.size = new Vector2(1.2f, 3f);
            collider.offset = new Vector2(0f, 0f);

            // Child: BottleBack (SpriteRenderer)
            GameObject bottleBack = new GameObject("BottleBack");
            bottleBack.transform.SetParent(root.transform);
            bottleBack.transform.localPosition = Vector3.zero;
            var backSR = bottleBack.AddComponent<SpriteRenderer>();
            backSR.color = new Color(0.6f, 0.6f, 0.6f, 0.4f);
            backSR.sortingOrder = 0;
            // Size is controlled by sprite asset - placeholder uses default

            // Child: BottleFront (SpriteRenderer)
            GameObject bottleFront = new GameObject("BottleFront");
            bottleFront.transform.SetParent(root.transform);
            bottleFront.transform.localPosition = Vector3.zero;
            var frontSR = bottleFront.AddComponent<SpriteRenderer>();
            frontSR.color = new Color(0.7f, 0.7f, 0.7f, 0.5f);
            frontSR.sortingOrder = 2;

            // Child: WaterContainer (empty transform, parent for water slot instances)
            GameObject waterContainer = new GameObject("WaterContainer");
            waterContainer.transform.SetParent(root.transform);
            waterContainer.transform.localPosition = new Vector3(0f, -0.6f, 0f);

            // Create 4 water slot children (for max 4 layers)
            for (int i = 0; i < 4; i++)
            {
                GameObject waterSlot = new GameObject($"WaterSlot_{i}");
                waterSlot.transform.SetParent(waterContainer.transform);
                waterSlot.transform.localPosition = new Vector3(0f, i * 0.6f, 0f);
                var waterSR = waterSlot.AddComponent<SpriteRenderer>();
                waterSR.color = Color.clear;
                waterSR.sortingOrder = 1;
                waterSlot.SetActive(false);
            }

            // Wire SerializeField references on BottleItem via SerializedObject
            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(root, path);
            Object.DestroyImmediate(root);

            // Re-open the prefab to wire SerializedObject fields
            if (prefab != null)
            {
                WireBottlePrefabFields(prefab);
            }

            Debug.Log($"[GameSetup] Prefab created: {path}");
            return prefab;
        }

        private static void WireBottlePrefabFields(GameObject prefab)
        {
            var bottleItem = prefab.GetComponent<Domain.BottleItem>();
            if (bottleItem == null) return;

            SerializedObject so = new SerializedObject(bottleItem);

            // Wire _bottleBack
            Transform bottleBack = prefab.transform.Find("BottleBack");
            if (bottleBack != null)
            {
                SerializedProperty propBack = so.FindProperty("_bottleBack");
                if (propBack != null)
                {
                    propBack.objectReferenceValue = bottleBack.GetComponent<SpriteRenderer>();
                }
            }

            // Wire _bottleFront
            Transform bottleFront = prefab.transform.Find("BottleFront");
            if (bottleFront != null)
            {
                SerializedProperty propFront = so.FindProperty("_bottleFront");
                if (propFront != null)
                {
                    propFront.objectReferenceValue = bottleFront.GetComponent<SpriteRenderer>();
                }
            }

            // Wire _waterContainer
            Transform waterContainer = prefab.transform.Find("WaterContainer");
            if (waterContainer != null)
            {
                SerializedProperty propContainer = so.FindProperty("_waterContainer");
                if (propContainer != null)
                {
                    propContainer.objectReferenceValue = waterContainer;
                }
            }

            // Wire _bottleSprite (use BottleFront as main sprite)
            if (bottleFront != null)
            {
                SerializedProperty propSprite = so.FindProperty("_bottleSprite");
                if (propSprite != null)
                {
                    propSprite.objectReferenceValue = bottleFront.GetComponent<SpriteRenderer>();
                }
            }

            so.ApplyModifiedPropertiesWithoutUndo();
        }

        private static GameObject CreateWaterSlotPrefab()
        {
            string path = $"{PREFABS_PATH}/WaterSlotPrefab.prefab";

            GameObject root = new GameObject("WaterSlotPrefab");
            var sr = root.AddComponent<SpriteRenderer>();
            sr.color = Color.white;
            sr.sortingOrder = 1;

            // Scale to approximate 0.8x0.6 via transform
            root.transform.localScale = new Vector3(0.8f, 0.6f, 1f);

            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(root, path);
            Object.DestroyImmediate(root);

            Debug.Log($"[GameSetup] Prefab created: {path}");
            return prefab;
        }

        private static GameObject CreatePopupBasePrefab()
        {
            string path = $"{PREFABS_PATH}/PopupBasePrefab.prefab";

            // Canvas-based popup
            GameObject root = new GameObject("PopupBasePrefab");
            var rectRoot = root.AddComponent<RectTransform>();
            StretchFull(rectRoot);

            // Dimming background
            GameObject dimBg = CreateUIElement("DimBackground", root.transform);
            var dimImage = dimBg.AddComponent<Image>();
            dimImage.color = new Color(0f, 0f, 0f, 0.6f);
            StretchFull(dimBg.GetComponent<RectTransform>());

            // Content panel (centered)
            GameObject contentPanel = CreateUIElement("ContentPanel", root.transform);
            var contentImage = contentPanel.AddComponent<Image>();
            contentImage.color = new Color(0.15f, 0.1f, 0.25f, 0.95f);
            var contentRT = contentPanel.GetComponent<RectTransform>();
            contentRT.anchorMin = new Vector2(0.1f, 0.3f);
            contentRT.anchorMax = new Vector2(0.9f, 0.7f);
            contentRT.offsetMin = Vector2.zero;
            contentRT.offsetMax = Vector2.zero;

            // Close button (top-right of content panel)
            GameObject closeBtn = CreateUIElement("CloseButton", contentPanel.transform);
            var closeBtnImage = closeBtn.AddComponent<Image>();
            closeBtnImage.color = new Color(0.8f, 0.2f, 0.2f, 1f);
            closeBtn.AddComponent<Button>();
            var closeBtnRT = closeBtn.GetComponent<RectTransform>();
            closeBtnRT.anchorMin = new Vector2(1f, 1f);
            closeBtnRT.anchorMax = new Vector2(1f, 1f);
            closeBtnRT.pivot = new Vector2(1f, 1f);
            closeBtnRT.sizeDelta = new Vector2(80f, 80f);
            closeBtnRT.anchoredPosition = new Vector2(10f, 10f);

            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(root, path);
            Object.DestroyImmediate(root);

            Debug.Log($"[GameSetup] Prefab created: {path}");
            return prefab;
        }

        #endregion

        #region Title Scene Setup

        private static void SetupTitleScene()
        {
            string scenePath = $"{SCENES_PATH}/{TITLE_SCENE}.unity";
            var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);

            // --- Camera ---
            Camera cam = SetupCamera(BG_COLOR);

            // --- Canvas + EventSystem ---
            var canvasGO = CreateCanvas("Canvas");
            EnsureEventSystem();

            // --- ProjectContext (DontDestroyOnLoad, global singleton container) ---
            var projectCtxGO = new GameObject("ProjectContext");
            projectCtxGO.AddComponent<Core.ProjectContext>();

            // --- Managers (DontDestroyOnLoad) ---
            var managersGO = new GameObject("Managers");

            // Core Singletons
            managersGO.AddComponent<Core.SceneLoader>();
            managersGO.AddComponent<Core.SaveManager>();
            managersGO.AddComponent<Core.PopUpService>();
            managersGO.AddComponent<Core.CustomUpdater>();

            // SoundManager with AudioSources
            var soundMgr = managersGO.AddComponent<Core.SoundManager>();
            var bgmSource = managersGO.AddComponent<AudioSource>();
            bgmSource.playOnAwake = false;
            bgmSource.loop = true;
            var sfxSource = managersGO.AddComponent<AudioSource>();
            sfxSource.playOnAwake = false;

            // Wire SoundManager AudioSources
            WireSerializedField(soundMgr, "bgmSource", bgmSource);
            WireSerializedField(soundMgr, "sfxSource", sfxSource);

            // Domain Singletons
            managersGO.AddComponent<Domain.CurrencyManager>();

            // --- Canvas UI Elements ---

            // Background panel
            var bgPanel = CreatePanel("Background", canvasGO.transform, BG_COLOR);
            StretchFull(bgPanel.GetComponent<RectTransform>());

            // Logo placeholder (Text as placeholder)
            var logoGO = CreateUIElement("Logo", canvasGO.transform);
            var logoText = logoGO.AddComponent<Text>();
            logoText.text = "Magic Sort";
            logoText.fontSize = 60;
            logoText.alignment = TextAnchor.MiddleCenter;
            logoText.color = Color.white;
            logoText.font = GetBuiltinFont();
            var logoRT = logoGO.GetComponent<RectTransform>();
            logoRT.anchorMin = new Vector2(0.5f, 0.7f);
            logoRT.anchorMax = new Vector2(0.5f, 0.7f);
            logoRT.pivot = new Vector2(0.5f, 0.5f);
            logoRT.sizeDelta = new Vector2(400f, 200f);
            logoRT.anchoredPosition = Vector2.zero;

            // Loading bar (Slider)
            var sliderGO = CreateSlider("LoadingBar", canvasGO.transform);
            var sliderRT = sliderGO.GetComponent<RectTransform>();
            sliderRT.anchorMin = new Vector2(0.5f, 0.15f);
            sliderRT.anchorMax = new Vector2(0.5f, 0.15f);
            sliderRT.pivot = new Vector2(0.5f, 0.5f);
            sliderRT.sizeDelta = new Vector2(800f, 40f);
            sliderRT.anchoredPosition = Vector2.zero;
            var slider = sliderGO.GetComponent<Slider>();
            slider.interactable = false;

            // Version text
            var versionGO = CreateUIElement("VersionText", canvasGO.transform);
            var versionText = versionGO.AddComponent<Text>();
            versionText.text = "v1.0.0";
            versionText.fontSize = 24;
            versionText.alignment = TextAnchor.LowerRight;
            versionText.color = new Color(1f, 1f, 1f, 0.5f);
            versionText.font = GetBuiltinFont();
            var versionRT = versionGO.GetComponent<RectTransform>();
            versionRT.anchorMin = new Vector2(1f, 0f);
            versionRT.anchorMax = new Vector2(1f, 0f);
            versionRT.pivot = new Vector2(1f, 0f);
            versionRT.sizeDelta = new Vector2(200f, 50f);
            versionRT.anchoredPosition = new Vector2(-20f, 20f);

            // --- TitleController on Canvas ---
            var titleCtrl = canvasGO.AddComponent<Game.TitleController>();
            WireSerializedField(titleCtrl, "loadingBar", slider);
            WireSerializedField(titleCtrl, "versionText", versionText);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            Debug.Log("[GameSetup] Title scene configured.");
        }

        #endregion

        #region Home Scene Setup

        private static void SetupHomeScene()
        {
            string scenePath = $"{SCENES_PATH}/{HOME_SCENE}.unity";
            var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);

            // --- Camera ---
            Camera cam = SetupCamera(BG_COLOR);

            // --- Canvas + EventSystem ---
            var canvasGO = CreateCanvas("Canvas");
            EnsureEventSystem();

            // --- Top Bar ---
            var topBar = CreatePanel("TopBar", canvasGO.transform, new Color(0.1f, 0.05f, 0.2f, 0.8f));
            var topBarRT = topBar.GetComponent<RectTransform>();
            topBarRT.anchorMin = new Vector2(0f, 0.9f);
            topBarRT.anchorMax = new Vector2(1f, 1f);
            topBarRT.offsetMin = Vector2.zero;
            topBarRT.offsetMax = Vector2.zero;

            // Coin text in top bar
            var coinGO = CreateUIElement("CoinText", topBar.transform);
            var coinText = coinGO.AddComponent<Text>();
            coinText.text = "0";
            coinText.fontSize = 36;
            coinText.alignment = TextAnchor.MiddleLeft;
            coinText.color = new Color(1f, 0.85f, 0f, 1f);
            coinText.font = GetBuiltinFont();
            var coinRT = coinGO.GetComponent<RectTransform>();
            coinRT.anchorMin = new Vector2(0f, 0f);
            coinRT.anchorMax = new Vector2(0.4f, 1f);
            coinRT.offsetMin = new Vector2(60f, 0f);
            coinRT.offsetMax = Vector2.zero;

            // Gem text in top bar
            var gemGO = CreateUIElement("GemText", topBar.transform);
            var gemText = gemGO.AddComponent<Text>();
            gemText.text = "0";
            gemText.fontSize = 36;
            gemText.alignment = TextAnchor.MiddleRight;
            gemText.color = new Color(0.4f, 0.8f, 1f, 1f);
            gemText.font = GetBuiltinFont();
            var gemRT = gemGO.GetComponent<RectTransform>();
            gemRT.anchorMin = new Vector2(0.6f, 0f);
            gemRT.anchorMax = new Vector2(1f, 1f);
            gemRT.offsetMin = Vector2.zero;
            gemRT.offsetMax = new Vector2(-60f, 0f);

            // --- Center Area ---
            var centerArea = CreatePanel("CenterArea", canvasGO.transform, new Color(0f, 0f, 0f, 0f));
            var centerRT = centerArea.GetComponent<RectTransform>();
            centerRT.anchorMin = new Vector2(0f, 0.3f);
            centerRT.anchorMax = new Vector2(1f, 0.9f);
            centerRT.offsetMin = Vector2.zero;
            centerRT.offsetMax = Vector2.zero;

            // Level text
            var levelGO = CreateUIElement("LevelText", centerArea.transform);
            var levelText = levelGO.AddComponent<Text>();
            levelText.text = "Level 1";
            levelText.fontSize = 72;
            levelText.alignment = TextAnchor.MiddleCenter;
            levelText.color = Color.white;
            levelText.font = GetBuiltinFont();
            var levelRT = levelGO.GetComponent<RectTransform>();
            levelRT.anchorMin = new Vector2(0.1f, 0.5f);
            levelRT.anchorMax = new Vector2(0.9f, 0.8f);
            levelRT.offsetMin = Vector2.zero;
            levelRT.offsetMax = Vector2.zero;

            // Play button
            var playBtnGO = CreateButton("PlayButton", centerArea.transform, "PLAY", 48,
                new Color(0.3f, 0.7f, 0.3f, 1f));
            var playBtnRT = playBtnGO.GetComponent<RectTransform>();
            playBtnRT.anchorMin = new Vector2(0.25f, 0.15f);
            playBtnRT.anchorMax = new Vector2(0.75f, 0.4f);
            playBtnRT.offsetMin = Vector2.zero;
            playBtnRT.offsetMax = Vector2.zero;

            // --- Bottom Bar ---
            var bottomBar = CreatePanel("BottomBar", canvasGO.transform, new Color(0.1f, 0.05f, 0.2f, 0.8f));
            var bottomBarRT = bottomBar.GetComponent<RectTransform>();
            bottomBarRT.anchorMin = new Vector2(0f, 0f);
            bottomBarRT.anchorMax = new Vector2(1f, 0.08f);
            bottomBarRT.offsetMin = Vector2.zero;
            bottomBarRT.offsetMax = Vector2.zero;

            // Settings button in bottom bar
            var settingsBtnGO = CreateButton("SettingsButton", bottomBar.transform, "Settings", 28,
                new Color(0.4f, 0.3f, 0.6f, 1f));
            var settingsBtnRT = settingsBtnGO.GetComponent<RectTransform>();
            settingsBtnRT.anchorMin = new Vector2(0.35f, 0.1f);
            settingsBtnRT.anchorMax = new Vector2(0.65f, 0.9f);
            settingsBtnRT.offsetMin = Vector2.zero;
            settingsBtnRT.offsetMax = Vector2.zero;

            // --- HomeController on Canvas ---
            var homeCtrl = canvasGO.AddComponent<Game.HomeController>();

            // Wire fields -- using Text since TMP_Text requires TMPro package import
            // The HomeController uses TMP_Text but we wire via SerializedObject
            // If TMPro is installed, these would use TMP_Text components
            WireSerializedField(homeCtrl, "playButton", playBtnGO.GetComponent<Button>());
            WireSerializedField(homeCtrl, "settingsButton", settingsBtnGO.GetComponent<Button>());

            // Note: coinText, gemText, levelText fields on HomeController are TMP_Text.
            // In a project without TMP, they will remain null and the controller handles nulls gracefully.
            // When the user imports TMPro, they can manually create TMP_Text objects and wire them.

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            Debug.Log("[GameSetup] Home scene configured.");
        }

        #endregion

        #region GamePlay Scene Setup

        private static void SetupGamePlayScene()
        {
            string scenePath = $"{SCENES_PATH}/{GAMEPLAY_SCENE}.unity";
            var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);

            // --- Camera ---
            Camera cam = SetupCamera(BG_COLOR);

            // --- Canvas + EventSystem ---
            var canvasGO = CreateCanvas("Canvas");
            EnsureEventSystem();

            // --- SceneContext ---
            var sceneCtxGO = new GameObject("SceneContext");
            sceneCtxGO.AddComponent<Core.SceneContext>();

            // --- Managers ---
            var managersGO = new GameObject("Managers");

            // LevelManager (Singleton)
            var levelMgr = managersGO.AddComponent<Domain.LevelManager>();

            // SelectionManager
            var selectionMgr = managersGO.AddComponent<Domain.SelectionManager>();
            WireSerializedField(selectionMgr, "_camera", cam);

            // PourProcessor
            var pourProcessor = managersGO.AddComponent<Domain.PourProcessor>();

            // --- BottleCollection ---
            var bottleCollectionGO = new GameObject("BottleCollection");
            var bottleCollection = bottleCollectionGO.AddComponent<Domain.BottleCollection>();

            // Create a BottleParent child
            var bottleParentGO = new GameObject("BottleParent");
            bottleParentGO.transform.SetParent(bottleCollectionGO.transform);
            bottleParentGO.transform.localPosition = new Vector3(0f, -1f, 0f);

            // Wire BottleCollection fields
            WireSerializedField(bottleCollection, "_bottleParent", bottleParentGO.transform);

            // Load and wire bottle prefab
            var bottlePrefab = AssetDatabase.LoadAssetAtPath<GameObject>($"{PREFABS_PATH}/BottlePrefab.prefab");
            if (bottlePrefab != null)
            {
                var prefabBottleItem = bottlePrefab.GetComponent<Domain.BottleItem>();
                if (prefabBottleItem != null)
                {
                    WireSerializedField(bottleCollection, "_bottlePrefab", prefabBottleItem);
                }
            }

            // Wire LevelManager scene references
            WireSerializedField(levelMgr, "_bottleCollection", bottleCollection);
            WireSerializedField(levelMgr, "_selectionManager", selectionMgr);
            WireSerializedField(levelMgr, "_pourProcessor", pourProcessor);

            // --- Canvas HUD ---

            // Top HUD
            var topHUD = CreatePanel("TopHUD", canvasGO.transform, new Color(0.1f, 0.05f, 0.2f, 0.7f));
            var topHUDRT = topHUD.GetComponent<RectTransform>();
            topHUDRT.anchorMin = new Vector2(0f, 0.92f);
            topHUDRT.anchorMax = new Vector2(1f, 1f);
            topHUDRT.offsetMin = Vector2.zero;
            topHUDRT.offsetMax = Vector2.zero;

            // Level text in top HUD
            var lvlTextGO = CreateUIElement("LevelText", topHUD.transform);
            var lvlText = lvlTextGO.AddComponent<Text>();
            lvlText.text = "Level 1";
            lvlText.fontSize = 36;
            lvlText.alignment = TextAnchor.MiddleLeft;
            lvlText.color = Color.white;
            lvlText.font = GetBuiltinFont();
            var lvlTextRT = lvlTextGO.GetComponent<RectTransform>();
            lvlTextRT.anchorMin = new Vector2(0f, 0f);
            lvlTextRT.anchorMax = new Vector2(0.5f, 1f);
            lvlTextRT.offsetMin = new Vector2(30f, 0f);
            lvlTextRT.offsetMax = Vector2.zero;

            // Move count text in top HUD
            var moveTextGO = CreateUIElement("MoveCountText", topHUD.transform);
            var moveText = moveTextGO.AddComponent<Text>();
            moveText.text = "Moves: 0";
            moveText.fontSize = 32;
            moveText.alignment = TextAnchor.MiddleRight;
            moveText.color = Color.white;
            moveText.font = GetBuiltinFont();
            var moveTextRT = moveTextGO.GetComponent<RectTransform>();
            moveTextRT.anchorMin = new Vector2(0.5f, 0f);
            moveTextRT.anchorMax = new Vector2(1f, 1f);
            moveTextRT.offsetMin = Vector2.zero;
            moveTextRT.offsetMax = new Vector2(-30f, 0f);

            // Pause button (top-right)
            var pauseBtnGO = CreateButton("PauseButton", canvasGO.transform, "||", 32,
                new Color(0.4f, 0.3f, 0.6f, 0.9f));
            var pauseBtnRT = pauseBtnGO.GetComponent<RectTransform>();
            pauseBtnRT.anchorMin = new Vector2(1f, 1f);
            pauseBtnRT.anchorMax = new Vector2(1f, 1f);
            pauseBtnRT.pivot = new Vector2(1f, 1f);
            pauseBtnRT.sizeDelta = new Vector2(100f, 100f);
            pauseBtnRT.anchoredPosition = new Vector2(-20f, -20f);

            // Bottom HUD
            var bottomHUD = CreatePanel("BottomHUD", canvasGO.transform, new Color(0.1f, 0.05f, 0.2f, 0.7f));
            var bottomHUDRT = bottomHUD.GetComponent<RectTransform>();
            bottomHUDRT.anchorMin = new Vector2(0f, 0f);
            bottomHUDRT.anchorMax = new Vector2(1f, 0.1f);
            bottomHUDRT.offsetMin = Vector2.zero;
            bottomHUDRT.offsetMax = Vector2.zero;

            // Booster buttons (4 in bottom HUD, evenly spaced)
            var undoBtnGO = CreateBoosterButton("UndoButton", bottomHUD.transform, "Undo", 0, 4);
            var hintBtnGO = CreateBoosterButton("HintButton", bottomHUD.transform, "Hint", 1, 4);
            var extraBtnGO = CreateBoosterButton("ExtraBottleButton", bottomHUD.transform, "+Bottle", 2, 4);
            var shuffleBtnGO = CreateBoosterButton("ShuffleButton", bottomHUD.transform, "Shuffle", 3, 4);

            // --- GamePlayController on Canvas ---
            var gpCtrl = canvasGO.AddComponent<Game.GamePlayController>();

            // Wire GamePlayController fields
            WireSerializedField(gpCtrl, "levelManager", levelMgr);
            WireSerializedField(gpCtrl, "bottleCollection", bottleCollection);
            WireSerializedField(gpCtrl, "undoButton", undoBtnGO.GetComponent<Button>());
            WireSerializedField(gpCtrl, "hintButton", hintBtnGO.GetComponent<Button>());
            WireSerializedField(gpCtrl, "extraBottleButton", extraBtnGO.GetComponent<Button>());
            WireSerializedField(gpCtrl, "shuffleButton", shuffleBtnGO.GetComponent<Button>());
            WireSerializedField(gpCtrl, "pauseButton", pauseBtnGO.GetComponent<Button>());

            // Note: levelText and moveCountText fields on GamePlayController are TMP_Text.
            // Same as HomeController, these will be null until TMPro is set up.
            // The controller handles null gracefully.

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            Debug.Log("[GameSetup] GamePlay scene configured.");
        }

        #endregion

        #region Helpers - Camera

        private static Camera SetupCamera(Color bgColor)
        {
            Camera cam = Camera.main;
            if (cam == null)
            {
                var camGO = new GameObject("Main Camera");
                cam = camGO.AddComponent<Camera>();
                camGO.AddComponent<AudioListener>();
                camGO.tag = "MainCamera";
            }

            cam.orthographic = true;
            cam.orthographicSize = 10f;
            cam.backgroundColor = bgColor;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.transform.position = new Vector3(0f, 0f, -10f);

            return cam;
        }

        #endregion

        #region Helpers - Canvas / EventSystem

        private static GameObject CreateCanvas(string name)
        {
            var canvasGO = new GameObject(name);
            var canvas = canvasGO.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 0;

            var scaler = canvasGO.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = CANVAS_REF_RESOLUTION;
            scaler.matchWidthOrHeight = 0.5f;
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;

            canvasGO.AddComponent<GraphicRaycaster>();

            return canvasGO;
        }

        private static void EnsureEventSystem()
        {
            if (Object.FindObjectOfType<EventSystem>() == null)
            {
                var esGO = new GameObject("EventSystem");
                esGO.AddComponent<EventSystem>();
                esGO.AddComponent<StandaloneInputModule>();
            }
        }

        #endregion

        #region Helpers - UI Elements

        private static GameObject CreateUIElement(string name, Transform parent)
        {
            var go = new GameObject(name);
            go.AddComponent<RectTransform>();
            go.transform.SetParent(parent, false);
            return go;
        }

        private static GameObject CreatePanel(string name, Transform parent, Color color)
        {
            var go = CreateUIElement(name, parent);
            var image = go.AddComponent<Image>();
            image.color = color;
            image.raycastTarget = false;
            return go;
        }

        private static GameObject CreateButton(string name, Transform parent, string label, int fontSize, Color bgColor)
        {
            var go = CreateUIElement(name, parent);
            var image = go.AddComponent<Image>();
            image.color = bgColor;
            var button = go.AddComponent<Button>();

            // Button label
            var labelGO = CreateUIElement("Label", go.transform);
            var text = labelGO.AddComponent<Text>();
            text.text = label;
            text.fontSize = fontSize;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.font = GetBuiltinFont();
            StretchFull(labelGO.GetComponent<RectTransform>());

            return go;
        }

        private static GameObject CreateSlider(string name, Transform parent)
        {
            // Create slider manually for full control
            var sliderGO = CreateUIElement(name, parent);
            var slider = sliderGO.AddComponent<Slider>();
            slider.minValue = 0f;
            slider.maxValue = 1f;
            slider.value = 0f;

            // Background
            var bgGO = CreateUIElement("Background", sliderGO.transform);
            var bgImage = bgGO.AddComponent<Image>();
            bgImage.color = new Color(0.3f, 0.2f, 0.4f, 0.8f);
            StretchFull(bgGO.GetComponent<RectTransform>());

            // Fill Area
            var fillAreaGO = CreateUIElement("Fill Area", sliderGO.transform);
            var fillAreaRT = fillAreaGO.GetComponent<RectTransform>();
            fillAreaRT.anchorMin = new Vector2(0f, 0.25f);
            fillAreaRT.anchorMax = new Vector2(1f, 0.75f);
            fillAreaRT.offsetMin = new Vector2(5f, 0f);
            fillAreaRT.offsetMax = new Vector2(-5f, 0f);

            var fillGO = CreateUIElement("Fill", fillAreaGO.transform);
            var fillImage = fillGO.AddComponent<Image>();
            fillImage.color = new Color(0.6f, 0.3f, 0.9f, 1f);
            StretchFull(fillGO.GetComponent<RectTransform>());

            slider.fillRect = fillGO.GetComponent<RectTransform>();

            return sliderGO;
        }

        private static GameObject CreateBoosterButton(string name, Transform parent, string label, int index, int total)
        {
            float segmentWidth = 1f / total;
            float minX = index * segmentWidth;
            float maxX = (index + 1) * segmentWidth;

            var go = CreateUIElement(name, parent);
            var image = go.AddComponent<Image>();
            image.color = new Color(0.25f, 0.15f, 0.4f, 0.9f);
            go.AddComponent<Button>();

            var goRT = go.GetComponent<RectTransform>();
            goRT.anchorMin = new Vector2(minX, 0.05f);
            goRT.anchorMax = new Vector2(maxX, 0.95f);
            goRT.offsetMin = new Vector2(5f, 0f);
            goRT.offsetMax = new Vector2(-5f, 0f);

            // Label
            var labelGO = CreateUIElement("Label", go.transform);
            var text = labelGO.AddComponent<Text>();
            text.text = label;
            text.fontSize = 24;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.font = GetBuiltinFont();
            StretchFull(labelGO.GetComponent<RectTransform>());

            return go;
        }

        #endregion

        #region Helpers - RectTransform

        private static void StretchFull(RectTransform rt)
        {
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;
        }

        #endregion

        #region Helpers - Font

        private static Font _cachedFont;

        /// <summary>
        /// Gets a built-in font. Tries LegacyRuntime.ttf first (Unity 2022+), then Arial.ttf.
        /// </summary>
        private static Font GetBuiltinFont()
        {
            if (_cachedFont != null) return _cachedFont;

            _cachedFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (_cachedFont == null)
            {
                _cachedFont = Resources.GetBuiltinResource<Font>("Arial.ttf");
            }

            return _cachedFont;
        }

        #endregion

        #region Helpers - SerializeField Wiring

        /// <summary>
        /// Wires a SerializeField on a MonoBehaviour component using SerializedObject.
        /// </summary>
        /// <param name="component">The target MonoBehaviour.</param>
        /// <param name="fieldName">The serialized field name (private fields need matching name).</param>
        /// <param name="value">The Object reference to assign.</param>
        private static void WireSerializedField(Component component, string fieldName, Object value)
        {
            if (component == null || value == null) return;

            SerializedObject so = new SerializedObject(component);
            SerializedProperty prop = so.FindProperty(fieldName);
            if (prop != null)
            {
                prop.objectReferenceValue = value;
                so.ApplyModifiedPropertiesWithoutUndo();
            }
            else
            {
                // Some fields may not be found if the script has compilation issues or TMP is missing
                Debug.LogWarning($"[GameSetup] Could not find property '{fieldName}' on {component.GetType().Name}. It may require TMPro or a missing dependency.");
            }
        }

        #endregion
    }
}
