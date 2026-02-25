using UnityEngine;

namespace BlockBlast.Core
{
    public class AudioManager : Singleton<AudioManager>
    {
        private AudioSource _bgmSource;
        private AudioSource _sfxSource;
        private bool _isMuted;

        protected override void Awake()
        {
            base.Awake();
            InitAudioSources();
            _isMuted = SaveManager.Instance.LoadInt(SaveManager.KEY_SOUND_ON, 1) == 0;
            ApplyMute();
        }

        private void InitAudioSources()
        {
            _bgmSource = gameObject.AddComponent<AudioSource>();
            _bgmSource.loop = true;
            _bgmSource.playOnAwake = false;
            _bgmSource.volume = 0.5f;

            _sfxSource = gameObject.AddComponent<AudioSource>();
            _sfxSource.loop = false;
            _sfxSource.playOnAwake = false;
            _sfxSource.volume = 0.7f;
        }

        public void PlaySFX(AudioClip clip)
        {
            if (clip == null || _isMuted) return;
            _sfxSource.PlayOneShot(clip);
        }

        public void PlayBGM(AudioClip clip)
        {
            if (clip == null) return;
            _bgmSource.clip = clip;
            if (!_isMuted)
                _bgmSource.Play();
        }

        public void StopBGM()
        {
            _bgmSource.Stop();
        }

        public bool IsMuted => _isMuted;

        public void ToggleMute()
        {
            _isMuted = !_isMuted;
            SaveManager.Instance.SaveInt(SaveManager.KEY_SOUND_ON, _isMuted ? 0 : 1);
            ApplyMute();
        }

        private void ApplyMute()
        {
            _bgmSource.mute = _isMuted;
            _sfxSource.mute = _isMuted;
        }

        public void SetBGMVolume(float volume)
        {
            _bgmSource.volume = Mathf.Clamp01(volume);
        }

        public void SetSFXVolume(float volume)
        {
            _sfxSource.volume = Mathf.Clamp01(volume);
        }
    }
}
