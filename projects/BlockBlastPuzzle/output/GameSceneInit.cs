using UnityEngine;
using UnityEngine.UI;
using BlockBlast.Core;
using BlockBlast.Domain;

namespace BlockBlast.Game
{
    public class GameSceneInit : MonoBehaviour
    {
        private void Start()
        {
            Debug.Log("[GameSceneInit] Start() begin");
            SetupCamera();
            EnsurePhysics2D();
            SetupCanvas();
            SetupManagers();
            StartGame();
            Debug.Log("[GameSceneInit] Start() complete");
        }

        private void SetupCamera()
        {
            var cam = Camera.main;
            if (cam != null)
            {
                cam.orthographic = true;
                cam.orthographicSize = 10f;
                cam.backgroundColor = new Color(0.05f, 0.05f, 0.12f, 1f);
                cam.transform.position = new Vector3(0, 2f, -10f);
                Debug.Log("[GameSceneInit] Camera setup complete");
            }
            else
            {
                Debug.LogError("[GameSceneInit] Camera.main is null!");
            }
        }

        private void EnsurePhysics2D()
        {
            // Ensure Physics2D is active (needed for block drag detection)
            Physics2D.queriesHitTriggers = true;
            Physics2D.queriesStartInColliders = true;
        }

        private void SetupCanvas()
        {
            var canvas = FindObjectOfType<Canvas>();
            if (canvas == null)
            {
                var canvasGo = new GameObject("Canvas");
                canvas = canvasGo.AddComponent<Canvas>();
                canvas.renderMode = RenderMode.ScreenSpaceOverlay;
                var scaler = canvasGo.AddComponent<CanvasScaler>();
                scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
                scaler.referenceResolution = new Vector2(1080, 1920);
                scaler.matchWidthOrHeight = 0.5f;
                canvasGo.AddComponent<GraphicRaycaster>();
                Debug.Log("[GameSceneInit] Created new Canvas");
            }

            // Init UI with the canvas
            UIManager.Instance.InitUI(canvas);
            Debug.Log("[GameSceneInit] UI initialized");

            // Show banner ad
            #if GOOGLE_MOBILE_ADS
            if (!SaveManager.Instance.IsAdsRemoved())
                SDK.AdMobManager.Instance.ShowBanner();
            #endif
        }

        private void SetupManagers()
        {
            // Touch all singletons to ensure they are created
            var em = EventManager.Instance;
            var am = AudioManager.Instance;
            var sm = SaveManager.Instance;
            var gb = GameBoard.Instance;
            var bs = BlockSpawner.Instance;
            var ef = EffectManager.Instance;

            Debug.Log($"[GameSceneInit] Managers ready - EventManager:{em != null}, AudioManager:{am != null}, SaveManager:{sm != null}, GameBoard:{gb != null}, BlockSpawner:{bs != null}, EffectManager:{ef != null}");
        }

        private void StartGame()
        {
            Debug.Log("[GameSceneInit] Starting game...");
            GameManager.Instance.StartGame();
        }
    }
}
