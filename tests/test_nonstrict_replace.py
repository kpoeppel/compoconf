"""
Tests for native ``dataclasses`` function support on :class:`NonStrictDataclass`.

The focus is :func:`dataclasses.replace`, which historically dropped the
"extra" (non-declared) attributes because ``_extras`` was an ``init=False``
field and therefore invisible to ``replace``.  These tests pin down the desired
behavior and assert parity with plain stdlib dataclasses wherever it applies,
plus coverage of the other stdlib dataclass helpers (``asdict``, ``astuple``,
``fields``, ``is_dataclass``) and config round-tripping through the parser.
"""

import copy
import pickle
from dataclasses import FrozenInstanceError, InitVar
from dataclasses import asdict as dc_asdict
from dataclasses import astuple as dc_astuple
from dataclasses import dataclass, field, fields, is_dataclass, replace
from typing import Any

import pytest  # pylint: disable=E0401

from compoconf.nonstrict_dataclass import FrozenNonStrictDataclass, NonStrictDataclass, asdict
from compoconf.parsing import dump_config, parse_config


@dataclass
class PlainPoint:
    """A vanilla stdlib dataclass used as the parity baseline."""

    x: int
    y: int = 0


@dataclass(init=False)
class StrictlyTyped(NonStrictDataclass):
    """A NonStrictDataclass with declared fields and room for extras."""

    a: int
    b: str = "default_b"


@dataclass(init=False)
class Outer(NonStrictDataclass):
    """A NonStrictDataclass that nests another (non-)strict dataclass."""

    name: str = "outer"
    inner: Any = None


@dataclass(init=False)
class ChildCfg(NonStrictDataclass):
    """A nested NonStrict config used as a *declared, typed* field (not an extra)."""

    a: int = 0


@dataclass(init=False)
class ParentCfg(NonStrictDataclass):
    """The recommended pattern for a nested, typed config: ``Type | None = None``."""

    name: str = "p"
    child: ChildCfg | None = None


# --------------------------------------------------------------------------- #
# Parity baseline: plain dataclasses                                           #
# --------------------------------------------------------------------------- #
def test_replace_plain_dataclass():
    """``replace`` on a normal dataclass behaves as the stdlib defines it."""
    p = PlainPoint(1, 2)
    assert replace(p, y=5) == PlainPoint(1, 5)
    assert replace(p, x=9) == PlainPoint(9, 2)
    # the original is never mutated
    assert p == PlainPoint(1, 2)


def test_replace_non_init_field_raises():
    """Replacing a genuinely ``init=False`` field raises, matching stdlib."""

    @dataclass
    class HasNonInit:
        """Dataclass with one non-init field."""

        a: int = 1
        b: int = field(init=False, default=2)

    obj = HasNonInit(a=1)
    with pytest.raises(ValueError):
        replace(obj, b=5)


# --------------------------------------------------------------------------- #
# NonStrictDataclass: strict (declared-only) behavior                          #
# --------------------------------------------------------------------------- #
def test_replace_nonstrict_without_extras():
    """Without extras, ``replace`` matches plain dataclass semantics."""
    obj = StrictlyTyped(a=1, b="x")
    r = replace(obj, a=2)
    assert r.a == 2
    assert r.b == "x"
    assert not r._extras  # pylint: disable=W0212
    # original untouched
    assert obj.a == 1


def test_positional_construction_still_works():
    """The fix must not break positional construction of declared fields."""
    obj = StrictlyTyped(1, "bee", c="x")
    assert obj.a == 1
    assert obj.b == "bee"
    assert obj.c == "x"  # pylint: disable=E1101
    assert obj._extras == {"c": "x"}  # pylint: disable=W0212


# --------------------------------------------------------------------------- #
# NonStrictDataclass: extras must survive replace                              #
# --------------------------------------------------------------------------- #
def test_replace_preserves_extras():
    """Replacing a declared field keeps all extras intact."""
    obj = StrictlyTyped(a=1, c="extra_c", d=3.14)
    r = replace(obj, a=2)
    assert r.a == 2
    assert r.b == "default_b"
    assert r.c == "extra_c"  # pylint: disable=E1101
    assert r.d == 3.14  # pylint: disable=E1101
    assert r._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212
    # original untouched
    assert obj.a == 1
    assert obj._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212


