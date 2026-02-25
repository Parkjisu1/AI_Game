using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using BlockBlast.Core;

namespace BlockBlast.Game
{
    public class EffectManager : Singleton<EffectManager>
    {
        public void PlayLineClearEffect(List<Vector3> positions)
        {
            foreach (var pos in positions)
            {
                StartCoroutine(LineClearParticle(pos));
            }
        }

        public void PlayComboEffect(int combo, Vector3 position)
        {
            StartCoroutine(ComboEffectCoroutine(combo, position));
        }

        public void PlayPlaceEffect(Vector3 position)
        {
            StartCoroutine(PlaceEffectCoroutine(position));
        }

        public void PlayScorePopup(int score, Vector3 position)
        {
            StartCoroutine(ScorePopupCoroutine(score, position));
        }

        private IEnumerator LineClearParticle(Vector3 pos)
        {
            var go = new GameObject("ClearEffect");
            var sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = SpriteFactory.CreateCircleSprite(32, Color.white);
            sr.sortingOrder = 50;
            go.transform.position = pos;

            float duration = 0.4f;
            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = elapsed / duration;
                float scale = Mathf.Lerp(0.3f, 1.5f, t);
                go.transform.localScale = Vector3.one * scale;
                Color c = Color.white;
                c.a = Mathf.Lerp(1f, 0f, t);
                sr.color = c;
                yield return null;
            }
            Destroy(go);
        }

        private IEnumerator ComboEffectCoroutine(int combo, Vector3 position)
        {
            var go = new GameObject("ComboEffect");
            go.transform.position = position + Vector3.up * 0.5f;

            var canvas = CreateWorldCanvas(go.transform);
            var text = CreateWorldText(canvas.transform, $"COMBO x{combo}!", 40);
            text.color = Color.yellow;

            float duration = 1.0f;
            float elapsed = 0f;
            Vector3 startPos = go.transform.position;

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = elapsed / duration;
                go.transform.position = startPos + Vector3.up * t * 1.5f;
                float scale = t < 0.2f ? Mathf.Lerp(0.5f, 1.3f, t / 0.2f) : Mathf.Lerp(1.3f, 1f, (t - 0.2f) / 0.8f);
                go.transform.localScale = Vector3.one * scale;
                Color c = text.color;
                c.a = t < 0.7f ? 1f : Mathf.Lerp(1f, 0f, (t - 0.7f) / 0.3f);
                text.color = c;
                yield return null;
            }
            Destroy(go);
        }

        private IEnumerator PlaceEffectCoroutine(Vector3 position)
        {
            var go = new GameObject("PlaceEffect");
            var sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = SpriteFactory.CreateCircleSprite(48, new Color(1f, 1f, 1f, 0.5f));
            sr.sortingOrder = 30;
            go.transform.position = position;

            float duration = 0.25f;
            float elapsed = 0f;
            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = elapsed / duration;
                float scale = Mathf.Lerp(0.5f, 1.2f, t);
                go.transform.localScale = Vector3.one * scale;
                Color c = sr.color;
                c.a = Mathf.Lerp(0.5f, 0f, t);
                sr.color = c;
                yield return null;
            }
            Destroy(go);
        }

        private IEnumerator ScorePopupCoroutine(int score, Vector3 position)
        {
            var go = new GameObject("ScorePopup");
            go.transform.position = position;

            var canvas = CreateWorldCanvas(go.transform);
            var text = CreateWorldText(canvas.transform, $"+{score}", 32);
            text.color = Color.white;

            float duration = 0.8f;
            float elapsed = 0f;
            Vector3 startPos = go.transform.position;

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = elapsed / duration;
                go.transform.position = startPos + Vector3.up * t * 1.0f;
                Color c = text.color;
                c.a = t < 0.5f ? 1f : Mathf.Lerp(1f, 0f, (t - 0.5f) / 0.5f);
                text.color = c;
                yield return null;
            }
            Destroy(go);
        }

        private Canvas CreateWorldCanvas(Transform parent)
        {
            var canvasGo = new GameObject("Canvas");
            canvasGo.transform.SetParent(parent);
            canvasGo.transform.localPosition = Vector3.zero;
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            canvas.sortingOrder = 100;
            canvasGo.transform.localScale = Vector3.one * 0.02f;
            return canvas;
        }

        private UnityEngine.UI.Text CreateWorldText(Transform parent, string content, int fontSize)
        {
            var textGo = new GameObject("Text");
            textGo.transform.SetParent(parent);
            textGo.transform.localPosition = Vector3.zero;
            var text = textGo.AddComponent<UnityEngine.UI.Text>();
            text.text = content;
            text.fontSize = fontSize;
            text.alignment = TextAnchor.MiddleCenter;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var rt = text.GetComponent<RectTransform>();
            rt.sizeDelta = new Vector2(300, 100);
            return text;
        }
    }
}
