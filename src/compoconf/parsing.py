"""
This submodule provides parsing / dumping capabilities for compoconf. So you can take your json/yaml string and a type
and parse it to a compoconf config structure, or vice versa.

Parsing is *compiled*: the first time a type annotation is parsed, it is turned into a small
closure ("plan") that knows how to read exactly that annotation, and the plan is cached and reused.
All the reflection -- resolving type hints, walking union members, deciding which branch of
:func:`parse_config` applies, looking up extension types -- therefore happens once per annotation
instead of once per value, which is what makes repeated parsing of large configs cheap.

The cache is keyed by ``(annotation, strict, strict_types)``; see :func:`clear_parse_cache` if you
generate config classes dynamically and want to release them.
"""

# One parser shape per annotation shape, and they only make sense next to the dispatch that picks
# between them, so this is over pylint's per-module line budget by design.
# pylint: disable=too-many-lines

import logging
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from inspect import isclass
from typing import Any, Dict, FrozenSet, List, Literal
from typing import Sequence as tSequence
from typing import Set, Tuple, TypeVar, get_args, get_origin

from compoconf.compoconf import _REGISTRY_EPOCH, LazyConfigUnion, _LazyOr, cached_type_hints, clear_type_hints_cache
from compoconf.extension_types import dump_extension, extension_parser
from compoconf.nonstrict_dataclass import _NonStrictDataclassBase, asdict

if sys.version_info >= (3, 10):
    from types import UnionType
    from typing import Union
else:  # pragma: no cover - keep compatibility for older Python versions
    from typing import Union  # ignore: W0404
    from typing import Union as UnionType

try:
    from omegaconf import ListConfig
except ImportError:
    ListConfig = list  # type: ignore[misc,assignment]


LOGGER = logging.getLogger(__name__)

_NONE_TYPE = type(None)

# Origins routed to the container handlers.  Built-in and ``typing.*`` spellings both normalize to
# the built-in via ``__origin__``, but the ``typing`` aliases are kept so a bare ``List`` matches.
_COMPOSITIONAL_ORIGINS = (list, List, dict, Dict, tuple, Tuple, Sequence, set, Set, frozenset, FrozenSet)

# Value types a ``class_name`` discriminator may be read from.  ``dict`` is listed first so the
# overwhelmingly common case short-circuits before the (slower) ABC check that catches OmegaConf's
# ``DictConfig`` and anything else mapping-shaped.
_MAPPING_CLASSES: tuple = (dict, Mapping)

# Value classes that can never carry a ``class_name`` discriminator, used to skip the lookup for
# the overwhelmingly common case of a scalar or a plain sequence field value.
_NON_MAPPING_CLASSES = frozenset(
    {str, bytes, bytearray, int, float, bool, complex, _NONE_TYPE, list, tuple, set, frozenset}
)

# Compiled plans, keyed by (annotation, strict, strict_types).
_PLAN_CACHE: dict = {}

# Safety valve: dynamically generated config classes would otherwise accumulate here forever.
_PLAN_CACHE_LIMIT = 20000


def clear_parse_cache() -> None:
    """Drop all compiled parse plans (and the type-hint cache they are built from).

    Only needed by programs that generate config classes dynamically in a loop: the caches hold a
    reference to every annotation they have seen, which keeps those classes alive.  Parsing stays
    correct either way -- the next call simply recompiles.
    """
    _PLAN_CACHE.clear()
    clear_type_hints_cache()


class _LazyMessage:
    """An error message that is only built when something actually reads it.

    Union parsing discards the error of every member it tries before finding one that fits, and
    those messages embed the whole offending data blob -- so rendering them eagerly made the common
    "a later union member matches" case pay for a string nobody ever looks at.  Passed as the single
    argument of a plain ``ValueError``, so the raised exception is an ordinary ``ValueError`` whose
    ``str()`` is the message; attribute access and comparison forward to the rendered text, so it
    also behaves like the string it stands in for.
    """

    __slots__ = ("_render", "_text")

    def __init__(self, render):
        self._render = render
        self._text = None

    def __str__(self):
        text = self._text
        if text is None:
            text = self._text = self._render()
        return text

    def __repr__(self):
        return repr(self.__str__())

    def __getattr__(self, name):
        if name.startswith("_"):  # never route own/internal lookups through the rendered text
            raise AttributeError(name)
        return getattr(self.__str__(), name)

    def __reduce__(self):
        # Render before pickling/copying: the message is produced by a closure, which is not
        # picklable, and a round-tripped exception only needs the finished text.
        return (str, (self.__str__(),))

    def __eq__(self, other):
        return self.__str__() == other

    def __hash__(self):
        return hash(self.__str__())

    def __len__(self):
        return len(self.__str__())

    def __contains__(self, item):
        return item in self.__str__()


