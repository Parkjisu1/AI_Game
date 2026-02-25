using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.UI;

namespace BlockBlast.Editor
{
    [InitializeOnLoad]
    public class SceneBuilder
    {
        private const string PREF_KEY = "GameForge_SceneBuilt_BlockBlastPuzzle";

        static SceneBuilder()
        {
            EditorApplication.delayCall += () =>
            {
                if (EditorPrefs.GetBool(PREF_KEY, false)) return;

                if (EditorApplication.isPlayingOrWillChangePlaymode) return;

                Debug.Log("[GameForge] SceneBuilder: Building scenes for BlockBlastPuzzle...");
                BuildAllScenes();
                EditorPrefs.SetBool(PREF_KEY, true);
                Debug.Log("[GameForge] SceneBuilder: Complete!");
            };
        }

        [MenuItem("GameForge/Rebuild Scenes (Force)")]
        public static void ForceRebuild()
        {
            EditorPrefs.DeleteKey(PREF_KEY);
            BuildAllScenes();
            EditorPrefs.SetBool(PREF_KEY, true);
        }

        private static void BuildAllScenes()
        {
            if (!AssetDatabase.IsValidFolder("Assets/Scenes"))
                AssetDatabase.CreateFolder("Assets", "Scenes");

            BuildTitleScene();
            BuildMainScene();
            BuildGameScene();
            RegisterBuildSettings();

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
        }

        // ============================================================
        // Title Scene
        // ============================================================
        private static void BuildTitleScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // --- Main Camera ---
            var camGo = new GameObject("Main Camera");
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 10f;
            cam.backgroundColor = new Color(0.05f, 0.05f, 0.12f, 1f);
            cam.clearFlags = CameraClearFlags.SolidColor;
            camGo.transform.position = new Vector3(0, 0, -10);
            camGo.tag = "MainCamera";
            camGo.AddComponent<AudioListener>();

            // --- Canvas ---
            var canvasGo = CreateCanvas();

            // --- EventSystem ---
            CreateEventSystem();

            // --- TitleController (handles all UI creation in Start) ---
            var titleCtrl = new GameObject("TitleController");
            titleCtrl.AddComponent<Game.TitleController>();

            EditorSceneManager.SaveScene(scene, "Assets/Scenes/Title.unity");
        }

        // ============================================================
        // Main Scene
        // ============================================================
        private static void BuildMainScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // --- Main Camera ---
            var camGo = new GameObject("Main Camera");
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 10f;
            cam.backgroundColor = new Color(0.05f, 0.05f, 0.12f, 1f);
            cam.clearFlags = CameraClearFlags.SolidColor;
            camGo.transform.position = new Vector3(0, 0, -10);
            camGo.tag = "MainCamera";
            camGo.AddComponent<AudioListener>();

            // --- Canvas ---
            var canvasGo = CreateCanvas();

            // --- EventSystem ---
            CreateEventSystem();

            // --- MainMenuController (handles all UI creation in Start) ---
            var menuCtrl = new GameObject("MainMenuController");
            menuCtrl.AddComponent<Game.MainMenuController>();

            EditorSceneManager.SaveScene(scene, "Assets/Scenes/Main.unity");
        }

        // ============================================================
        // Game Scene
        // ============================================================
        private static void BuildGameScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // --- Main Camera ---
            var camGo = new GameObject("Main Camera");
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 10f;
            cam.backgroundColor = new Color(0.05f, 0.05f, 0.12f, 1f);
            cam.clearFlags = CameraClearFlags.SolidColor;
            camGo.transform.position = new Vector3(0, 2f, -10f);
            camGo.tag = "MainCamera";
            camGo.AddComponent<AudioListener>();

            // --- Canvas ---
            var canvasGo = CreateCanvas();

            // --- EventSystem ---
            CreateEventSystem();

            // --- Managers (all singletons on one object) ---
            var managersGo = new GameObject("Managers");
            managersGo.AddComponent<Core.EventManager>();
            managersGo.AddComponent<Core.AudioManager>();
            managersGo.AddComponent<Core.SaveManager>();
            managersGo.AddComponent<Domain.GameBoard>();
            managersGo.AddComponent<Domain.BlockSpawner>();
            managersGo.AddComponent<Game.GameManager>();
            managersGo.AddComponent<Game.UIManager>();
            managersGo.AddComponent<Game.EffectManager>();

            // --- GameSceneInit (starts game on Play) ---
            var initGo = new GameObject("GameSceneInit");
            initGo.AddComponent<Game.GameSceneInit>();

            EditorSceneManager.SaveScene(scene, "Assets/Scenes/GameScene.unity");
        }

        // ============================================================
        // Helpers
        // ============================================================
        private static GameObject CreateCanvas()
        {
            var canvasGo = new GameObject("Canvas");
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080, 1920);
            scaler.matchWidthOrHeight = 0.5f;
            canvasGo.AddComponent<GraphicRaycaster>();
            return canvasGo;
        }

        private static void CreateEventSystem()
        {
            var esGo = new GameObject("EventSystem");
            esGo.AddComponent<UnityEngine.EventSystems.EventSystem>();
            esGo.AddComponent<UnityEngine.EventSystems.StandaloneInputModule>();
        }

        private static void RegisterBuildSettings()
        {
            var scenes = new EditorBuildSettingsScene[]
            {
                new EditorBuildSettingsScene("Assets/Scenes/Title.unity", true),
                new EditorBuildSettingsScene("Assets/Scenes/Main.unity", true),
                new EditorBuildSettingsScene("Assets/Scenes/GameScene.unity", true),
            };
            EditorBuildSettings.scenes = scenes;
        }
    }
}
