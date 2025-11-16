"""
This submodule provides parsing / dumping capabilities for compoconf. So you can take your json/yaml string and a type
and parse it to a compoconf config structure, or vice versa.
"""

import logging
import sys
from collections.abc import Sequence
from dataclasses import is_dataclass
from typing import Any, Dict, FrozenSet, List, Literal
from typing import Sequence as tSequence
from typing import Set, Tuple, TypeVar, get_args, get_origin, get_type_hints

from compoconf.nonstrict_dataclass import NonStrictDataclass, asdict

if sys.version_info >= (3, 10):
    from types import UnionType
    from typing import Union
else:  # pragma: no cover - keep compatibility for older Python versions
    from typing import Union  # ignore: W0404
    from typing import Union as UnionType

try:
    from omegaconf import ListConfig
except ImportError:
    ListConfig = list


LOGGER = logging.getLogger(__name__)


def _extend_key_history(key_history: str, key: Any) -> str:
    """Build a dotted key path without leading separators.

    Args:
        key_history: The current dotted path.
        key: The next key or index being traversed.

    Returns:
        Updated key path including ``key``.
    """
    key_str = str(key)
    if not key_str:
        return key_history
    if not key_history:
        return key_str
    return f"{key_history}.{key_str}"


def _get_all_annotations(datacls: Any):
    """Return all resolved type hints for a dataclass.

    Args:
        datacls: Dataclass type whose annotations should be inspected.

    Returns:
        Mapping from field name to resolved type annotation.
    """

    return get_type_hints(datacls)
    # annotations = {}
    # for parent in reversed(datacls.__mro__):
    #     if is_dataclass(parent):
    #         annotations.update(parent.__annotations__)
    # return annotations


def _is_literal_instance(obj, clsann) -> bool:
    """Check whether a value matches a ``typing.Literal`` annotation.

    Args:
        obj: Value to validate.
        clsann: Annotation that may be a literal or regular type.

    Returns:
        ``True`` when the value matches the literal or type, otherwise ``False``.
    """

    try:
        if hasattr(clsann, "__origin__") and clsann.__origin__ is Literal:
            # Extract arguments of the Literal type
            return any(
                _is_literal_instance(obj, arg) if isinstance(arg, type) else obj == arg for arg in get_args(clsann)
            )
        return isinstance(obj, clsann)
    except TypeError:
        return False


def _handle_list(data, args, key_history: str = "") -> list:
    """Parse a list-like structure according to its element type.

    Args:
        data: The incoming raw list/tuple/config object.
        args: Type arguments for the list annotation.
        key_history: Dotted key path used for error reporting.

    Returns:
        Parsed list with elements converted via :func:`parse_config`.
    """

    if not isinstance(data, (tuple, list, ListConfig)):
        raise ValueError(f"Expected list, got {type(data)} at key {key_history}")
    if not args or len(args) != 1:
        # Don't allow untyped list
        # args = (Any,)
        raise ValueError(f"List type must have exactly 1 type argument at key {key_history}")
    return [
        parse_config(args[0], item, key_history=_extend_key_history(key_history, idx)) for idx, item in enumerate(data)
    ]


def _handle_set(data, args, origin, key_history: str = "") -> Set | FrozenSet:
    """Parse a set-like structure according to its element type.

    Args:
        data: The incoming raw iterable of values.
        args: Type arguments describing the element type.
        origin: Original ``typing`` container type (``set`` or ``frozenset``).
        key_history: Dotted key path build-up for errors.

    Returns:
        A ``set`` or ``frozenset`` with elements converted via :func:`parse_config`.
    """

    if not isinstance(data, (set, frozenset, list, tuple, ListConfig)):
        raise ValueError(f"Expected set, got {type(data)} at key {key_history}")
    if not args or len(args) != 1:
        # args = (Any,)
        # Don't allow untyped set
        raise ValueError(f"Set type must have exactly 1 type argument at key {key_history}")
    parsed_items = [
        parse_config(args[0], item, key_history=_extend_key_history(key_history, idx)) for idx, item in enumerate(data)
    ]
    return frozenset(parsed_items) if origin in (frozenset, FrozenSet) else set(parsed_items)