# Every error raised here names the dotted path it failed at, as ``at key <path>`` (``at key:
# <path>`` for a union's own error).  ``_failure_depth`` reads those back out.
_AT_KEY_RE = re.compile(r" at key:? (\S*)")


def _failure_depth(error) -> int:
    """How deep into the data a failed union member got before giving up.

    All members of a union are tried against the same value at the same key, so the one that
    reports the deepest key path is the one that matched furthest -- which is almost always the one
    the user meant. For a nested failure the deepest path mentioned anywhere in the message counts,
    so a member that failed three levels down outranks one that was rejected on its own key set.

    An error that does not carry a key path (a ``__post_init__`` raising on its own, say) scores 0
    and is ordered by message length instead.
    """
    return max((path.count(".") + 1 for path in _AT_KEY_RE.findall(str(error)) if path), default=0)


def _union_error(union_types, errors, data, key_history):
    """Build the (lazily rendered) ``ValueError`` for a union where no member accepted the data."""

    def render():
        # Sort: class_name match first (the member the user most likely intended), then the member
        # that got deepest into the data, then the shortest message as a stable tie-break.
        data_class_name = data.get("class_name") if isinstance(data, dict) else None
        ordered = sorted(
            errors,
            key=lambda opt_err: (
                not (hasattr(opt_err[0], "class_name") and opt_err[0].class_name == data_class_name),
                -_failure_depth(opt_err[1]),
                len(str(opt_err[1])),
            ),
        )
        error_details = "\n  ".join(
            f"{opt.__name__ if hasattr(opt, '__name__') else opt}: {err}" for opt, err in ordered
        )
        return f"Could not parse into any of {union_types} at key: {key_history}\n" f"Tried:\n  {error_details}"

    return ValueError(_LazyMessage(render))


def _get_all_annotations(datacls: Any):
    """Return all resolved type hints for a dataclass.

    Args:
        datacls: Dataclass type whose annotations should be inspected.

    Returns:
        Mapping from field name to resolved type annotation.
    """

    return cached_type_hints(datacls)


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


def _accepts_none(annotation) -> bool:
    """Whether ``None`` is a valid value for ``annotation`` (``Optional``/``Any`` in any nesting)."""
    for typ in _recursive_type_unwrapping(annotation):
        if typ is None or typ is _NONE_TYPE or typ is Any:
            return True
    return False


def _none_result(accepts_none: bool, annotation, key_history: str):
    """Resolve a ``None`` value for a non-union annotation: ``None`` if allowed, else raise.

    Called only on the ``data is None`` path, so the extra call never shows up in a normal parse,
    and every parser shape ends up sharing one definition of what ``None`` means.
    """
    if accepts_none:
        return None
    raise ValueError(f"Tried to parse None to {annotation} at key {key_history}")


def _handle_unset_key(config_class: type, key: str) -> bool:
    """Whether ``key`` must be present in the data, i.e. the class supplies no value for it.

    Args:
        config_class: The target configuration class.
        key: Name of an annotated field.

    Returns:
        ``True`` when the field has no default of any kind and the data must therefore provide it.
    """
    if not hasattr(config_class, key):
        if is_dataclass(config_class):
            for f in fields(config_class):
                if f.name == key:
                    # The f.default case is already covered by the hasattr above, so a
                    # default_factory is the only remaining way this field can fill itself in.
                    return f.default_factory is MISSING
        # Not a dataclass (e.g. a TypedDict), or annotated without being a field: the class
        # supplies nothing, so the data has to.
        return True
    return False


def _shadowed_attribute_owner(cls, name, default):
    """Return the base class whose own attribute ``default`` came from, or ``None``.

    ``None`` means the default is legitimate: either some class in the MRO declares ``name`` as a
    real dataclass field, or nothing in the MRO supplies the value at all.
    """
    owner = None
    for base in cls.__mro__[1:]:
        if name in getattr(base, "__dataclass_fields__", ()):
            return None
        if owner is None and name in base.__dict__ and base.__dict__[name] is default:
            owner = base
    return owner


