using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using BlockBlast.Core;

namespace BlockBlast.Game
{
    public class UIManager : Singleton<UIManager>
    {
        private Text _scoreText;
        private Text _highScoreText;
        private Text _comboText;
        private GameObject _gameOverPanel;
        private GameObject _settingsPanel;
        private Canvas _mainCanvas;
        private Transform _canvasTransform;

        // Game Over popup references
        private Text _goScoreText;
        private Text _goHighScoreText;
        private Text _goNewHighText;
        private Button _goContinueBtn;
        private Button _goRestartBtn;
        private Button _goMainMenuBtn;

        // Settings popup references
        private Text _soundBtnText;
        private Text _vibrationBtnText;

        public void InitUI(Canvas canvas)
        {
            _mainCanvas = canvas;
            _canvasTransform = canvas.transform;

            CreateGameHUD();
            CreateGameOverPopup();
            CreateSettingsPopup();
            CreatePauseButton();
        }

        private void CreateGameHUD()
        {
            // Score display - top area
            var scorePanel = CreatePanel("ScorePanel", _canvasTransform,
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0.5f, 1f),
                new Vector2(400, 120), new Vector2(0, -60));
            scorePanel.GetComponent<Image>().color = new Color(0.1f, 0.1f, 0.2f, 0.8f);

            var scoreLbl = CreateText("ScoreLabel", scorePanel.transform, "SCORE", 24,
                new Vector2(0, 0.5f), new Vector2(1, 1f), Color.gray);

            _scoreText = CreateText("ScoreText", scorePanel.transform, "0", 48,
                new Vector2(0, 0f), new Vector2(1, 0.6f), Color.white);

            // High score - small text top right
            _highScoreText = CreateText("HighScore", _canvasTransform, "BEST: 0", 22,
                new Vector2(0.95f, 0.97f), Color.gray);
            _highScoreText.alignment = TextAnchor.UpperRight;
            var hsrt = _highScoreText.GetComponent<RectTransform>();
            hsrt.anchorMin = new Vector2(0.5f, 1f);
            hsrt.anchorMax = new Vector2(1f, 1f);
            hsrt.offsetMin = new Vector2(0, -50);
            hsrt.offsetMax = new Vector2(-20, -10);

            int best = SaveManager.Instance.GetHighScore();
            _highScoreText.text = $"BEST: {best}";

            // Combo text - center, hidden by default
            _comboText = CreateText("ComboText", _canvasTransform, "", 36,
                new Vector2(0.5f, 0.75f), Color.yellow);
            _comboText.alignment = TextAnchor.MiddleCenter;
            var crt = _comboText.GetComponent<RectTransform>();
            crt.anchorMin = new Vector2(0.3f, 0.7f);
            crt.anchorMax = new Vector2(0.7f, 0.8f);
            crt.offsetMin = Vector2.zero;
            crt.offsetMax = Vector2.zero;
            _comboText.gameObject.SetActive(false);
        }

        private void CreatePauseButton()
        {
            var btnGo = CreateButton("PauseBtn", _canvasTransform, "||", 32, new Color(0.3f, 0.3f, 0.4f, 0.8f));
            var rt = btnGo.GetComponent<RectTransform>();
            rt.anchorMin = new Vector2(0f, 1f);
            rt.anchorMax = new Vector2(0f, 1f);
            rt.pivot = new Vector2(0f, 1f);
            rt.anchoredPosition = new Vector2(20, -20);
            rt.sizeDelta = new Vector2(70, 70);

            btnGo.GetComponent<Button>().onClick.AddListener(() =>
            {
                if (GameManager.Instance.State == GameState.Playing)
                {
                    GameManager.Instance.PauseGame();
                    ShowSettingsPopup();
                }
            });
        }

        private void CreateGameOverPopup()
        {
            _gameOverPanel = CreatePanel("GameOverPanel", _canvasTransform,
                Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f),
                Vector2.zero, Vector2.zero);
            _gameOverPanel.GetComponent<Image>().color = new Color(0, 0, 0, 0.7f);

            var rt = _gameOverPanel.GetComponent<RectTransform>();
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;

            var centerPanel = CreatePanel("CenterPanel", _gameOverPanel.transform,
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(500, 600), Vector2.zero);
            centerPanel.GetComponent<Image>().color = new Color(0.12f, 0.12f, 0.18f, 1f);

            var cpTransform = centerPanel.transform;

