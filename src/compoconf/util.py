"""
Utilities for compoconf to provide dynamic configuration capabilities with proper type support.
"""

import inspect
import sys
from collections.abc import Callable
from dataclasses import asdict, field, fields, is_dataclass, make_dataclass
from typing import Any, Generic, Literal, Optional, Protocol, TypeVar, Union, cast, get_type_hints, runtime_checkable

from .compoconf import RegistrableConfigInterface, Registry

T_co = TypeVar("T_co", covariant=True)
ConfigT = TypeVar("ConfigT", bound="DynamicConfig")


class MissingValue:
    """
    A singular type that represents a MissingValue that can be replaced in the
    __post_init__ of a dataclass (unlike dataclasses.MISSING), but should
    ultimately raise ConfigError if not set.
    """


class LiteralError(ValueError):
    """
    A ValueError representing a bad value of a Literal type.
    """


class ConfigError(ValueError):
    """
    A ValueError representing a bad configuration recognized in the __post_init__
    of a dataclass.
    """


@runtime_checkable
class DynamicConfig(Protocol):
    """Protocol for dynamic config objects that support attribute access."""

    class_name: str

    def __getattr__(self, name: str) -> Any: ...  # pragma: no cover - protocol definition

    def __setattr__(self, name: str, value: Any) -> None: ...  # pragma: no cover - protocol definition


@runtime_checkable
class ConfigurableCallable(Protocol[T_co]):
    """Protocol for callable objects with dynamic configuration."""

    config: DynamicConfig

    def __call__(self, *args: Any, **kwargs: Any) -> T_co: ...  # pragma: no cover - protocol definition


