using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using VeilBreaker.Core;
using VeilBreaker.Quest;
using VeilBreaker.UI;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Dungeon selection popup. Lists available dungeons with remaining entries.
    /// Entry button is disabled when remaining count is zero.
    /// Refreshes entry counts in response to OnDungeonComplete event.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: UX
    /// System: UI
    /// Phase: 3
    /// </remarks>
    public class PopupDungeon : PopupBase
    {
        #region Fields

        [SerializeField] private DungeonItemUI[] _dungeonItems;
        [SerializeField] private TextMeshProUGUI _dungeonKeyText;
        [SerializeField] private Button _closeButton;

        #endregion

        #region Unity Lifecycle

        private void OnEnable()
        {
            _closeButton?.onClick.AddListener(OnCloseClicked);
            EventManager.Subscribe(GameConstants.Events.OnDungeonComplete, OnDungeonComplete);
        }

        private void OnDisable()
        {
            _closeButton?.onClick.RemoveListener(OnCloseClicked);
            EventManager.Unsubscribe(GameConstants.Events.OnDungeonComplete, OnDungeonComplete);
        }

        #endregion

        #region Public Methods (PopupBase override)

        /// <summary>
        /// Opens the dungeon popup and populates the dungeon list.
        /// </summary>
        public override void Open(object data = null)
        {
            RefreshDungeonList();
        }

        /// <summary>
        /// No cleanup required on close.
        /// </summary>
        public override void Close()
        {
        }

        #endregion

        #region Private Methods

        private void RefreshDungeonList()
        {
            if (!DungeonManager.HasInstance) return;

            List<DungeonManager.DungeonData> dungeons = DungeonManager.Instance.GetAvailableDungeons();

            if (_dungeonItems != null)
            {
                for (int i = 0; i < _dungeonItems.Length; i++)
                {
                    if (_dungeonItems[i] == null) continue;

                    if (i < dungeons?.Count)
                    {
                        _dungeonItems[i].SetDungeon(dungeons[i]);
                        _dungeonItems[i].gameObject.SetActive(true);
                    }
                    else
                    {
                        _dungeonItems[i].gameObject.SetActive(false);
                    }
                }
            }

            RefreshDungeonKeyText();
        }

        private void RefreshDungeonKeyText()
        {
            if (_dungeonKeyText == null) return;

            if (VeilBreaker.Economy.CurrencyManager.HasInstance)
            {
                long keys = VeilBreaker.Economy.CurrencyManager.Instance
                    .GetBalance(GameConstants.CurrencyType.DungeonTicket);
                _dungeonKeyText.text = keys.ToString();
            }
        }

        private void OnDungeonComplete(object data)
        {
            RefreshDungeonList();
        }

        private void OnCloseClicked()
        {
            CloseThis();
        }

        #endregion
    }

    /// <summary>
    /// A single dungeon entry row in PopupDungeon.
    /// User assigns Inspector fields; SetDungeon populates runtime data.
    /// </summary>
    public class DungeonItemUI : MonoBehaviour
    {
        #region Fields

        [SerializeField] private TextMeshProUGUI _nameText;
        [SerializeField] private TextMeshProUGUI _remainText;
        [SerializeField] private Button _enterButton;

        private DungeonManager.DungeonData _dungeonData;

        #endregion

        #region Public Methods

        /// <summary>
        /// Populates this row with dungeon data.
        /// Disables the enter button if remaining entries are zero.
        /// </summary>
        public void SetDungeon(DungeonManager.DungeonData dungeonData)
        {
            _dungeonData = dungeonData;

            if (_nameText != null) _nameText.text = dungeonData?.name ?? "";
            if (_remainText != null) _remainText.text = $"{dungeonData?.remainEntries ?? 0}";

            _enterButton?.onClick.RemoveAllListeners();
            _enterButton?.onClick.AddListener(OnEnterClicked);

            if (_enterButton != null)
            {
                _enterButton.interactable = (dungeonData?.remainEntries ?? 0) > 0;
            }
        }

        #endregion

        #region Private Methods

        private void OnEnterClicked()
        {
            if (_dungeonData == null || !DungeonManager.HasInstance) return;

            DungeonManager.Instance.EnterDungeon(_dungeonData.dungeonId);
        }

        #endregion
    }
}
