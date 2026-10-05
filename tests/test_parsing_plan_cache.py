"""Tests for the compiled-plan cache in :mod:`compoconf.parsing`.

Parsing compiles a reusable plan per type annotation, so these cover the things that caching makes
possible to get wrong: a plan outliving a registry change, a ``class_name`` index outliving a
rename, and the lazily rendered error messages.
"""

import copy
import pickle
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Literal, Optional, Sequence, Set, Tuple, Union

import pytest  # pylint: disable=E0401

try:
    from omegaconf import OmegaConf  # pylint: disable=E0401

    is_omegaconf_available = True
except ImportError:
    is_omegaconf_available = False

import compoconf.parsing as parsing_module
from compoconf.compoconf import (
    ConfigInterface,
    RegistrableConfigInterface,
    _EpochDict,
    register,
    register_interface,
    registry_epoch,
)
from compoconf.parsing import parse_config

# pylint: disable=C0115,C0116,W0212,W0621,W0613


@dataclass
class Simple:
    a: int = 1
    b: str = "x"


# ---------------------------------------------------------------------- lazily rendered messages


def test_parse_error_is_a_plain_value_error():
    """The deferred message must not leak a custom exception type to callers."""
    with pytest.raises(ValueError) as exc_info:
        parse_config(Simple, {"a": 1, "bogus": 2})
    assert type(exc_info.value) is ValueError  # pylint: disable=C0123
    assert "bogus" in str(exc_info.value)
    # rendering twice must be stable
    assert str(exc_info.value) == str(exc_info.value)


def test_parse_error_message_behaves_like_a_string():
    with pytest.raises(ValueError) as exc_info:
        parse_config(Simple, {"bogus": 2})
    message = exc_info.value.args[0]
    rendered = str(exc_info.value)
    assert message == rendered
    assert message.startswith("Undefined keys")
    assert "bogus" in message
    assert len(message) == len(rendered)
    assert repr(exc_info.value)
    assert hash(message) == hash(rendered)
    assert f"{exc_info.value}" == rendered


def test_parse_error_survives_pickle_and_copy():
    with pytest.raises(ValueError) as exc_info:
        parse_config(Simple, {"bogus": 2})
    error = exc_info.value
    assert str(pickle.loads(pickle.dumps(error))) == str(error)
    assert type(pickle.loads(pickle.dumps(error)).args[0]) is str  # pylint: disable=C0123
    assert str(copy.deepcopy(error)) == str(error)


def test_union_parse_error_message_is_rendered_lazily():
    with pytest.raises(ValueError) as exc_info:
        parse_config(Union[int, float], "nope")
    assert "Tried:" in str(exc_info.value)
    assert str(exc_info.value) == str(exc_info.value)


# ---------------------------------------------------------------------- cache invalidation


def test_late_registration_is_picked_up_by_cached_plans(reset_registry):
    @register_interface
    class Mixer(RegistrableConfigInterface):
        pass

    @dataclass
    class FirstConfig(ConfigInterface):
        v: int = 1

    @register
    class First(Mixer):  # pylint: disable=W0612
        config: FirstConfig

    @dataclass
    class Holder:
        impl: Mixer.cfgtype = None

    # compile and cache a plan for Holder (and for the cfgtype union) while only First exists
    assert parse_config(Holder, {"impl": {"class_name": "First", "v": 5}}).impl.v == 5
    assert parse_config(Mixer.cfgtype, {"class_name": "First"}).v == 1

    epoch_before = registry_epoch()

    @dataclass
    class SecondConfig(ConfigInterface):
        w: str = "x"

    @register
    class Second(Mixer):  # pylint: disable=W0612
        config: SecondConfig

    assert registry_epoch() != epoch_before

    # the cached plans must now see the new implementation, through both the field-level
    # class_name resolution and the union parser itself
    assert isinstance(parse_config(Holder, {"impl": {"class_name": "Second", "w": "y"}}).impl, SecondConfig)
    assert isinstance(parse_config(Mixer.cfgtype, {"class_name": "Second"}), SecondConfig)
    # ... without losing the one that was already there
    assert isinstance(parse_config(Holder, {"impl": {"class_name": "First"}}).impl, FirstConfig)


