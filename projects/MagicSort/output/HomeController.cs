using UnityEngine;
using UnityEngine.UI;
using TMPro;
using MagicSort.Core;
using MagicSort.Domain;

namespace MagicSort.Game
{
    /// <summary>
    /// Controls the Home screen: displays player stats and navigates to gameplay.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Puzzle
    /// Role: Controller
    /// Phase: 1
    /// </remarks>
    public class HomeController : MonoBehaviour
    {
        #region Fields

        [Header("Currency Display")]
        [SerializeField] private TMP_Text coinText;
        [SerializeField] private TMP_Text gemText;

        [Header("Level Display")]
        [SerializeField] private TMP_Text levelText;

        [Header("Buttons")]
        [SerializeField] private Button playButton;
        [SerializeField] private Button settingsButton;

        private SignalBus _signalBus;
        private int _currentLevel;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            if (ProjectContext.HasInstance)
            {
                _signalBus = ProjectContext.Instance.Resolve<SignalBus>();
            }
        }

        private void Start()
        {
            SetupButtons();
            LoadPlayerData();
            UpdateUI();
            SubscribeSignals();
        }

        private void OnDestroy()
        {
            UnsubscribeSignals();
        }

        #endregion

        #region Private Methods

        private void SetupButtons()
        {
            if (playButton != null)
            {
                playButton.onClick.AddListener(OnPlayButtonClicked);
            }

            if (settingsButton != null)
            {
                settingsButton.onClick.AddListener(OnSettingsButtonClicked);
            }
        }

        private void LoadPlayerData()
        {
            if (SaveManager.HasInstance)
            {
                _currentLevel = SaveManager.Instance.LoadInt("HighestLevel", 0) + 1;
            }
            else
            {
                _currentLevel = 1;
            }
        }

        private void UpdateUI()
        {
            // Update currency display
            if (CurrencyManager.HasInstance)
            {
                if (coinText != null)
                {
                    coinText.text = CurrencyManager.Instance.Coins.ToString("N0");
                }

                if (gemText != null)
                {
                    gemText.text = CurrencyManager.Instance.Gems.ToString("N0");
                }
            }
            else
            {
                if (coinText != null) coinText.text = "0";
                if (gemText != null) gemText.text = "0";
            }

            // Update level display
            if (levelText != null)
            {
                levelText.text = $"Level {_currentLevel}";
            }
        }

        private void SubscribeSignals()
        {
            if (_signalBus != null)
            {
                _signalBus.Subscribe<CurrencyChangedSignal>(OnCurrencyChanged);
            }
        }

        private void UnsubscribeSignals()
        {
            if (_signalBus != null)
            {
                _signalBus.Unsubscribe<CurrencyChangedSignal>(OnCurrencyChanged);
            }
        }

        #endregion

        #region Signal Handlers

        private void OnCurrencyChanged(CurrencyChangedSignal signal)
        {
            UpdateUI();
        }

        #endregion

        #region Button Handlers

        private void OnPlayButtonClicked()
        {
            if (SceneLoader.HasInstance)
            {
                SceneLoader.Instance.LoadScene(SceneName.GamePlay);
            }
            else
            {
                UnityEngine.SceneManagement.SceneManager.LoadScene("GamePlay");
            }
        }

        private void OnSettingsButtonClicked()
        {
            // Settings popup would be shown via PopUpService
            if (PopUpService.HasInstance)
            {
                PopUpService.Instance.ShowPopup("Settings");
            }

            Debug.Log("[HomeController] Settings button clicked.");
        }

        #endregion
    }
}
