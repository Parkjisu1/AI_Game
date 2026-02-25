using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace MagicSort.Core
{
    /// <summary>
    /// Attribute to mark fields or properties for automatic dependency injection.
    /// </summary>
    [AttributeUsage(AttributeTargets.Field | AttributeTargets.Property, AllowMultiple = false)]
    public class InjectAttribute : Attribute { }

    /// <summary>
    /// Lightweight Dependency Injection container.
    /// Supports Bind/Resolve pattern with optional [Inject] attribute for field injection.
    /// </summary>
    /// <remarks>
    /// Layer: Core
    /// Genre: Generic
    /// Role: Service
    /// Phase: 0
    /// </remarks>
    public class DIContainer
    {
        #region Fields

        private readonly Dictionary<Type, object> _bindings = new Dictionary<Type, object>();
        private readonly Dictionary<Type, Func<object>> _factories = new Dictionary<Type, Func<object>>();
        private DIContainer _parent;

        #endregion

        #region Properties

        /// <summary>
        /// The parent container for hierarchical resolution (e.g., ProjectContext -> SceneContext).
        /// </summary>
        public DIContainer Parent
        {
            get => _parent;
            set => _parent = value;
        }

        #endregion

        #region Public Methods

        /// <summary>
        /// Binds a specific instance to a type.
        /// </summary>
        /// <typeparam name="T">The type to bind.</typeparam>
        /// <param name="instance">The instance to register.</param>
        public void BindInstance<T>(T instance) where T : class
        {
            if (instance == null)
            {
                Debug.LogError($"[DIContainer] Cannot bind null instance for type {typeof(T).Name}.");
                return;
            }

            Type type = typeof(T);
            if (_bindings.ContainsKey(type))
            {
                Debug.LogWarning($"[DIContainer] Overwriting existing binding for {type.Name}.");
            }

            _bindings[type] = instance;
        }

        /// <summary>
        /// Binds a factory function for lazy/transient resolution.
        /// </summary>
        /// <typeparam name="T">The type to bind.</typeparam>
        /// <param name="factory">Factory function that creates the instance.</param>
        public void BindFactory<T>(Func<T> factory) where T : class
        {
            if (factory == null)
            {
                Debug.LogError($"[DIContainer] Cannot bind null factory for type {typeof(T).Name}.");
                return;
            }

            _factories[typeof(T)] = () => factory();
        }

        /// <summary>
        /// Resolves an instance of the given type.
        /// Checks local bindings first, then factories, then parent container.
        /// </summary>
        /// <typeparam name="T">The type to resolve.</typeparam>
        /// <returns>The resolved instance, or null if not found.</returns>
        public T Resolve<T>() where T : class
        {
            Type type = typeof(T);

            // Check local instance bindings
            if (_bindings.TryGetValue(type, out object instance))
            {
                return instance as T;
            }

            // Check local factory bindings
            if (_factories.TryGetValue(type, out Func<object> factory))
            {
                T created = factory() as T;
                // Cache the result for singleton-like behavior
                _bindings[type] = created;
                return created;
            }

            // Check parent container
            if (_parent != null)
            {
                return _parent.Resolve<T>();
            }

            Debug.LogWarning($"[DIContainer] No binding found for type {type.Name}.");
            return null;
        }

        /// <summary>
        /// Checks if a binding exists for the given type (including parent).
        /// </summary>
        /// <typeparam name="T">The type to check.</typeparam>
        /// <returns>True if a binding or factory exists.</returns>
        public bool HasBinding<T>() where T : class
        {
            Type type = typeof(T);

            if (_bindings.ContainsKey(type) || _factories.ContainsKey(type))
            {
                return true;
            }

            if (_parent != null)
            {
                return _parent.HasBinding<T>();
            }

            return false;
        }

        /// <summary>
        /// Injects dependencies into all fields and properties marked with [Inject].
        /// </summary>
        /// <param name="target">The object to inject into.</param>
        public void InjectInto(object target)
        {
            if (target == null)
            {
                Debug.LogError("[DIContainer] Cannot inject into null target.");
                return;
            }

            Type targetType = target.GetType();
            BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

            // Inject fields
            FieldInfo[] fields = targetType.GetFields(flags);
            for (int i = 0; i < fields.Length; i++)
            {
                FieldInfo field = fields[i];
                if (field.GetCustomAttribute<InjectAttribute>() == null) continue;

                object resolved = ResolveByType(field.FieldType);
                if (resolved != null)
                {
                    field.SetValue(target, resolved);
                }
                else
                {
                    Debug.LogWarning($"[DIContainer] Could not resolve {field.FieldType.Name} for field '{field.Name}' in {targetType.Name}.");
                }
            }

            // Inject properties
            PropertyInfo[] properties = targetType.GetProperties(flags);
            for (int i = 0; i < properties.Length; i++)
            {
                PropertyInfo prop = properties[i];
                if (prop.GetCustomAttribute<InjectAttribute>() == null) continue;
                if (!prop.CanWrite) continue;

                object resolved = ResolveByType(prop.PropertyType);
                if (resolved != null)
                {
                    prop.SetValue(target, resolved);
                }
                else
                {
                    Debug.LogWarning($"[DIContainer] Could not resolve {prop.PropertyType.Name} for property '{prop.Name}' in {targetType.Name}.");
                }
            }
        }

        /// <summary>
        /// Removes a specific binding.
        /// </summary>
        /// <typeparam name="T">The type to unbind.</typeparam>
        public void Unbind<T>() where T : class
        {
            Type type = typeof(T);
            _bindings.Remove(type);
            _factories.Remove(type);
        }

        /// <summary>
        /// Clears all bindings and factories.
        /// </summary>
        public void Clear()
        {
            _bindings.Clear();
            _factories.Clear();
        }

        #endregion

        #region Private Methods

        private object ResolveByType(Type type)
        {
            if (_bindings.TryGetValue(type, out object instance))
            {
                return instance;
            }

            if (_factories.TryGetValue(type, out Func<object> factory))
            {
                object created = factory();
                _bindings[type] = created;
                return created;
            }

            if (_parent != null)
            {
                return _parent.ResolveByType(type);
            }

            return null;
        }

        #endregion
    }
}
