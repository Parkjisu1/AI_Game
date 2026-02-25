using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Per-scene DI container that inherits from the global ProjectContext.
    /// Destroyed when the scene unloads. Scene-specific managers register here.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Context
    /// Phase: 0
    /// </remarks>
    public class SceneContext : MonoBehaviour
    {
        #region Fields

        private DIContainer _container;

        #endregion

        #region Properties

        /// <summary>
        /// The scene-specific DI container. Falls back to ProjectContext for unresolved types.
        /// </summary>
        public DIContainer Container => _container;

        #endregion

        #region Unity Lifecycle

        private void Awake()
        {
            _container = new DIContainer();

            // Set parent to global container so unresolved types fall through
            if (ProjectContext.HasInstance)
            {
                _container.Parent = ProjectContext.Instance.Container;
            }
            else
            {
                Debug.LogWarning("[SceneContext] ProjectContext not found. Scene container has no parent.");
            }

            RegisterSceneBindings();

            Debug.Log($"[SceneContext] Initialized for scene: {gameObject.scene.name}");
        }

        private void OnDestroy()
        {
            _container?.Clear();
            _container = null;

            Debug.Log("[SceneContext] Destroyed and scene bindings cleared.");
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Registers an instance in the scene container.
        /// </summary>
        /// <typeparam name="T">The type to bind.</typeparam>
        /// <param name="instance">The instance to register.</param>
        public void Register<T>(T instance) where T : class
        {
            _container?.BindInstance(instance);
        }

        /// <summary>
        /// Resolves an instance from the scene container (or parent ProjectContext).
        /// </summary>
        /// <typeparam name="T">The type to resolve.</typeparam>
        /// <returns>The resolved instance.</returns>
        public T Resolve<T>() where T : class
        {
            return _container?.Resolve<T>();
        }

        /// <summary>
        /// Injects dependencies into the target object using the scene container.
        /// </summary>
        /// <param name="target">The object to inject into.</param>
        public void Inject(object target)
        {
            _container?.InjectInto(target);
        }

        #endregion

        #region Private Methods

        /// <summary>
        /// Override point for scene-specific bindings.
        /// Called during Awake after parent is set.
        /// </summary>
        protected virtual void RegisterSceneBindings()
        {
            // Subclasses or scene-specific setups can override this.
            // By default, the scene container binds itself so others can find it.
            _container.BindInstance(this);
        }

        #endregion
    }
}