def _handle_tuple(data, args, key_history: str = "") -> tuple:
    """Parse a tuple according to its element arity and types.

    Args:
        data: The incoming raw tuple/list/config object.
        args: Type arguments for the tuple annotation.
        key_history: Dotted key path used for error reporting.

    Returns:
        Tuple of parsed values matching the declared type annotation.
    """

    if not isinstance(data, (tuple, list, ListConfig)):
        raise ValueError(f"Expected tuple or list, got {type(data)} ({data}) at key {key_history}")
    if not args:
        # args = (Any, ...)
        # don't allow tuples with Any as type
        raise ValueError("Tuple type must have type arguments")
    if len(args) == 2 and args[1] == Ellipsis:
        args = [args[0] for _ in data]
    if len(args) != len(data):
        raise ValueError(f"Expected {len(args)} items, got {len(data)} at key {key_history}")
    return tuple(
        parse_config(arg_type, item, key_history=_extend_key_history(key_history, idx))
        for idx, (arg_type, item) in enumerate(zip(args, data))
    )


def _handle_dict(data, args, key_history: str = "") -> dict[str, Any]:
    """Parse a mapping by converting both keys and values.

    Args:
        data: The incoming dictionary-like object.
        args: Two type arguments describing key and value types.
        key_history: Dotted key path for error reporting.

    Returns:
        Dictionary with keys/values converted via :func:`parse_config`.
    """

    if not args or len(args) != 2:
        # args = (str, Any)
        # Don't allow untyped dicts with str as key type
        raise ValueError(f"Dict type must have exactly 2 type arguments at key {key_history}")
    result = {}
    key_type, value_type = args
    if not hasattr(data, "items") or not callable(data.items):
        raise ValueError(f"Expected dict, got {type(data)} at key {key_history}")
    for key, value in data.items():
        child_key_history = _extend_key_history(key_history, key)
        parsed_key = parse_config(key_type, key, key_history=child_key_history)
        parsed_value = parse_config(value_type, value, key_history=child_key_history)
        result[parsed_key] = parsed_value
    # if not isinstance(data, (dict, DictConfig)):
    #     raise ValueError(f"Expected dict, got {type(data)}")
    return result


def _parse_compositional_types(origin, args, data, key_history: str = "") -> Any:
    """
    Parse data to a compositional generic origin type with args.
    E.g. _parse_compositional_types(dict, (str, str), {"abc": "abc"})

    Args:
        origin: Generic type.
        args: Generic type args.
        data: Data to be parsed into object.

    Returns:
        Object of origin[args] type from parsed data.
    """
    # Handle dict types (both typing.Dict and dict)
    if origin in (dict, Dict):
        return _handle_dict(data, args, key_history=key_history)

    # Handle list types (both typing.List and list)
    if origin in (list, List, Sequence, tSequence):
        return _handle_list(data, args, key_history=key_history)

    # Handle set types (typing.Set, set, typing.FrozenSet, frozenset)
    if origin in (set, Set, frozenset, FrozenSet):
        return _handle_set(data, args, origin, key_history=key_history)

    # Handle tuple types (both typing.Tuple and tuple)
    if origin in (tuple, Tuple):
        return _handle_tuple(data, args, key_history=key_history)

    return None


def _recursive_type_unwrapping(typ) -> list[type]:
    """Recursively unwrap union-like types into individual options.

    Args:
        typ: Composite type (e.g. ``TypeVar`` or ``Union``) to unwrap.

    Returns:
        List of plain types contained in ``typ``.
    """
    return (
        [core_typ for sub_typ in typ.__constraints__ for core_typ in _recursive_type_unwrapping(sub_typ)]
        if hasattr(typ, "__constraints__")
        else (
            [core_typ for sub_typ in typ.__args__ for core_typ in _recursive_type_unwrapping(sub_typ)]
            if hasattr(typ, "__args__")
            else [typ]
        )
    )