def _check_shadowed_fields(cls) -> None:
    """Reject a field whose "default" is really an attribute inherited from a base class.

    ``@dataclass`` turns any class attribute into the default of a same-named field, so annotating a
    field with a name a base class already uses for something else -- ``instantiate``, ``_to_dict``,
    ``config`` -- silently defaults that field to the inherited object (usually a method) instead of
    making it required::

        @dataclass
        class MyConfig(ConfigInterface):
            instantiate: int            # no default written, yet not required

        parse_config(MyConfig, {})      # -> instantiate=<function ConfigInterface.instantiate>

    Nothing downstream can tell that apart from a deliberate default, so the config parses and only
    breaks much later, far from the declaration. This runs once per class, when its plan is compiled.

    Raises:
        TypeError: If a field's default is an attribute inherited from a base class.
    """
    dc_fields = getattr(cls, "__dataclass_fields__", None)
    if not dc_fields:
        return
    for name, f in dc_fields.items():
        # A default written in this class's own body is deliberate, whatever it shadows.
        if f.default is MISSING or name in cls.__dict__:
            continue
        owner = _shadowed_attribute_owner(cls, name, f.default)
        if owner is not None:
            raise TypeError(
                f"Field {name!r} of {cls.__name__} shadows the inherited attribute "
                f"{owner.__name__}.{name}, so the dataclass machinery made that attribute "
                f"({f.default!r}) its default value instead of leaving the field required. "
                f"Rename the field, or give it an explicit default if the shadowing is intended."
            )


# ---------------------------------------------------------------------------
# plan cache
# ---------------------------------------------------------------------------


def _get_plan(annotation, strict: bool, strict_types: bool):
    """Return the (cached) compiled parser for ``annotation``.

    Args:
        annotation: The type annotation to build a parser for.
        strict: Whether unknown/missing keys are an error.  Inherited by every nested plan, so it
            is part of the cache key.
        strict_types: Whether scalars are validated instead of coerced.

    Returns:
        A callable ``parser(data, key_history="") -> value``.
    """
    key = (annotation, strict, strict_types)
    try:
        plan = _PLAN_CACHE.get(key)
    except TypeError:  # unhashable annotation -- compile fresh every time
        return _compile(annotation, strict, strict_types)
    if plan is None:
        plan = _compile(annotation, strict, strict_types)
        if len(_PLAN_CACHE) >= _PLAN_CACHE_LIMIT:
            _PLAN_CACHE.clear()
        _PLAN_CACHE[key] = plan
    return plan


def _compile(annotation, strict: bool, strict_types: bool):
    """Build a parser closure for ``annotation``.

    The branch order mirrors :func:`parse_config`'s historical dispatch exactly: ``None``,
    dataclass (or ``dict`` subclass such as a ``TypedDict``), container, union, then scalar.
    """
    if annotation is None or annotation is _NONE_TYPE:
        return _parse_none_annotation

    if (is_dataclass(annotation) and annotation is not Any) or (
        isclass(annotation) and issubclass(annotation, dict) and annotation is not dict
    ):
        return _make_dataclass_parser(annotation, strict, strict_types)

    origin = getattr(annotation, "__origin__", annotation)
    args = getattr(annotation, "__args__", None)
    if origin in _COMPOSITIONAL_ORIGINS:
        return _make_compositional_parser(origin, args, strict, strict_types, annotation)

    if _is_union_like(annotation):
        return _make_union_parser(annotation, strict, strict_types)

    return _make_scalar_parser(annotation, strict_types)


def _parse_none_annotation(data, key_history: str = ""):
    """Parser for an annotation that is literally ``None`` / ``NoneType``."""
    if data is not None:
        raise ValueError(f"Tried to parse {data} into None annotated at key {key_history}")
    return data


def _is_union_like(annotation) -> bool:
    """Whether ``annotation`` is a union, a constrained ``TypeVar``, or a lazy config union."""
    is_union_base = (hasattr(annotation, "__name__") and annotation.__name__ == "Union") or (
        hasattr(annotation, "__or__") and (get_origin(annotation) in {Union, UnionType})
    )
    return is_union_base or isinstance(annotation, (TypeVar, LazyConfigUnion, _LazyOr))


def _union_options(annotation):
    """Return the member types of a union-like annotation (re-reads lazy unions each time)."""
    return (
        getattr(annotation, "__args__", None)
        or getattr(annotation, "__union_params__", None)
        or getattr(annotation, "__constraints__", None)
    )


# ---------------------------------------------------------------------------
# dataclasses
# ---------------------------------------------------------------------------


def _class_name_map(annotation, strict, strict_types):
    """Index the config classes reachable from ``annotation`` by their ``class_name``.

    Returns:
        ``(by_name, options)`` where ``options`` is the unwrapped member list (kept for the error
        message) and ``by_name`` maps each ``class_name`` to ``(class, parser)``.  Later members
        win, matching the original linear scan that kept assigning without breaking.
    """
    options = _recursive_type_unwrapping(annotation)
    by_name = {}
    for option in options:
        name = getattr(option, "class_name", None)
        if isinstance(name, str):
            by_name[name] = (option, _get_plan(option, strict, strict_types))
    return by_name, options


