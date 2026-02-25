#if UNITY_EDITOR

using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using UnityEngine.EventSystems;

namespace VeilBreaker.Editor
{
    /// <summary>
    /// Editor utility that creates and configures the three required game scenes:
    /// Title, Main, and GameScene. Run once via the menu item.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Generic
    /// Role: Helper
    /// Phase: 3
    /// System: Editor
    /// Place in Assets/Editor/ — NOT Assets/Scripts/
    /// </remarks>
    public static class SceneSetup
    {
        private const string SceneFolder    = "Assets/Scenes";
        private const string PrefKey        = "VeilBreaker_ScenesCreated";
        private const int    ReferenceWidth = 1080;
        private const int    ReferenceHeight = 1920;

        #region Menu Items

        /// <summary>
        /// Creates all three game scenes and registers them in Build Settings.
        /// Safe to run multiple times — existing scenes are not overwritten.
        /// </summary>
        [MenuItem("VeilBreaker/Setup Scenes")]
        public static void CreateAllScenes()
        {
            EnsureScenesFolder();

            SetupTitleScene();
            SetupMainScene();
            SetupGameScene();
            AddScenesToBuildSettings();

            EditorPrefs.SetBool(PrefKey, true);
            Debug.Log("[SceneSetup] All scenes created and registered in Build Settings.");
        }

        [MenuItem("VeilBreaker/Setup Scenes", validate = true)]
        private static bool ValidateCreateAllScenes()
        {
            return true; // Always allow re-run
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Creates Title.unity with Camera, Canvas (logo/loading bar placeholder), and EventSystem.
        /// </summary>
        public static void SetupTitleScene()
        {
            const string scenePath = SceneFolder + "/Title.unity";
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            CreateCamera(scene, "Main Camera");
            var canvas = CreateCanvas(scene, "Canvas");
            CreateEventSystem(scene);

            // Placeholder UI labels for designer
            CreateLabel(canvas, "Logo",       new Vector2(0f, 200f));
            CreateLabel(canvas, "LoadingBar", new Vector2(0f, -300f));

            EditorSceneManager.SaveScene(scene, scenePath);
            Debug.Log($"[SceneSetup] Title scene saved: {scenePath}");
        }

        /// <summary>
        /// Creates Main.unity with Camera, Canvas (menu buttons placeholder), and EventSystem.
        /// </summary>
        public static void SetupMainScene()
        {
            const string scenePath = SceneFolder + "/Main.unity";
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            CreateCamera(scene, "Main Camera");
            var canvas = CreateCanvas(scene, "Canvas");
            CreateEventSystem(scene);

            CreateLabel(canvas, "BtnPlay",     new Vector2(0f,   50f));
            CreateLabel(canvas, "BtnSettings", new Vector2(0f,  -50f));
            CreateLabel(canvas, "ScoreDisplay",new Vector2(0f,  300f));

            EditorSceneManager.SaveScene(scene, scenePath);
            Debug.Log($"[SceneSetup] Main scene saved: {scenePath}");
        }

        /// <summary>
        /// Creates GameScene.unity with Camera, Canvas, EventSystem,
        /// and a "Managers" GameObject for Singleton components.
        /// </summary>
        public static void SetupGameScene()
        {
            const string scenePath = SceneFolder + "/GameScene.unity";
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            CreateCamera(scene, "Main Camera");
            var canvas = CreateCanvas(scene, "Canvas");
            CreateEventSystem(scene);
            CreateManagersRoot(scene);

            CreateLabel(canvas, "HUD",        new Vector2(0f,  600f));
            CreateLabel(canvas, "GameBoard",  new Vector2(0f,    0f));

            EditorSceneManager.SaveScene(scene, scenePath);
            Debug.Log($"[SceneSetup] GameScene saved: {scenePath}");
        }

        /// <summary>
        /// Registers Title, Main, and GameScene in the Build Settings scene list.
        /// Preserves any additional scenes already in Build Settings.
        /// </summary>
        public static void AddScenesToBuildSettings()
        {
            var requiredPaths = new[]
            {
                SceneFolder + "/Title.unity",
                SceneFolder + "/Main.unity",
                SceneFolder + "/GameScene.unity"
            };

            var existing = new System.Collections.Generic.List<EditorBuildSettingsScene>(
                EditorBuildSettings.scenes);

            foreach (var path in requiredPaths)
            {
                bool alreadyAdded = false;
                foreach (var s in existing)
                {
                    if (s.path == path) { alreadyAdded = true; break; }
                }
                if (!alreadyAdded)
                    existing.Add(new EditorBuildSettingsScene(path, true));
            }

            EditorBuildSettings.scenes = existing.ToArray();
            Debug.Log("[SceneSetup] Build Settings updated with 3 scenes.");
        }

        #endregion

        #region Private Helpers

        private static void EnsureScenesFolder()
        {
            if (!AssetDatabase.IsValidFolder(SceneFolder))
            {
                AssetDatabase.CreateFolder("Assets", "Scenes");
                Debug.Log($"[SceneSetup] Created folder: {SceneFolder}");
            }
        }

        private static void CreateCamera(Scene scene, string name)
        {
            var camGo = new GameObject(name, typeof(Camera), typeof(AudioListener));
            camGo.transform.position = new Vector3(0f, 0f, -10f);
            var cam = camGo.GetComponent<Camera>();
            cam.clearFlags       = CameraClearFlags.SolidColor;
            cam.backgroundColor  = Color.black;
            cam.orthographic     = true;
            cam.orthographicSize = 5f;
            SceneManager.MoveGameObjectToScene(camGo, scene);
        }

        private static GameObject CreateCanvas(Scene scene, string name)
        {
            var canvasGo = new GameObject(name, typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            SceneManager.MoveGameObjectToScene(canvasGo, scene);

            var canvas = canvasGo.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;

            var scaler = canvasGo.GetComponent<CanvasScaler>();
            scaler.uiScaleMode         = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(ReferenceWidth, ReferenceHeight);
            scaler.screenMatchMode     = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight  = 0.5f;

            return canvasGo;
        }

        private static void CreateEventSystem(Scene scene)
        {
            var esGo = new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
            SceneManager.MoveGameObjectToScene(esGo, scene);
        }

        private static void CreateManagersRoot(Scene scene)
        {
            var managersGo = new GameObject("Managers");
            SceneManager.MoveGameObjectToScene(managersGo, scene);
            Debug.Log("[SceneSetup] 'Managers' root created — attach Singleton components in Inspector.");
        }

        private static void CreateLabel(GameObject canvasGo, string name, Vector2 anchoredPos)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(canvasGo.transform, false);
            var rt = go.GetComponent<RectTransform>();
            rt.anchoredPosition = anchoredPos;
            rt.sizeDelta        = new Vector2(400f, 80f);
        }

        #endregion
    }
}

#endif
