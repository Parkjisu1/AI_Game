using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UnityEditor;
using UnityEditor.SceneManagement;
using System.IO;
using DropTheCat.Core;
using DropTheCat.Domain;
using DropTheCat.Game;

/// <summary>
/// One-click editor tool that creates all scenes, prefabs, and folder structure
/// for the "Drop the Cat" game so it is immediately playable.
/// </summary>
/// <remarks>
/// Menu: DropTheCat > Setup Game
/// </remarks>
public class GameSetup : Editor
{
    #region Constants

    private const string SPRITES_PATH = "Assets/Sprites";
    private const string PREFABS_PATH = "Assets/Prefabs";
    private const string SCENES_PATH = "Assets/Scenes";
    private const string WHITE_SQUARE_PATH = "Assets/Sprites/WhiteSquare.png";

    private const string CAT_PREFAB_PATH = "Assets/Prefabs/Cat.prefab";
    private const string TILE_PREFAB_PATH = "Assets/Prefabs/Tile.prefab";
    private const string HOLE_PREFAB_PATH = "Assets/Prefabs/Hole.prefab";
    private const string GROUND_PREFAB_PATH = "Assets/Prefabs/Ground.prefab";
    private const string WALL_PREFAB_PATH = "Assets/Prefabs/Wall.prefab";
    private const string HOLE_MARKER_PREFAB_PATH = "Assets/Prefabs/HoleMarker.prefab";
    private const string LEVEL_BUTTON_PREFAB_PATH = "Assets/Prefabs/LevelButton.prefab";

    private const string TITLE_SCENE_PATH = "Assets/Scenes/Title.unity";
    private const string MAIN_SCENE_PATH = "Assets/Scenes/Main.unity";
    private const string GAME_SCENE_PATH = "Assets/Scenes/GameScene.unity";

    #endregion

    #region Menu Item

    [MenuItem("DropTheCat/Setup Game")]
    public static void SetupGame()
    {
        if (!EditorUtility.DisplayDialog(
            "DropTheCat Setup",
            "This will create scenes, prefabs, and configure the project. Proceed?",
            "Yes",
            "Cancel"))
        {
            return;
        }

        try
        {
            AssetDatabase.StartAssetEditing();

            // Step 1: Create folder structure
            EditorUtility.DisplayProgressBar("DropTheCat Setup", "Creating folders...", 0.05f);
            CreateFolders();

            // Step 2: Create white square sprite
            EditorUtility.DisplayProgressBar("DropTheCat Setup", "Creating sprite asset...", 0.10f);
            CreateWhiteSquareSprite();
        }
        finally
        {
            AssetDatabase.StopAssetEditing();
        }

        // Import and configure the sprite outside of StartAssetEditing block
        AssetDatabase.Refresh();
        ConfigureWhiteSquareImporter();

        Sprite whiteSquare = LoadWhiteSquareSprite();
        if (whiteSquare == null)
        {
            Debug.LogError("[GameSetup] Failed to load WhiteSquare sprite. Aborting.");
            EditorUtility.ClearProgressBar();
            return;
        }

        try
        {
            // Step 3: Create prefabs
            EditorUtility.DisplayProgressBar("DropTheCat Setup", "Creating prefabs...", 0.20f);
            CreatePrefabs(whiteSquare);

            // Step 4: Create Title scene
            EditorUtility.DisplayProgressBar("DropTheCat Setup", "Creating Title scene...", 0.40f);
            CreateTitleScene();

            // Step 5: Create Main scene
            EditorUtility.DisplayProgressBar("DropTheCat Setup", "Creating Main scene...", 0.60f);
            CreateMainScene();

            // Step 6: Create GameScene
            EditorUtility.DisplayProgressBar("DropTheCat Setup", "Creating GameScene...", 0.80f);
            CreateGameScene();

            // Step 7: Set Build Settings
            EditorUtility.DisplayProgressBar("DropTheCat Setup", "Configuring build settings...", 0.95f);
            SetBuildSettings();

            // Step 8: Open Title scene and log completion
            EditorUtility.DisplayProgressBar("DropTheCat Setup", "Finalizing...", 1.0f);
            EditorSceneManager.OpenScene(TITLE_SCENE_PATH);

            Debug.Log("[GameSetup] Setup complete. Title scene opened. All 3 scenes, 7 prefabs, and build settings configured.");
        }
        finally
        {
            EditorUtility.ClearProgressBar();
        }
    }

    #endregion

    #region Step 1: Folder Structure

    private static void CreateFolders()
    {
        CreateFolderIfMissing("Assets", "Prefabs");
        CreateFolderIfMissing("Assets", "Sprites");
        CreateFolderIfMissing("Assets", "Scenes");
    }