def _handle_dataclass_cases(config_class: type, data: Any) -> Any:
    if hasattr(config_class, "class_name") and "class_name" in data and config_class.class_name != data["class_name"]:
        raise ValueError(f"Bad data {data['class_name']}/config_class {config_class.class_name} match.")
    if issubclass(config_class, NonStrictDataclass):
        if "_extras" in data and isinstance(data, dict):
            data = {**data}
            data.update(data["_extras"])
            del data["_extras"]
    return data


def _handle_dataclass(config_class: type, data: Any, strict: bool = True, key_history: str = "") -> Any:
    """
    Handle the dataclass case for config_class in parse_config.

    Args:
        config_class: The target configuration class (here only a dataclass)
        data: The configuration data to parse (dict, list, or primitive type)
        strict: If True, raises error on unknown keys in data

    Returns:
        An instance of config_class initialized with the parsed data

    Raises:
        ValueError: If the data cannot be parsed into the specified config_class
        KeyError: If required fields are missing or unknown fields are present in strict mode


    """
    dataclass_dict = {}
    if is_dataclass(data) and isinstance(data, config_class):
        return data
    data = _handle_dataclass_cases(config_class, data)
    for key, key_type in _get_all_annotations(config_class).items():
        if key in data:
            if hasattr(data[key], "__contains__") and "class_name" in data[key]:
                class_name = data[key]["class_name"]
                # resolve key_type
                potential_classes = _recursive_type_unwrapping(key_type)
                resolved_dataclass = None
                for sub_config_cls in potential_classes:
                    if hasattr(sub_config_cls, "class_name") and sub_config_cls.class_name == class_name:
                        resolved_dataclass = sub_config_cls
                if resolved_dataclass is None:
                    raise KeyError(
                        f"Cannot resolve dataclass in {key_type} "
                        f"{[(p, p.class_name if hasattr(p, 'class_name') else None) for p in potential_classes]}"
                        f" with class name {class_name}"
                    )
                key_type = resolved_dataclass
            if key != "class_name":
                dataclass_dict[key] = parse_config(
                    key_type, data[key], key_history=_extend_key_history(key_history, key)
                )

    remaining_keys = set(data).difference(set(dataclass_dict))
    remaining_keys.discard("class_name")

    # override remaining keys for non strict dataclasses
    if hasattr(config_class, "_non_strict") and config_class._non_strict:  # pylint: disable=W0212
        dataclass_dict.update({rk: data[rk] for rk in data if rk not in dataclass_dict})
        remaining_keys = set()

    if remaining_keys and strict:
        raise ValueError(
            f"Undefined keys {remaining_keys} in data at key {key_history} for "
            f"{config_class}: {list(_get_all_annotations(config_class))}"
        )
    return config_class(**dataclass_dict)


def _handle_none_case(config_class, data, key_history: str = ""):
    """
    Handle the None cases for config_class and data in parse_config.

    Args:
        config_class: The target configuration class.
        data: The configuration data to parse (dict, list, or primitive type)
        strict: If True, raises error on unknown keys in data

    Returns:
        None if None is the parsing result, the original data otherwise.

    Raises:
        ValueError: If the data cannot be parsed into the specified config_class
        KeyError: If required fields are missing or unknown fields are present in strict mode


    """
    if isinstance(config_class, None.__class__) or config_class is None.__class__:
        if data is not None:
            raise ValueError(f"Tried to parse {data} into None annotated at key {key_history}")
        return None

    if data is None:
        if any(
            isinstance(typ, None.__class__) or typ is None.__class__ or typ is Any
            for typ in _recursive_type_unwrapping(config_class)
        ):
            return None
        raise ValueError(f"Tried to parse None to {config_class} at key {key_history}")
    return data