def test_replace_overrides_single_extra():
    """Replacing one extra changes it and keeps the others (merge semantics)."""
    obj = StrictlyTyped(a=1, c="extra_c", d=3.14)
    r = replace(obj, c="new_c")
    assert r.c == "new_c"  # pylint: disable=E1101
    assert r.d == 3.14  # pylint: disable=E1101
    assert r._extras == {"c": "new_c", "d": 3.14}  # pylint: disable=W0212
    # original untouched
    assert obj.c == "extra_c"  # pylint: disable=E1101


def test_replace_adds_new_extra():
    """A previously-absent extra can be added via replace."""
    obj = StrictlyTyped(a=1, c="extra_c")
    r = replace(obj, e="added")
    assert r.e == "added"  # pylint: disable=E1101
    assert r._extras == {"c": "extra_c", "e": "added"}  # pylint: disable=W0212


def test_replace_noop_equals_original():
    """A no-op replace yields an equal object (extras included)."""
    obj = StrictlyTyped(a=1, c="extra_c", d=3.14)
    assert replace(obj) == obj


# --------------------------------------------------------------------------- #
# Nested replacements                                                          #
# --------------------------------------------------------------------------- #
def test_nested_replace_nonstrict_in_nonstrict():
    """Nested NonStrict objects replace correctly and keep their extras."""
    inner = StrictlyTyped(a=1, c="ic")
    outer = Outer(name="o", inner=inner)
    r = replace(outer, inner=replace(inner, a=2))
    assert r.name == "o"
    assert r.inner.a == 2
    assert r.inner.c == "ic"
    # original inner / outer untouched
    assert outer.inner.a == 1


def test_nested_replace_plain_in_nonstrict():
    """A plain dataclass nested inside a NonStrict one replaces normally."""
    p = PlainPoint(1, 2)
    outer = Outer(name="o2", inner=p)
    r = replace(outer, inner=replace(p, x=9))
    assert r.inner == PlainPoint(9, 2)
    assert outer.inner == PlainPoint(1, 2)


# --------------------------------------------------------------------------- #
# Round-trip: both dump shapes must load identically                          #
# --------------------------------------------------------------------------- #
def test_roundtrip_both_shapes_via_parser():
    """Explicit-``_extras`` and flattened dumps load identically via the parser."""
    obj = StrictlyTyped(a=1, c="extra_c", d=3.14)
    explicit = dc_asdict(obj)  # stdlib shape: nested {'_extras': {...}, ...}
    flattened = asdict(obj)  # compoconf shape: extras flattened to top level

    assert "_extras" in explicit
    assert "_extras" not in flattened

    r1 = parse_config(StrictlyTyped, explicit)
    r2 = parse_config(StrictlyTyped, flattened)
    assert r1._extras == r2._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212
    assert r1.a == r2.a == 1


def test_roundtrip_both_shapes_via_direct_construction():
    """Both dump shapes also reconstruct via direct ``Class(**dump)``."""
    obj = StrictlyTyped(a=1, c="extra_c", d=3.14)
    explicit = dc_asdict(obj)
    flattened = asdict(obj)

    r1 = StrictlyTyped(**explicit)
    r2 = StrictlyTyped(**flattened)
    assert r1._extras == r2._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212
    assert r1.a == r2.a == 1
    assert r1 == r2


# --------------------------------------------------------------------------- #
# Other stdlib dataclass helpers                                              #
# --------------------------------------------------------------------------- #
def test_native_asdict_includes_extras_nested():
    """stdlib ``dataclasses.asdict`` exposes extras under the ``_extras`` key."""
    obj = StrictlyTyped(a=1, c="extra_c")
    d = dc_asdict(obj)
    assert d["a"] == 1
    assert d["b"] == "default_b"
    assert d["_extras"] == {"c": "extra_c"}
    assert d["_non_strict"] is True