def _resolve_by_class_name(entry, class_name, strict, strict_types):
    """Return the parser for the member of ``entry``'s annotation named by ``class_name``.

    Raises:
        KeyError: If no member of the field's annotation carries that ``class_name``.
    """
    epoch = _REGISTRY_EPOCH[0]
    state = entry[4]
    if state is None or state[0] != epoch:
        state = entry[4] = (epoch,) + _class_name_map(entry[1], strict, strict_types)
        resolved = state[1].get(class_name)
    else:
        resolved = state[1].get(class_name)
        if resolved is None or getattr(resolved[0], "class_name", None) != class_name:
            # ``class_name`` can also be reassigned without touching the registry; rebuild once
            # before giving up so a stale index never turns a valid config into an error.
            state = entry[4] = (epoch,) + _class_name_map(entry[1], strict, strict_types)
            resolved = state[1].get(class_name)
    if resolved is None:
        raise KeyError(
            f"Cannot resolve dataclass in {entry[1]} "
            f"{[(p, p.class_name if hasattr(p, 'class_name') else None) for p in state[2]]}"
            f" with class name {class_name}"
        )
    return resolved[1]


def _make_dataclass_parser(cls, strict: bool, strict_types: bool):  # noqa: C901
    """Compile a parser for a dataclass (or ``dict`` subclass such as a ``TypedDict``)."""
    _check_shadowed_fields(cls)
    accepts_none = _accepts_none(cls)
    annotations = _get_all_annotations(cls)
    # Keys the data is allowed to contain: every annotated field, plus the implicit discriminator.
    known = frozenset(annotations) | {"class_name"}
    required = tuple(key for key in annotations if _handle_unset_key(cls, key))
    is_non_strict = bool(getattr(cls, "_non_strict", False))
    flattens_extras = isclass(cls) and issubclass(cls, _NonStrictDataclassBase)
    checks_class_name = hasattr(cls, "class_name")
    check_keys = strict and not is_non_strict

    # One mutable entry per parsed field: [name, annotation, parser, key suffix, class_name index].
    # ``parser`` and the index are filled in on first use -- lazily, so a self-referential config
    # does not recurse forever at compile time and a field that never appears in the data never
    # pays for resolving its annotation.
    entries = [[key, typ, None, "." + key, None] for key, typ in annotations.items() if key != "class_name"]

    def parse(data, key_history: str = ""):  # pylint: disable=too-many-branches
        if data is None:
            return _none_result(accepts_none, cls, key_history)

        if data.__class__ is not dict and is_dataclass(data) and isinstance(data, cls):
            return data

        if checks_class_name and "class_name" in data:
            own_name = cls.class_name
            if own_name != data["class_name"]:
                raise ValueError(f"Bad data {data['class_name']}/config_class {own_name} match.")

        if flattens_extras and isinstance(data, dict) and "_extras" in data:
            data = {**data}
            data.update(data["_extras"])
            del data["_extras"]

        # Structural validation up front: whether the key set fits depends only on the keys, never
        # on the parsed values, and rejecting a mismatch before descending turns the "try every
        # union member" path from exponential into linear on deeply nested configs.  The common
        # "everything lines up" case is answered by two C-level set operations; the offending key
        # sets are only materialized to build the error.
        if check_keys and not (known.issuperset(data) and all(key in data for key in required)):
            undefined = {key for key in data if key not in known}
            unset = {key for key in required if key not in data}
            raise ValueError(
                _LazyMessage(
                    lambda: (
                        f"Undefined keys {undefined} and unset keys {unset} in data {data} at key "
                        f"{key_history} for {cls}: {list(annotations)}"
                    )
                )
            )

        values = {}
        for entry in entries:
            key = entry[0]
            if key not in data:
                continue
            value = data[key]
            value_class = value.__class__
            if value_class is dict:
                discriminated = "class_name" in value
            elif value_class in _NON_MAPPING_CLASSES:
                discriminated = False
            else:
                discriminated = isinstance(value, _MAPPING_CLASSES) and "class_name" in value
            if discriminated:
                parser = _resolve_by_class_name(entry, value["class_name"], strict, strict_types)
            else:
                parser = entry[2]
                if parser is None:
                    parser = entry[2] = _get_plan(entry[1], strict, strict_types)
            values[key] = parser(value, key_history + entry[3] if key_history else key)

        # Non-strict dataclasses absorb everything the annotations did not claim.
        if is_non_strict:
            for key in data:
                if key not in values:
                    values[key] = data[key]

        return cls(**values)

    return parse