def _handle_bool(data: Any, key_history: str = "") -> bool:
    """Parse a boolean from native bool or well-known string values.

    Args:
        data: Input value to convert.
        key_history: Dotted key path for error reporting.

    Returns:
        Parsed boolean value.

    Raises:
        ValueError: If the value cannot be interpreted as boolean.
    """
    if isinstance(data, bool):
        return data
    if isinstance(data, str):
        normalized = data.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError(f"Could not parse {data} in bool at key {key_history}")


def _handle_base_types_and_literals(config_class: type, data: Any, key_history: str = "") -> Any:
    """Handle primitive, bool, and literal parsing fallbacks.

    Args:
        config_class: Target type to coerce into.
        data: Input value provided by the user.
        key_history: Dotted key path for error reporting.

    Returns:
        Parsed value matching ``config_class`` or the original data for literals.
    """
    if config_class is bool:
        return _handle_bool(data, key_history=key_history)

    # Handle primitive types and dataclasses
    if isinstance(config_class, type) and config_class is not Any:
        try:
            return config_class(data)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Could not convert {data} to {config_class} at key {key_history}") from exc

    if _is_literal_instance(data, config_class) or config_class is Any:
        return data
    raise TypeError(f"Invalid type {config_class}")


def parse_config(config_class: type, data: Any, strict: bool = True, key_history: str = ""):
    """
    Parse a dictionary of configuration data into a strongly typed configuration object.

    This function handles the conversion of raw configuration data (typically from JSON/YAML)
    into typed configuration objects, supporting nested configurations, unions, and collections.
    It can optionally integrate with OmegaConf for enhanced configuration handling.

    Args:
        config_class: The target configuration class (typically a dataclass)
        data: The configuration data to parse (dict, list, or primitive type)
        strict: If True, raises error on unknown keys in data

    Returns:
        An instance of config_class initialized with the parsed data

    Raises:
        ValueError: If the data cannot be parsed into the specified config_class
        KeyError: If required fields are missing or unknown fields are present in strict mode

    Example:
        @dataclass
        class ModelConfig:
            hidden_size: int
            activation: str

        data = {"hidden_size": 128, "activation": "relu"}
        config = parse_config(ModelConfig, data)
    """
    data = _handle_none_case(config_class, data, key_history=key_history)
    if data is None:
        return None

    if is_dataclass(config_class) and config_class is not Any:
        return _handle_dataclass(config_class, data, strict=strict, key_history=key_history)
    # Handle both typing.* and built-in collection types
    origin = getattr(config_class, "__origin__", config_class)
    args = getattr(config_class, "__args__", None)

    if origin in (list, List, dict, Dict, tuple, Tuple, Sequence, set, Set, frozenset, FrozenSet):
        return _parse_compositional_types(origin, args, data, key_history=key_history)

    # Handle Union types (both typing.Union and | syntax)
    if (
        (hasattr(config_class, "__name__") and config_class.__name__ == "Union")
        or (hasattr(config_class, "__or__") and (get_origin(config_class) in {Union, UnionType}))
        or isinstance(config_class, TypeVar)
    ):
        union_types = (
            getattr(config_class, "__args__", None)
            or getattr(config_class, "__union_params__", None)
            or getattr(config_class, "__constraints__", None)
        )
        if not union_types:
            raise ValueError("Union type must have type arguments")
        for option in union_types:
            try:
                return parse_config(option, data, key_history=key_history)
            except (ValueError, KeyError, TypeError):
                continue
        raise ValueError(f"Could not parse {data} into any of {union_types} at key: {key_history}")

    # handle bool
    return _handle_base_types_and_literals(config_class, data, key_history=key_history)


def dump_config(a: Any) -> Any:
    """
    Converts a dataclass or dict/list of dataclasses into a PyTree, i.e.
    a nested structure of core python types.

    Args:
        a: Any dataclass or structure of dataclasses

    Returns:
        A pure python structure (that can be dumped to yaml/json).
    """
    if is_dataclass(a) and not isinstance(a, type):
        return asdict(a)
    if hasattr(a, "items"):
        return {k: dump_config(v) for k, v in a.items()}
    return a