    private static void CreateFolderIfMissing(string parent, string folderName)
    {
        string fullPath = parent + "/" + folderName;
        if (!AssetDatabase.IsValidFolder(fullPath))
        {
            AssetDatabase.CreateFolder(parent, folderName);
        }
    }

    #endregion

    #region Step 2: White Square Sprite

    private static void CreateWhiteSquareSprite()
    {
        if (File.Exists(WHITE_SQUARE_PATH)) return;

        Texture2D tex = new Texture2D(64, 64, TextureFormat.RGBA32, false);
        Color[] pixels = new Color[64 * 64];
        for (int i = 0; i < pixels.Length; i++)
        {
            pixels[i] = Color.white;
        }
        tex.SetPixels(pixels);
        tex.Apply();

        byte[] pngData = tex.EncodeToPNG();
        Object.DestroyImmediate(tex);

        string directory = Path.GetDirectoryName(WHITE_SQUARE_PATH);
        if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
        {
            Directory.CreateDirectory(directory);
        }

        File.WriteAllBytes(WHITE_SQUARE_PATH, pngData);
    }

    private static void ConfigureWhiteSquareImporter()
    {
        AssetDatabase.ImportAsset(WHITE_SQUARE_PATH, ImportAssetOptions.ForceUpdate);

        TextureImporter importer = AssetImporter.GetAtPath(WHITE_SQUARE_PATH) as TextureImporter;
        if (importer != null)
        {
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = 64;
            importer.filterMode = FilterMode.Point;
            importer.SaveAndReimport();
        }

        AssetDatabase.Refresh();
    }