            // Title
            CreateText("GOTitle", cpTransform, "GAME OVER", 48,
                new Vector2(0.5f, 0.9f), Color.white);

            // Score
            _goScoreText = CreateText("GOScore", cpTransform, "0", 56,
                new Vector2(0.5f, 0.72f), Color.white);

            _goHighScoreText = CreateText("GOHighScore", cpTransform, "BEST: 0", 28,
                new Vector2(0.5f, 0.6f), Color.gray);

            _goNewHighText = CreateText("GONewHigh", cpTransform, "NEW HIGH SCORE!", 30,
                new Vector2(0.5f, 0.52f), Color.yellow);
            _goNewHighText.gameObject.SetActive(false);

            // Continue button
            var continueBtn = CreateButton("ContinueBtn", cpTransform, "Continue (Ad)", 28,
                new Color(0.2f, 0.7f, 0.3f, 1f));
            SetButtonRect(continueBtn, new Vector2(0.5f, 0.38f), new Vector2(350, 70));
            _goContinueBtn = continueBtn.GetComponent<Button>();
            _goContinueBtn.onClick.AddListener(OnContinueClicked);

            // Restart button
            var restartBtn = CreateButton("RestartBtn", cpTransform, "Restart", 28,
                new Color(0.3f, 0.5f, 0.8f, 1f));
            SetButtonRect(restartBtn, new Vector2(0.5f, 0.24f), new Vector2(350, 70));
            _goRestartBtn = restartBtn.GetComponent<Button>();
            _goRestartBtn.onClick.AddListener(() => GameManager.Instance.RestartGame());

            // Main Menu button
            var menuBtn = CreateButton("MainMenuBtn", cpTransform, "Main Menu", 28,
                new Color(0.4f, 0.4f, 0.5f, 1f));
            SetButtonRect(menuBtn, new Vector2(0.5f, 0.1f), new Vector2(350, 70));
            _goMainMenuBtn = menuBtn.GetComponent<Button>();
            _goMainMenuBtn.onClick.AddListener(() => GameManager.Instance.GoToMainMenu());

