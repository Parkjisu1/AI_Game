using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using VeilBreaker.Core;

namespace VeilBreaker.UI
{
    /// <summary>
    /// Central UI lifecycle manager for popups and pages.
    /// Handles opening, closing, stacking, and resource-based loading of UI elements.
    /// </summary>
    /// <remarks>
    /// Layer: Game
    /// Genre: Idle
    /// Role: Manager
    /// Phase: 3
    /// </remarks>
    public class UISystem : Singleton<UISystem>
    {
        #region Constants

        private const string PopupResourcePath = "UI/Popups/";
        private const string PageResourcePath = "UI/Pages/";

        #endregion

        #region Fields

        [SerializeField] private Transform _popupRoot;
        [SerializeField] private Transform _pageRoot;

        private readonly Stack<PopupBase> _popupStack = new();
        private readonly Dictionary<Type, PopupBase> _cachedPopups = new();
        private readonly Dictionary<Type, PageBase> _cachedPages = new();
        private PageBase _currentPage;

        #endregion

        #region Properties

        /// <summary>
        /// Currently active page.
        /// </summary>
        public PageBase CurrentPage => _currentPage;

        /// <summary>
        /// Number of popups currently in the stack.
        /// </summary>
        public int PopupCount => _popupStack.Count;

        /// <summary>
        /// True if any popup is currently open.
        /// </summary>
        public bool HasOpenPopup => _popupStack.Count > 0;

        #endregion

        #region Unity Lifecycle

        private void Update()
        {
            if (Input.GetKeyDown(KeyCode.Escape) && _popupStack.Count > 0)
            {
                ClosePopup();
            }
        }

        #endregion

        #region Public Methods - Popups

        /// <summary>
        /// Open a popup of type T with no data.
        /// </summary>
        public void OpenPopup<T>() where T : PopupBase
        {
            OpenPopup<T>(null);
        }

        /// <summary>
        /// Open a popup of type T with optional data payload.
        /// Loads from Resources if not cached, pushes onto popup stack.
        /// </summary>
        public void OpenPopup<T>(object data) where T : PopupBase
        {
            var type = typeof(T);

            if (_cachedPopups.TryGetValue(type, out var cached) && cached != null)
            {
                cached.gameObject.SetActive(true);
                PushPopup(cached, data);
                return;
            }

            var prefab = Resources.Load<GameObject>(PopupResourcePath + type.Name);
            if (prefab == null)
            {
                Debug.LogError($"[UISystem] Popup prefab not found: {PopupResourcePath}{type.Name}");
                return;
            }

            var root = _popupRoot != null ? _popupRoot : transform;
            var instance = Instantiate(prefab, root);
            var popup = instance.GetComponent<T>();

            if (popup == null)
            {
                Debug.LogError($"[UISystem] Prefab '{type.Name}' missing {type.Name} component.");
                Destroy(instance);
                return;
            }

            _cachedPopups[type] = popup;
            PushPopup(popup, data);
        }

        /// <summary>
        /// Close the topmost popup in the stack.
        /// </summary>
        public void ClosePopup()
        {
            if (_popupStack.Count == 0) return;

            var popup = _popupStack.Pop();
            if (popup != null)
            {
                popup.Close();
                popup.gameObject.SetActive(false);
            }

            EventManager.Publish(GameConstants.Events.OnPopupClosed);
        }

        /// <summary>
        /// Close all open popups.
        /// </summary>
        public void CloseAllPopups()
        {
            while (_popupStack.Count > 0)
            {
                ClosePopup();
            }
        }

        /// <summary>
        /// Get the current topmost popup if it matches type T.
        /// </summary>
        public T GetCurrentPopup<T>() where T : PopupBase
        {
            if (_popupStack.Count == 0) return null;

            var top = _popupStack.Peek();
            return top as T;
        }

        /// <summary>
        /// Find a cached popup of type T regardless of stack position.
        /// </summary>
        public T FindPopup<T>() where T : PopupBase
        {
            var type = typeof(T);
            if (_cachedPopups.TryGetValue(type, out var popup))
            {
                return popup as T;
            }
            return null;
        }

        #endregion

        #region Public Methods - Pages

        /// <summary>
        /// Switch to a page of type T. Hides current page, shows new page.
        /// </summary>
        public void OpenPage<T>() where T : PageBase
        {
            OpenPage<T>(null);
        }

        /// <summary>
        /// Switch to a page of type T with optional data.
        /// </summary>
        public void OpenPage<T>(object data) where T : PageBase
        {
            var type = typeof(T);

            if (_currentPage != null)
            {
                _currentPage.Hide();
                _currentPage.gameObject.SetActive(false);
            }

            CloseAllPopups();

            if (_cachedPages.TryGetValue(type, out var cached) && cached != null)
            {
                cached.gameObject.SetActive(true);
                _currentPage = cached;
                _currentPage.Show(data);
                EventManager.Publish(GameConstants.Events.OnPageChanged, type.Name);
                return;
            }

            var prefab = Resources.Load<GameObject>(PageResourcePath + type.Name);
            if (prefab == null)
            {
                Debug.LogError($"[UISystem] Page prefab not found: {PageResourcePath}{type.Name}");
                return;
            }

            var root = _pageRoot != null ? _pageRoot : transform;
            var instance = Instantiate(prefab, root);
            var page = instance.GetComponent<T>();

            if (page == null)
            {
                Debug.LogError($"[UISystem] Prefab '{type.Name}' missing {type.Name} component.");
                Destroy(instance);
                return;
            }

            _cachedPages[type] = page;
            _currentPage = page;
            _currentPage.Show(data);
            EventManager.Publish(GameConstants.Events.OnPageChanged, type.Name);
        }

        /// <summary>
        /// Get the current active page if it matches type T.
        /// </summary>
        public T GetCurrentPage<T>() where T : PageBase
        {
            return _currentPage as T;
        }

        #endregion

        #region Private Methods

        private void PushPopup(PopupBase popup, object data)
        {
            _popupStack.Push(popup);
            popup.Open(data);
            EventManager.Publish(GameConstants.Events.OnPopupOpened, popup.GetType().Name);
        }

        #endregion
    }

    /// <summary>
    /// Base class for all popup UI elements.
    /// Popups are stacked and managed by UISystem.
    /// </summary>
    public abstract class PopupBase : MonoBehaviour
    {
        /// <summary>
        /// Called when popup is opened. Override to handle initialization with data.
        /// </summary>
        public virtual void Open(object data = null) { }

        /// <summary>
        /// Called when popup is closed. Override to handle cleanup.
        /// </summary>
        public virtual void Close() { }

        /// <summary>
        /// Convenience method to close this popup via UISystem.
        /// </summary>
        protected void CloseThis()
        {
            if (UISystem.HasInstance)
            {
                UISystem.Instance.ClosePopup();
            }
        }
    }

    /// <summary>
    /// Base class for all page UI elements.
    /// Pages are mutually exclusive - only one active at a time.
    /// </summary>
    public abstract class PageBase : MonoBehaviour
    {
        /// <summary>
        /// Called when page becomes active. Override to refresh UI.
        /// </summary>
        public virtual void Show(object data = null) { }

        /// <summary>
        /// Called when page becomes inactive. Override to handle cleanup.
        /// </summary>
        public virtual void Hide() { }
    }
}
