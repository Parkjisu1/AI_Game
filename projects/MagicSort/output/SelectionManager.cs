using UnityEngine;
using MagicSort.Core;

namespace MagicSort.Domain
{
    /// <summary>
    /// Handles player touch/click input to select bottles and initiate pours.
    /// Uses Physics2D raycasting to detect bottle taps.
    /// </summary>
    /// <remarks>
    /// Layer: Domain
    /// Genre: Puzzle
    /// Role: Manager
    /// Phase: 1
    /// </remarks>
    public class SelectionManager : MonoBehaviour
    {
        #region Fields

        [Header("References")]
        [SerializeField] private Camera _camera;

        [Inject] private SignalBus _signalBus;

        private PourValidator _pourValidator;
        private PourProcessor _pourProcessor;
        private BottleCollection _bottleCollection;
        private UndoManager _undoManager;

        private BottleItem _selectedOrigin;
        private bool _isProcessing;
        private bool _isEnabled;

        #endregion

        #region Properties

        /// <summary>Whether input handling is currently enabled.</summary>
        public bool IsEnabled => _isEnabled;

        /// <summary>Whether a pour is currently being processed.</summary>
        public bool IsProcessing => _isProcessing;

        /// <summary>The currently selected origin bottle, or null if none.</summary>
        public BottleItem SelectedOrigin => _selectedOrigin;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            if (ProjectContext.HasInstance)
            {
                ProjectContext.Instance.Inject(this);
            }

            if (_camera == null)
            {
                _camera = Camera.main;
            }
        }

        private void Update()
        {
            if (!_isEnabled || _isProcessing)
            {
                return;
            }

            // Mouse/Touch input
            if (Input.GetMouseButtonDown(0))
            {
                HandleTap(Input.mousePosition);
            }
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Initializes the selection manager with required dependencies.
        /// </summary>
        /// <param name="validator">Pour validator instance.</param>
        /// <param name="processor">Pour processor instance.</param>
        /// <param name="collection">Bottle collection instance.</param>
        /// <param name="undoManager">Undo manager for saving states before pours.</param>
        public void Initialize(PourValidator validator, PourProcessor processor,
            BottleCollection collection, UndoManager undoManager)
        {
            _pourValidator = validator;
            _pourProcessor = processor;
            _bottleCollection = collection;
            _undoManager = undoManager;
        }

        /// <summary>
        /// Enables input handling.
        /// </summary>
        public void Enable()
        {
            _isEnabled = true;
        }

        /// <summary>
        /// Disables input handling and clears selection.
        /// </summary>
        public void Disable()
        {
            _isEnabled = false;
            ClearSelection();
        }

        /// <summary>
        /// Handles a bottle tap. If no origin is selected, selects it.
        /// If the same bottle is tapped again, deselects. Otherwise attempts a pour.
        /// </summary>
        /// <param name="bottle">The bottle that was tapped.</param>
        public void OnBottleTapped(BottleItem bottle)
        {
            if (bottle == null || _isProcessing)
            {
                return;
            }

            // No origin selected yet: select this as origin
            if (_selectedOrigin == null)
            {
                // Only select if it has water and is not completed
                if (bottle.CanPourFrom() && !bottle.IsComplete)
                {
                    _selectedOrigin = bottle;
                    _selectedOrigin.SetSelected(true);

                    FireBottleSelected(bottle, true);
                }
                return;
            }

            // Same bottle tapped: deselect
            if (_selectedOrigin == bottle)
            {
                ClearSelection();
                return;
            }

            // Different bottle tapped: try to pour
            if (_pourValidator != null && _pourValidator.CanPour(_selectedOrigin, bottle))
            {
                SelectionResult result = _pourValidator.CreateResult(_selectedOrigin, bottle);
                if (result != null && result.IsValid())
                {
                    // Save state for undo before executing pour
                    _undoManager?.SaveState(_bottleCollection);

                    ExecutePour(result);
                    return;
                }
            }

            // Pour not valid: try selecting the tapped bottle as new origin instead
            ClearSelection();

            if (bottle.CanPourFrom() && !bottle.IsComplete)
            {
                _selectedOrigin = bottle;
                _selectedOrigin.SetSelected(true);
                FireBottleSelected(bottle, true);
            }
        }

        /// <summary>
        /// Clears the current selection, deselecting any selected bottle.
        /// </summary>
        public void ClearSelection()
        {
            if (_selectedOrigin != null)
            {
                _selectedOrigin.SetSelected(false);
                _selectedOrigin = null;
            }
        }

        #endregion

        #region Private Methods

        private void HandleTap(Vector3 screenPosition)
        {
            if (_camera == null)
            {
                return;
            }

            Vector2 worldPos = _camera.ScreenToWorldPoint(screenPosition);
            RaycastHit2D hit = Physics2D.Raycast(worldPos, Vector2.zero);

            if (hit.collider != null)
            {
                BottleItem bottle = hit.collider.GetComponent<BottleItem>();
                if (bottle == null)
                {
                    bottle = hit.collider.GetComponentInParent<BottleItem>();
                }

                if (bottle != null)
                {
                    OnBottleTapped(bottle);
                    return;
                }
            }

            // Tapped empty space: deselect
            ClearSelection();
        }

        private void ExecutePour(SelectionResult result)
        {
            _isProcessing = true;
            ClearSelection();

            // Use animated pour
            StartCoroutine(_pourProcessor.ExecutePourAnimated(result, () =>
            {
                _isProcessing = false;
            }));
        }

        private void FireBottleSelected(BottleItem bottle, bool isSource)
        {
            if (_signalBus == null || _bottleCollection == null)
            {
                return;
            }

            int index = _bottleCollection.GetBottleIndex(bottle);
            _signalBus.Fire(new BottleSelectedSignal
            {
                BottleIndex = index,
                IsSource = isSource
            });
        }

        #endregion
    }
}