# Template classes defined at module level
class _PartialCallTemplate(RegistrableConfigInterface, Generic[T_co]):
    """Template class for partial_call wrapper with generic type support."""

    _fun: Callable
    _pass_args: Optional[list[int]] = None
    _pass_kwargs: Optional[list[str]] = None
    _cfg_args: Optional[list[int]] = None
    _cfg_kwargs: Optional[list[str]] = None
    _default_as_pass_args: bool
    _param_names: list[str]
    _param_indices: dict
    _pass_param_names: set
    _cfg_param_names: set
    config_class = None

    def __init__(self, config: DynamicConfig, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: DynamicConfig = config
        self.args: tuple = args
        self.kwargs: dict = kwargs

    def __reduce__(self):
        """Support for pickling."""
        return (self.__class__, (self.config,) + self.args, self.kwargs)

    def __call__(self, *args, **kwargs):
        # Prepare arguments for the function call
        call_args = []
        call_kwargs = {}

        # Get config values
        config_dict = asdict(self.config)
        if "class_name" in config_dict:
            del config_dict["class_name"]

        args_idx = 0

        # Process all parameters
        for name in self._param_names:
            idx = self._param_indices[name]
            if name in self._pass_param_names:
                # Parameter should come from function call
                if name in kwargs:
                    call_kwargs[name] = kwargs[name]
                elif args_idx < len(args):
                    call_args.append(args[args_idx])
                    args_idx += 1
            elif name in self._cfg_param_names:
                # Parameter should come from config
                if name in config_dict:
                    # Use as positional arg only if pass_args is used positional
                    if idx == len(call_args) and idx < len(self._param_names):
                        call_args.append(config_dict[name])
                    else:  # Use as keyword arg
                        call_kwargs[name] = config_dict[name]

        # Call the function with prepared arguments
        return self._fun(*call_args, **call_kwargs)

    @classmethod
    def __class_getitem__(cls, item: Any) -> type["_PartialCallTemplate[T_co]"]:
        """Support for generic type parameters."""
        return type(f"_PartialCallTemplate[{item}]", (cls,), {"__orig_class__": cls})


class _AnnotatedTemplate(RegistrableConfigInterface, Generic[T_co]):
    """Template class for from_annotations wrapper with generic type support."""

    _wrapped_cls: Callable
    _pass_args: Optional[Union[list[int], set[int]]] = None
    _pass_kwargs: Optional[Union[list[int], set[int]]] = None
    _cfg_args: Optional[Union[list[int], set[int]]] = None
    _cfg_kwargs: Optional[Union[list[int], set[int]]] = None
    _default_as_pass_args: bool = False
    _params_to_add: Union[list[str], set[str]] = set()
    config_class: Any = None

    def __init__(self, config: DynamicConfig, *args: Any, **kwargs: Any) -> None:
        super().__init__(config, *args, **kwargs)
        self.config: DynamicConfig = config
        self.args: tuple = args
        self.kwargs: dict = kwargs

        # Prepare arguments for cls constructor
        init_kwargs = {**kwargs}
        config_dict = asdict(cast(Any, config))

        # Remove class_name from config dict
        if "class_name" in config_dict:
            del config_dict["class_name"]

        # Map config values to constructor parameters
        for name in self._params_to_add:
            if name in config_dict:
                init_kwargs[name] = config_dict[name]

        # Create instance of original class
        self._instance = self.__class__._wrapped_cls(*args, **init_kwargs)

    def __reduce__(self):
        """Support for pickling."""
        return (self.__class__, (self.config,) + self.args, self.kwargs)

    def __getattr__(self, name: str):
        return getattr(self._instance, name)

    def __call__(self, *args, **kwargs):
        return self._instance(*args, **kwargs)

    def __str__(self):
        return str(self._instance)

    def __repr__(self):
        return repr(self._instance)

    def __len__(self):
        return len(self._instance)

    def __iter__(self):
        return iter(self._instance)

    def __getitem__(self, key):
        return self._instance[key]

    def __setitem__(self, key, value):
        self._instance[key] = value

    @classmethod
    def __class_getitem__(cls, item: Any) -> type["_AnnotatedTemplate[T_co]"]:
        """Support for generic type parameters."""
        return type(f"_AnnotatedTemplate[{item}]", (cls,), {"__orig_class__": cls})


def make_dataclass_picklable(
    name: str,
    fields_list: list[tuple[str, type, Any]],
    bases: tuple[type, ...],
    namespace: dict[str, Any],
    module_name: str,
) -> type[DynamicConfig]:
    """Create a picklable dataclass by properly setting its module and qualname."""
    cls = make_dataclass(name, fields_list, bases=bases, namespace=namespace)
    # Make the class picklable by setting proper module and qualname
    cls.__module__ = module_name
    # Add the class to the module's namespace so pickle can find it
    module = sys.modules[module_name]
    setattr(module, name, cls)
    return cls


def partial_call(  # pylint: disable=R0913
    fun: Callable[..., T_co],
    class_name: str,
    reg: type[RegistrableConfigInterface],
    *,
    pass_args: Optional[list[int]] = None,
    pass_kwargs: Optional[list[str]] = None,
    cfg_args: Optional[list[int]] = None,
    cfg_kwargs: Optional[list[str]] = None,
    default_as_pass_args: bool = True,
) -> Callable[[type[ConfigT]], type[ConfigT]]:
    """
    This  takes a function fun and a RegistrableConfigInterface reg, with the function matching the __call__
    function of the registered interface, except for configuration args / keyword args.
    It creates a new class inheriting from reg, configured by a config class and executes the partial
    fun, configured by the config class.

    Example:
        @register_interface
        class NumpyArrayFunc(RegistrableConfigInterface):
            def forward(x: torch.Tensor) -> torch.Tensor:
                raise NotImplementedError

        def multiply(x: torch.Tensor, multiplier: float):
            return x * multiplier

        @partial_call(multiply, "Multiply", NumpyArrayFunc)
        @dataclass
        class MultiplyConfig(ConfigInterface):
            multiplier: float = 1.0

        np.testing.assert_allclose(MultiplyConfig(2.0).instantiate(NumpyArrayFunc)(np.array([1.0])), np.array([2.0]))

        @partial_call(multiply, "Multiply2", NumpyArrayFunc, pass_args=[0])
        @dataclass
        class MultiplyConfig2(ConfigInterface):
            pass

        np.testing.assert_allclose(MultiplyConfig2(2.0).instantiate(NumpyArrayFunc)(np.array([1.0])), np.array([2.0]))


        @partial_call(multiply, "Multiply3", NumpyArrayFunc, pass_kwargs=["x"])
        @dataclass
        class MultiplyConfig3(ConfigInterface):
            pass

        np.testing.assert_allclose(MultiplyConfig3(2.0).instantiate(NumpyArrayFunc)(np.array([1.0])), np.array([2.0]))


        @partial_call(multiply, "Multiply4", NumpyArrayFunc, cfg_args=[1])
        @dataclass
        class MultiplyConfig4(ConfigInterface):
            pass

        np.testing.assert_allclose(MultiplyConfig4(2.0).instantiate(NumpyArrayFunc)(np.array([1.0])), np.array([2.0]))

    """

    def _get_cfg_pass_param_names(param_names, existing_param_names):
        cfg_param_names = set()
        pass_param_names = set()

        if cfg_args or cfg_kwargs:
            if cfg_args:
                cfg_param_names.update(param_names[i] for i in cfg_args if i < len(param_names))
            if cfg_kwargs:
                cfg_param_names.update(name for name in cfg_kwargs if name in param_names)
            # Infer pass parameters as everything else
            if default_as_pass_args:
                pass_param_names = set(param_names) - cfg_param_names
            else:
                cfg_param_names.update(existing_param_names)
        # If pass_args/pass_kwargs are specified, use them to determine pass parameters
        if pass_args or pass_kwargs:
            if not default_as_pass_args:
                pass_param_names = set()
            if pass_args:
                pass_param_names.update(param_names[i] for i in pass_args if i < len(param_names))
            if pass_kwargs:
                pass_param_names.update(name for name in pass_kwargs if name in param_names)
            # Infer config parameters as everything else
            cfg_param_names = set(param_names) - pass_param_names

        # If nothing is specified, use existing config attributes as cfg_kwargs
        elif not (cfg_args or cfg_kwargs):
            if default_as_pass_args:
                cfg_param_names = existing_param_names
                pass_param_names = set(param_names) - cfg_param_names
            else:
                cfg_param_names = set(param_names)
        return cfg_param_names, pass_param_names

    def decorator(cls):
        # Get function signature and type hints
        sig = inspect.signature(fun)
        type_hints = get_type_hints(fun)

        # Get all function parameters
        param_names = list(sig.parameters.keys())
        param_indices = {name: idx for idx, name in enumerate(param_names)}

        # Initialize sets for tracking parameters
        existing_param_names = set((f.name for f in fields(cls) if f.name != "class_name"))

        # If cfg_args/cfg_kwargs are specified, use them to determine config parameters
        cfg_param_names, pass_param_names = _get_cfg_pass_param_names(param_names, existing_param_names)

        # If config_class is a dataclass, create a new one with additional fields
        if is_dataclass(cls):
            # Prepare fields for make_dataclass
            dc_fields = []

            for name in cfg_param_names:
                param = sig.parameters[name]
                param_type = type_hints.get(name, Any)
                default = (
                    getattr(cls, name)
                    if hasattr(cls, name)
                    else (param.default if param.default != inspect.Parameter.empty else None)
                )

                dc_fields.append((name, param_type, field(default=default)))  # pylint: disable=E3701
            dc_fields.append(("class_name", str, field(default=class_name)))  # pylint: disable=E3701

            # Create new picklable dataclass inheriting from original
            cls = make_dataclass_picklable(
                cls.__name__,
                dc_fields,
                bases=(cls,),
                namespace={
                    "__module__": cls.__module__,
                    "__reduce__": lambda self: (self.__class__, (), asdict(self)),
                    "__setstate__": lambda self, state: [setattr(self, k, v) for k, v in state.items()],
                },
                module_name=cls.__module__,
            )

        # Create a new class by inheriting from the template
        attrs = {
            "_fun": staticmethod(fun),
            "_pass_args": pass_args,
            "_pass_kwargs": pass_kwargs,
            "_cfg_args": cfg_args,
            "_cfg_kwargs": cfg_kwargs,
            "_default_as_pass_args": default_as_pass_args,
            "_param_names": param_names,
            "_param_indices": param_indices,
            "_pass_param_names": pass_param_names,
            "_cfg_param_names": cfg_param_names,
            "config_class": cls,
            "__module__": cls.__module__,
            "__name__": class_name,
        }

        # Create the class in the module's namespace
        PartialCallClass = type(class_name, (_PartialCallTemplate, reg), attrs)
        setattr(sys.modules[cls.__module__], class_name, PartialCallClass)

        # Register the class
        Registry.add_class_to_registry(PartialCallClass)

        return cls

    return decorator


def from_annotations(  # pylint: disable=R0913
    cls: type[T_co],
    class_name: str,
    reg: type[RegistrableConfigInterface],
    *,
    pass_args: Optional[list[int]] = None,
    pass_kwargs: Optional[list[str]] = None,
    cfg_args: Optional[list[int]] = None,
    cfg_kwargs: Optional[list[str]] = None,
    default_as_pass_args: bool = False,
    use_init: bool = True,
) -> Callable[[type[ConfigT]], type[ConfigT]]:
    """
    This function takes a class cls and uses the (keyword) arguments and their
    annotations of its constructor for adapting a config.
    The newly created and registered class is configured by the config class.
    Besides the constructor, it acts like the original cls.

    The cls should already satisfy the requirements of the registered interface
    reg, but does not need to inherit from the interface.

    Example:
        @register_interface
        class NumpyArrayFunc(RegistrableConfigInterface):
            def forward(x: torch.Tensor) -> torch.Tensor:
                return x

        class ExternalClass:
            def __init__(self, multiplier: float = 2.0)
                self.multiplier = multiplier

            def forward(x: torch.Tensor) -> torch.Tensor:
                return self.multiplier * x

        @from_annotations(ExternalClass, "Multiply", NumpyArrayFunc)
        @dataclass
        class MultiplyConfig(ConfigInterface):
            pass

        np.testing.assert_allclose(MultiplyConfig(3.0).instantiate(NumpyArrayFunc)(np.array([1.0])), np.array([3.0]))
    """

    def decorator(config_class):
        # Get constructor signature and type hints
        if use_init:
            sig = inspect.signature(cls.__init__)
            type_hints = get_type_hints(cls.__init__)
        else:
            sig = inspect.signature(cls)
            type_hints = get_type_hints(cls)

        # Track which parameters should be added to config
        params_to_add = set()

        existing_param_names = set((f.name for f in fields(config_class) if f.name != "class_name"))

        # Process all parameters except 'self' and *args, **kwargs
        for idx, (name, param) in enumerate(sig.parameters.items()):
            if name == "self" or param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            if default_as_pass_args and name not in existing_param_names:
                continue

            # Skip parameters that should be passed directly
            if (pass_args and idx - 1 in pass_args) or (pass_kwargs and name in pass_kwargs):
                continue

            params_to_add.add(name)

        # If config_class is a dataclass, create a new one with additional fields
        if is_dataclass(config_class):
            # Prepare fields for make_dataclass
            cfg_fields = []
            cfg_defaults = inspect.signature(config_class)
            for name in params_to_add:
                param = sig.parameters[name]
                param_type = type_hints.get(name, Any)
                default = (
                    getattr(cls, name)
                    if hasattr(cls, name)
                    else (param.default if param.default != inspect.Parameter.empty else None)
                )
                if (
                    name in cfg_defaults.parameters
                    and cfg_defaults.parameters[name].default is not inspect.Parameter.empty
                ):
                    default = cfg_defaults.parameters[name].default
                cfg_fields.append((name, param_type, field(default=default)))  # pylint: disable=E3701

            cfg_fields.append(("class_name", str, field(default=class_name)))  # pylint: disable=E3701
            # Create new picklable dataclass inheriting from original
            config_class = make_dataclass_picklable(
                config_class.__name__,
                cfg_fields,
                bases=(config_class,),
                namespace={
                    "__module__": config_class.__module__,
                    "__reduce__": lambda self: (self.__class__, (), asdict(self)),
                    "__setstate__": lambda self, state: [setattr(self, k, v) for k, v in state.items()],
                },
                module_name=config_class.__module__,
            )

        _cfg_class = config_class
        # Create a new class by inheriting from the template
        attrs = {
            "_wrapped_cls": cls,
            "_pass_args": pass_args,
            "_pass_kwargs": pass_kwargs,
            "_cfg_args": cfg_args,
            "_cfg_kwargs": cfg_kwargs,
            "_default_as_pass_args": default_as_pass_args,
            "_params_to_add": params_to_add,
            "config_class": _cfg_class,
            "__module__": config_class.__module__,
            "__name__": class_name,
        }

        # Create the class in the module's namespace
        AnnotatedClass = type(
            class_name,
            (
                _AnnotatedTemplate,
                reg,
            ),
            attrs,
        )
        setattr(sys.modules[config_class.__module__], class_name, AnnotatedClass)

        # Register the class
        Registry.add_class_to_registry(AnnotatedClass)

        return config_class

    return decorator


def validate_literal_field(obj, field_name):
    """Validates if the value of a specified field in a dataclass object is
    within the allowed Literal options defined in its type annotations.

    Args:
        obj: The dataclass object to validate.
        field_name: The name of the field to check.

    Returns:
        bool: True if the field value is valid, False otherwise.

    Raises:
        ValueError: If the field is not defined or not annotated with Literal.
        TypeError: If the object is not a dataclass instance.
    """
    if not is_dataclass(obj):
        raise TypeError(f"The provided object {obj} is not a dataclass instance.")

    type_hints = get_type_hints(type(obj))

    if field_name not in type_hints:
        raise ValueError(f"Field '{field_name}' is not defined in the dataclass.")

    field_type = type_hints[field_name]

    # Check if the type is a Literal
    if not hasattr(field_type, "__origin__") or field_type.__origin__ is not Literal:
        raise ValueError(f"Field '{field_name}' is not annotated with a Literal.")

    # Extract the allowed values from the Literal
    allowed_values = field_type.__args__

    # Check if the current value is in the allowed values
    current_value = getattr(obj, field_name)
    return current_value in allowed_values


def assert_check_literals(obj):
    """
    Validates if the value of all Literal field in a dataclass object are
    within the allowed Literal options defined in their type annotations.

    Args:
        obj: The dataclass object to validate.

    Raises:
        compoconf.LiteralError: If the field is not defined or not annotated with Literal.
        TypeError: If the object is not a dataclass instance.
    """
    if not is_dataclass(obj):
        raise TypeError(f"The provided object {obj} is not a dataclass instance.")

    type_hints = get_type_hints(type(obj))

    errors = []
    for field_name in type_hints:
        field_type = type_hints[field_name]
        # Check if the type is a Literal
        if hasattr(field_type, "__origin__") and field_type.__origin__ is Literal:
            allowed_values = field_type.__args__
            current_value = getattr(obj, field_name)
            if current_value not in allowed_values:
                errors.append((field_name, current_value, allowed_values))
    if errors:
        field_names, values, allowed_values = zip(*errors)
        raise LiteralError(
            f"In dataclass {type(obj)}: The field {field_names} has a value {values} "
            f"not in {allowed_values} defined by Literal annotation."
        )


def assert_check_nonmissing(obj):
    """
    Validates if the value of all Literal field in a dataclass object are
    within the allowed Literal options defined in their type annotations.

    Args:
        obj: The dataclass object to validate.

    Raises:
        compoconf.ConfigError: If the field is not defined or not annotated with Literal.
        TypeError: If the object is not a dataclass instance.
    """
    if not is_dataclass(obj):
        raise TypeError(f"The provided object {obj} is not a dataclass instance.")

    type_hints = get_type_hints(type(obj))

    errors = []
    for field_name in type_hints:
        # Check if the value is still MissingValue
        if getattr(obj, field_name) is MissingValue:
            errors.append(field_name)
    if errors:
        raise ConfigError(f"In dataclass {type(obj)}: The fields {errors} have MissingValue as value.")
