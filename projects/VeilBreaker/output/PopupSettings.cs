using TMPro;
using UnityEngine;
using UnityEngine.UI;
using VeilBreaker.Data;
using VeilBreaker.UI;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Settings popup for BGM/SFX toggles and app version display.
    /// Saves settings to PlayerPrefs (lightweight) rather than the JSON save file.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Generic
    /// Role: UX
    /// System: UI
    /// Phase: 3
    /// </remarks>
    public class PopupSettings : PopupBase
    {
        #region Constants

        private const string PrefsBGM = "BGM";
        private const string PrefsSFX = "SFX";
        private const int DefaultOn = 1;

        #endregion

        #region Fields

        [SerializeField] private Toggle _bgmToggle;
        [SerializeField] private Toggle _sfxToggle;
        [SerializeField] private TextMeshProUGUI _versionText;
        [SerializeField] private Button _closeButton;

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            _bgmToggle?.onValueChanged.AddListener(OnBgmToggleChanged);
            _sfxToggle?.onValueChanged.AddListener(OnSfxToggleChanged);
            _closeButton?.onClick.AddListener(OnCloseClicked);
        }

        private void OnDisable()
        {
            _bgmToggle?.onValueChanged.RemoveListener(OnBgmToggleChanged);
            _sfxToggle?.onValueChanged.RemoveListener(OnSfxToggleChanged);
            _closeButton?.onClick.RemoveListener(OnCloseClicked);
        }

        #endregion

        #region Public Methods (PopupBase override)

        /// <summary>
        /// Opens the settings popup and loads current settings from PlayerPrefs.
        /// </summary>
        public override void Open(object data = null)
        {
            LoadSettingsFromPrefs();
        }

        /// <summary>
        /// Saves settings to PlayerPrefs on close.
        /// </summary>
        public override void Close()
        {
            PlayerPrefs.Save();
        }

        #endregion

        #region Private Methods

        private void LoadSettingsFromPrefs()
        {
            bool bgmOn = PlayerPrefs.GetInt(PrefsBGM, DefaultOn) == 1;
            bool sfxOn = PlayerPrefs.GetInt(PrefsSFX, DefaultOn) == 1;

            // Temporarily remove listener to prevent immediate callbacks during setup
            _bgmToggle?.onValueChanged.RemoveListener(OnBgmToggleChanged);
            _sfxToggle?.onValueChanged.RemoveListener(OnSfxToggleChanged);

            if (_bgmToggle != null) _bgmToggle.isOn = bgmOn;
            if (_sfxToggle != null) _sfxToggle.isOn = sfxOn;

            _bgmToggle?.onValueChanged.AddListener(OnBgmToggleChanged);
            _sfxToggle?.onValueChanged.AddListener(OnSfxToggleChanged);

            ApplyBGM(bgmOn);
            ApplySFX(sfxOn);

            if (_versionText != null)
            {
                _versionText.text = $"v{Application.version}";
            }
        }

        private void OnBgmToggleChanged(bool value)
        {
            PlayerPrefs.SetInt(PrefsBGM, value ? 1 : 0);
            ApplyBGM(value);
        }

        private void OnSfxToggleChanged(bool value)
        {
            PlayerPrefs.SetInt(PrefsSFX, value ? 1 : 0);
            ApplySFX(value);
        }

        /// <summary>
        /// Pauses AudioListener to mute all audio when BGM is disabled.
        /// </summary>
        private void ApplyBGM(bool value)
        {
            AudioListener.pause = !value;
        }

        /// <summary>
        /// Sets AudioListener volume for SFX. 0 when disabled, 1 when enabled.
        /// </summary>
        private void ApplySFX(bool value)
        {
            AudioListener.volume = value ? 1f : 0f;
        }

        private void OnCloseClicked()
        {
            CloseThis();
        }

        #endregion
    }
}