def test_registry_reset_invalidates_cached_unions(reset_registry):
    from compoconf.compoconf import Registry  # pylint: disable=C0415

    @register_interface
    class Thing(RegistrableConfigInterface):
        pass

    @dataclass
    class ThingConfig(ConfigInterface):
        v: int = 1

    @register
    class TheThing(Thing):  # pylint: disable=W0612
        config: ThingConfig

    @dataclass
    class Holder:
        impl: Thing.cfgtype = None

    assert parse_config(Holder, {"impl": {"class_name": "TheThing"}}).impl.v == 1

    for key in list(Registry._registries):
        Registry._registries.pop(key)

    with pytest.raises((ValueError, KeyError)):
        parse_config(Holder, {"impl": {"class_name": "TheThing"}})


def test_class_name_reassignment_is_picked_up(reset_registry):
    @dataclass
    class RenamedConfig(ConfigInterface):
        q: int = 0

    @dataclass
    class Holder:
        sub: Optional[RenamedConfig] = None

    RenamedConfig.class_name = "Alpha"
    assert parse_config(Holder, {"sub": {"class_name": "Alpha", "q": 1}}).sub.q == 1

    RenamedConfig.class_name = "Beta"
    assert parse_config(Holder, {"sub": {"class_name": "Beta", "q": 2}}).sub.q == 2
    with pytest.raises((ValueError, KeyError)):
        parse_config(Holder, {"sub": {"class_name": "Alpha"}})


