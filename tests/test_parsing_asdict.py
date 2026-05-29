"""
Parsing Tests for CompoConf.
"""

from dataclasses import dataclass, field

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface
from compoconf.parsing import parse_config


# pylint: disable=C0115,C0116,W0212,W0621,W0613
def test_parse_config_with_non_strict_dataclass():
    """Test parse_config with NonStrictDataclass and extra fields."""
    from compoconf.nonstrict_dataclass import NonStrictDataclass  # pylint: disable=C0415

    @dataclass(init=False)
    class MyNonStrictConfig(NonStrictDataclass):
        typed_field: int
        default_field: str = "default"

    # Data with typed fields and extra untyped fields
    data_with_extras = {
        "typed_field": 123,
        "default_field": "overridden",
        "extra_field_1": "some_value",
        "extra_field_2": 456,
    }

    # Test parsing with strict=True (should still allow extras due to _non_strict)
    parsed_strict = parse_config(MyNonStrictConfig, data_with_extras, strict=True)
    assert isinstance(parsed_strict, MyNonStrictConfig)
    assert parsed_strict.typed_field == 123
    assert parsed_strict.default_field == "overridden"
    # Check that extra fields are accessible as attributes
    assert parsed_strict.extra_field_1 == "some_value"
    assert parsed_strict.extra_field_2 == 456
    # Check that extra fields are stored in _extras
    assert parsed_strict._extras == {"extra_field_1": "some_value", "extra_field_2": 456}

    # Test parsing with strict=False (should also allow extras)
    parsed_non_strict = parse_config(MyNonStrictConfig, data_with_extras, strict=False)
    assert isinstance(parsed_non_strict, MyNonStrictConfig)
    assert parsed_non_strict.typed_field == 123
    assert parsed_non_strict.default_field == "overridden"
    assert parsed_non_strict.extra_field_1 == "some_value"
    assert parsed_non_strict.extra_field_2 == 456
    assert parsed_non_strict._extras == {"extra_field_1": "some_value", "extra_field_2": 456}

    # Test parsing with only typed fields
    data_typed_only = {"typed_field": 789}
    parsed_typed_only = parse_config(MyNonStrictConfig, data_typed_only)
    assert isinstance(parsed_typed_only, MyNonStrictConfig)
    assert parsed_typed_only.typed_field == 789
    assert parsed_typed_only.default_field == "default"
    assert parsed_typed_only._extras == {}

    # Test parsing with missing required field (should raise error)
    data_missing_required = {"default_field": "value"}
    with pytest.raises(TypeError):
        parse_config(MyNonStrictConfig, data_missing_required)

    # Test parsing with extra fields that are not in _extras (should be handled by NonStrictDataclass __init__)
    # The _handle_dataclass logic in parsing.py should correctly pass these to the NonStrictDataclass constructor.
    # The NonStrictDataclass constructor then assigns them to attributes and stores them in _extras.
    # So, the above tests already cover this implicitly.


def test_parse_nonstrict_nested_typed():
    """Test checking that dataclasses are still resolved for parsing in the NonStrict case"""
    from compoconf.nonstrict_dataclass import NonStrictDataclass  # pylint: disable=C0415

    @dataclass(init=False)
    class Inner(NonStrictDataclass):
        b: int = 2

    @dataclass(init=False)
    class Outer(NonStrictDataclass):
        a: int = 1
        b: Inner = field(default_factory=Inner)

    cfg = parse_config(Outer, {"a": 2, "b": {"b": 3}})
    assert isinstance(cfg.b, Inner)
    assert cfg.b.b == 3
    assert cfg.a == 2


