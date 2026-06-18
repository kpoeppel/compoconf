"""
This submodule introduces an adapted dataclass interface that enables a runtime extension of a dataclass.
"""

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any

from compoconf.extension_types import dump_extension

# ``_FIELD`` / ``_FIELD_INITVAR`` are private sentinels, but they are the canonical (and only)
# way to tell a real field from an ``InitVar`` pseudo-field, which is required to forward
# InitVars to ``__post_init__`` the way the stdlib-generated ``__init__`` does.  Accessed via
# ``getattr`` so static type checkers don't flag the private module attributes.
_FIELD = getattr(dataclasses, "_FIELD")
_FIELD_INITVAR = getattr(dataclasses, "_FIELD_INITVAR")

# internal bookkeeping fields, managed explicitly in ``_nonstrict_init`` and kept out of
# the positional/keyword arg matching so they never shadow user-declared fields.
_INTERNAL_FIELDS = ("_extras", "_non_strict")


def _iter_init_params(cls):
    """Yield ``(field, is_initvar)`` for each init parameter of ``cls`` in declaration order.

    Unlike :func:`dataclasses.fields`, this includes ``InitVar`` pseudo-fields (so they can be
    forwarded to ``__post_init__``) while excluding ``ClassVar`` pseudo-fields and the internal
    bookkeeping fields.  The order matches the stdlib-generated ``__init__`` signature.
    """
    for f in cls.__dataclass_fields__.values():
        field_type = f._field_type  # pylint: disable=protected-access
        if f.init and field_type in (_FIELD, _FIELD_INITVAR) and f.name not in _INTERNAL_FIELDS:
            yield f, field_type is _FIELD_INITVAR


def _nonstrict_init(self, args, kwargs):  # pylint: disable=too-many-locals
    """Shared ``__init__`` body for the (frozen) non-strict dataclasses.

    Uses ``object.__setattr__`` for every assignment so the exact same logic works for
    both mutable and ``frozen=True`` subclasses (a frozen ``__setattr__`` would reject
    plain ``setattr``, exactly as the stdlib-generated frozen ``__init__`` does).

    ``InitVar`` pseudo-fields are supported: they participate in positional/keyword argument
    matching, are *not* stored as attributes, and are forwarded to ``__post_init__`` in
    declaration order, mirroring stdlib dataclass behavior.

    Args:
        self: The instance being initialized.
        args: Positional arguments mapped onto the init parameters (fields and InitVars), in order.
        kwargs: Keyword arguments; init-parameter names are consumed, everything else
            becomes an "extra" attribute.  A ``_extras`` kwarg (fed back by
            ``dataclasses.replace`` / stdlib-``asdict``-shaped dicts) seeds the extras.
    """
    set_ = object.__setattr__

    # ``replace`` (and stdlib-``asdict``-shaped dicts) feed ``_extras`` back in as a
    # kwarg; pop it out as the base set of extras and drop the ``_non_strict`` flag.
    base_extras = dict(kwargs.pop("_extras", {}) or {})
    kwargs.pop("_non_strict", None)

    # look at the *runtime* class so this also sees subclass fields and InitVars
    init_params = list(_iter_init_params(type(self)))
    param_names = {f.name for f, _ in init_params}

    # split kwargs into init parameters vs extras
    init_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in param_names}
    extra_kwargs = kwargs

    # resolve each init parameter (positional, keyword, or default); InitVars are collected
    # for __post_init__ instead of being stored, everything else replicates dataclass auto-init
    initvars = []
    for idx, (f, is_initvar) in enumerate(init_params):
        if idx < len(args):
            value = args[idx]
        elif f.name in init_kwargs:
            value = init_kwargs[f.name]
        elif f.default is not MISSING:
            value = f.default
        elif f.default_factory is not MISSING:  # type: ignore[attr-defined]
            value = f.default_factory()  # type: ignore[attr-defined]
        else:
            raise TypeError(f"Missing required argument: {f.name}")
        if is_initvar:
            initvars.append(value)
        else:
            set_(self, f.name, value)

    # stash and attach extras: replace()-supplied ``_extras`` first, then any loose
    # keyword arguments (so an explicitly passed extra overrides the round-tripped one)
    extras = {**base_extras, **extra_kwargs}
    set_(self, "_extras", extras)
    for k, v in extras.items():
        set_(self, k, v)
    set_(self, "_non_strict", True)
    self.__post_init__(*initvars)


class _NonStrictDataclassBase:
    """Shared, non-dataclass behavior for :class:`NonStrictDataclass` and its frozen twin.

    Holds the common ``__init__``/``__post_init__``/``_to_dict`` implementation so that the
    mutable and frozen variants differ only in their ``@dataclass`` decorator.  Subclasses
    use ``@dataclass(init=False)`` (or ``@dataclass(init=False, frozen=True)``) so this
    shared ``__init__`` is inherited rather than regenerated.
    """

    # Declared as dataclass fields on the concrete subclasses below; annotated here so static
    # analysis knows the shared methods may rely on them (this class is not itself a dataclass,
    # so these annotations are not collected as fields).
    _extras: dict[str, Any]
    _non_strict: bool

    def __init__(self, *args, **kwargs):
        _nonstrict_init(self, args, kwargs)

    def __post_init__(self):
        """
        Post init functionality like for dataclasses.
        """

    def _to_dict(self, *, extras_key=None):
        """
        Convert the (frozen) NonStrictDataclass to a dictionary including the extra attributes.
        """
        # NOTE: extras are *untyped* by contract (see README): use a declared
        # ``Type | None = None`` field for nested configs that must round-trip.  Dataclass-valued
        # extras are therefore not supported and are intentionally not recursed into here.
        d = asdict_patched(self, use_to_dict=False)
        del d["_extras"]
        del d["_non_strict"]
        if extras_key is None:
            d.update(self._extras)
        else:
            d[extras_key] = dict(self._extras)
        return d