def test_every_registry_mutation_bumps_the_epoch():
    """Plan invalidation hangs off the epoch, so no mutating ``dict`` method may skip the bump."""
    tracked = _EpochDict({"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6})
    mutations = [
        lambda: tracked.__setitem__("x", 0),
        lambda: tracked.__delitem__("a"),
        tracked.popitem,
        lambda: tracked.pop("b"),
        lambda: tracked.update({"y": 0}),
        lambda: tracked.setdefault("z", 0),
        tracked.clear,
    ]
    for mutate in mutations:
        before = registry_epoch()
        mutate()
        assert registry_epoch() != before, mutate


def test_dataclass_instance_is_not_a_usable_annotation():
    """An unhashable annotation cannot be cached; it must still fail the way it always did."""

    @dataclass
    class Mutable:
        a: int = 1

    with pytest.raises(TypeError):
        parse_config(Mutable(), {"a": 2})


def test_clear_parse_cache_keeps_parsing_correct():
    # read through the module: an existing test reloads compoconf.parsing, which rebinds the cache
    assert parse_config(Simple, {"a": 2}).a == 2
    assert parsing_module._PLAN_CACHE
    parsing_module.clear_parse_cache()
    assert not parsing_module._PLAN_CACHE
    assert parse_config(Simple, {"a": 3}).a == 3
    assert parsing_module._PLAN_CACHE


def test_unhashable_annotation_still_parses():
    """An annotation that cannot be a cache key is compiled fresh instead of blowing up."""

    class Unhashable:
        __hash__ = None  # type: ignore[assignment]

    with pytest.raises(TypeError, match="Invalid type"):
        parse_config(Unhashable(), "anything")


def test_plan_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(parsing_module, "_PLAN_CACHE_LIMIT", 2)
    parsing_module.clear_parse_cache()
    for annotation, value in ((int, 1), (float, 1.0), (str, "s"), (bool, True), (bytes, b"x")):
        assert parse_config(annotation, value) == value
    assert len(parsing_module._PLAN_CACHE) <= 2
    parsing_module.clear_parse_cache()


def test_strict_flag_propagates_and_does_not_leak_between_plans():
    @dataclass
    class Outer:
        inner: Simple = field(default_factory=Simple)
        items: list[Simple] = field(default_factory=list)
        mapping: dict[str, Simple] = field(default_factory=dict)

    # strict=False reaches nested configs, through fields, lists and dict values alike
    relaxed = parse_config(
        Outer,
        {
            "inner": {"a": 1, "junk": 2},
            "items": [{"a": 2, "junk": 3}],
            "mapping": {"k": {"a": 3, "junk": 4}},
            "junk": 5,
        },
        strict=False,
    )
    assert (relaxed.inner.a, relaxed.items[0].a, relaxed.mapping["k"].a) == (1, 2, 3)

    # the strict=True plan must be a separate one, not the relaxed plan from the call above
    with pytest.raises(ValueError, match="Undefined keys"):
        parse_config(Outer, {"inner": {"a": 1}, "junk": 2})
    with pytest.raises(ValueError, match="Undefined keys"):
        parse_config(Outer, {"inner": {"a": 1, "junk": 2}})


def test_default_factory_is_not_invoked_to_test_for_a_default():
    """Deciding whether a field is required must not run the user's factory."""
    calls = []

    def factory():
        calls.append(1)
        return []

    @dataclass
    class WithFactory:
        present: int = 0
        absent: list = field(default_factory=factory)

    for _ in range(5):
        assert parse_config(WithFactory, {"present": 1}).absent == []
    # exactly one call per parse, all of them from the dataclass __init__ filling the field in
    assert len(calls) == 5


def test_annotation_on_a_non_dataclass_base_counts_as_a_required_key():
    """An annotation-only attribute on a plain mixin is seen by get_type_hints but is not a field.

    Long-standing behaviour, pinned rather than endorsed: the class supplies no value for it, so it
    is reported as a required key -- and supplying it then fails in the constructor, because it is
    not an init parameter. Such a config simply cannot be parsed either way.
    """

    class Mixin:
        hint_only: int  # annotated, never assigned, and not a dataclass field

    @dataclass
    class WithMixin(Mixin):
        a: int = 1

    with pytest.raises(ValueError, match="hint_only"):
        parse_config(WithMixin, {"a": 1})
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        parse_config(WithMixin, {"a": 1, "hint_only": 2})


def test_field_shadowing_an_inherited_attribute_is_rejected():
    """A field named after an inherited method silently defaults to that method; reject it."""

    @dataclass
    class ShadowsMethod(ConfigInterface):
        instantiate: int  # no default written, but ConfigInterface.instantiate exists

    with pytest.raises(TypeError, match="shadows the inherited attribute"):
        parse_config(ShadowsMethod, {})


def test_field_shadowing_with_an_explicit_default_is_allowed():
    """Writing a default in the class body is deliberate, whatever name it shadows."""

    @dataclass
    class Deliberate(ConfigInterface):
        instantiate: int = 5

    assert parse_config(Deliberate, {}).instantiate == 5
    assert parse_config(Deliberate, {"instantiate": 7}).instantiate == 7


def test_inherited_dataclass_fields_are_not_mistaken_for_shadowing():
    """``class_name`` and ordinary inherited fields have real defaults, not shadowed ones."""

    @dataclass
    class Base:
        a: int = 1
        b: list = field(default_factory=list)

    @dataclass
    class Derived(Base):
        c: int = 3

    assert parse_config(Derived, {"a": 9}) == Derived(9, [], 3)

    @dataclass
    class Registered(ConfigInterface):
        v: int = 1

    assert parse_config(Registered, {"v": 2}).class_name == ""


def test_required_fields_are_still_detected_around_defaults():
    @dataclass
    class Mixed:
        needed: int
        with_factory: list = field(default_factory=list)
        with_default: int = 3

    assert parse_config(Mixed, {"needed": 1}) == Mixed(1, [], 3)
    with pytest.raises(ValueError, match="needed"):
        parse_config(Mixed, {})


# ---------------------------------------------------------------------- None handling per shape


@dataclass
class Target:
    x: int = 0


NON_OPTIONAL_ANNOTATIONS = [
    int,
    float,
    str,
    bool,
    bytes,
    Literal["a", "b"],
    Target,
    list[int],
    List[int],
    Sequence[int],
    set[int],
    Set[int],
    frozenset[int],
    FrozenSet[int],
    tuple[int, str],
    tuple[int, ...],
    Tuple[int],
    dict[str, int],
    Dict[str, int],
    Union[int, str],
    list,  # untyped container: still must reject None rather than crash
    dict,
    tuple,
    set,
]


@pytest.mark.parametrize("annotation", NON_OPTIONAL_ANNOTATIONS)
def test_none_is_rejected_for_non_optional_annotations(annotation):
    with pytest.raises(ValueError, match="Tried to parse None"):
        parse_config(annotation, None)


@pytest.mark.parametrize("annotation", NON_OPTIONAL_ANNOTATIONS)
def test_none_is_accepted_when_wrapped_in_optional(annotation):
    assert parse_config(Optional[annotation], None) is None


@pytest.mark.parametrize(
    "annotation",
    [
        Any,
        Optional[Any],
        Union[int, None],
        list[Any],
        set[Any],
        frozenset[Any],
        dict[str, Any],
        tuple[Any, ...],
        tuple[Any, str],
        dict[Any],  # type: ignore[misc]  # wrong arity on purpose: shape rejected, None is not
        Literal[Any],
        Callable[..., Any],
    ],
)
def test_none_is_accepted_for_any_bearing_annotations(annotation):
    """``Any`` anywhere in an annotation's unwrapping makes ``None`` a valid value."""
    assert parse_config(annotation, None) is None


@pytest.mark.parametrize(
    ("annotation", "message"),
    [
        (list, "Expected list"),
        (set, "Expected set"),
        (tuple, "Expected tuple or list"),
        (dict, "Dict type must have exactly 2 type arguments"),
    ],
)
def test_untyped_containers_report_shape_before_arity(annotation, message):
    """An untyped container still complains about the value's shape first (as it always has)."""
    with pytest.raises(ValueError, match=message):
        parse_config(annotation, "nope")


def test_untyped_containers_reject_right_shaped_values():
    with pytest.raises(ValueError, match="List type must have exactly 1 type argument"):
        parse_config(list, [1])
    with pytest.raises(ValueError, match="Set type must have exactly 1 type argument"):
        parse_config(set, {1})
    with pytest.raises(ValueError, match="Tuple type must have type arguments"):
        parse_config(tuple, (1,))


def test_literal_mismatch_raises_invalid_type():
    with pytest.raises(TypeError, match="Invalid type"):
        parse_config(Literal["a", "b"], "c")


def test_tuple_of_types_annotation_acts_as_an_isinstance_check():
    """A bare tuple of types is not a supported annotation, but it never has been rejected."""
    assert parse_config((int, str), 5) == 5
    with pytest.raises(TypeError, match="Invalid type"):
        parse_config((int, str), [])


def test_handle_bool_helper_accepts_native_bools():
    from compoconf.parsing import _handle_bool  # pylint: disable=C0415

    assert _handle_bool(True) is True
    assert _handle_bool(" FALSE ") is False
    with pytest.raises(ValueError, match="Could not parse"):
        _handle_bool(1)


def test_is_literal_instance_helper_handles_nested_literals():
    from compoconf.parsing import _is_literal_instance  # pylint: disable=C0415

    assert _is_literal_instance("a", Literal["a", "b"])
    assert not _is_literal_instance("c", Literal["a", "b"])
    assert _is_literal_instance(5, Literal[int])  # a type member matches by isinstance
    assert not _is_literal_instance("x", object())  # unusable annotation -> no match


@pytest.mark.skipif(not is_omegaconf_available, reason="OmegaConf not available")
def test_class_name_discriminator_is_read_from_a_dict_config(reset_registry):
    @register_interface
    class Iface(RegistrableConfigInterface):
        pass

    @dataclass
    class ImplConfig(ConfigInterface):
        v: int = 1

    @register
    class Impl(Iface):  # pylint: disable=W0612
        config: ImplConfig

    @dataclass
    class Holder:
        impl: Iface.cfgtype = None

    data = OmegaConf.create({"impl": {"class_name": "Impl", "v": 7}})
    assert parse_config(Holder, data).impl.v == 7


def test_any_annotation_passes_values_through():
    sentinel = object()
    assert parse_config(Any, sentinel) is sentinel


def test_variadic_tuple_and_set_key_history_in_errors():
    @dataclass
    class Holder:
        many: tuple[int, ...] = ()
        uniq: set[int] = field(default_factory=set)

    with pytest.raises(ValueError, match=r"many\.1"):
        parse_config(Holder, {"many": [1, "nope"]})
    with pytest.raises(ValueError, match=r"uniq\.0"):
        parse_config(Holder, {"uniq": ["nope"]})
    with pytest.raises(ValueError, match="Expected tuple or list"):
        parse_config(Holder, {"many": "nope"})


def test_class_name_substring_in_scalar_values_is_not_a_discriminator():
    """A string/list value that merely contains ``class_name`` is ordinary data."""

    @dataclass
    class Named:
        label: str = ""
        items: list[str] = field(default_factory=list)

    parsed = parse_config(Named, {"label": "my_class_name_here", "items": ["class_name"]})
    assert parsed.label == "my_class_name_here"
    assert parsed.items == ["class_name"]


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