# ---------------------------------------------------------------------------
# containers
# ---------------------------------------------------------------------------


def _make_compositional_parser(origin, args, strict, strict_types, annotation):
    """Dispatch to the container parser matching ``origin``."""
    if origin in (dict, Dict):
        return _make_dict_parser(args, strict, strict_types, annotation)
    if origin in (list, List, Sequence, tSequence):
        return _make_list_parser(args, strict, strict_types, annotation)
    if origin in (set, Set, frozenset, FrozenSet):
        return _make_set_parser(args, origin, strict, strict_types, annotation)
    if origin in (tuple, Tuple):
        return _make_tuple_parser(args, strict, strict_types, annotation)
    return None


def _make_list_parser(args, strict: bool, strict_types: bool, annotation):
    """Compile a parser for ``list``/``Sequence`` annotations."""
    accepts_none = _accepts_none(annotation)
    if not args or len(args) != 1:
        # Untyped lists are rejected -- but only once the value itself is known to be list-shaped,
        # which is why this is checked inside the parser rather than here.
        return _make_bad_container_parser(
            annotation,
            (tuple, list, ListConfig),
            "Expected list, got {t} at key {k}",
            "List type must have exactly 1 type argument at key {k}",
        )
    element = _get_plan(args[0], strict, strict_types)

    def parse(data, key_history: str = ""):
        if data is None:
            return _none_result(accepts_none, annotation, key_history)
        if data.__class__ is not list and not isinstance(data, (tuple, list, ListConfig)):
            raise ValueError(f"Expected list, got {type(data)} at key {key_history}")
        if key_history:
            return [element(item, f"{key_history}.{idx}") for idx, item in enumerate(data)]
        return [element(item, str(idx)) for idx, item in enumerate(data)]

    return parse


def _make_set_parser(args, origin, strict: bool, strict_types: bool, annotation):
    """Compile a parser for ``set``/``frozenset`` annotations."""
    accepts_none = _accepts_none(annotation)
    if not args or len(args) != 1:
        return _make_bad_container_parser(
            annotation,
            (set, frozenset, list, tuple, ListConfig),
            "Expected set, got {t} at key {k}",
            "Set type must have exactly 1 type argument at key {k}",
        )
    factory = frozenset if origin in (frozenset, FrozenSet) else set
    element = _get_plan(args[0], strict, strict_types)

    def parse(data, key_history: str = ""):
        if data is None:
            return _none_result(accepts_none, annotation, key_history)
        if not isinstance(data, (set, frozenset, list, tuple, ListConfig)):
            raise ValueError(f"Expected set, got {type(data)} at key {key_history}")
        if key_history:
            return factory(element(item, f"{key_history}.{idx}") for idx, item in enumerate(data))
        return factory(element(item, str(idx)) for idx, item in enumerate(data))

    return parse


def _make_tuple_parser(args, strict: bool, strict_types: bool, annotation):
    """Compile a parser for ``tuple`` annotations (fixed arity and ``tuple[X, ...]``)."""
    accepts_none = _accepts_none(annotation)
    if not args:
        return _make_bad_container_parser(
            annotation,
            (tuple, list, ListConfig),
            "Expected tuple or list, got {t} ({d}) at key {k}",
            "Tuple type must have type arguments",
        )

    if len(args) == 2 and args[1] is Ellipsis:
        element = _get_plan(args[0], strict, strict_types)

        def parse_variadic(data, key_history: str = ""):
            if data is None:
                return _none_result(accepts_none, annotation, key_history)
            if not isinstance(data, (tuple, list, ListConfig)):
                raise ValueError(f"Expected tuple or list, got {type(data)} ({data}) at key {key_history}")
            if key_history:
                return tuple(element(item, f"{key_history}.{idx}") for idx, item in enumerate(data))
            return tuple(element(item, str(idx)) for idx, item in enumerate(data))

        return parse_variadic

    parsers = tuple(_get_plan(arg, strict, strict_types) for arg in args)
    arity = len(parsers)

    def parse(data, key_history: str = ""):
        if data is None:
            return _none_result(accepts_none, annotation, key_history)
        if not isinstance(data, (tuple, list, ListConfig)):
            raise ValueError(f"Expected tuple or list, got {type(data)} ({data}) at key {key_history}")
        if arity != len(data):
            raise ValueError(f"Expected {arity} items, got {len(data)} at key {key_history}")
        if key_history:
            return tuple(
                item_parser(item, f"{key_history}.{idx}") for idx, (item_parser, item) in enumerate(zip(parsers, data))
            )
        return tuple(item_parser(item, str(idx)) for idx, (item_parser, item) in enumerate(zip(parsers, data)))

    return parse


