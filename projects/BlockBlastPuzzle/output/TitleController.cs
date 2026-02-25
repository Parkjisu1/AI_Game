using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.SceneManagement;

namespace BlockBlast.Game
{
    public class TitleController : MonoBehaviour
    {
        private Image _loadingBarFill;
        private Text _titleText;

        private void Start()
        {
            CreateTitleUI();
            StartCoroutine(LoadSequence());
        }

        private void CreateTitleUI()
        {
            // Find or create canvas
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

            // Title text
            var titleGo = new GameObject("Title");
            titleGo.transform.SetParent(ct, false);
            var titleRt = titleGo.AddComponent<RectTransform>();
            titleRt.anchorMin = new Vector2(0.1f, 0.5f);
            titleRt.anchorMax = new Vector2(0.9f, 0.7f);
            titleRt.offsetMin = Vector2.zero;
            titleRt.offsetMax = Vector2.zero;
            _titleText = titleGo.AddComponent<Text>();
            _titleText.text = "BLOCK\nBLAST";
            _titleText.fontSize = 96;
            _titleText.color = Color.white;
            _titleText.alignment = TextAnchor.MiddleCenter;
            _titleText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            // Subtitle
            var subGo = new GameObject("Subtitle");
            subGo.transform.SetParent(ct, false);
            var subRt = subGo.AddComponent<RectTransform>();
            subRt.anchorMin = new Vector2(0.2f, 0.42f);
            subRt.anchorMax = new Vector2(0.8f, 0.48f);
            subRt.offsetMin = Vector2.zero;
            subRt.offsetMax = Vector2.zero;
            var subText = subGo.AddComponent<Text>();
            subText.text = "PUZZLE";
            subText.fontSize = 36;
            subText.color = new Color(0.6f, 0.6f, 0.8f, 1f);
            subText.alignment = TextAnchor.MiddleCenter;
            subText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            // Loading bar background
            var barBgGo = new GameObject("LoadingBarBG");
            barBgGo.transform.SetParent(ct, false);
            var barBgRt = barBgGo.AddComponent<RectTransform>();
            barBgRt.anchorMin = new Vector2(0.15f, 0.18f);
            barBgRt.anchorMax = new Vector2(0.85f, 0.2f);
            barBgRt.offsetMin = Vector2.zero;
            barBgRt.offsetMax = Vector2.zero;
            var barBgImg = barBgGo.AddComponent<Image>();
            barBgImg.color = new Color(0.2f, 0.2f, 0.3f, 1f);

            // Loading bar fill
            var barFillGo = new GameObject("LoadingBarFill");
            barFillGo.transform.SetParent(barBgGo.transform, false);
            var barFillRt = barFillGo.AddComponent<RectTransform>();
            barFillRt.anchorMin = Vector2.zero;
            barFillRt.anchorMax = new Vector2(0, 1);
            barFillRt.offsetMin = new Vector2(2, 2);
            barFillRt.offsetMax = new Vector2(-2, -2);
            _loadingBarFill = barFillGo.AddComponent<Image>();
            _loadingBarFill.color = new Color(0.3f, 0.6f, 1f, 1f);

            // Loading text
            var loadGo = new GameObject("LoadingText");
            loadGo.transform.SetParent(ct, false);
            var loadRt = loadGo.AddComponent<RectTransform>();
            loadRt.anchorMin = new Vector2(0.2f, 0.14f);
            loadRt.anchorMax = new Vector2(0.8f, 0.17f);
            loadRt.offsetMin = Vector2.zero;
            loadRt.offsetMax = Vector2.zero;
            var loadText = loadGo.AddComponent<Text>();
            loadText.text = "Loading...";
            loadText.fontSize = 24;
            loadText.color = new Color(0.6f, 0.6f, 0.7f, 1f);
            loadText.alignment = TextAnchor.MiddleCenter;
            loadText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }

        private IEnumerator LoadSequence()
        {
            float duration = 2.0f;
            float elapsed = 0f;

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float progress = Mathf.Clamp01(elapsed / duration);

                // Update fill bar
                if (_loadingBarFill != null)
                {
                    var rt = _loadingBarFill.GetComponent<RectTransform>();
                    rt.anchorMax = new Vector2(progress, 1);
                }

                yield return null;
            }

            yield return new WaitForSeconds(0.3f);
            SceneManager.LoadScene("Main");
        }
    }
}
