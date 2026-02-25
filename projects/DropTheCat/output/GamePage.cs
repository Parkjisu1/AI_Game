using UnityEngine;
using UnityEngine.UI;
using DropTheCat.Core;
using DropTheCat.Domain;

namespace DropTheCat.Game
{
    /// <summary>
    /// Handles in-game UI display and touch/drag input for tile sliding.
    /// Delegates all game logic to domain systems (SlideProcessor, BoosterManager, etc.).
    /// </summary>
    /// <remarks>
    /// Layer: Game | Genre: Puzzle | Role: Handler | Phase: 3
    /// </remarks>
    public class GamePage : MonoBehaviour
    {
        #region Constants

        private const float MIN_DRAG_DISTANCE = 0.5f;

        #endregion

        #region Fields

        [Header("Level Info")]
        [SerializeField] private Text levelText;
        [SerializeField] private Text moveCountText;

        [Header("Booster Buttons")]
        [SerializeField] private Button hintButton;
        [SerializeField] private Button undoButton;
        [SerializeField] private Button magnetButton;
        [SerializeField] private Button shuffleButton;

        [Header("Booster Count Labels")]
        [SerializeField] private Text hintCountText;
        [SerializeField] private Text undoCountText;
        [SerializeField] private Text magnetCountText;
        [SerializeField] private Text shuffleCountText;

        [Header("Controls")]
        [SerializeField] private Button pauseButton;

        [Header("Input Settings")]
        [SerializeField] private float dragThreshold = MIN_DRAG_DISTANCE;

        private bool _inputLocked;
        private bool _isDragging;
        private Vector3 _dragStartWorldPos;
        private Vector2Int _dragStartGridPos;
        private Camera _mainCamera;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            _mainCamera = Camera.main;
        }

