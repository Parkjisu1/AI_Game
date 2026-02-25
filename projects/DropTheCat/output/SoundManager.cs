using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace DropTheCat.Core
{
    /// <summary>
    /// BGM and SFX playback manager with volume/mute persistence.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Manager
    /// Phase: 0
    /// </remarks>
    public class SoundManager : Singleton<SoundManager>
    {
        #region Constants

        private const string KEY_BGM_VOLUME = "BGMVolume";
        private const string KEY_SFX_VOLUME = "SFXVolume";
        private const string KEY_BGM_MUTE = "BGMMute";
        private const string KEY_SFX_MUTE = "SFXMute";
        private const float DEFAULT_FADE_DURATION = 0.5f;

        #endregion

        #region Fields

        [SerializeField] private AudioSource bgmSource;
        [SerializeField] private AudioSource sfxSource;
        [SerializeField] private AudioClip[] bgmClips;
        [SerializeField] private AudioClip[] sfxClips;

        private readonly Dictionary<string, AudioClip> _bgmCache = new Dictionary<string, AudioClip>();
        private readonly Dictionary<string, AudioClip> _sfxCache = new Dictionary<string, AudioClip>();

        private float _bgmVolume = 1f;
        private float _sfxVolume = 1f;
        private bool _bgmMuted;
        private bool _sfxMuted;
        private Coroutine _fadeCoroutine;
        private string _currentBgmId;

        #endregion

        #region Properties

        public bool IsBGMMuted => _bgmMuted;
        public bool IsSFXMuted => _sfxMuted;
        public float BGMVolume => _bgmVolume;
        public float SFXVolume => _sfxVolume;

        #endregion

        #region Unity Lifecycle

        protected override void OnSingletonAwake()
        {
            InitAudioSources();
            CacheClips();
            LoadSettings();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Play BGM with crossfade.
        /// </summary>
        public void PlayBGM(string bgmId)
        {
            if (string.IsNullOrEmpty(bgmId)) return;
            if (_currentBgmId == bgmId && bgmSource.isPlaying) return;

            if (!_bgmCache.TryGetValue(bgmId, out var clip))
            {
                Debug.LogWarning($"[SoundManager] BGM '{bgmId}' not found.");
                return;
            }

            _currentBgmId = bgmId;

            if (_fadeCoroutine != null)
            {
                StopCoroutine(_fadeCoroutine);
            }

            if (bgmSource.isPlaying)
            {
                _fadeCoroutine = StartCoroutine(CrossFadeBGM(clip));
            }
            else
            {
                bgmSource.clip = clip;
                bgmSource.volume = _bgmMuted ? 0f : _bgmVolume;
                bgmSource.Play();
            }
        }

        /// <summary>
        /// Stop BGM with optional fade out.
        /// </summary>
        public void StopBGM(float fadeDuration = DEFAULT_FADE_DURATION)
        {
            if (!bgmSource.isPlaying) return;

            if (_fadeCoroutine != null)
            {
                StopCoroutine(_fadeCoroutine);
            }

            _fadeCoroutine = StartCoroutine(FadeOutBGM(fadeDuration));
            _currentBgmId = null;
        }

        /// <summary>
        /// Play a one-shot SFX.
        /// </summary>
        public void PlaySFX(string sfxId)
        {
            if (string.IsNullOrEmpty(sfxId)) return;
            if (_sfxMuted) return;

            if (!_sfxCache.TryGetValue(sfxId, out var clip))
            {
                Debug.LogWarning($"[SoundManager] SFX '{sfxId}' not found.");
                return;
            }

            sfxSource.PlayOneShot(clip, _sfxVolume);
        }

        /// <summary>
        /// Set BGM volume (0~1).
        /// </summary>
        public void SetBGMVolume(float volume)
        {
            _bgmVolume = Mathf.Clamp01(volume);
            if (!_bgmMuted)
            {
                bgmSource.volume = _bgmVolume;
            }
            SaveSettings();
        }

        /// <summary>
        /// Set SFX volume (0~1).
        /// </summary>
        public void SetSFXVolume(float volume)
        {
            _sfxVolume = Mathf.Clamp01(volume);
            sfxSource.volume = _sfxVolume;
            SaveSettings();
        }

        /// <summary>
        /// Set mute state for BGM and SFX.
        /// </summary>
        public void SetMute(bool bgmMute, bool sfxMute)
        {
            _bgmMuted = bgmMute;
            _sfxMuted = sfxMute;

            bgmSource.volume = _bgmMuted ? 0f : _bgmVolume;
            sfxSource.mute = _sfxMuted;

            SaveSettings();
        }

        /// <summary>
        /// Toggle BGM mute.
        /// </summary>
        public void ToggleBGMMute()
        {
            SetMute(!_bgmMuted, _sfxMuted);
        }

        /// <summary>
        /// Toggle SFX mute.
        /// </summary>
        public void ToggleSFXMute()
        {
            SetMute(_bgmMuted, !_sfxMuted);
        }

        #endregion

        #region Private Methods

        private void InitAudioSources()
        {
            if (bgmSource == null)
            {
                bgmSource = gameObject.AddComponent<AudioSource>();
            }
            bgmSource.loop = true;
            bgmSource.playOnAwake = false;

            if (sfxSource == null)
            {
                sfxSource = gameObject.AddComponent<AudioSource>();
            }
            sfxSource.loop = false;
            sfxSource.playOnAwake = false;
        }

        private void CacheClips()
        {
            if (bgmClips != null)
            {
                foreach (var clip in bgmClips)
                {
                    if (clip != null && !_bgmCache.ContainsKey(clip.name))
                    {
                        _bgmCache[clip.name] = clip;
                    }
                }
            }

            if (sfxClips != null)
            {
                foreach (var clip in sfxClips)
                {
                    if (clip != null && !_sfxCache.ContainsKey(clip.name))
                    {
                        _sfxCache[clip.name] = clip;
                    }
                }
            }
        }

        private void LoadSettings()
        {
            if (SaveManager.Instance == null) return;

            _bgmVolume = SaveManager.Instance.LoadFloat(KEY_BGM_VOLUME, 1f);
            _sfxVolume = SaveManager.Instance.LoadFloat(KEY_SFX_VOLUME, 1f);
            _bgmMuted = SaveManager.Instance.LoadInt(KEY_BGM_MUTE, 0) == 1;
            _sfxMuted = SaveManager.Instance.LoadInt(KEY_SFX_MUTE, 0) == 1;

            bgmSource.volume = _bgmMuted ? 0f : _bgmVolume;
            sfxSource.volume = _sfxVolume;
            sfxSource.mute = _sfxMuted;
        }

        private void SaveSettings()
        {
            if (SaveManager.Instance == null) return;

            SaveManager.Instance.SaveFloat(KEY_BGM_VOLUME, _bgmVolume);
            SaveManager.Instance.SaveFloat(KEY_SFX_VOLUME, _sfxVolume);
            SaveManager.Instance.SaveInt(KEY_BGM_MUTE, _bgmMuted ? 1 : 0);
            SaveManager.Instance.SaveInt(KEY_SFX_MUTE, _sfxMuted ? 1 : 0);
        }

        private IEnumerator CrossFadeBGM(AudioClip newClip)
        {
            float timer = 0f;
            float startVolume = bgmSource.volume;

            // Fade out
            while (timer < DEFAULT_FADE_DURATION)
            {
                timer += Time.unscaledDeltaTime;
                bgmSource.volume = Mathf.Lerp(startVolume, 0f, timer / DEFAULT_FADE_DURATION);
                yield return null;
            }

            // Switch clip
            bgmSource.clip = newClip;
            bgmSource.Play();

            // Fade in
            timer = 0f;
            float targetVolume = _bgmMuted ? 0f : _bgmVolume;
            while (timer < DEFAULT_FADE_DURATION)
            {
                timer += Time.unscaledDeltaTime;
                bgmSource.volume = Mathf.Lerp(0f, targetVolume, timer / DEFAULT_FADE_DURATION);
                yield return null;
            }

            bgmSource.volume = targetVolume;
            _fadeCoroutine = null;
        }

        private IEnumerator FadeOutBGM(float duration)
        {
            float timer = 0f;
            float startVolume = bgmSource.volume;

            while (timer < duration)
            {
                timer += Time.unscaledDeltaTime;
                bgmSource.volume = Mathf.Lerp(startVolume, 0f, timer / duration);
                yield return null;
            }

            bgmSource.Stop();
            bgmSource.volume = _bgmMuted ? 0f : _bgmVolume;
            _fadeCoroutine = null;
        }

        #endregion
    }
}