def test_native_astuple_runs():
    """stdlib ``dataclasses.astuple`` includes declared values and the extras dict."""
    obj = StrictlyTyped(a=1, c="extra_c")
    t = dc_astuple(obj)
    assert 1 in t
    assert {"c": "extra_c"} in t


def test_fields_reports_extras_field_as_init():
    """``fields`` lists declared + bookkeeping fields; ``_extras`` now participates in init."""
    obj = StrictlyTyped(a=1, c="extra_c")
    names = {f.name for f in fields(obj)}
    assert {"a", "b", "_extras", "_non_strict"} <= names
    # extras are *not* promoted to real (class-level) fields
    assert "c" not in names
    assert is_dataclass(obj)
    extras_field = next(f for f in fields(obj) if f.name == "_extras")
    assert extras_field.init is True


# --------------------------------------------------------------------------- #
# compoconf's own asdict hides the internal bookkeeping fields                 #
# --------------------------------------------------------------------------- #
def test_compoconf_asdict_omits_internal_fields():
    """compoconf ``asdict`` flattens extras and never leaks ``_extras``/``_non_strict``."""
    obj = StrictlyTyped(a=1, c="extra_c", d=3.14)
    d = asdict(obj)
    assert d == {"a": 1, "b": "default_b", "c": "extra_c", "d": 3.14}
    assert "_extras" not in d
    assert "_non_strict" not in d


def test_compoconf_asdict_omits_internal_fields_when_nested():
    """The internal fields stay hidden for nested NonStrict dataclasses too."""
    outer = Outer(name="top", inner=StrictlyTyped(a=1, c="extra_c"), y=99)
    d = asdict(outer)
    assert d == {"name": "top", "inner": {"a": 1, "b": "default_b", "c": "extra_c"}, "y": 99}
    for sub in (d, d["inner"]):
        assert "_extras" not in sub
        assert "_non_strict" not in sub


# --------------------------------------------------------------------------- #
# copy / deepcopy / pickle preserve extras                                     #
# --------------------------------------------------------------------------- #
def test_copy_and_deepcopy_preserve_extras():
    """Shallow and deep copies keep declared fields and extras."""
    obj = StrictlyTyped(a=1, c="extra_c", d=[1, 2])
    shallow = copy.copy(obj)
    deep = copy.deepcopy(obj)
    assert shallow.c == deep.c == "extra_c"  # pylint: disable=E1101
    assert shallow == deep == obj
    # deepcopy is independent
    deep.d.append(3)  # pylint: disable=E1101
    assert obj.d == [1, 2]  # pylint: disable=E1101


def test_pickle_preserves_extras():
    """A NonStrictDataclass survives a pickle round-trip with its extras."""
    obj = StrictlyTyped(a=1, c="extra_c", d=3.14)
    restored = pickle.loads(pickle.dumps(obj))
    assert restored.a == 1
    assert restored.c == "extra_c"  # pylint: disable=E1101
    assert restored._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212
    assert restored == obj


# --------------------------------------------------------------------------- #
# Documented limitations (pinned so we are alerted if behavior changes)        #
# --------------------------------------------------------------------------- #
def test_frozen_subclass_of_mutable_base_is_rejected():
    """A ``frozen=True`` subclass of the *mutable* base is still rejected by Python.

    Python forbids inheriting a frozen dataclass from a non-frozen one, so frozen
    non-strict dataclasses must inherit from :class:`FrozenNonStrictDataclass`
    (see the frozen tests below) rather than from :class:`NonStrictDataclass`.
    """
    with pytest.raises(TypeError):

        @dataclass(init=False, frozen=True)
        class _Frozen(NonStrictDataclass):
            a: int = 1


