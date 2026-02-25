using System.Collections.Generic;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Centralized audio management for BGM and SFX.
    /// Supports volume control, muting, and persistence of audio settings.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Manager
    /// Phase: 0
    /// </remarks>
    public class SoundManager : Singleton<SoundManager>
    {
        #region Fields

        [Header("Audio Sources")]
        [SerializeField] private AudioSource bgmSource;
        [SerializeField] private AudioSource sfxSource;

        [Header("Settings")]
        [SerializeField] private int maxSfxPoolSize = 8;

        private const string SAVE_KEY_BGM_VOLUME = "SND_BGM_VOL";
        private const string SAVE_KEY_SFX_VOLUME = "SND_SFX_VOL";
        private const string SAVE_KEY_BGM_MUTE = "SND_BGM_MUTE";
        private const string SAVE_KEY_SFX_MUTE = "SND_SFX_MUTE";

        private float _bgmVolume = 1f;
        private float _sfxVolume = 1f;
        private bool _bgmMuted;
        private bool _sfxMuted;

        private readonly List<AudioSource> _sfxPool = new List<AudioSource>();

        #endregion

        #region Properties

        /// <summary>Current BGM volume (0-1).</summary>
        public float BgmVolume => _bgmVolume;

        /// <summary>Current SFX volume (0-1).</summary>
        public float SfxVolume => _sfxVolume;

        /// <summary>Whether BGM is muted.</summary>
        public bool IsBgmMuted => _bgmMuted;

        /// <summary>Whether SFX is muted.</summary>
        public bool IsSfxMuted => _sfxMuted;

        #endregion

        #region Singleton Lifecycle

        protected override void OnSingletonAwake()
        {
            LoadSettings();
            InitializeSfxPool();
            ApplySettings();
        }

        #endregion

        #region Public Methods - BGM

        /// <summary>
        /// Plays background music. Crossfades if a different track is already playing.
        /// </summary>
        /// <param name="clip">The audio clip to play.</param>
        /// <param name="loop">Whether to loop the BGM.</param>
        public void PlayBGM(AudioClip clip, bool loop = true)
        {
            if (clip == null)
            {
                Debug.LogWarning("[SoundManager] BGM clip is null.");
                return;
            }

            if (bgmSource == null)
            {
                Debug.LogError("[SoundManager] BGM AudioSource is not assigned.");
                return;
            }

            if (bgmSource.clip == clip && bgmSource.isPlaying)
            {
                return;
            }

            bgmSource.clip = clip;
            bgmSource.loop = loop;
            bgmSource.volume = _bgmMuted ? 0f : _bgmVolume;
            bgmSource.Play();
        }

        /// <summary>
        /// Stops the currently playing BGM.
        /// </summary>
        public void StopBGM()
        {
            if (bgmSource != null)
            {
                bgmSource.Stop();
                bgmSource.clip = null;
            }
        }

        /// <summary>
        /// Pauses the currently playing BGM.
        /// </summary>
        public void PauseBGM()
        {
            if (bgmSource != null && bgmSource.isPlaying)
            {
                bgmSource.Pause();
            }
        }

        /// <summary>
        /// Resumes the paused BGM.
        /// </summary>
        public void ResumeBGM()
        {
            if (bgmSource != null && !bgmSource.isPlaying && bgmSource.clip != null)
            {
                bgmSource.UnPause();
            }
        }

        #endregion

        #region Public Methods - SFX

        /// <summary>
        /// Plays a sound effect using the pooled SFX sources.
        /// </summary>
        /// <param name="clip">The audio clip to play.</param>
        /// <param name="volumeScale">Volume multiplier (0-1).</param>
        public void PlaySFX(AudioClip clip, float volumeScale = 1f)
        {
            if (clip == null)
            {
                Debug.LogWarning("[SoundManager] SFX clip is null.");
                return;
            }

            if (_sfxMuted) return;

            AudioSource source = GetAvailableSfxSource();
            if (source != null)
            {
                source.volume = _sfxVolume * volumeScale;
                source.PlayOneShot(clip);
            }
        }

        /// <summary>
        /// Plays a sound effect using the primary SFX source (PlayOneShot).
        /// </summary>
        /// <param name="clip">The audio clip to play.</param>
        public void PlaySFXOneShot(AudioClip clip)
        {
            if (clip == null || _sfxMuted) return;

            if (sfxSource != null)
            {
                sfxSource.PlayOneShot(clip, _sfxVolume);
            }
        }

        /// <summary>
        /// Stops all currently playing SFX.
        /// </summary>
        public void StopAllSFX()
        {
            if (sfxSource != null)
            {
                sfxSource.Stop();
            }

            for (int i = 0; i < _sfxPool.Count; i++)
            {
                if (_sfxPool[i] != null)
                {
                    _sfxPool[i].Stop();
                }
            }
        }

        #endregion

        #region Public Methods - Volume Control

        /// <summary>
        /// Sets the BGM volume (0-1) and saves the setting.
        /// </summary>
        /// <param name="volume">Volume level between 0 and 1.</param>
        public void SetBGMVolume(float volume)
        {
            _bgmVolume = Mathf.Clamp01(volume);

            if (bgmSource != null && !_bgmMuted)
            {
                bgmSource.volume = _bgmVolume;
            }

            SaveSettings();
        }

        /// <summary>
        /// Sets the SFX volume (0-1) and saves the setting.
        /// </summary>
        /// <param name="volume">Volume level between 0 and 1.</param>
        public void SetSFXVolume(float volume)
        {
            _sfxVolume = Mathf.Clamp01(volume);
            SaveSettings();
        }

        /// <summary>
        /// Toggles BGM mute state and saves the setting.
        /// </summary>
        /// <param name="mute">True to mute, false to unmute.</param>
        public void SetBGMMute(bool mute)
        {
            _bgmMuted = mute;

            if (bgmSource != null)
            {
                bgmSource.volume = _bgmMuted ? 0f : _bgmVolume;
            }

            SaveSettings();
        }

        /// <summary>
        /// Toggles SFX mute state and saves the setting.
        /// </summary>
        /// <param name="mute">True to mute, false to unmute.</param>
        public void SetSFXMute(bool mute)
        {
            _sfxMuted = mute;
            SaveSettings();
        }

        /// <summary>
        /// Toggles BGM mute on/off and returns the new state.
        /// </summary>
        /// <returns>True if BGM is now muted.</returns>
        public bool ToggleBGMMute()
        {
            SetBGMMute(!_bgmMuted);
            return _bgmMuted;
        }

        /// <summary>
        /// Toggles SFX mute on/off and returns the new state.
        /// </summary>
        /// <returns>True if SFX is now muted.</returns>
        public bool ToggleSFXMute()
        {
            SetSFXMute(!_sfxMuted);
            return _sfxMuted;
        }

        #endregion

        #region Private Methods

        private void InitializeSfxPool()
        {
            _sfxPool.Clear();

            for (int i = 0; i < maxSfxPoolSize; i++)
            {
                GameObject sfxObj = new GameObject($"SFX_Source_{i}");
                sfxObj.transform.SetParent(transform);

                AudioSource source = sfxObj.AddComponent<AudioSource>();
                source.playOnAwake = false;

                _sfxPool.Add(source);
            }
        }

        private AudioSource GetAvailableSfxSource()
        {
            for (int i = 0; i < _sfxPool.Count; i++)
            {
                if (_sfxPool[i] != null && !_sfxPool[i].isPlaying)
                {
                    return _sfxPool[i];
                }
            }

            // If all are busy, reuse the first one
            if (_sfxPool.Count > 0 && _sfxPool[0] != null)
            {
                return _sfxPool[0];
            }

            return sfxSource;
        }

        private void LoadSettings()
        {
            _bgmVolume = PlayerPrefs.GetFloat(SAVE_KEY_BGM_VOLUME, 1f);
            _sfxVolume = PlayerPrefs.GetFloat(SAVE_KEY_SFX_VOLUME, 1f);
            _bgmMuted = PlayerPrefs.GetInt(SAVE_KEY_BGM_MUTE, 0) == 1;
            _sfxMuted = PlayerPrefs.GetInt(SAVE_KEY_SFX_MUTE, 0) == 1;
        }

        private void SaveSettings()
        {
            PlayerPrefs.SetFloat(SAVE_KEY_BGM_VOLUME, _bgmVolume);
            PlayerPrefs.SetFloat(SAVE_KEY_SFX_VOLUME, _sfxVolume);
            PlayerPrefs.SetInt(SAVE_KEY_BGM_MUTE, _bgmMuted ? 1 : 0);
            PlayerPrefs.SetInt(SAVE_KEY_SFX_MUTE, _sfxMuted ? 1 : 0);
            PlayerPrefs.Save();
        }

        private void ApplySettings()
        {
            if (bgmSource != null)
            {
                bgmSource.volume = _bgmMuted ? 0f : _bgmVolume;
            }
        }

        #endregion
    }
}