            _gameOverPanel.SetActive(false);
        }

        private void CreateSettingsPopup()
        {
            _settingsPanel = CreatePanel("SettingsPanel", _canvasTransform,
                Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f),
                Vector2.zero, Vector2.zero);
            _settingsPanel.GetComponent<Image>().color = new Color(0, 0, 0, 0.7f);

            var rt = _settingsPanel.GetComponent<RectTransform>();
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;

            // Close on background click
            var bgBtn = _settingsPanel.AddComponent<Button>();
            bgBtn.onClick.AddListener(HideSettingsPopup);

            var centerPanel = CreatePanel("SettingsCenter", _settingsPanel.transform,
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(450, 400), Vector2.zero);
            centerPanel.GetComponent<Image>().color = new Color(0.12f, 0.12f, 0.18f, 1f);

            var cpTransform = centerPanel.transform;

            CreateText("SettingsTitle", cpTransform, "SETTINGS", 40,
                new Vector2(0.5f, 0.88f), Color.white);

            // Sound toggle
            bool soundOn = SaveManager.Instance.LoadInt(SaveManager.KEY_SOUND_ON, 1) == 1;
            var soundBtn = CreateButton("SoundBtn", cpTransform,
                soundOn ? "Sound: ON" : "Sound: OFF", 28,
                soundOn ? new Color(0.2f, 0.6f, 0.3f, 1f) : new Color(0.5f, 0.3f, 0.3f, 1f));
            SetButtonRect(soundBtn, new Vector2(0.5f, 0.62f), new Vector2(350, 65));
            _soundBtnText = soundBtn.GetComponentInChildren<Text>();
            soundBtn.GetComponent<Button>().onClick.AddListener(ToggleSound);

            // Vibration toggle
            bool vibOn = SaveManager.Instance.LoadInt(SaveManager.KEY_VIBRATION_ON, 1) == 1;
            var vibBtn = CreateButton("VibrationBtn", cpTransform,
                vibOn ? "Vibration: ON" : "Vibration: OFF", 28,
                vibOn ? new Color(0.2f, 0.6f, 0.3f, 1f) : new Color(0.5f, 0.3f, 0.3f, 1f));
            SetButtonRect(vibBtn, new Vector2(0.5f, 0.4f), new Vector2(350, 65));
            _vibrationBtnText = vibBtn.GetComponentInChildren<Text>();
            vibBtn.GetComponent<Button>().onClick.AddListener(ToggleVibration);

            // Resume button
            var resumeBtn = CreateButton("ResumeBtn", cpTransform, "Resume", 32,
                new Color(0.3f, 0.5f, 0.8f, 1f));
            SetButtonRect(resumeBtn, new Vector2(0.5f, 0.15f), new Vector2(350, 70));
            resumeBtn.GetComponent<Button>().onClick.AddListener(HideSettingsPopup);

            _settingsPanel.SetActive(false);
        }

        public void UpdateScoreDisplay(int score)
        {
            if (_scoreText != null)
                _scoreText.text = score.ToString();
        }

        public void UpdateComboDisplay(int combo)
        {
            if (combo > 1)
            {
                _comboText.text = $"COMBO x{combo}!";
                _comboText.gameObject.SetActive(true);
                StopCoroutine("HideComboAfterDelay");
                StartCoroutine(HideComboAfterDelay());
            }
        }

        private IEnumerator HideComboAfterDelay()
        {
            yield return new WaitForSeconds(1.5f);
            if (_comboText != null)
                _comboText.gameObject.SetActive(false);
        }

        public void ShowGameOverPopup(int score, int highScore, bool isNewHigh)
        {
            _goScoreText.text = score.ToString();
            _goHighScoreText.text = $"BEST: {highScore}";
            _goNewHighText.gameObject.SetActive(isNewHigh);
            _highScoreText.text = $"BEST: {highScore}";
            _gameOverPanel.SetActive(true);
        }

        public void ShowSettingsPopup()
        {
            _settingsPanel.SetActive(true);
        }

        public void HideSettingsPopup()
        {
            _settingsPanel.SetActive(false);
            if (GameManager.Instance.State == GameState.Paused)
                GameManager.Instance.ResumeGame();
        }

        public void HideAllPopups()
        {
            if (_gameOverPanel != null) _gameOverPanel.SetActive(false);
            if (_settingsPanel != null) _settingsPanel.SetActive(false);
        }

        private void OnContinueClicked()
        {
            #if GOOGLE_MOBILE_ADS
            SDK.AdMobManager.Instance.ShowRewarded((bool success) =>
            {
                if (success)
                    GameManager.Instance.ContinueWithAdReward();
            });
            #else
            // Simulation: just continue
            GameManager.Instance.ContinueWithAdReward();
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

        // ---- UI Helpers ----

        private GameObject CreatePanel(string name, Transform parent,
            Vector2 anchorMin, Vector2 anchorMax, Vector2 pivot,
            Vector2 sizeDelta, Vector2 anchoredPos)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = anchorMin;
            rt.anchorMax = anchorMax;
            rt.pivot = pivot;
            rt.sizeDelta = sizeDelta;
            rt.anchoredPosition = anchoredPos;
            var img = go.AddComponent<Image>();
            img.color = new Color(0.15f, 0.15f, 0.2f, 0.9f);
            return go;
        }

        private Text CreateText(string name, Transform parent, string content, int fontSize,
            Vector2 anchoredPos, Color color)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = new Vector2(0, 0);
            rt.anchorMax = new Vector2(1, 1);
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;
            rt.anchoredPosition = anchoredPos;
            var text = go.AddComponent<Text>();
            text.text = content;
            text.fontSize = fontSize;
            text.color = color;
            text.alignment = TextAnchor.MiddleCenter;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            return text;
        }

        private Text CreateText(string name, Transform parent, string content, int fontSize,
            Vector2 anchorMin, Vector2 anchorMax, Color color)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = anchorMin;
            rt.anchorMax = anchorMax;
            rt.offsetMin = new Vector2(10, 5);
            rt.offsetMax = new Vector2(-10, -5);
            var text = go.AddComponent<Text>();
            text.text = content;
            text.fontSize = fontSize;
            text.color = color;
            text.alignment = TextAnchor.MiddleCenter;
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            return text;
        }

        private GameObject CreateButton(string name, Transform parent, string label, int fontSize, Color bgColor)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
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

        private void SetButtonRect(GameObject btn, Vector2 anchorPos, Vector2 size)
        {
            var rt = btn.GetComponent<RectTransform>();
            rt.anchorMin = anchorPos;
            rt.anchorMax = anchorPos;
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.sizeDelta = size;
            rt.anchoredPosition = Vector2.zero;
        }
    }
}