# --------------------------------------------------------------------------- #
# InitVar support                                                              #
# --------------------------------------------------------------------------- #
def test_initvar_forwarded_to_post_init_and_not_stored():
    """An InitVar reaches ``__post_init__``, is not stored, and coexists with extras."""

    @dataclass(init=False)
    class WithInitVar(NonStrictDataclass):
        """NonStrict dataclass with an InitVar consumed by __post_init__."""

        a: int = 1
        seed: InitVar[int] = 0
        b: int = 0

        def __post_init__(self, seed):  # pylint: disable=arguments-differ
            self.b = self.a + seed

    obj = WithInitVar(a=2, seed=5, extra="x")
    assert obj.b == 7  # __post_init__ received the InitVar
    assert "seed" not in obj.__dict__  # InitVar is never stored on the instance
    assert obj.extra == "x"  # extras still work alongside InitVars  # pylint: disable=E1101
    assert obj._extras == {"extra": "x"}  # pylint: disable=W0212
    assert asdict(obj) == {"a": 2, "b": 7, "extra": "x"}  # InitVar absent from the dump


def test_initvar_positional_and_required():
    """InitVars participate in positional matching and may be required (no default)."""

    @dataclass(init=False)
    class Interleaved(NonStrictDataclass):
        """InitVar between two regular fields to check positional ordering."""

        a: int = 0
        seed: InitVar[int] = 0
        out: int = 0

        def __post_init__(self, seed):  # pylint: disable=arguments-differ
            self.out = self.a + seed

    assert Interleaved(3, 10).out == 13  # positional: a=3, seed=10

    @dataclass(init=False)
    class RequiredInitVar(NonStrictDataclass):
        """An InitVar with no default is a required argument."""

        seed: InitVar[int]
        out: int = 0

        def __post_init__(self, seed):  # pylint: disable=arguments-differ
            self.out = seed

    assert RequiredInitVar(seed=7).out == 7
    with pytest.raises(TypeError):
        RequiredInitVar()


def test_frozen_initvar_is_supported():
    """InitVars work on the frozen variant (``__post_init__`` uses ``object.__setattr__``)."""

    @dataclass(init=False, frozen=True)
    class FrozenWithInitVar(FrozenNonStrictDataclass):
        """Frozen NonStrict dataclass deriving a field from an InitVar."""

        a: int = 1
        seed: InitVar[int] = 0
        b: int = 0

        def __post_init__(self, seed):  # pylint: disable=arguments-differ
            object.__setattr__(self, "b", self.a + seed)

    obj = FrozenWithInitVar(a=2, seed=5, y="Y")
    assert obj.b == 7
    assert obj.y == "Y"  # pylint: disable=E1101
    # replace re-runs __init__/__post_init__; the InitVar falls back to its default (0)
    assert replace(obj, a=10).b == 10


# --------------------------------------------------------------------------- #
# FrozenNonStrictDataclass: the supported immutable variant                    #
# --------------------------------------------------------------------------- #
@dataclass(init=False, frozen=True)
class FrozenTyped(FrozenNonStrictDataclass):
    """An immutable NonStrict dataclass with declared fields and room for extras."""

    a: int
    b: str = "default_b"


def test_frozen_construction_with_extras_and_positional():
    """Frozen variant supports positional declared args plus arbitrary extras."""
    obj = FrozenTyped(1, c="x", d=3.14)
    assert obj.a == 1
    assert obj.b == "default_b"
    assert obj.c == "x"  # pylint: disable=E1101
    assert obj.d == 3.14  # pylint: disable=E1101
    assert obj._extras == {"c": "x", "d": 3.14}  # pylint: disable=W0212


def test_frozen_is_immutable_for_declared_and_extras():
    """Both declared fields and extras are read-only after construction."""
    obj = FrozenTyped(a=1, c="x")
    with pytest.raises(FrozenInstanceError):
        obj.a = 2
    with pytest.raises(FrozenInstanceError):
        obj.c = "y"  # pylint: disable=E1101,W0201


def test_frozen_replace_preserves_extras():
    """``dataclasses.replace`` round-trips extras on the frozen variant too."""
    obj = FrozenTyped(a=1, c="extra_c", d=3.14)
    r = replace(obj, a=2)
    assert r.a == 2
    assert r.c == "extra_c"  # pylint: disable=E1101
    assert r._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212
    # original untouched
    assert obj.a == 1


