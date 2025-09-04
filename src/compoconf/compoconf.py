"""
CompoConf: A Compositional Configuration Library

This module provides a framework for managing configurations in a type-safe and composable way.
It allows for the definition of interfaces, their implementations, and corresponding configurations
using Python's dataclass system.

Key components:
- RegistrableConfigInterface: Base class for defining interfaces
- ConfigInterface: Base class for configuration dataclasses
- Registry: Singleton managing registration of interfaces and their implementations
- register/register_interface: Decorators for class registration

Example:
    @register_interface
    class ModelInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class MLPConfig(ConfigInterface):
        hidden_size: int = 128

    @register
    class MLPModel(ModelInterface):
        config_class = MLPConfig

        def __init__(self, config):
            self.config = config

    or better:

    @register
    class MLPModel(ModelInterface):
        config: MLPConfig

        def __init__(self, config: MLPConfig):
            self.config = config
"""

import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional, Type, TypeVar, get_type_hints

from compoconf.nonstrict_dataclass import asdict

LOGGER = logging.getLogger(__name__)


class classproperty(property):
    """
    Classproperty decorator to combine @property with @classmethod
    """

    def __get__(self, instance, owner):
        # Call the classmethod and return its value
        if hasattr(self.fget, "__call__"):
            return self.fget(owner)
        if hasattr(self.fget, "__wrapped__"):
            return self.fget.__wrapped__(owner)
        return None


def _get_config_class(cls: Type) -> Optional[Type]:
    """
    Get the config class of a class, returns None if it doesn't have one.
    """
    config_class = None
    if hasattr(cls, "config_class") and hasattr(cls.config_class, "class_name"):
        config_class = cls.config_class
    if config_class is None and hasattr(cls, "config"):
        type_hints = get_type_hints(cls)
        if "config" in type_hints and type_hints["config"] is not Any and type_hints["config"] is not type(None):
            config_class = type_hints["config"]
    return config_class


class RegistrableConfigInterface:
    """
    Base interface for classes that can be configured and instantiated via a configuration class.

    This class serves as a base for creating registrable interfaces in a type-safe configuration system.
    Classes inheriting from this interface must define a config_class attribute pointing to their
    corresponding configuration dataclass.

    Attributes:
        config_class: Class attribute defining the configuration dataclass for this interface
        config: Instance attribute storing the configuration object

    Example:
        @register_interface
        class ModelInterface(RegistrableConfigInterface):
            pass

        @register
        class ConcreteModel(ModelInterface):
            config_class = ModelConfig
    """

    __name__ = "RegistrableConfigInterface"  # overridden by child classes
    config_class: Any = None
    config: Any = None

    def __init__(self, *args, **kwargs):
        _ = args, kwargs

    @classproperty
    @classmethod
    def cfgtype(cls) -> Any:
        """
        Returns the config type of the registry interface class.
        If more than one class is registered, this results in a union type.

        Returns:
            Annotation type for config class
        """
        cfg_classes: List[type] = []

        if not Registry.has_registry(cls):
            return None
        for reg_cls in Registry.registered_classes(cls):
            cfg_cls = _get_config_class(reg_cls)
            if cfg_cls is not None:
                cfg_classes.append(cfg_cls)
        if len(cfg_classes) == 0:
            LOGGER.warning(f"No option for this type {cls} registry")
        T = cfg_classes[0] if len(cfg_classes) == 1 else TypeVar(cls.__name__ + "ConfigType", *cfg_classes)
        setattr(T, "registry_class", cls)
        setattr(T, "is_config_type", True)
        return T