@dataclass(init=False)
class NonStrictDataclass(_NonStrictDataclassBase):
    """
    Dataclass Interface that allows for non-strict behavior, so it can be extended with extra
    keyword arguments on initialization.
    Note that for an inheriting class, one must use @dataclass(init=False) as decorator.

    For an immutable variant, inherit from :class:`FrozenNonStrictDataclass` instead and use
    ``@dataclass(init=False, frozen=True)``.

    Example:

    >>> @dataclass(init=False)
    ... class MyDataclass(NonStrictDataclass):
    ...     a: int
    >>> obj = MyDataclass(a=1, b=2)
    >>> obj.b
    2
    """

    # ``_extras`` participates in init (``init=True``) so that ``dataclasses.replace``
    # round-trips the extra values: ``replace`` only collects ``init=True`` fields, so
    # an ``init=False`` ``_extras`` would be silently dropped on every replace.  The
    # custom ``__init__`` still owns ``_extras`` entirely (it is excluded from the
    # positional/keyword arg matching and reconstructed from the leftover kwargs).
    # ``hash=False`` keeps the frozen variant hashable (a dict is unhashable); it is a
    # harmless no-op here since a mutable dataclass is unhashable anyway.
    _extras: dict[str, Any] = field(default_factory=dict, repr=False, hash=False)
    _non_strict: bool = True


@dataclass(init=False, frozen=True)
class FrozenNonStrictDataclass(_NonStrictDataclassBase):
    """
    Immutable counterpart of :class:`NonStrictDataclass`.

    Behaves exactly like :class:`NonStrictDataclass` (extra keyword arguments on init,
    ``dataclasses.replace`` round-tripping, flattened ``asdict``), but instances are frozen:
    declared fields *and* extras are read-only after construction, and instances are hashable.

    A frozen dataclass can only inherit from a frozen dataclass base, which is why this is a
    separate class rather than a flag on :class:`NonStrictDataclass`.  Inheriting classes must
    use ``@dataclass(init=False, frozen=True)`` as decorator.

    Example:

    >>> @dataclass(init=False, frozen=True)
    ... class MyFrozen(FrozenNonStrictDataclass):
    ...     a: int
    >>> obj = MyFrozen(a=1, b=2)
    >>> obj.b
    2
    """

    _extras: dict[str, Any] = field(default_factory=dict, repr=False, hash=False)
    _non_strict: bool = True


def _has_to_dict(o: Any) -> bool:
    """
    Checks for the _to_dict method in the dataclass

    Args:
        o: Any
            Object

    Returns:
        If o has `_to_dict` method.
    """
    return hasattr(o, "_to_dict") and callable(getattr(o, "_to_dict"))


def asdict_patched(obj, *, dict_factory=dict, use_to_dict=True) -> dict[str, Any]:
    """
    Converts a dataclass (including NonStrictDataclass) to a dictionary.

    Args:
        obj: dataclass
            Object to be converted.
        use_to_dict: bool
            If to use the _to_dict method of the dataclass. Needed to avoid infinite recursion.
        dict_factory:
            Dict object type

    Returns:
        Dictionary created from `obj` content.

    Raises:
        TypeError
            In case of observed recursion.
    """
    seen = set()  # recursion guard by id()

    def convert(o, use_to_dict: bool = True):  # pylint: disable=too-many-return-statements
        oid = id(o)
        if oid in seen:
            # Match stdlib behavior: raise on cycles
            raise TypeError("asdict() should be called on acyclic structures")
        # Only track container-like or dataclass objects to avoid overhead
        track = is_dataclass(o) or isinstance(o, (Mapping, Sequence)) and not isinstance(o, (str, bytes, bytearray))
        if track:
            seen.add(oid)

        try:
            # 1) Honor custom to_dict() first
            if _has_to_dict(o) and use_to_dict:
                return o._to_dict()  # pylint: disable=W0212

            # 2) Dataclasses (recurse field-wise)
            if is_dataclass(o):
                items = []
                for f in fields(o):
                    items.append((f.name, convert(getattr(o, f.name))))

                return dict_factory(items)

            # 2b) Enums serialize to their value (round-trips via parse-by-value)
            if isinstance(o, Enum):
                return o.value

            # 2c) Extension scalar types (Path, datetime/date/time, Decimal, UUID) -> JSON-safe form
            handled, ext_value = dump_extension(o)
            if handled:
                return ext_value

            # 3) Mappings
            if isinstance(o, Mapping):
                # if retain_collection_types:
                #     return type(o)((convert(k), convert(v)) for k, v in o.items())
                # else:
                return {convert(k): convert(v) for k, v in o.items()}

            # 4) Sequences (but not str/bytes)
            if isinstance(o, Sequence) and not isinstance(o, (str, bytes, bytearray)):
                # if retain_collection_types:
                #     return type(o)(convert(v) for v in o)
                if isinstance(o, tuple):
                    return tuple((convert(v) for v in o))
                return [convert(v) for v in o]

            # 5) Base case: leave as-is
            return o
        finally:
            if track:
                seen.discard(oid)

    res = convert(obj, use_to_dict=use_to_dict)
    return res


asdict = asdict_patched