def _make_dict_parser(args, strict: bool, strict_types: bool, annotation):
    """Compile a parser for ``dict`` annotations."""
    accepts_none = _accepts_none(annotation)
    if not args or len(args) != 2:
        # Don't allow untyped dicts; unlike the sequence containers, the arity complaint comes
        # before the shape complaint, which the error-message tests pin down.
        return _make_bad_container_parser(
            annotation, None, None, "Dict type must have exactly 2 type arguments at key {k}"
        )
    key_parser = _get_plan(args[0], strict, strict_types)
    value_parser = _get_plan(args[1], strict, strict_types)

    def parse(data, key_history: str = ""):
        if data is None:
            return _none_result(accepts_none, annotation, key_history)
        if not hasattr(data, "items") or not callable(data.items):
            raise ValueError(f"Expected dict, got {type(data)} at key {key_history}")
        result = {}
        for key, value in data.items():
            key_str = str(key)
            if key_history:
                child = f"{key_history}.{key_str}" if key_str else key_history
            else:
                child = key_str
            result[key_parser(key, child)] = value_parser(value, child)
        return result

    return parse


def _make_bad_container_parser(annotation, shapes, shape_error, arity_error):
    """Parser for a container annotation with a missing/invalid element type.

    The value is still shape-checked first (``shapes``/``shape_error``) where the original code did
    so, so that e.g. ``list[...]`` without an argument still reports "Expected list" for a string.
    """
    accepts_none = _accepts_none(annotation)

    def parse(data, key_history: str = ""):
        if data is None:
            return _none_result(accepts_none, annotation, key_history)
        if shapes is not None and not isinstance(data, shapes):
            raise ValueError(shape_error.format(t=type(data), d=data, k=key_history))
        raise ValueError(arity_error.format(k=key_history))

    return parse


# ---------------------------------------------------------------------------
# unions
# ---------------------------------------------------------------------------


def _discriminator(options, parsers):
    """Build a ``class_name`` -> parser index, or ``None`` if the union is not purely discriminated.

    Only a union whose every member is a registered config dataclass (plus, optionally, ``None``)
    can be dispatched on ``class_name``: for those, every non-matching member is guaranteed to
    reject the data outright, so picking the matching one first cannot change the outcome.  A union
    containing e.g. ``str`` or ``Any`` would happily swallow a config dict, so it keeps the
    original first-member-wins ordering.
    """
    by_name: dict = {}
    for option, parser in zip(options, parsers):
        if option is None or option is _NONE_TYPE:
            continue
        name = getattr(option, "class_name", None)
        if not isinstance(name, str) or not name or not is_dataclass(option):
            return None
        by_name.setdefault(name, parser)
    return by_name or None


def _make_union_parser(annotation, strict: bool, strict_types: bool):
    """Compile a parser for a union, a constrained ``TypeVar``, or a lazy ``cfgtype`` union."""
    # Lazy unions resolve against the registry, so their member list can still grow after the plan
    # was built; re-resolve whenever the registry changed.
    is_lazy = isinstance(annotation, (TypeVar, LazyConfigUnion, _LazyOr))

    def resolve():
        options = _union_options(annotation)
        accepts_none = _accepts_none(annotation)
        if not options:
            return (_REGISTRY_EPOCH[0], (), (), None, accepts_none)
        options = tuple(options)
        parsers = tuple(_get_plan(option, strict, strict_types) for option in options)
        return (_REGISTRY_EPOCH[0], options, parsers, _discriminator(options, parsers), accepts_none)

    state = [resolve()]

    def parse(data, key_history: str = ""):
        current = state[0]
        if is_lazy and current[0] != _REGISTRY_EPOCH[0]:
            current = state[0] = resolve()
        if data is None:
            return _none_result(current[4], annotation, key_history)
        options, parsers, discriminator = current[1], current[2], current[3]
        if not options:
            raise ValueError("Union type must have type arguments")

        if discriminator is not None and isinstance(data, _MAPPING_CLASSES) and "class_name" in data:
            chosen = discriminator.get(data["class_name"])
            if chosen is not None:
                try:
                    return chosen(data, key_history)
                except (ValueError, KeyError, TypeError):
                    # Fall through to the full scan so the reported error lists every member in
                    # declaration order, exactly as it always has.
                    pass

        errors = []
        for option, parser in zip(options, parsers):
            try:
                return parser(data, key_history)
            except (ValueError, KeyError, TypeError) as exc:
                errors.append((option, exc))
        raise _union_error(options, errors, data, key_history)

    return parse


