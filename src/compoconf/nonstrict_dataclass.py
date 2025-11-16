"""
This submodule introduces an adapted dataclass interface that enables a runtime extension of a dataclass.
"""

from collections.abc import Mapping, Sequence
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from typing import Any


@dataclass
class NonStrictDataclass:
    """
    Dataclass Interface that allows for non-strict behavior, so it can be extended with extra
    keyword arguments on initialization.
    Note that for an inheriting class, one must use @dataclass(init=False) as decorator.

    Example:

    >>> @dataclass(init=False)
    ... class MyDataclass(NonStrictDataclass):
    ...     a: int
    >>> obj = MyDataclass(a=1, b=2)
    >>> obj.b
    2
    """

    _extras: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _non_strict: bool = True

    def __init__(self, *args, **kwargs):
        # look at *runtime* class so this also sees subclass fields
        declared = [f for f in fields(type(self)) if f.init]
        idx = [idx for idx, f in enumerate(declared) if f.name == "_non_strict"][0]
        declared = declared[:idx] + declared[(idx + 1) :] + [declared[idx]]
        declared_names = {f.name for f in declared}

        # split kwargs into declared vs extras
        init_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in declared_names}
        extra_kwargs = kwargs

        # assign declared fields (replicates dataclass auto-init)
        for f, val in zip(declared, args):
            setattr(self, f.name, val)
        for f in declared[len(args) :]:
            if f.name in init_kwargs:
                setattr(self, f.name, init_kwargs[f.name])
            elif f.default is not MISSING:
                setattr(self, f.name, f.default)
            elif f.default_factory is not MISSING:  # type: ignore[attr-defined]
                setattr(self, f.name, f.default_factory())  # type: ignore[attr-defined]
            else:
                raise TypeError(f"Missing required argument: {f.name}")

        # stash and attach extras
        self._extras = extra_kwargs
        for k, v in extra_kwargs.items():
            setattr(self, k, v)
        self._non_strict = True
        self.__post_init__()

    def __post_init__(self):
        """
        Post init functionality like for dataclasses.
        """

    def _to_dict(self, *, extras_key=None):
        """
        Convert the NonStrictDataclass to a dictionary including the extra attributes.
        """
        d = asdict_patched(self, use_to_dict=False)
        del d["_extras"]
        if extras_key is None:
            d.update(self._extras)
        else:
            d[extras_key] = dict(self._extras)
        return d


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

    def convert(o, use_to_dict: bool = True):
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
