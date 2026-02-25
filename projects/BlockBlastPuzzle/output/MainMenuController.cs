using UnityEngine;
using UnityEngine.UI;
using UnityEngine.SceneManagement;
using BlockBlast.Core;

namespace BlockBlast.Game
{
    public class MainMenuController : MonoBehaviour
    {
        private Text _highScoreText;
        private GameObject _settingsPanel;
        private Text _soundBtnText;
        private Text _vibrationBtnText;

        private void Start()
        {
            CreateMainMenuUI();

            #if GOOGLE_MOBILE_ADS
            if (!SaveManager.Instance.IsAdsRemoved())
                SDK.AdMobManager.Instance.ShowBanner();
            #endif
        }

        private void CreateMainMenuUI()
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
            }

            var ct = canvas.transform;

            // Background
            var bgGo = new GameObject("Background");
            bgGo.transform.SetParent(ct, false);
            var bgRt = bgGo.AddComponent<RectTransform>();
            bgRt.anchorMin = Vector2.zero;
            bgRt.anchorMax = Vector2.one;
            bgRt.offsetMin = Vector2.zero;
            bgRt.offsetMax = Vector2.zero;
            var bgImg = bgGo.AddComponent<Image>();
            bgImg.color = new Color(0.05f, 0.05f, 0.12f, 1f);

            // Title
            var titleGo = new GameObject("Title");
            titleGo.transform.SetParent(ct, false);
            var titleRt = titleGo.AddComponent<RectTransform>();
            titleRt.anchorMin = new Vector2(0.1f, 0.65f);
            titleRt.anchorMax = new Vector2(0.9f, 0.85f);
            titleRt.offsetMin = Vector2.zero;
            titleRt.offsetMax = Vector2.zero;
            var titleText = titleGo.AddComponent<Text>();
            titleText.text = "BLOCK\nBLAST";
            titleText.fontSize = 80;
            titleText.color = Color.white;
            titleText.alignment = TextAnchor.MiddleCenter;
            titleText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            // High Score
            var hsGo = new GameObject("HighScore");
            hsGo.transform.SetParent(ct, false);
            var hsRt = hsGo.AddComponent<RectTransform>();
            hsRt.anchorMin = new Vector2(0.2f, 0.56f);
            hsRt.anchorMax = new Vector2(0.8f, 0.63f);
            hsRt.offsetMin = Vector2.zero;
            hsRt.offsetMax = Vector2.zero;
            _highScoreText = hsGo.AddComponent<Text>();
            int best = SaveManager.Instance.GetHighScore();
            _highScoreText.text = $"Best Score: {best}";
            _highScoreText.fontSize = 32;
            _highScoreText.color = new Color(0.7f, 0.7f, 0.85f, 1f);
            _highScoreText.alignment = TextAnchor.MiddleCenter;
            _highScoreText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            // Play button
            var playBtn = CreateButton("PlayButton", ct, "PLAY", 42,
                new Color(0.2f, 0.6f, 0.3f, 1f));
            var playRt = playBtn.GetComponent<RectTransform>();
            playRt.anchorMin = new Vector2(0.25f, 0.38f);
            playRt.anchorMax = new Vector2(0.75f, 0.46f);
            playRt.offsetMin = Vector2.zero;
            playRt.offsetMax = Vector2.zero;
            playBtn.GetComponent<Button>().onClick.AddListener(OnPlayButton);

            // Settings button
            var settingsBtn = CreateButton("SettingsButton", ct, "Settings", 32,
                new Color(0.3f, 0.3f, 0.45f, 1f));
            var settingsRt = settingsBtn.GetComponent<RectTransform>();
            settingsRt.anchorMin = new Vector2(0.25f, 0.28f);
            settingsRt.anchorMax = new Vector2(0.75f, 0.35f);
            settingsRt.offsetMin = Vector2.zero;
            settingsRt.offsetMax = Vector2.zero;
            settingsBtn.GetComponent<Button>().onClick.AddListener(OnSettingsButton);

            // Remove Ads button (only if ads not already removed)
            if (!SaveManager.Instance.IsAdsRemoved())
            {
                var removeAdsBtn = CreateButton("RemoveAdsBtn", ct, "Remove Ads", 26,
                    new Color(0.6f, 0.4f, 0.1f, 1f));
                var raRt = removeAdsBtn.GetComponent<RectTransform>();
                raRt.anchorMin = new Vector2(0.3f, 0.2f);
                raRt.anchorMax = new Vector2(0.7f, 0.26f);
                raRt.offsetMin = Vector2.zero;
                raRt.offsetMax = Vector2.zero;
                removeAdsBtn.GetComponent<Button>().onClick.AddListener(OnRemoveAds);
            }