def test_frozen_is_hashable_and_eq_includes_extras():
    """Frozen instances are hashable, and equality/hash account for extras."""
    a1 = FrozenTyped(a=1, c="x")
    a2 = FrozenTyped(a=1, c="x")
    b = FrozenTyped(a=1, c="y")
    assert a1 == a2
    assert a1 != b
    assert hash(a1) == hash(a2)
    # usable as set/dict keys (the whole point of frozen)
    assert len({a1, a2, b}) == 2


def test_frozen_compoconf_asdict_omits_internal_fields():
    """compoconf ``asdict`` flattens extras and hides bookkeeping for the frozen variant."""
    obj = FrozenTyped(a=1, c="extra_c", d=3.14)
    d = asdict(obj)
    assert d == {"a": 1, "b": "default_b", "c": "extra_c", "d": 3.14}
    assert "_extras" not in d
    assert "_non_strict" not in d


def test_frozen_roundtrips_through_parser():
    """A frozen config round-trips through both dump shapes via the parser."""
    obj = FrozenTyped(a=1, c="extra_c", d=3.14)
    r_flat = parse_config(FrozenTyped, asdict(obj))
    r_explicit = parse_config(FrozenTyped, dc_asdict(obj))
    assert r_flat == r_explicit == obj
    assert r_flat._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212


@dataclass(init=False, frozen=True)
class FrozenOuter(FrozenNonStrictDataclass):
    """A frozen NonStrict dataclass that nests another (non-)strict dataclass."""

    name: str = "outer"
    inner: Any = None


# --------------------------------------------------------------------------- #
# asdict / parse round-trip for (untyped) plain-container extras               #
# --------------------------------------------------------------------------- #
def test_asdict_keeps_plain_container_extras():
    """Untyped extras that are plain dicts/lists are carried through asdict as-is."""
    obj = StrictlyTyped(a=1, meta={"k": "v", "nums": [1, 2, 3]})
    d = asdict(obj)
    assert d == {"a": 1, "b": "default_b", "meta": {"k": "v", "nums": [1, 2, 3]}}


def test_dump_config_with_plain_extras_is_json_serializable():
    """``dump_config`` with untyped plain-container extras yields a pure JSON tree."""
    obj = StrictlyTyped(a=1, meta={"k": "v", "nums": [1, 2, 3]})
    import json  # local import keeps the dependency obvious  # pylint: disable=C0415

    assert json.loads(json.dumps(dump_config(obj))) == {
        "a": 1,
        "b": "default_b",
        "meta": {"k": "v", "nums": [1, 2, 3]},
    }


def test_asdict_parse_roundtrip_is_stable_with_plain_nested_extras():
    """``asdict(parse(asdict(x))) == asdict(x)`` for untyped plain-container extras.

    Extras are untyped by contract, so the parser restores them as plain data rather than
    typed configs; the invariant that holds is round-trip stability at the dict level.
    """
    obj = StrictlyTyped(a=1, meta={"k": "v", "nums": [1, 2, 3]})
    flat = asdict(obj)
    reparsed = parse_config(StrictlyTyped, flat)
    assert asdict(reparsed) == flat


def test_typed_nested_field_roundtrips_with_type_reconstruction():
    """The recommended pattern: a declared ``Type | None = None`` field round-trips as the real type.

    Unlike an (untyped) extra, a declared typed field carries the type information the parser
    needs, so ``parse_config`` reconstructs the nested config object (not just a dict), and the
    nested config keeps its own extras.
    """
    obj = ParentCfg(name="top", child=ChildCfg(a=2, x="extra"))
    dumped = asdict(obj)
    assert dumped == {"name": "top", "child": {"a": 2, "x": "extra"}}

    restored = parse_config(ParentCfg, dumped)
    assert isinstance(restored.child, ChildCfg)  # reconstructed as the real type, not a dict
    assert restored.child.a == 2
    assert restored.child.x == "extra"  # the nested config's own extras survive  # pylint: disable=E1101
    assert restored == obj


