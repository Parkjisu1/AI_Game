using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace BlockBlast.Editor
{
    public class SceneSetup
    {
        private const string SCENES_PATH = "Assets/Scenes/";

        [MenuItem("GameForge/Setup Scenes")]
        public static void SetupAllScenes()
        {
            // Ensure directories exist
            if (!AssetDatabase.IsValidFolder("Assets/Scenes"))
                AssetDatabase.CreateFolder("Assets", "Scenes");

            CreateTitleScene();
            CreateMainScene();
            CreateGameScene();
            RegisterScenesInBuildSettings();

            Debug.Log("[GameForge] All scenes created and registered!");
        }

        private static void CreateTitleScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // Camera
            var camGo = new GameObject("Main Camera");
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 10f;
            cam.backgroundColor = new Color(0.05f, 0.05f, 0.12f, 1f);
            cam.clearFlags = CameraClearFlags.SolidColor;
            camGo.transform.position = new Vector3(0, 0, -10);
            camGo.tag = "MainCamera";
            camGo.AddComponent<AudioListener>();

            // Canvas
            var canvasGo = new GameObject("Canvas");
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080, 1920);
            scaler.matchWidthOrHeight = 0.5f;
            canvasGo.AddComponent<GraphicRaycaster>();

            // EventSystem
            var esGo = new GameObject("EventSystem");
            esGo.AddComponent<UnityEngine.EventSystems.EventSystem>();
            esGo.AddComponent<UnityEngine.EventSystems.StandaloneInputModule>();

            // TitleController
            var titleCtrl = new GameObject("TitleController");
            titleCtrl.AddComponent<Game.TitleController>();

            EditorSceneManager.SaveScene(scene, SCENES_PATH + "Title.unity");
            Debug.Log("[GameForge] Title scene created");
        }

        private static void CreateMainScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // Camera
            var camGo = new GameObject("Main Camera");
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 10f;
            cam.backgroundColor = new Color(0.05f, 0.05f, 0.12f, 1f);
            cam.clearFlags = CameraClearFlags.SolidColor;
            camGo.transform.position = new Vector3(0, 0, -10);
            camGo.tag = "MainCamera";
            camGo.AddComponent<AudioListener>();

            // Canvas
            var canvasGo = new GameObject("Canvas");
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080, 1920);
            scaler.matchWidthOrHeight = 0.5f;
            canvasGo.AddComponent<GraphicRaycaster>();

            // EventSystem
            var esGo = new GameObject("EventSystem");
            esGo.AddComponent<UnityEngine.EventSystems.EventSystem>();
            esGo.AddComponent<UnityEngine.EventSystems.StandaloneInputModule>();

            // MainMenuController
            var menuCtrl = new GameObject("MainMenuController");
            menuCtrl.AddComponent<Game.MainMenuController>();

            EditorSceneManager.SaveScene(scene, SCENES_PATH + "Main.unity");
            Debug.Log("[GameForge] Main scene created");
        }

        private static void CreateGameScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            // Camera
            var camGo = new GameObject("Main Camera");
            var cam = camGo.AddComponent<Camera>();
            cam.orthographic = true;
            cam.orthographicSize = 10f;
            cam.backgroundColor = new Color(0.05f, 0.05f, 0.12f, 1f);
            cam.clearFlags = CameraClearFlags.SolidColor;
            camGo.transform.position = new Vector3(0, 2f, -10f);
            camGo.tag = "MainCamera";
            camGo.AddComponent<AudioListener>();

            // Canvas
            var canvasGo = new GameObject("Canvas");
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080, 1920);
            scaler.matchWidthOrHeight = 0.5f;
            canvasGo.AddComponent<GraphicRaycaster>();

            // EventSystem
            var esGo = new GameObject("EventSystem");
            esGo.AddComponent<UnityEngine.EventSystems.EventSystem>();
            esGo.AddComponent<UnityEngine.EventSystems.StandaloneInputModule>();

            // Managers GameObject
            var managersGo = new GameObject("Managers");
            managersGo.AddComponent<Core.EventManager>();
            managersGo.AddComponent<Core.AudioManager>();
            managersGo.AddComponent<Core.SaveManager>();
            managersGo.AddComponent<Domain.GameBoard>();
            managersGo.AddComponent<Domain.BlockSpawner>();
            managersGo.AddComponent<Game.GameManager>();
            managersGo.AddComponent<Game.UIManager>();
            managersGo.AddComponent<Game.EffectManager>();

            // GameSceneInit - starts the game
            var initGo = new GameObject("GameSceneInit");
            initGo.AddComponent<Game.GameSceneInit>();

            EditorSceneManager.SaveScene(scene, SCENES_PATH + "GameScene.unity");
            Debug.Log("[GameForge] GameScene created");
        }

        private static void RegisterScenesInBuildSettings()
        {
            var scenes = new EditorBuildSettingsScene[]
            {
                new EditorBuildSettingsScene(SCENES_PATH + "Title.unity", true),
                new EditorBuildSettingsScene(SCENES_PATH + "Main.unity", true),
                new EditorBuildSettingsScene(SCENES_PATH + "GameScene.unity", true),
            };
            EditorBuildSettings.scenes = scenes;
            Debug.Log("[GameForge] Scenes registered in Build Settings");
        }
    }
}