            CreateSettingsPopup(ct);
        }

        private void CreateSettingsPopup(Transform parent)
        {
            _settingsPanel = new GameObject("SettingsPopup");
            _settingsPanel.transform.SetParent(parent, false);
            var rt = _settingsPanel.AddComponent<RectTransform>();
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;

            // Semi-transparent background
            var bgImg = _settingsPanel.AddComponent<Image>();
            bgImg.color = new Color(0, 0, 0, 0.7f);

            // Center panel
            var center = new GameObject("CenterPanel");
            center.transform.SetParent(_settingsPanel.transform, false);
            var crt = center.AddComponent<RectTransform>();
            crt.anchorMin = new Vector2(0.5f, 0.5f);
            crt.anchorMax = new Vector2(0.5f, 0.5f);
            crt.pivot = new Vector2(0.5f, 0.5f);
            crt.sizeDelta = new Vector2(450, 350);
            var cImg = center.AddComponent<Image>();
            cImg.color = new Color(0.12f, 0.12f, 0.18f, 1f);

            var cTransform = center.transform;

            // Title
            var titleGo = new GameObject("Title");
            titleGo.transform.SetParent(cTransform, false);
            var trt = titleGo.AddComponent<RectTransform>();
            trt.anchorMin = new Vector2(0.1f, 0.8f);
            trt.anchorMax = new Vector2(0.9f, 0.95f);
            trt.offsetMin = Vector2.zero;
            trt.offsetMax = Vector2.zero;
            var tText = titleGo.AddComponent<Text>();
            tText.text = "SETTINGS";
            tText.fontSize = 36;
            tText.color = Color.white;
            tText.alignment = TextAnchor.MiddleCenter;
            tText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            // Sound toggle
            bool soundOn = SaveManager.Instance.LoadInt(SaveManager.KEY_SOUND_ON, 1) == 1;
            var soundBtn = CreateButton("SoundBtn", cTransform,
                soundOn ? "Sound: ON" : "Sound: OFF", 28,
                soundOn ? new Color(0.2f, 0.6f, 0.3f, 1f) : new Color(0.5f, 0.3f, 0.3f, 1f));
            var srt = soundBtn.GetComponent<RectTransform>();
            srt.anchorMin = new Vector2(0.5f, 0.55f);
            srt.anchorMax = new Vector2(0.5f, 0.55f);
            srt.pivot = new Vector2(0.5f, 0.5f);
            srt.sizeDelta = new Vector2(350, 60);
            _soundBtnText = soundBtn.GetComponentInChildren<Text>();
            soundBtn.GetComponent<Button>().onClick.AddListener(ToggleSound);

            // Vibration toggle
            bool vibOn = SaveManager.Instance.LoadInt(SaveManager.KEY_VIBRATION_ON, 1) == 1;
            var vibBtn = CreateButton("VibrationBtn", cTransform,
                vibOn ? "Vibration: ON" : "Vibration: OFF", 28,
                vibOn ? new Color(0.2f, 0.6f, 0.3f, 1f) : new Color(0.5f, 0.3f, 0.3f, 1f));
            var vrt = vibBtn.GetComponent<RectTransform>();
            vrt.anchorMin = new Vector2(0.5f, 0.35f);
            vrt.anchorMax = new Vector2(0.5f, 0.35f);
            vrt.pivot = new Vector2(0.5f, 0.5f);
            vrt.sizeDelta = new Vector2(350, 60);
            _vibrationBtnText = vibBtn.GetComponentInChildren<Text>();
            vibBtn.GetComponent<Button>().onClick.AddListener(ToggleVibration);

            // Close button
            var closeBtn = CreateButton("CloseBtn", cTransform, "Close", 30,
                new Color(0.4f, 0.4f, 0.5f, 1f));
            var clrt = closeBtn.GetComponent<RectTransform>();
            clrt.anchorMin = new Vector2(0.5f, 0.1f);
            clrt.anchorMax = new Vector2(0.5f, 0.1f);
            clrt.pivot = new Vector2(0.5f, 0.5f);
            clrt.sizeDelta = new Vector2(350, 60);
            closeBtn.GetComponent<Button>().onClick.AddListener(() => _settingsPanel.SetActive(false));

            _settingsPanel.SetActive(false);
        }

        private void OnPlayButton()
        {
            #if FIREBASE_ANALYTICS
            SDK.FirebaseManager.Instance.LogEvent("click_play");
            #endif
            SceneManager.LoadScene("GameScene");
        }

        private void OnSettingsButton()
        {
            _settingsPanel.SetActive(true);
        }

        private void OnRemoveAds()
        {
            #if UNITY_IAP
            SDK.IAPManager.Instance.BuyProduct("remove_ads");
            #else
            Debug.Log("[IAP Sim] Purchase: remove_ads");
            #endif
        }

        private void ToggleSound()
        {
            AudioManager.Instance.ToggleMute();
            bool on = !AudioManager.Instance.IsMuted;
            _soundBtnText.text = on ? "Sound: ON" : "Sound: OFF";
            _soundBtnText.transform.parent.GetComponent<Image>().color =
                on ? new Color(0.2f, 0.6f, 0.3f, 1f) : new Color(0.5f, 0.3f, 0.3f, 1f);
        }

        private void ToggleVibration()
        {
            int current = SaveManager.Instance.LoadInt(SaveManager.KEY_VIBRATION_ON, 1);
            int newVal = current == 1 ? 0 : 1;
            SaveManager.Instance.SaveInt(SaveManager.KEY_VIBRATION_ON, newVal);
            bool on = newVal == 1;
            _vibrationBtnText.text = on ? "Vibration: ON" : "Vibration: OFF";
            _vibrationBtnText.transform.parent.GetComponent<Image>().color =
                on ? new Color(0.2f, 0.6f, 0.3f, 1f) : new Color(0.5f, 0.3f, 0.3f, 1f);
        }

        private GameObject CreateButton(string name, Transform parent, string label, int fontSize, Color bgColor)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.AddComponent<RectTransform>();
            var img = go.AddComponent<Image>();
            img.color = bgColor;
            var btn = go.AddComponent<Button>();
            btn.targetGraphic = img;

            var textGo = new GameObject("Text");
            textGo.transform.SetParent(go.transform, false);
            var trt = textGo.AddComponent<RectTransform>();
            trt.anchorMin = Vector2.zero;
            trt.anchorMax = Vector2.one;
            trt.offsetMin = Vector2.zero;
            trt.offsetMax = Vector2.zero;
            var text = textGo.AddComponent<Text>();
            text.text = label;
            text.fontSize = fontSize;
            text.color = Color.white;
            text.alignment = TextAnchor.MiddleCenter;
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            return go;
        }
    }
}