class _RegistrySingleton:
    """
    Singleton class managing the registration of interfaces and their implementations.

    This class maintains a mapping of interface names to their registered implementations,
    allowing for runtime instantiation of classes based on their configuration.

    The registry is hierarchical, following the inheritance structure of registered interfaces.
    When a class is registered, it is added to all compatible interface registries based on
    its inheritance hierarchy.

    Attributes:
        _registries (dict): Maps interface names to their implementation registries
        _registry_classes (dict): Maps interface names to their interface classes

    Methods:
        add_registry(cls): Register a new interface class
        add_class_to_registry(cls): Register an implementation class
        registered_classes(registry_interface): Get all registered implementations for an interface
        get_class(registry_interface, name): Get a specific implementation class
    """

    def __init__(self):
        LOGGER.debug("Initializing new Registry instance")
        self._registries = {}
        self._registry_classes = {}

    @staticmethod
    def _unique_name(other_cls):
        return f"{other_cls.__module__}.{other_cls.__qualname__}"

    def add_registry(self, cls):
        """
        Add a new registry via a subclass of RegistrableConfigInterface
        """
        LOGGER.debug(f"Adding registry for class {self._unique_name(cls)}")
        if self._unique_name(cls) in self._registries:
            LOGGER.warning(f"Tried to re-register registry with interface name {self._unique_name(cls)}")
        if RegistrableConfigInterface not in cls.__mro__:
            raise RuntimeError(
                f"Tried to create registry for {self._unique_name(cls)} that doesn't inherit from "
                "RegistrableConfigInterface"
            )
        self._registries[self._unique_name(cls)] = {}
        self._registry_classes[self._unique_name(cls)] = cls

    def _reregistration_warnings(self, config_class, cls, cls_name, parent):
        if isinstance(config_class.class_name, str) and not config_class.class_name == "":
            if config_class.class_name != cls_name:
                LOGGER.info(
                    f"Re-Registering {cls_name} for dataclass {config_class} "
                    f"previous class_name {config_class.class_name} in {self._unique_name(parent)}."
                )
            elif config_class.class_name in self._registries[self._unique_name(parent)] and (
                self._registries[self._unique_name(parent)][cls_name] is not cls
            ):
                LOGGER.warning(
                    f"Re-Registering {cls_name} for dataclass {config_class} "
                    f"previous class_name {config_class.class_name} in {self._unique_name(parent)}."
                )

    def add_class_to_registry(self, cls):
        """
        Add a class to all registries via the inherance scheme and parents of type RegistrableConfigInterface.
        """
        cls_name = cls.__name__
        LOGGER.debug(f"Adding class {cls_name} to registry")
        for parent in cls.__mro__:
            # if RegistrableConfigInterface is not registered, it is not tracked
            if issubclass(parent, RegistrableConfigInterface):
                if self._unique_name(parent) in self._registries:
                    if cls_name in self._registries[self._unique_name(parent)]:
                        LOGGER.warning(
                            f"Tried to re-register class {cls_name} for interface {self._unique_name(parent)}"
                        )
                    else:
                        config_class = _get_config_class(cls)

                        if config_class is None:
                            raise RuntimeError(f"Class {cls} does not have a proper config class")
                        self._reregistration_warnings(config_class, cls, cls_name, parent)
                        self._registries[self._unique_name(parent)][cls_name] = cls
                        config_class.class_name = cls_name

    def has_registry(self, cls: Type) -> bool:
        """
        Check if an interface class is forming a (registered) registry.
        """
        return self._unique_name(cls) in self._registries

    def registered_classes(self, registry_interface: type[RegistrableConfigInterface]):
        """
        Get all classes for a registry interface

        Args:
            registry_interface: The registry interface of which to get all registered classes.
        """
        for cls in self._registries[self._unique_name(registry_interface)]:
            yield self._registries[self._unique_name(registry_interface)][cls]

    def get_class(self, registry_interface: RegistrableConfigInterface, name: str) -> type:
        """
        Get the class from a registry interface and the name (i.e. the class name).
        Note that this way (even though they should not) a name can exist
        multiple times in different registries for different classes.
        """
        if self._unique_name(registry_interface) in self._registries:
            if name in self._registries[self._unique_name(registry_interface)]:
                return self._registries[self._unique_name(registry_interface)][name]
            raise KeyError(f"{name} not found in registry {self._unique_name(registry_interface)}")
        raise KeyError(f"No such registry interface {self._unique_name(registry_interface)}")

    def __str__(self):
        st = (
            "{"
            + ("\n" if self._registries else "")
            + ",\n".join(
                '"'
                + reg
                + '"'
                + ": ["
                + ("\n\t" if reg_classes else "")
                + '",\n\t'.join('"' + str(reg_cls) + '"' for reg_cls in reg_classes)
                + ("\n\t]" if reg_classes else "]")
                for reg, reg_classes in self._registries.items()
            )
            + ("\n}" if self._registries else "}")
        )
        return st


Registry = _RegistrySingleton()


def register(cls):
    """
    Decorator to register an implementation class with its interfaces.

    This decorator registers a class with all its parent interfaces that inherit from
    RegistrableConfigInterface. The class must define a config_class attribute.

    Args:
        cls: The class to register

    Returns:
        The registered class

    Example:
        @register
        class MyModel(ModelInterface):
            config_class = MyModelConfig
    """
    Registry.add_class_to_registry(cls)
    return cls


def register_interface(cls):
    """
    Decorator to register a new interface in the registry system.

    This decorator marks a class as a registrable interface, allowing implementation
    classes to be registered with it.

    Args:
        cls: The interface class to register

    Returns:
        The registered interface class

    Example:
        @register_interface
        class ModelInterface(RegistrableConfigInterface):
            pass
    """
    Registry.add_registry(cls)
    return cls


@dataclass
class ConfigInterface:
    """
    Base class for configuration dataclasses in the CompoConf system.

    This class provides the foundation for creating type-safe configurations that can
    instantiate their corresponding implementation classes. It automatically handles
    the registration of class names and provides instantiation capabilities.

    Attributes:
        class_name (str): Name of the implementation class (auto-populated during registration)

    Methods:
        instantiate(interface_class, *args, **kwargs): Create an instance of the implementation class
        __reduce__(): Support for pickling

    Example:
        @dataclass
        class ModelConfig(ConfigInterface):
            hidden_size: int = 128
            activation: str = "relu"

        config = ModelConfig(hidden_size=256)
        model = config.instantiate(ModelInterface)
    """

    class_name: str = field(init=False, default="")

    def __reduce__(self):
        """Support for pickling by storing all state."""
        state = asdict(self)
        return (self.__class__, (), state)

    def __setstate__(self, state):
        """Support for unpickling by restoring state."""
        for key, value in state.items():
            setattr(self, key, value)

    def instantiate(self, interface_class, *args, **kwargs):
        """
        Instantiates the corresponding class from this config (with potential additional arguments)

        Args:
            interface_class: Interface class to retrieve the object class from corresponding to this config class.
            args: Additional positional arguments.
            kwargs: Additional keyword arguments.
        """
        if self.class_name == "":
            raise ValueError(f"Configuration class {self.__class__} has no instantiation class.")
        return Registry.get_class(interface_class, self.class_name)(self, *args, **kwargs)

    def _to_dict(self):
        """
        Returns a PyTree / dictionary of the config via dataclasses.asdict.

        Returns:
            Dictionary containing the dataclass object attributes.
        """
        return asdict(self, use_to_dict=False)