    private static Sprite LoadWhiteSquareSprite()
    {
        Sprite sprite = AssetDatabase.LoadAssetAtPath<Sprite>(WHITE_SQUARE_PATH);
        if (sprite != null) return sprite;

        // Fallback: load as Texture2D and create sprite manually
        Texture2D tex = AssetDatabase.LoadAssetAtPath<Texture2D>(WHITE_SQUARE_PATH);
        if (tex != null)
        {
            sprite = Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f), 64f);
        }
        return sprite;
    }

    #endregion

    #region Step 3: Create Prefabs

    private static void CreatePrefabs(Sprite whiteSquare)
    {
        CreateCatPrefab(whiteSquare);
        CreateTilePrefab(whiteSquare);
        CreateHolePrefab(whiteSquare);
        CreateGroundPrefab(whiteSquare);
        CreateWallPrefab(whiteSquare);
        CreateHoleMarkerPrefab(whiteSquare);
        CreateLevelButtonPrefab();
    }

    private static void CreateCatPrefab(Sprite whiteSquare)
    {
        GameObject go = new GameObject("Cat");
        go.transform.localScale = new Vector3(0.7f, 0.7f, 1f);

        SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = whiteSquare;
        sr.color = Color.white;
        sr.sortingOrder = 2;

        CatController cat = go.AddComponent<CatController>();
        WireSerializedField(cat, "spriteRenderer", sr);

        PrefabUtility.SaveAsPrefabAsset(go, CAT_PREFAB_PATH);
        Object.DestroyImmediate(go);
    }

    private static void CreateTilePrefab(Sprite whiteSquare)
    {
        GameObject go = new GameObject("Tile");
        go.transform.localScale = new Vector3(0.9f, 0.9f, 1f);

        SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = whiteSquare;
        sr.color = new Color(0.95f, 0.95f, 0.9f);
        sr.sortingOrder = 1;

        TileController tile = go.AddComponent<TileController>();
        WireSerializedField(tile, "spriteRenderer", sr);

        PrefabUtility.SaveAsPrefabAsset(go, TILE_PREFAB_PATH);
        Object.DestroyImmediate(go);
    }

    private static void CreateHolePrefab(Sprite whiteSquare)
    {
        GameObject go = new GameObject("Hole");
        go.transform.localScale = new Vector3(0.6f, 0.6f, 1f);

        SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = whiteSquare;
        sr.color = Color.white;
        sr.sortingOrder = 2;

        HoleController hole = go.AddComponent<HoleController>();
        WireSerializedField(hole, "spriteRenderer", sr);

        PrefabUtility.SaveAsPrefabAsset(go, HOLE_PREFAB_PATH);
        Object.DestroyImmediate(go);
    }

    private static void CreateGroundPrefab(Sprite whiteSquare)
    {
        GameObject go = new GameObject("Ground");

        SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = whiteSquare;
        sr.color = new Color(0.92f, 0.92f, 0.88f);
        sr.sortingOrder = 0;

        PrefabUtility.SaveAsPrefabAsset(go, GROUND_PREFAB_PATH);
        Object.DestroyImmediate(go);
    }

    private static void CreateWallPrefab(Sprite whiteSquare)
    {
        GameObject go = new GameObject("Wall");

        SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = whiteSquare;
        sr.color = new Color(0.3f, 0.3f, 0.3f);
        sr.sortingOrder = 0;

        PrefabUtility.SaveAsPrefabAsset(go, WALL_PREFAB_PATH);
        Object.DestroyImmediate(go);
    }

    private static void CreateHoleMarkerPrefab(Sprite whiteSquare)
    {
        GameObject go = new GameObject("HoleMarker");
        go.transform.localScale = new Vector3(0.5f, 0.5f, 1f);

        SpriteRenderer sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = whiteSquare;
        sr.color = new Color(0.15f, 0.15f, 0.15f);
        sr.sortingOrder = 0;

        PrefabUtility.SaveAsPrefabAsset(go, HOLE_MARKER_PREFAB_PATH);
        Object.DestroyImmediate(go);
    }

    private static void CreateLevelButtonPrefab()
    {
        GameObject go = new GameObject("LevelButton");
        RectTransform rt = go.AddComponent<RectTransform>();
        rt.sizeDelta = new Vector2(160f, 160f);

        Image img = go.AddComponent<Image>();
        img.color = Color.white;

        go.AddComponent<Button>();

        // Child Text
        GameObject textGo = new GameObject("Text");
        textGo.transform.SetParent(go.transform, false);

        RectTransform textRt = textGo.AddComponent<RectTransform>();
        textRt.anchorMin = Vector2.zero;
        textRt.anchorMax = Vector2.one;
        textRt.offsetMin = Vector2.zero;
        textRt.offsetMax = Vector2.zero;

        Text text = textGo.AddComponent<Text>();
        text.text = "1";
        text.fontSize = 28;
        text.color = Color.black;
        text.alignment = TextAnchor.MiddleCenter;
        text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        PrefabUtility.SaveAsPrefabAsset(go, LEVEL_BUTTON_PREFAB_PATH);
        Object.DestroyImmediate(go);
    }

    #endregion

    #region Step 4: Title Scene

    private static void CreateTitleScene()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        // Main Camera
        GameObject camGo = new GameObject("Main Camera");
        camGo.tag = "MainCamera";
        Camera cam = camGo.AddComponent<Camera>();
        cam.orthographic = true;
        cam.orthographicSize = 6f;
        cam.transform.position = new Vector3(0f, 0f, -10f);
        cam.backgroundColor = new Color(0.2f, 0.2f, 0.3f);
        cam.clearFlags = CameraClearFlags.SolidColor;
        camGo.AddComponent<AudioListener>();

        // Managers
        GameObject managersGo = new GameObject("Managers");
        managersGo.AddComponent<EventManager>();
        managersGo.AddComponent<SaveManager>();
        managersGo.AddComponent<SoundManager>();
        managersGo.AddComponent<ObjectPool>();

        // Domain managers
        managersGo.AddComponent<GridManager>();
        managersGo.AddComponent<LevelDataProvider>();
        managersGo.AddComponent<CurrencyManager>();
        managersGo.AddComponent<ObstacleManager>();
        managersGo.AddComponent<SlideProcessor>();
        managersGo.AddComponent<BoosterManager>();

        // ColorMatcher and ScoreCalculator (plain MonoBehaviour)
        ColorMatcher colorMatcher = managersGo.AddComponent<ColorMatcher>();
        ScoreCalculator scoreCalculator = managersGo.AddComponent<ScoreCalculator>();

        // DropProcessor with wired references
        DropProcessor dropProcessor = managersGo.AddComponent<DropProcessor>();
        WireSerializedField(dropProcessor, "_colorMatcher", colorMatcher);
        WireSerializedField(dropProcessor, "_scoreCalculator", scoreCalculator);

        // LevelManager with wired levelDataProvider
        LevelManager levelManager = managersGo.AddComponent<LevelManager>();
        LevelDataProvider ldp = managersGo.GetComponent<LevelDataProvider>();
        WireSerializedField(levelManager, "levelDataProvider", ldp);

        // GameManager with wired scoreCalculator
        GameManager gameManager = managersGo.AddComponent<GameManager>();
        WireSerializedField(gameManager, "scoreCalculator", scoreCalculator);

        // Canvas
        GameObject canvasGo = CreateCanvas("Canvas");

        // EventSystem
        CreateEventSystem();

        // Logo (Image)
        GameObject logoGo = CreateUIElement("Logo", canvasGo.transform);
        RectTransform logoRt = logoGo.GetComponent<RectTransform>();
        logoRt.anchorMin = new Vector2(0.5f, 0.5f);
        logoRt.anchorMax = new Vector2(0.5f, 0.5f);
        logoRt.pivot = new Vector2(0.5f, 0.5f);
        logoRt.anchoredPosition = Vector2.zero;
        logoRt.sizeDelta = new Vector2(400f, 200f);
        Image logoImg = logoGo.AddComponent<Image>();
        logoImg.color = new Color(0.9f, 0.5f, 0.2f);

        // LoadingBar (Slider)
        GameObject sliderGo = CreateSlider("LoadingBar", canvasGo.transform);
        RectTransform sliderRt = sliderGo.GetComponent<RectTransform>();
        sliderRt.anchorMin = new Vector2(0.5f, 0.5f);
        sliderRt.anchorMax = new Vector2(0.5f, 0.5f);
        sliderRt.pivot = new Vector2(0.5f, 0.5f);
        sliderRt.anchoredPosition = new Vector2(0f, -200f);
        sliderRt.sizeDelta = new Vector2(600f, 30f);

        // VersionText
        GameObject versionGo = CreateTextElement("VersionText", canvasGo.transform, "v1.0", 24, Color.white, TextAnchor.MiddleCenter);
        RectTransform versionRt = versionGo.GetComponent<RectTransform>();
        versionRt.anchorMin = new Vector2(0.5f, 0f);
        versionRt.anchorMax = new Vector2(0.5f, 0f);
        versionRt.pivot = new Vector2(0.5f, 0f);
        versionRt.anchoredPosition = new Vector2(0f, 30f);
        versionRt.sizeDelta = new Vector2(200f, 40f);

        // TitlePage component on Canvas
        TitlePage titlePage = canvasGo.AddComponent<TitlePage>();
        WireSerializedField(titlePage, "logo", logoImg);
        WireSerializedField(titlePage, "loadingBar", sliderGo.GetComponent<Slider>());
        WireSerializedField(titlePage, "versionText", versionGo.GetComponent<Text>());

        EditorSceneManager.SaveScene(scene, TITLE_SCENE_PATH);
    }

    #endregion

    #region Step 5: Main Scene

    private static void CreateMainScene()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        // Main Camera
        GameObject camGo = new GameObject("Main Camera");
        camGo.tag = "MainCamera";
        Camera cam = camGo.AddComponent<Camera>();
        cam.orthographic = true;
        cam.orthographicSize = 6f;
        cam.transform.position = new Vector3(0f, 0f, -10f);
        cam.backgroundColor = new Color(0.2f, 0.2f, 0.3f);
        cam.clearFlags = CameraClearFlags.SolidColor;
        camGo.AddComponent<AudioListener>();

        // Canvas
        GameObject canvasGo = CreateCanvas("Canvas");

        // EventSystem
        CreateEventSystem();

        // Header panel
        GameObject headerGo = CreateUIElement("Header", canvasGo.transform);
        RectTransform headerRt = headerGo.GetComponent<RectTransform>();
        headerRt.anchorMin = new Vector2(0f, 1f);
        headerRt.anchorMax = new Vector2(1f, 1f);
        headerRt.pivot = new Vector2(0.5f, 1f);
        headerRt.anchoredPosition = Vector2.zero;
        headerRt.sizeDelta = new Vector2(0f, 120f);

        // CoinText in header
        GameObject coinTextGo = CreateTextElement("CoinText", headerGo.transform, "0", 32, Color.white, TextAnchor.MiddleRight);
        RectTransform coinRt = coinTextGo.GetComponent<RectTransform>();
        coinRt.anchorMin = new Vector2(1f, 0.5f);
        coinRt.anchorMax = new Vector2(1f, 0.5f);
        coinRt.pivot = new Vector2(1f, 0.5f);
        coinRt.anchoredPosition = new Vector2(-30f, 0f);
        coinRt.sizeDelta = new Vector2(300f, 60f);

        // LevelScroll (ScrollRect)
        GameObject scrollGo = CreateUIElement("LevelScroll", canvasGo.transform);
        RectTransform scrollRt = scrollGo.GetComponent<RectTransform>();
        scrollRt.anchorMin = new Vector2(0.5f, 0.5f);
        scrollRt.anchorMax = new Vector2(0.5f, 0.5f);
        scrollRt.pivot = new Vector2(0.5f, 0.5f);
        scrollRt.anchoredPosition = Vector2.zero;
        scrollRt.sizeDelta = new Vector2(900f, 1200f);
        ScrollRect scrollRect = scrollGo.AddComponent<ScrollRect>();
        scrollGo.AddComponent<Image>().color = new Color(0f, 0f, 0f, 0.05f); // slight bg

        // Viewport
        GameObject viewportGo = CreateUIElement("Viewport", scrollGo.transform);
        RectTransform viewportRt = viewportGo.GetComponent<RectTransform>();
        viewportRt.anchorMin = Vector2.zero;
        viewportRt.anchorMax = Vector2.one;
        viewportRt.offsetMin = Vector2.zero;
        viewportRt.offsetMax = Vector2.zero;
        viewportGo.AddComponent<Image>().color = Color.white;
        viewportGo.AddComponent<Mask>().showMaskGraphic = false;

        // Content inside Viewport
        GameObject contentGo = CreateUIElement("Content", viewportGo.transform);
        RectTransform contentRt = contentGo.GetComponent<RectTransform>();
        contentRt.anchorMin = new Vector2(0f, 1f);
        contentRt.anchorMax = new Vector2(1f, 1f);
        contentRt.pivot = new Vector2(0.5f, 1f);
        contentRt.anchoredPosition = Vector2.zero;
        contentRt.sizeDelta = new Vector2(0f, 0f);

        VerticalLayoutGroup vlg = contentGo.AddComponent<VerticalLayoutGroup>();
        vlg.spacing = 10f;
        vlg.childAlignment = TextAnchor.UpperCenter;
        vlg.childControlWidth = false;
        vlg.childControlHeight = false;
        vlg.childForceExpandWidth = false;
        vlg.childForceExpandHeight = false;

        ContentSizeFitter csf = contentGo.AddComponent<ContentSizeFitter>();
        csf.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

        scrollRect.viewport = viewportRt;
        scrollRect.content = contentRt;
        scrollRect.horizontal = false;
        scrollRect.vertical = true;

        // SettingsButton
        GameObject settingsGo = CreateButtonElement("SettingsButton", canvasGo.transform, "\u2699", 36);
        RectTransform settingsRt = settingsGo.GetComponent<RectTransform>();
        settingsRt.anchorMin = new Vector2(0f, 0f);
        settingsRt.anchorMax = new Vector2(0f, 0f);
        settingsRt.pivot = new Vector2(0f, 0f);
        settingsRt.anchoredPosition = new Vector2(30f, 30f);
        settingsRt.sizeDelta = new Vector2(120f, 120f);

        // ShopButton
        GameObject shopGo = CreateButtonElement("ShopButton", canvasGo.transform, "\uD83D\uDED2", 36);
        RectTransform shopRt = shopGo.GetComponent<RectTransform>();
        shopRt.anchorMin = new Vector2(1f, 0f);
        shopRt.anchorMax = new Vector2(1f, 0f);
        shopRt.pivot = new Vector2(1f, 0f);
        shopRt.anchoredPosition = new Vector2(-30f, 30f);
        shopRt.sizeDelta = new Vector2(120f, 120f);

        // Load LevelButton prefab
        GameObject levelButtonPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(LEVEL_BUTTON_PREFAB_PATH);
        Button levelButtonPrefabBtn = levelButtonPrefab != null ? levelButtonPrefab.GetComponent<Button>() : null;

        // MainPage component on Canvas
        MainPage mainPage = canvasGo.AddComponent<MainPage>();
        WireSerializedField(mainPage, "levelScrollRect", scrollRect);
        WireSerializedField(mainPage, "levelButtonContainer", contentRt);
        if (levelButtonPrefabBtn != null)
        {
            WireSerializedField(mainPage, "levelButtonPrefab", levelButtonPrefabBtn);
        }
        WireSerializedField(mainPage, "coinText", coinTextGo.GetComponent<Text>());
        WireSerializedField(mainPage, "settingsButton", settingsGo.GetComponent<Button>());
        WireSerializedField(mainPage, "shopButton", shopGo.GetComponent<Button>());

        EditorSceneManager.SaveScene(scene, MAIN_SCENE_PATH);
    }

    #endregion

    #region Step 6: Game Scene

    private static void CreateGameScene()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        // Main Camera
        GameObject camGo = new GameObject("Main Camera");
        camGo.tag = "MainCamera";
        Camera cam = camGo.AddComponent<Camera>();
        cam.orthographic = true;
        cam.orthographicSize = 6f;
        cam.transform.position = new Vector3(0f, 0f, -10f);
        cam.backgroundColor = new Color(0.15f, 0.15f, 0.25f);
        cam.clearFlags = CameraClearFlags.SolidColor;
        camGo.AddComponent<AudioListener>();

        // Canvas
        GameObject canvasGo = CreateCanvas("Canvas");

        // EventSystem
        CreateEventSystem();

        // --- Top Bar ---

        // LevelText
        GameObject levelTextGo = CreateTextElement("LevelText", canvasGo.transform, "Level 1", 36, Color.white, TextAnchor.MiddleCenter);
        RectTransform levelTextRt = levelTextGo.GetComponent<RectTransform>();
        levelTextRt.anchorMin = new Vector2(0.5f, 1f);
        levelTextRt.anchorMax = new Vector2(0.5f, 1f);
        levelTextRt.pivot = new Vector2(0.5f, 1f);
        levelTextRt.anchoredPosition = new Vector2(0f, -20f);
        levelTextRt.sizeDelta = new Vector2(400f, 60f);

        // MoveCountText
        GameObject moveCountGo = CreateTextElement("MoveCountText", canvasGo.transform, "0", 32, Color.white, TextAnchor.MiddleRight);
        RectTransform moveCountRt = moveCountGo.GetComponent<RectTransform>();
        moveCountRt.anchorMin = new Vector2(1f, 1f);
        moveCountRt.anchorMax = new Vector2(1f, 1f);
        moveCountRt.pivot = new Vector2(1f, 1f);
        moveCountRt.anchoredPosition = new Vector2(-30f, -20f);
        moveCountRt.sizeDelta = new Vector2(200f, 60f);

        // PauseButton
        GameObject pauseGo = CreateButtonElement("PauseButton", canvasGo.transform, "\u275A\u275A", 28);
        RectTransform pauseRt = pauseGo.GetComponent<RectTransform>();
        pauseRt.anchorMin = new Vector2(0f, 1f);
        pauseRt.anchorMax = new Vector2(0f, 1f);
        pauseRt.pivot = new Vector2(0f, 1f);
        pauseRt.anchoredPosition = new Vector2(20f, -20f);
        pauseRt.sizeDelta = new Vector2(80f, 80f);

        // --- Bottom Bar: Booster Buttons ---

        // Hint Button
        GameObject hintGo = CreateBoosterButton("HintButton", canvasGo.transform, "Hint", 0);
        GameObject hintCountGo = hintGo.transform.Find("CountText").gameObject;

        // Undo Button
        GameObject undoGo = CreateBoosterButton("UndoButton", canvasGo.transform, "Undo", 1);
        GameObject undoCountGo = undoGo.transform.Find("CountText").gameObject;

        // Magnet Button
        GameObject magnetGo = CreateBoosterButton("MagnetButton", canvasGo.transform, "Magnet", 2);
        GameObject magnetCountGo = magnetGo.transform.Find("CountText").gameObject;

        // Shuffle Button
        GameObject shuffleGo = CreateBoosterButton("ShuffleButton", canvasGo.transform, "Shuffle", 3);
        GameObject shuffleCountGo = shuffleGo.transform.Find("CountText").gameObject;

        // GamePage component on Canvas
        GamePage gamePage = canvasGo.AddComponent<GamePage>();
        WireSerializedField(gamePage, "levelText", levelTextGo.GetComponent<Text>());
        WireSerializedField(gamePage, "moveCountText", moveCountGo.GetComponent<Text>());
        WireSerializedField(gamePage, "pauseButton", pauseGo.GetComponent<Button>());
        WireSerializedField(gamePage, "hintButton", hintGo.GetComponent<Button>());
        WireSerializedField(gamePage, "undoButton", undoGo.GetComponent<Button>());
        WireSerializedField(gamePage, "magnetButton", magnetGo.GetComponent<Button>());
        WireSerializedField(gamePage, "shuffleButton", shuffleGo.GetComponent<Button>());
        WireSerializedField(gamePage, "hintCountText", hintCountGo.GetComponent<Text>());
        WireSerializedField(gamePage, "undoCountText", undoCountGo.GetComponent<Text>());
        WireSerializedField(gamePage, "magnetCountText", magnetCountGo.GetComponent<Text>());
        WireSerializedField(gamePage, "shuffleCountText", shuffleCountGo.GetComponent<Text>());

        // GridVisualizer
        GameObject gridVisGo = new GameObject("GridVisualizer");
        GridVisualizer gridVis = gridVisGo.AddComponent<GridVisualizer>();

        // Load prefab assets and wire to GridVisualizer
        GameObject tilePrefab = AssetDatabase.LoadAssetAtPath<GameObject>(TILE_PREFAB_PATH);
        GameObject catPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(CAT_PREFAB_PATH);
        GameObject holePrefab = AssetDatabase.LoadAssetAtPath<GameObject>(HOLE_PREFAB_PATH);
        GameObject groundPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(GROUND_PREFAB_PATH);
        GameObject wallPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(WALL_PREFAB_PATH);
        GameObject holeMarkerPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(HOLE_MARKER_PREFAB_PATH);

        if (tilePrefab != null)
            WireSerializedField(gridVis, "tilePrefab", tilePrefab.GetComponent<TileController>());
        if (catPrefab != null)
            WireSerializedField(gridVis, "catPrefab", catPrefab.GetComponent<CatController>());
        if (holePrefab != null)
            WireSerializedField(gridVis, "holePrefab", holePrefab.GetComponent<HoleController>());
        if (groundPrefab != null)
            WireSerializedField(gridVis, "groundPrefab", groundPrefab.GetComponent<SpriteRenderer>());
        if (wallPrefab != null)
            WireSerializedField(gridVis, "wallPrefab", wallPrefab.GetComponent<SpriteRenderer>());
        if (holeMarkerPrefab != null)
            WireSerializedField(gridVis, "holeMarkerPrefab", holeMarkerPrefab.GetComponent<SpriteRenderer>());

        EditorSceneManager.SaveScene(scene, GAME_SCENE_PATH);
    }

    #endregion

    #region Step 7: Build Settings

    private static void SetBuildSettings()
    {
        EditorBuildSettings.scenes = new[]
        {
            new EditorBuildSettingsScene(TITLE_SCENE_PATH, true),
            new EditorBuildSettingsScene(MAIN_SCENE_PATH, true),
            new EditorBuildSettingsScene(GAME_SCENE_PATH, true)
        };
    }

    #endregion

    #region Helper Methods

    /// <summary>
    /// Wire a SerializedField reference on a component using SerializedObject.
    /// Works with private [SerializeField] fields.
    /// </summary>
    private static void WireSerializedField(Component component, string fieldName, Object value)
    {
        SerializedObject so = new SerializedObject(component);
        SerializedProperty prop = so.FindProperty(fieldName);
        if (prop != null)
        {
            prop.objectReferenceValue = value;
            so.ApplyModifiedProperties();
        }
        else
        {
            Debug.LogWarning($"[GameSetup] Could not find property '{fieldName}' on {component.GetType().Name}");
        }
    }

    /// <summary>
    /// Create a standard Canvas with CanvasScaler (1080x1920) and GraphicRaycaster.
    /// </summary>
    private static GameObject CreateCanvas(string name)
    {
        GameObject canvasGo = new GameObject(name);
        Canvas canvas = canvasGo.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;

        CanvasScaler scaler = canvasGo.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1080f, 1920f);
        scaler.matchWidthOrHeight = 0.5f;

        canvasGo.AddComponent<GraphicRaycaster>();

        return canvasGo;
    }

    /// <summary>
    /// Create a standard EventSystem with StandaloneInputModule.
    /// </summary>
    private static GameObject CreateEventSystem()
    {
        GameObject esGo = new GameObject("EventSystem");
        esGo.AddComponent<EventSystem>();
        esGo.AddComponent<StandaloneInputModule>();
        return esGo;
    }

    /// <summary>
    /// Create an empty UI element with RectTransform.
    /// </summary>
    private static GameObject CreateUIElement(string name, Transform parent)
    {
        GameObject go = new GameObject(name);
        go.transform.SetParent(parent, false);
        go.AddComponent<RectTransform>();
        return go;
    }

    /// <summary>
    /// Create a Text UI element with the specified properties.
    /// </summary>
    private static GameObject CreateTextElement(
        string name, Transform parent, string text, int fontSize, Color color, TextAnchor alignment)
    {
        GameObject go = new GameObject(name);
        go.transform.SetParent(parent, false);

        RectTransform rt = go.AddComponent<RectTransform>();
        rt.sizeDelta = new Vector2(200f, 50f);

        Text textComp = go.AddComponent<Text>();
        textComp.text = text;
        textComp.fontSize = fontSize;
        textComp.color = color;
        textComp.alignment = alignment;
        textComp.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        return go;
    }

    /// <summary>
    /// Create a Button UI element with an Image background and child Text.
    /// </summary>
    private static GameObject CreateButtonElement(string name, Transform parent, string label, int fontSize)
    {
        GameObject go = new GameObject(name);
        go.transform.SetParent(parent, false);

        RectTransform rt = go.AddComponent<RectTransform>();
        rt.sizeDelta = new Vector2(120f, 120f);

        Image img = go.AddComponent<Image>();
        img.color = Color.white;

        go.AddComponent<Button>();

        // Child text
        GameObject textGo = new GameObject("Text");
        textGo.transform.SetParent(go.transform, false);

        RectTransform textRt = textGo.AddComponent<RectTransform>();
        textRt.anchorMin = Vector2.zero;
        textRt.anchorMax = Vector2.one;
        textRt.offsetMin = Vector2.zero;
        textRt.offsetMax = Vector2.zero;

        Text textComp = textGo.AddComponent<Text>();
        textComp.text = label;
        textComp.fontSize = fontSize;
        textComp.color = Color.black;
        textComp.alignment = TextAnchor.MiddleCenter;
        textComp.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        return go;
    }

    /// <summary>
    /// Create a booster button (120x120) with a label and a CountText child.
    /// Positioned at the bottom of the screen, indexed left to right (0-3).
    /// </summary>
    private static GameObject CreateBoosterButton(string name, Transform parent, string label, int index)
    {
        GameObject go = new GameObject(name);
        go.transform.SetParent(parent, false);

        RectTransform rt = go.AddComponent<RectTransform>();
        rt.anchorMin = new Vector2(0f, 0f);
        rt.anchorMax = new Vector2(0f, 0f);
        rt.pivot = new Vector2(0f, 0f);
        // Position 4 buttons evenly along the bottom: offsets at ~90, 240, 390, 540
        float xOffset = 90f + index * 240f;
        rt.anchoredPosition = new Vector2(xOffset, 30f);
        rt.sizeDelta = new Vector2(120f, 120f);

        Image img = go.AddComponent<Image>();
        img.color = new Color(0.85f, 0.85f, 0.85f);

        go.AddComponent<Button>();

        // Label text
        GameObject labelGo = new GameObject("Label");
        labelGo.transform.SetParent(go.transform, false);

        RectTransform labelRt = labelGo.AddComponent<RectTransform>();
        labelRt.anchorMin = new Vector2(0f, 0.3f);
        labelRt.anchorMax = new Vector2(1f, 1f);
        labelRt.offsetMin = Vector2.zero;
        labelRt.offsetMax = Vector2.zero;

        Text labelText = labelGo.AddComponent<Text>();
        labelText.text = label;
        labelText.fontSize = 20;
        labelText.color = Color.black;
        labelText.alignment = TextAnchor.MiddleCenter;
        labelText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        // Count text
        GameObject countGo = new GameObject("CountText");
        countGo.transform.SetParent(go.transform, false);

        RectTransform countRt = countGo.AddComponent<RectTransform>();
        countRt.anchorMin = new Vector2(0f, 0f);
        countRt.anchorMax = new Vector2(1f, 0.3f);
        countRt.offsetMin = Vector2.zero;
        countRt.offsetMax = Vector2.zero;

        Text countText = countGo.AddComponent<Text>();
        countText.text = "0";
        countText.fontSize = 18;
        countText.color = Color.black;
        countText.alignment = TextAnchor.MiddleCenter;
        countText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        return go;
    }

    /// <summary>
    /// Create a minimal Slider UI element for loading bar use.
    /// </summary>
    private static GameObject CreateSlider(string name, Transform parent)
    {
        GameObject go = new GameObject(name);
        go.transform.SetParent(parent, false);
        go.AddComponent<RectTransform>();

        // Background
        GameObject bgGo = new GameObject("Background");
        bgGo.transform.SetParent(go.transform, false);
        RectTransform bgRt = bgGo.AddComponent<RectTransform>();
        bgRt.anchorMin = Vector2.zero;
        bgRt.anchorMax = Vector2.one;
        bgRt.offsetMin = Vector2.zero;
        bgRt.offsetMax = Vector2.zero;
        Image bgImg = bgGo.AddComponent<Image>();
        bgImg.color = new Color(0.3f, 0.3f, 0.3f);

        // Fill Area
        GameObject fillAreaGo = new GameObject("Fill Area");
        fillAreaGo.transform.SetParent(go.transform, false);
        RectTransform fillAreaRt = fillAreaGo.AddComponent<RectTransform>();
        fillAreaRt.anchorMin = Vector2.zero;
        fillAreaRt.anchorMax = Vector2.one;
        fillAreaRt.offsetMin = new Vector2(5f, 5f);
        fillAreaRt.offsetMax = new Vector2(-5f, -5f);

        // Fill
        GameObject fillGo = new GameObject("Fill");
        fillGo.transform.SetParent(fillAreaGo.transform, false);
        RectTransform fillRt = fillGo.AddComponent<RectTransform>();
        fillRt.anchorMin = Vector2.zero;
        fillRt.anchorMax = Vector2.one;
        fillRt.offsetMin = Vector2.zero;
        fillRt.offsetMax = Vector2.zero;
        Image fillImg = fillGo.AddComponent<Image>();
        fillImg.color = new Color(0.9f, 0.5f, 0.2f);

        // Slider component
        Slider slider = go.AddComponent<Slider>();
        slider.fillRect = fillRt;
        slider.minValue = 0f;
        slider.maxValue = 1f;
        slider.value = 0f;
        slider.interactable = false;

        // Hide the handle
        slider.handleRect = null;

        return go;
    }

    #endregion
}