# ---------------------------------------------------------------------------
# scalars, enums, literals
# ---------------------------------------------------------------------------


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


def _coerce_scalar_strict(config_class: type, data: Any, key_history: str = "") -> Any:
    """Accept a scalar value without silent coercion (used when ``strict_types`` is enabled).

    Rejects mismatched scalar types -- e.g. the string ``"5"`` for an ``int`` field, or a
    ``float`` for an ``int`` field -- instead of silently converting (and possibly truncating)
    them. The only widening allowed is ``int`` -> ``float`` (lossless). ``bool`` is never accepted
    for ``int``/``float`` even though it is a subclass of ``int``.

    Args:
        config_class: One of ``int``, ``float`` or ``str``.
        data: Input value to validate.
        key_history: Dotted key path for error reporting.

    Returns:
        ``data`` (or ``float(data)`` for the int -> float widening case).

    Raises:
        ValueError: If ``data`` does not already match ``config_class``.
    """
    if isinstance(data, bool):
        raise ValueError(f"Expected {config_class.__name__}, got bool ({data!r}) at key {key_history}")
    if config_class is float and isinstance(data, int):
        return float(data)
    if isinstance(data, config_class):
        return data
    raise ValueError(
        f"Expected {config_class.__name__}, got {type(data).__name__} ({data!r}) at key {key_history} "
        "(strict_types=True disables silent coercion)"
    )


def _handle_enum(enum_class: type[Enum], data: Any, key_history: str = "") -> Any:
    """Parse a value into an :class:`enum.Enum` member.

    Accepts an existing member of ``enum_class``, a string matching a member *name*, or a member
    *value* (via ``enum_class(data)``). This makes both ``{"color": "RED"}`` (by name) and
    ``{"color": "red"}`` (by value, for ``RED = "red"``) work.

    Args:
        enum_class: The target ``Enum`` subclass.
        data: Input value (member, name, or value).
        key_history: Dotted key path for error reporting.

    Returns:
        The matching enum member.

    Raises:
        ValueError: If ``data`` matches neither a member name nor a member value.
    """
    if isinstance(data, enum_class):
        return data
    members = enum_class.__members__
    if isinstance(data, str) and data in members:
        return members[data]
    try:
        return enum_class(data)
    except ValueError as exc:
        names = list(members)
        values = [member.value for member in members.values()]
        raise ValueError(
            f"Could not parse {data!r} into enum {enum_class.__name__} at key {key_history}; "
            f"expected one of names {names} or values {values}."
        ) from exc


# Types for which ``T(value)`` can be skipped when the value already has exactly that type.
_IDENTITY_SCALARS = frozenset({int, float, str, bytes, complex})


def _make_scalar_parser(annotation, strict_types: bool):  # noqa: C901  # pylint: disable=R0911
    """Compile a parser for a primitive, enum, extension, literal or ``Any`` annotation.

    The branch order matches the original ``_handle_base_types_and_literals``: ``bool``, enum,
    extension scalar (``Path``/``datetime``/``Decimal``/``UUID``), constructor call, literal/``Any``.
    """
    accepts_none = _accepts_none(annotation)

    if annotation is bool:

        def parse_bool(data, key_history: str = ""):
            if data is None:
                return _none_result(accepts_none, annotation, key_history)
            if data.__class__ is bool:
                return data
            return _handle_bool(data, key_history=key_history)

        return parse_bool

    if isinstance(annotation, type) and issubclass(annotation, Enum):

        def parse_enum(data, key_history: str = ""):
            if data is None:
                return _none_result(accepts_none, annotation, key_history)
            return _handle_enum(annotation, data, key_history=key_history)

        return parse_enum

    extension = extension_parser(annotation)
    if extension is not None:

        def parse_extension(data, key_history: str = ""):
            if data is None:
                return _none_result(accepts_none, annotation, key_history)
            try:
                return extension(data)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Could not parse {data!r} into {annotation.__name__} at key {key_history}") from exc

        return parse_extension

    if isinstance(annotation, type) and annotation is not Any:
        if strict_types and annotation in (int, float, str):

            def parse_strict_scalar(data, key_history: str = ""):
                if data is None:
                    return _none_result(accepts_none, annotation, key_history)
                return _coerce_scalar_strict(annotation, data, key_history=key_history)

            return parse_strict_scalar

        identity_ok = annotation in _IDENTITY_SCALARS

        def parse_constructed(data, key_history: str = ""):
            if data is None:
                return _none_result(accepts_none, annotation, key_history)
            if identity_ok and data.__class__ is annotation:
                return data
            try:
                return annotation(data)
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"Could not convert {data} to {annotation} at key {key_history}") from exc

        return parse_constructed

    if annotation is Any:

        def parse_any(data, key_history: str = ""):  # pylint: disable=unused-argument
            return data

        return parse_any

    if getattr(annotation, "__origin__", None) is Literal:
        # Pre-split the literal members into "match by isinstance" and "match by ==".
        checks = tuple((isinstance(arg, type), arg) for arg in get_args(annotation))

        def parse_literal(data, key_history: str = ""):
            if data is None:
                return _none_result(accepts_none, annotation, key_history)
            for is_type, arg in checks:
                if _is_literal_instance(data, arg) if is_type else data == arg:
                    return data
            raise TypeError(f"Invalid type {annotation}")

        return parse_literal

    def parse_invalid(data, key_history: str = ""):
        if data is None:
            return _none_result(accepts_none, annotation, key_history)
        if _is_literal_instance(data, annotation):
            return data
        raise TypeError(f"Invalid type {annotation}")

    return parse_invalid


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------