        private void OnEnable()
        {
            BindButtons();

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Subscribe<OnMoveCountChanged>(HandleMoveCountChanged);
                EventManager.Instance.Subscribe<OnBoosterCountChanged>(HandleBoosterCountChanged);
                EventManager.Instance.Subscribe<OnGameStateChanged>(HandleGameStateChanged);
                EventManager.Instance.Subscribe<OnLevelLoaded>(HandleLevelLoaded);
            }
        }

        private void OnDisable()
        {
            UnbindButtons();

            if (EventManager.HasInstance)
            {
                EventManager.Instance.Unsubscribe<OnMoveCountChanged>(HandleMoveCountChanged);
                EventManager.Instance.Unsubscribe<OnBoosterCountChanged>(HandleBoosterCountChanged);
                EventManager.Instance.Unsubscribe<OnGameStateChanged>(HandleGameStateChanged);
                EventManager.Instance.Unsubscribe<OnLevelLoaded>(HandleLevelLoaded);
            }
        }

        private void Update()
        {
            HandleTouchInput();
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initialize UI with level data: level number, move count reset, booster states.
        /// </summary>
        public void InitUI(LevelData levelData)
        {
            if (levelData == null) return;

            if (levelText != null)
            {
                levelText.text = $"Level {levelData.levelNumber}";
            }

            UpdateMoveCount(0);
            UpdateBoosterButtons();
        }

        /// <summary>
        /// Update the move count display.
        /// </summary>
        public void UpdateMoveCount(int count)
        {
            if (moveCountText != null)
            {
                moveCountText.text = count.ToString();
            }
        }

        /// <summary>
        /// Refresh all booster button states (count labels and interactability).
        /// </summary>
        public void UpdateBoosterButtons()
        {
            UpdateSingleBoosterButton(BoosterType.Hint, hintButton, hintCountText);
            UpdateSingleBoosterButton(BoosterType.Undo, undoButton, undoCountText);
            UpdateSingleBoosterButton(BoosterType.Magnet, magnetButton, magnetCountText);
            UpdateSingleBoosterButton(BoosterType.Shuffle, shuffleButton, shuffleCountText);
        }

        /// <summary>
        /// Handle pause button click: delegate to GameManager.
        /// </summary>
        public void OnPauseClicked()
        {
            if (GameManager.HasInstance)
            {
                GameManager.Instance.PauseGame();
            }
        }

        /// <summary>
        /// Lock or unlock player input. Locked during animations, transitions, etc.
        /// </summary>
        public void SetInputLocked(bool locked)
        {
            _inputLocked = locked;
        }

        #endregion

        #region Input Handling

        /// <summary>
        /// Process single-touch input: detect touch start, track drag, determine direction,
        /// and delegate to SlideProcessor on release.
        /// Uses Input.GetMouseButton for unified mouse/touch handling.
        /// </summary>
        private void HandleTouchInput()
        {
            if (_inputLocked) return;

            // Check if processing is ongoing
            if (SlideProcessor.HasInstance && SlideProcessor.Instance.IsProcessing) return;
            if (DropProcessor.HasInstance && DropProcessor.Instance.IsDropping) return;

            // Touch start
            if (Input.GetMouseButtonDown(0))
            {
                OnTouchStart(Input.mousePosition);
            }
            // Touch end
            else if (Input.GetMouseButtonUp(0) && _isDragging)
            {
                OnTouchEnd(Input.mousePosition);
            }
        }

        private void OnTouchStart(Vector3 screenPos)
        {
            if (_mainCamera == null) return;

            _dragStartWorldPos = _mainCamera.ScreenToWorldPoint(screenPos);
            _dragStartWorldPos.z = 0f;

            if (!GridManager.HasInstance) return;

            _dragStartGridPos = GridManager.Instance.WorldToGrid(_dragStartWorldPos);

            // Only start dragging if the cell has a valid tile
            if (GridManager.Instance.IsInBounds(_dragStartGridPos.x, _dragStartGridPos.y))
            {
                CellData cell = GridManager.Instance.GetCell(
                    _dragStartGridPos.x, _dragStartGridPos.y);

                if (cell.occupantType != CellOccupant.None && cell.state != CellState.Blocked)
                {
                    _isDragging = true;
                }
            }
        }

        private void OnTouchEnd(Vector3 screenPos)
        {
            _isDragging = false;

            if (_mainCamera == null) return;

            Vector3 endWorldPos = _mainCamera.ScreenToWorldPoint(screenPos);
            endWorldPos.z = 0f;

            float dx = endWorldPos.x - _dragStartWorldPos.x;
            float dy = endWorldPos.y - _dragStartWorldPos.y;

            float absDx = Mathf.Abs(dx);
            float absDy = Mathf.Abs(dy);

            // Check minimum drag distance
            if (absDx < dragThreshold && absDy < dragThreshold) return;

            // Determine slide direction (dominant axis)
            SlideDirection direction;
            if (absDx > absDy)
            {
                direction = dx > 0 ? SlideDirection.Right : SlideDirection.Left;
            }
            else
            {
                direction = dy > 0 ? SlideDirection.Up : SlideDirection.Down;
            }

            // Delegate to SlideProcessor
            if (SlideProcessor.HasInstance)
            {
                SlideProcessor.Instance.ProcessSlide(_dragStartGridPos, direction);

                if (SoundManager.HasInstance)
                {
                    SoundManager.Instance.PlaySFX("swipe");
                }
            }
        }

        #endregion

        #region Booster Handling

        private void OnHintClicked()
        {
            TryUseBooster(BoosterType.Hint);
        }

        private void OnUndoClicked()
        {
            if (SlideProcessor.HasInstance)
            {
                if (BoosterManager.HasInstance && BoosterManager.Instance.UseBooster(BoosterType.Undo))
                {
                    SlideProcessor.Instance.UndoLastSlide();
                }
            }
        }

        private void OnMagnetClicked()
        {
            TryUseBooster(BoosterType.Magnet);
        }

        private void OnShuffleClicked()
        {
            TryUseBooster(BoosterType.Shuffle);
        }

        private void TryUseBooster(BoosterType boosterType)
        {
            if (!BoosterManager.HasInstance) return;

            BoosterManager.Instance.UseBooster(boosterType);
        }

        #endregion

        #region Event Handlers

        private void HandleMoveCountChanged(OnMoveCountChanged eventData)
        {
            UpdateMoveCount(eventData.MoveCount);
        }

        private void HandleBoosterCountChanged(OnBoosterCountChanged eventData)
        {
            UpdateBoosterButtons();
        }

        private void HandleGameStateChanged(OnGameStateChanged eventData)
        {
            switch (eventData.NewState)
            {
                case GameState.Playing:
                    SetInputLocked(false);
                    break;

                case GameState.Paused:
                case GameState.Result:
                case GameState.Loading:
                    SetInputLocked(true);
                    break;
            }
        }

        private void HandleLevelLoaded(OnLevelLoaded eventData)
        {
            UpdateMoveCount(0);
            UpdateBoosterButtons();
        }

        #endregion

        #region Private Methods

        private void BindButtons()
        {
            if (pauseButton != null)
            {
                pauseButton.onClick.AddListener(OnPauseClicked);
            }

            if (hintButton != null)
            {
                hintButton.onClick.AddListener(OnHintClicked);
            }

            if (undoButton != null)
            {
                undoButton.onClick.AddListener(OnUndoClicked);
            }

            if (magnetButton != null)
            {
                magnetButton.onClick.AddListener(OnMagnetClicked);
            }

            if (shuffleButton != null)
            {
                shuffleButton.onClick.AddListener(OnShuffleClicked);
            }
        }

        private void UnbindButtons()
        {
            if (pauseButton != null)
            {
                pauseButton.onClick.RemoveListener(OnPauseClicked);
            }

            if (hintButton != null)
            {
                hintButton.onClick.RemoveListener(OnHintClicked);
            }

            if (undoButton != null)
            {
                undoButton.onClick.RemoveListener(OnUndoClicked);
            }

            if (magnetButton != null)
            {
                magnetButton.onClick.RemoveListener(OnMagnetClicked);
            }

            if (shuffleButton != null)
            {
                shuffleButton.onClick.RemoveListener(OnShuffleClicked);
            }
        }

        private void UpdateSingleBoosterButton(
            BoosterType boosterType, Button button, Text countText)
        {
            if (button == null) return;

            int count = 0;
            bool canUse = false;

            if (BoosterManager.HasInstance)
            {
                count = BoosterManager.Instance.GetBoosterCount(boosterType);
                canUse = BoosterManager.Instance.CanUseBooster(boosterType);
            }

            button.interactable = canUse;

            if (countText != null)
            {
                countText.text = count.ToString();
            }
        }

        #endregion
    }
}