def test_typed_nested_field_defaults_to_none():
    """The ``Type | None = None`` field is optional and parses to ``None`` when omitted."""
    restored = parse_config(ParentCfg, {"name": "x"})
    assert restored.child is None


# --------------------------------------------------------------------------- #
# Frozen parity with mutable for copy / pickle / native helpers                #
# --------------------------------------------------------------------------- #
def test_frozen_copy_and_deepcopy_preserve_extras():
    """Shallow/deep copies of a frozen instance keep declared fields and extras."""
    obj = FrozenTyped(a=1, c="extra_c", d=(1, 2))
    assert copy.copy(obj) == obj
    assert copy.deepcopy(obj) == obj
    assert copy.deepcopy(obj).c == "extra_c"  # pylint: disable=E1101


def test_frozen_pickle_preserves_extras():
    """A frozen NonStrictDataclass survives a pickle round-trip with its extras."""
    obj = FrozenTyped(a=1, c="extra_c", d=3.14)
    restored = pickle.loads(pickle.dumps(obj))
    assert restored == obj
    assert restored._extras == {"c": "extra_c", "d": 3.14}  # pylint: disable=W0212


def test_frozen_native_helpers():
    """stdlib ``asdict``/``astuple``/``fields`` behave for the frozen variant too."""
    obj = FrozenTyped(a=1, c="extra_c")
    assert dc_asdict(obj)["_extras"] == {"c": "extra_c"}
    assert {"c": "extra_c"} in dc_astuple(obj)
    assert {"a", "b", "_extras", "_non_strict"} <= {f.name for f in fields(obj)}


# --------------------------------------------------------------------------- #
# Cross-variant nesting (mutable / frozen / plain)                             #
# --------------------------------------------------------------------------- #
def test_frozen_nested_in_mutable():
    """A frozen NonStrict nested (as declared field) inside a mutable one."""
    obj = Outer(name="o", inner=FrozenTyped(a=2, c="fx"))
    assert replace(obj, name="o2").inner.c == "fx"
    assert asdict(obj) == {"name": "o", "inner": {"a": 2, "b": "default_b", "c": "fx"}}


def test_mutable_nested_in_frozen():
    """A mutable NonStrict nested (as declared field) inside a frozen one."""
    obj = FrozenOuter(name="o", inner=StrictlyTyped(a=2, c="mx"))
    assert obj.inner.c == "mx"
    assert asdict(obj) == {"name": "o", "inner": {"a": 2, "b": "default_b", "c": "mx"}}


def test_plain_frozen_dataclass_nested_in_nonstrict():
    """A plain (non-NonStrict) frozen dataclass nests cleanly and survives replace."""
    obj = Outer(name="o", inner=PlainPoint(1, 2))
    assert replace(obj, name="o2").inner == PlainPoint(1, 2)
    assert asdict(obj) == {"name": "o", "inner": {"x": 1, "y": 2}}


def test_nonstrict_nested_in_plain_dataclass():
    """A NonStrict (with extras) nested inside a plain dataclass dumps cleanly."""

    @dataclass
    class PlainHolder:
        """A plain stdlib dataclass holding a NonStrict instance."""

        inner: Any = None

    obj = PlainHolder(inner=StrictlyTyped(a=1, c="x"))
    assert asdict(obj) == {"inner": {"a": 1, "b": "default_b", "c": "x"}}


def test_nested_replace_frozen_in_frozen():
    """Frozen-in-frozen nested replace preserves extras at both levels."""
    inner = FrozenTyped(a=2, c="ic")
    outer = FrozenOuter(name="o", inner=inner)
    r = replace(outer, inner=replace(inner, a=3))
    assert r.inner.a == 3
    assert r.inner.c == "ic"
    assert outer.inner.a == 2  # original untouched


# --------------------------------------------------------------------------- #
# Hashability parity                                                           #
# --------------------------------------------------------------------------- #
def test_mutable_nonstrict_is_unhashable():
    """The mutable variant is unhashable, matching a normal mutable dataclass."""
    with pytest.raises(TypeError):
        hash(StrictlyTyped(a=1, c="x"))