def parse_config(config_class: type, data: Any, strict: bool = True, key_history: str = "", strict_types: bool = False):
    """
    Parse a dictionary of configuration data into a strongly typed configuration object.

    This function handles the conversion of raw configuration data (typically from JSON/YAML)
    into typed configuration objects, supporting nested configurations, unions, and collections.
    It can optionally integrate with OmegaConf for enhanced configuration handling.

    Args:
        config_class: The target configuration class (typically a dataclass)
        data: The configuration data to parse (dict, list, or primitive type)
        strict: If True, raises an error on unknown keys in the data and on declared fields
            that have neither a value nor a default. Applies recursively to nested configs.
        key_history: Dotted key path for error reporting (used internally during recursion).
        strict_types: If True, scalar fields (``int``/``float``/``str``) are validated instead of
            coerced. By default (False), values are coerced via the target type (e.g. the string
            ``"5"`` becomes ``5`` for an ``int`` field); enabling this rejects such mismatches so
            silent/lossy conversions surface as errors. Applies recursively to nested fields.

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
    return _get_plan(config_class, strict, strict_types)(data, key_history)


# ---------------------------------------------------------------------------
# legacy helper
#
# Predates the compiled plans and is kept as a thin wrapper over them because the test suite
# drives it directly.
# ---------------------------------------------------------------------------


def _parse_compositional_types(origin, args, data, key_history: str = "", strict_types: bool = False) -> Any:
    """
    Parse data to a compositional generic origin type with args.
    E.g. _parse_compositional_types(dict, (str, str), {"abc": "abc"})

    Args:
        origin: Generic type.
        args: Generic type args.
        data: Data to be parsed into object.
        key_history: Dotted key path for error reporting.
        strict_types: Disable silent scalar coercion.

    Returns:
        Object of origin[args] type from parsed data, or ``None`` for an unsupported origin.
    """
    parser = _make_compositional_parser(origin, args, True, strict_types, args)
    if parser is None:
        return None
    return parser(data, key_history)


def dump_config(a: Any) -> Any:
    """
    Converts a dataclass or dict/list of dataclasses into a PyTree, i.e.
    a nested structure of core python types.

    Conversions follow :func:`asdict` exactly, so a value dumps to the same thing whether it sits
    inside a config or is passed here directly: enums become their value, the extension scalars
    (``Path``, ``datetime``/``date``/``time``, ``Decimal``, ``UUID``) become their JSON-safe form,
    and mappings, lists and tuples are recursed into (tuples stay tuples). Strings and bytes are
    left alone rather than treated as sequences of characters.

    Args:
        a: Any dataclass or structure of dataclasses

    Returns:
        A pure python structure (that can be dumped to yaml/json).
    """
    if is_dataclass(a) and not isinstance(a, type):
        return asdict(a)
    if isinstance(a, Enum):
        return a.value
    handled, extension_value = dump_extension(a)
    if handled:
        return extension_value
    if hasattr(a, "items"):
        return {k: dump_config(v) for k, v in a.items()}
    if isinstance(a, (list, tuple)) or (isinstance(a, Sequence) and not isinstance(a, (str, bytes, bytearray))):
        dumped = (dump_config(item) for item in a)
        return tuple(dumped) if isinstance(a, tuple) else list(dumped)
    return a