def test_nonstrict_dataclass_parsing():
    from compoconf.nonstrict_dataclass import NonStrictDataclass  # pylint: disable=C0415
    from compoconf.nonstrict_dataclass import asdict  # pylint: disable=C0415

    @dataclass(init=False)
    class Inner(NonStrictDataclass):
        pass

    @dataclass(kw_only=True)
    class Outer(ConfigInterface):
        inner: Inner = field(default_factory=Inner)

    cfg = parse_config(Outer, {"inner": {"a": 1}})
    assert asdict(cfg) == {"class_name": "", "inner": {"a": 1}}


def test_standard_asdict_parsing():
    from dataclasses import asdict  # pylint: disable=C0415

    from compoconf.nonstrict_dataclass import NonStrictDataclass  # pylint: disable=C0415

    @dataclass(init=False)
    class Inner(NonStrictDataclass):
        pass

    @dataclass(kw_only=True)
    class Outer(ConfigInterface):
        inner: Inner = field(default_factory=Inner)

    base_dict = asdict(Outer(inner=Inner(a=1)))
    base_dict_ref = {"class_name": "", "inner": {"_extras": {"a": 1}, "_non_strict": True}}
    assert base_dict == base_dict_ref

    cfg = parse_config(Outer, base_dict)
    # check immutability
    assert base_dict["inner"]["_extras"]["a"] == 1
    # check correct dataclass composition
    assert cfg.inner.a == 1
    # check if asdict results in same base dict ref again
    assert asdict(cfg) == base_dict_ref


def test_own_asdict_parsing():
    from compoconf.nonstrict_dataclass import NonStrictDataclass  # pylint: disable=C0415
    from compoconf.nonstrict_dataclass import asdict  # pylint: disable=C0415

    @dataclass(init=False)
    class Inner(NonStrictDataclass):
        pass

    @dataclass(kw_only=True)
    class Outer(ConfigInterface):
        inner: Inner = field(default_factory=Inner)

    base_dict_ref = {"class_name": "", "inner": {"a": 1}}
    cfg = parse_config(Outer, base_dict_ref)
    assert asdict(cfg) == base_dict_ref


def test_roundtrips_asdict_matrix():
    """Round-trip idempotence for both serializers on a nested NonStrictDataclass tree.

    For X in {stdlib dataclasses.asdict, custom compoconf asdict}:
      - serialize-first: X(parse(X(obj)))      == X(obj)
      - parse-first:     parse(X(parse(dict))) == parse(dict)   (object equality)
    """
    from dataclasses import asdict as stdlib_asdict  # pylint: disable=C0415

    from compoconf.nonstrict_dataclass import NonStrictDataclass  # pylint: disable=C0415
    from compoconf.nonstrict_dataclass import asdict as custom_asdict  # pylint: disable=C0415

    @dataclass(init=False)
    class Inner(NonStrictDataclass):
        kept: int = 9
        tup: tuple[int, str] = (1, "a")

    @dataclass(init=False)
    class Mid(NonStrictDataclass):
        sub: Inner = field(default_factory=Inner)
        n: int = 0

    @dataclass(kw_only=True)
    class Outer(ConfigInterface):
        mid: Mid = field(default_factory=Mid)

    # nested NonStrict-in-NonStrict-in-strict, extras of mixed types at both levels
    obj = Outer(
        mid=Mid(
            n=2,
            sub=Inner(kept=1, tup=(5, "z"), e_int=3, e_str="s", e_list=[1, 2], e_dict={"k": 3}, e_tup=(2, 3)),
            e_top=[9, 8],
        )
    )

    for name, serialize in (("custom_asdict", custom_asdict), ("stdlib_asdict", stdlib_asdict)):
        dumped = serialize(obj)

        # serialize -> parse -> serialize  is stable
        assert serialize(parse_config(Outer, dumped)) == dumped, f"{name}: serialize round-trip not idempotent"

        # parse -> serialize -> parse  is stable (object equality)
        obj_a = parse_config(Outer, dumped)
        obj_b = parse_config(Outer, serialize(obj_a))
        assert obj_a == obj_b, f"{name}: parse round-trip not idempotent"


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
