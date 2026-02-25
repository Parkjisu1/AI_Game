using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Application-wide DI container that persists across scene transitions.
    /// Initializes core bindings (SignalBus, etc.) on Awake.
    /// All global managers should register themselves here.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Context
    /// Phase: 0
    /// </remarks>
    public class ProjectContext : Singleton<ProjectContext>
    {
        #region Fields

        private DIContainer _container;

        #endregion

        #region Properties

        /// <summary>
        /// The global DI container accessible throughout the application lifetime.
        /// </summary>
        public DIContainer Container => _container;

        #endregion

        #region Singleton Lifecycle

        protected override void OnSingletonAwake()
        {
            _container = new DIContainer();
            RegisterCoreBindings();

            Debug.Log("[ProjectContext] Initialized with core bindings.");
        }

        protected override void OnSingletonDestroy()
        {
            _container?.Clear();
            _container = null;

            Debug.Log("[ProjectContext] Destroyed and bindings cleared.");
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Registers an instance in the global container.
        /// Convenience wrapper for Container.BindInstance.
        /// </summary>
        /// <typeparam name="T">The type to bind.</typeparam>
        /// <param name="instance">The instance to register.</param>
        public void Register<T>(T instance) where T : class
        {
            _container?.BindInstance(instance);
        }

        /// <summary>
        /// Resolves an instance from the global container.
        /// Convenience wrapper for Container.Resolve.
        /// </summary>
        /// <typeparam name="T">The type to resolve.</typeparam>
        /// <returns>The resolved instance.</returns>
        public T Resolve<T>() where T : class
        {
            return _container?.Resolve<T>();
        }

        /// <summary>
        /// Injects dependencies into the target object using the global container.
        /// </summary>
        /// <param name="target">The object to inject into.</param>
        public void Inject(object target)
        {
            _container?.InjectInto(target);
        }

        #endregion

        #region Private Methods

        private void RegisterCoreBindings()
        {
            // SignalBus is a core service available to all systems
            SignalBus signalBus = new SignalBus();
            _container.BindInstance(signalBus);
        }

        #endregion
    }
}
