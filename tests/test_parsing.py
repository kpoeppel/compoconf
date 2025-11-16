"""
Parsing Tests for CompoConf.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Literal, Optional, Set, Tuple, Union

import pytest  # pylint: disable=E0401

try:
    from omegaconf import OmegaConf

    is_omegaconf_available = True
except ImportError:
    is_omegaconf_available = False

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, Registry, register, register_interface
from compoconf.parsing import dump_config, parse_config


# pylint: disable=C0115,C0116,W0212,W0621,W0613
@pytest.fixture
def reset_registry():
    """Reset the registry before each test."""
    for reg in list(Registry._registries):
        Registry._registries.pop(reg)
    for reg in list(Registry._registry_classes):
        Registry._registry_classes.pop(reg)
    yield


# Tests for configuration parsing


def test_configuration_parsing(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        pass

    @register
    class TestClass(TestInterface):
        config: TestConfig

    @dataclass
    class TestConfig2(ConfigInterface):
        pass

    @register
    class TestClass2(TestInterface):
        config: TestConfig2

    @dataclass
    class TestConfigAggregation3:
        interface: TestInterface.cfgtype

    config = {"interface": {"class_name": "TestClass"}}

    cfg = parse_config(TestConfigAggregation3, config)
    assert isinstance(cfg.interface, TestConfig)
    assert isinstance(cfg.interface.instantiate(TestInterface), TestClass)

    config = {"interface": {"class_name": "TestClass2"}}

    cfg = parse_config(TestConfigAggregation3, config)
    assert isinstance(cfg.interface, TestConfig2)
    assert isinstance(cfg.interface.instantiate(TestInterface), TestClass2)


def test_configuration_parsing_extended(reset_registry):
    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @register_interface
    class TestInterface2(TestInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        a: int = 1
        b: str = "test"

    @register
    class TestClass(TestInterface):
        config: TestConfig

    @dataclass
    class TestConfig2(TestConfig):
        a: int = 2
        c: str = "test2"

    @register
    class TestClass2(TestInterface2):
        config: TestConfig2

    @dataclass
    class TestConfigAggregation3:
        interface: TestInterface.cfgtype

    config = {"interface": {"class_name": "TestClass"}}

    cfg = parse_config(TestConfigAggregation3, config)
    assert isinstance(cfg.interface, TestConfig)
    assert isinstance(cfg.interface.instantiate(TestInterface), TestClass)

    config = {"interface": {"class_name": "TestClass2", "a": 3}}

    cfg = parse_config(TestConfigAggregation3, config)
    assert isinstance(cfg.interface, TestConfig2)
    assert isinstance(cfg.interface.instantiate(TestInterface), TestClass2)

    @dataclass
    class TestConfigAggregation4(ConfigInterface):
        submodule: TestInterface2.cfgtype

    @register
    class TestClass4(TestInterface):  # pylint: disable=W0612
        config: TestConfigAggregation4

        def __init__(self, config: TestConfigAggregation4):
            super().__init__(config)
            self.config = config
            self.submodule = self.config.submodule.instantiate(TestInterface2)

    with pytest.raises(KeyError, match="Cannot resolve dataclass"):
        config = {"submodule": {"class_name": "TestClass"}}
        cfg = parse_config(TestConfigAggregation4, config)


def test_parse_config_none():
    assert parse_config(None, None) is None
    with pytest.raises(ValueError):
        parse_config(None, "not none")


def test_parse_config_none_dataclass():
    @dataclass
    class TestConfig:
        a: int = 1

    with pytest.raises(ValueError):
        parse_config(TestConfig, None)


def test_parse_config_dataclass_in_dataclass():
    @dataclass
    class TestConfig:
        a: int = 1

    assert parse_config(TestConfig, TestConfig(a=2)) == TestConfig(a=2)


def test_parse_config_invalid_type():
    with pytest.raises(TypeError):
        parse_config("not a type", {})


def test_parse_none_str():
    @dataclass
    class TestConfig:
        val: Optional[str] = "abc"

    cfg = parse_config(TestConfig, {"val": None})

    assert cfg.val is None


def test_parse_config_collections(reset_registry):
    @dataclass
    class InnerConfig:
        value: int

    # Test Dict (both typing.Dict and dict)
    data_dict = {"key1": {"value": 1}, "key2": {"value": 2}}

    # Test with typing.Dict
    result = parse_config(Dict[str, InnerConfig], data_dict)
    assert isinstance(result, dict)
    assert isinstance(result["key1"], InnerConfig)
    assert result["key1"].value == 1

    # Test with dict[]
    result = parse_config(dict[str, InnerConfig], data_dict)
    assert isinstance(result, dict)
    assert isinstance(result["key1"], InnerConfig)
    assert result["key1"].value == 1

    # Test invalid dict input
    with pytest.raises(ValueError):
        parse_config(Dict[str, InnerConfig], "not a dict")

    # Test Dict without type args
    with pytest.raises(ValueError):
        parse_config(Dict, data_dict)

    # Test List (both typing.List and list)
    data_list = [{"value": 1}, {"value": 2}, {"value": 3}]

    # Test with typing.List
    result = parse_config(List[InnerConfig], data_list)
    assert isinstance(result, list)
    assert len(result) == 3
    assert isinstance(result[0], InnerConfig)

    # Test with list[]
    result = parse_config(list[InnerConfig], data_list)
    assert isinstance(result, list)
    assert len(result) == 3
    assert isinstance(result[0], InnerConfig)

    # Test invalid list input
    with pytest.raises(ValueError):
        parse_config(List[InnerConfig], "not a list")

    # Test List without type args
    with pytest.raises(ValueError):
        parse_config(List, data_list)

    # Test Tuple (both typing.Tuple and tuple)
    data_tuple = ({"value": 1}, {"value": 2})

    # Test with typing.Tuple
    result = parse_config(Tuple[InnerConfig, InnerConfig], data_tuple)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], InnerConfig)

    # Test with tuple[]
    result = parse_config(tuple[InnerConfig, InnerConfig], data_tuple)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], InnerConfig)

    # Test invalid tuple input
    with pytest.raises(ValueError):
        parse_config(Tuple[InnerConfig, InnerConfig], [{"value": 1}])  # Wrong length

    # Test Tuple without type args
    with pytest.raises(ValueError):
        parse_config(Tuple, data_tuple)


def test_parse_config_sets():
    # Test parsing into sets
    result = parse_config(Set[int], ["1", 2, 3])
    assert result == {1, 2, 3}

    result = parse_config(set[int], [1, 2, 2])
    assert result == {1, 2}

    # Test parsing into frozensets
    result = parse_config(FrozenSet[str], ["a", "b"])
    assert result == frozenset({"a", "b"})

    result = parse_config(frozenset[str], ("x", "y"))
    assert result == frozenset({"x", "y"})

    with pytest.raises(ValueError, match="Expected set"):
        parse_config(Set[int], "not a set")

    with pytest.raises(ValueError, match="Set type must have exactly 1 type argument"):
        parse_config(Set, [1, 2])

    with pytest.raises(ValueError, match="0"):
        parse_config(Set[int], ["not_int"])


def test_parse_config_union_types(reset_registry):
    @dataclass
    class Config1:
        value: int

    @dataclass
    class Config2:
        text: str

    # Test with typing.Union
    UnionType = Union[Config1, Config2]

    # Test parsing into first union option
    data1 = {"value": 42}
    result1 = parse_config(UnionType, data1)
    assert isinstance(result1, Config1)
    assert result1.value == 42

    # Test parsing into second union option
    data2 = {"text": "hello"}
    result2 = parse_config(UnionType, data2)
    assert isinstance(result2, Config2)
    assert result2.text == "hello"

    # Test parsing failure
    with pytest.raises(ValueError):
        parse_config(UnionType, {"invalid": "data"})

    # Test Union without type args
    with pytest.raises(ValueError):
        parse_config(Union, data1)  # pylint: disable=E1131

    # Test with | syntax (Python 3.10+)
    try:
        UnionTypePipe = Config1 | Config2  # pylint: disable=E1131

        # Test parsing into first union option
        result1 = parse_config(UnionTypePipe, data1)
        assert isinstance(result1, Config1)
        assert result1.value == 42

        # Test parsing into second union option
        result2 = parse_config(UnionTypePipe, data2)
        assert isinstance(result2, Config2)
        assert result2.text == "hello"

        # Test parsing failure
        with pytest.raises(ValueError):
            parse_config(UnionTypePipe, {"invalid": "data"})
    except TypeError:
        # Skip | syntax tests if running on Python < 3.10
        pass


def test_parse_config_edge_cases(reset_registry):
    # Test parsing primitive types
    assert parse_config(int, 42) == 42
    assert parse_config(str, "hello") == "hello"

    # Test invalid primitive type conversion
    with pytest.raises(ValueError):
        parse_config(int, "not an int")

    # Test invalid type
    with pytest.raises(TypeError):
        parse_config(object(), 42)

    with pytest.raises(ValueError):
        parse_config(tuple[int, str], "abc")

    with pytest.raises(TypeError):
        parse_config("abc", "abc")

    assert parse_config(Literal["abc"], "abc") == "abc"


def test_parse_bool_handling():
    @dataclass
    class BoolConfig:
        flag: bool

    assert parse_config(bool, True) is True
    assert parse_config(bool, " true ") is True
    assert parse_config(BoolConfig, {"flag": False}).flag is False
    assert parse_config(BoolConfig, {"flag": "FALSE"}).flag is False


def test_parse_bool_error_contains_key_history():
    @dataclass
    class InnerConfig:
        flag: bool

    @dataclass
    class OuterConfig:
        inner: InnerConfig

    with pytest.raises(ValueError, match="inner.flag"):
        parse_config(OuterConfig, {"inner": {"flag": "not_bool"}})


def test_parse_bool_invalid_input():
    with pytest.raises(ValueError, match="Could not parse 1"):
        parse_config(bool, 1)


def test_parse_config_empty_key_path():
    result = parse_config(Dict[str, int], {"": 1})
    assert result[""] == 1


def test_parsing_without_omegaconf(monkeypatch):
    import importlib  # pylint: disable=C0415
    import sys  # pylint: disable=C0415
    import types  # pylint: disable=C0415

    original_omegaconf = sys.modules.get("omegaconf", None)
    original_parsing = sys.modules.pop("compoconf.parsing", None)

    fake_module = types.ModuleType("omegaconf")
    monkeypatch.setitem(sys.modules, "omegaconf", fake_module)

    parsing_module = importlib.import_module("compoconf.parsing")
    assert parsing_module.ListConfig is list

    # restore environment
    if original_omegaconf is not None:
        sys.modules["omegaconf"] = original_omegaconf
    else:
        sys.modules.pop("omegaconf", None)

    sys.modules.pop("compoconf.parsing", None)
    if original_parsing is not None:
        sys.modules["compoconf.parsing"] = original_parsing
        importlib.reload(original_parsing)


def test_parse_config_bad_class_name(reset_registry):
    """Test error when class_name in data doesn't match config_class.class_name."""

    @dataclass
    class TestConfig(ConfigInterface):
        value: int = 42

    # Set class_name manually
    TestConfig.class_name = "CorrectClassName"

    # Try to parse with a different class_name
    with pytest.raises(ValueError, match="Bad data.*match"):
        parse_config(TestConfig, {"class_name": "WrongClassName", "value": 100})


@pytest.mark.skipif(not is_omegaconf_available, reason="OmegaConf not available")
def test_omega_conf(reset_registry):
    @dataclass
    class ConfigClass:
        abc: int = 234

    dc = OmegaConf.create({"abc": 123})
    co = parse_config(ConfigClass, dc)
    assert co.abc == 123

    lc = OmegaConf.create([12, 23])
    co = parse_config(list[int], lc)
    assert lc == [12, 23]


def test_parse_config_primitive_conversion_error():
    """Test error handling in parse_config for primitive type conversion."""
    # Test conversion error for primitive types
    with pytest.raises(ValueError, match="Could not convert"):
        parse_config(int, "not an int")

    # Test with a non-type object
    class NotAType:
        pass

    obj = NotAType()
    with pytest.raises(TypeError, match="Invalid type"):
        parse_config(obj, "test")


# Tests for dump_config function


def test_basic_dump(reset_registry):
    """Test basic dumping of a dataclass to a dictionary."""

    @dataclass
    class SimpleConfig:
        a: int = 1
        b: str = "test"
        c: float = 3.14

    config = SimpleConfig(a=42, b="hello", c=2.71)
    dumped = dump_config(config)

    assert isinstance(dumped, dict)
    assert dumped["a"] == 42
    assert dumped["b"] == "hello"
    assert dumped["c"] == 2.71


def test_nested_dump(reset_registry):
    """Test dumping of nested dataclasses."""

    @dataclass
    class InnerConfig:
        x: int = 10
        y: str = "inner"

    @dataclass
    class OuterConfig:
        name: str = "outer"
        inner: InnerConfig = field(default_factory=InnerConfig)

    config = OuterConfig(name="test", inner=InnerConfig(x=20, y="nested"))
    dumped = dump_config(config)

    assert isinstance(dumped, dict)
    assert dumped["name"] == "test"
    assert isinstance(dumped["inner"], dict)
    assert dumped["inner"]["x"] == 20
    assert dumped["inner"]["y"] == "nested"


def test_collection_dump(reset_registry):
    """Test dumping of collections (lists, dicts)."""

    @dataclass
    class ItemConfig:
        id: int
        name: str

    @dataclass
    class CollectionConfig:
        items: List[ItemConfig]
        mapping: Dict[str, ItemConfig]

    items = [ItemConfig(1, "one"), ItemConfig(2, "two")]
    mapping = {"a": ItemConfig(3, "three"), "b": ItemConfig(4, "four")}
    config = CollectionConfig(items=items, mapping=mapping)

    dumped = dump_config(config)

    assert isinstance(dumped, dict)
    assert isinstance(dumped["items"], list)
    assert len(dumped["items"]) == 2
    assert isinstance(dumped["items"][0], dict)
    assert dumped["items"][0]["id"] == 1
    assert dumped["items"][0]["name"] == "one"

    assert isinstance(dumped["mapping"], dict)
    assert isinstance(dumped["mapping"]["a"], dict)
    assert dumped["mapping"]["a"]["id"] == 3
    assert dumped["mapping"]["a"]["name"] == "three"


def test_config_interface_dump(reset_registry):
    """Test dumping of ConfigInterface instances."""

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        value: int = 42
        name: str = "test"

    @register
    class TestClass(TestInterface):  # pylint: disable=W0612
        config: TestConfig

    config = TestConfig(value=100, name="dumped")
    dumped = dump_config(config)

    assert isinstance(dumped, dict)
    assert dumped["value"] == 100
    assert dumped["name"] == "dumped"
    assert dumped["class_name"] == "TestClass"


def test_roundtrip_conversion(reset_registry):
    """Test round-trip conversion: parse_config -> dump_config -> parse_config."""

    @dataclass
    class ComplexConfig:
        name: str
        values: List[int]
        nested: Dict[str, Dict[str, int]]

    original_data = {
        "name": "test",
        "values": [1, 2, 3],
        "nested": {"a": {"x": 10, "y": 20}, "b": {"x": 30, "y": 40}},
    }

    # First parse
    parsed = parse_config(ComplexConfig, original_data)
    assert isinstance(parsed, ComplexConfig)

    # Then dump
    dumped = dump_config(parsed)
    assert isinstance(dumped, dict)

    # Then parse again
    reparsed = parse_config(ComplexConfig, dumped)
    assert isinstance(reparsed, ComplexConfig)

    # Verify the round-trip preserved all data
    assert reparsed.name == original_data["name"]
    assert reparsed.values == original_data["values"]
    assert reparsed.nested == original_data["nested"]


def test_registry_roundtrip(reset_registry):
    """Test round-trip conversion with registry classes."""

    @register_interface
    class TestInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class TestConfig(ConfigInterface):
        value: int = 42

    @register
    class TestClass(TestInterface):
        config: TestConfig

    @dataclass
    class ContainerConfig:
        interface: TestInterface.cfgtype

    # Create original config
    original_data = {"interface": {"class_name": "TestClass", "value": 100}}

    # Parse
    parsed = parse_config(ContainerConfig, original_data)
    assert isinstance(parsed.interface, TestConfig)
    assert parsed.interface.value == 100

    # Dump
    dumped = dump_config(parsed)
    assert isinstance(dumped, dict)
    assert isinstance(dumped["interface"], dict)
    assert dumped["interface"]["class_name"] == "TestClass"
    assert dumped["interface"]["value"] == 100

    # Parse again
    reparsed = parse_config(ContainerConfig, dumped)
    assert isinstance(reparsed.interface, TestConfig)
    assert reparsed.interface.value == 100

    # Instantiate from reparsed
    instance = reparsed.interface.instantiate(TestInterface)
    assert isinstance(instance, TestClass)


def test_primitive_types():
    """Test dumping of primitive types."""
    # Primitive types should be returned as-is
    assert dump_config(42) == 42
    assert dump_config("hello") == "hello"
    assert dump_config(3.14) == 3.14
    assert dump_config(True) is True

    # Lists of primitives
    assert dump_config([1, 2, 3]) == [1, 2, 3]

    # Dictionaries of primitives
    assert dump_config({"a": 1, "b": "test"}) == {"a": 1, "b": "test"}

    # Nested structures
    nested = {"a": [1, 2, {"b": "test"}]}
    assert dump_config(nested) == nested


def test_parse_compositional_types_edge_cases():
    """Test edge cases in _parse_compositional_types."""
    from compoconf.parsing import _parse_compositional_types  # pylint: disable=C0415

    # Test dict with invalid data (not a dict-like object)
    with pytest.raises(ValueError, match="Expected dict"):
        _parse_compositional_types(dict, (str, int), "not a dict")

    # Test dict without type args
    with pytest.raises(ValueError, match="Dict type must have exactly 2 type arguments"):
        _parse_compositional_types(dict, None, {})

    # Test dict with wrong number of type args
    with pytest.raises(ValueError, match="Dict type must have exactly 2 type arguments"):
        _parse_compositional_types(dict, (str,), {})

    # Create a dict-like object with items method
    class DictLike:
        def __init__(self, data):
            self.data = data

        def items(self):
            return self.data.items()

    # Test with dict-like object
    dict_like = DictLike({"key": "value"})
    result = _parse_compositional_types(dict, (str, str), dict_like)
    assert result == {"key": "value"}


def test_parse_compositional_types_list_tuple():
    """Test _parse_compositional_types with list and tuple types."""
    from compoconf.parsing import _parse_compositional_types  # pylint: disable=C0415

    # Test list with invalid data
    with pytest.raises(ValueError, match="Expected list"):
        _parse_compositional_types(list, (int,), "not a list")

    # Test list without type args
    with pytest.raises(ValueError, match="List type must have exactly 1 type argument"):
        _parse_compositional_types(list, None, [1, 2, 3])

    # Test with Sequence type (should behave like list)
    from typing import Sequence  # pylint: disable=C0415

    result = _parse_compositional_types(Sequence, (int,), [1, 2, 3])
    assert result == [1, 2, 3]

    # Test tuple with invalid data
    with pytest.raises(ValueError, match="Expected tuple or list"):
        _parse_compositional_types(tuple, (int, str), "not a tuple")

    # Test tuple without type args
    with pytest.raises(ValueError, match="Tuple type must have type arguments"):
        _parse_compositional_types(tuple, None, (1, "a"))

    # Test tuple with ellipsis
    result = _parse_compositional_types(tuple, (int, Ellipsis), [1, 2, 3])
    assert result == (1, 2, 3)

    # Test tuple with wrong length
    with pytest.raises(ValueError, match="Expected 2 items, got 3"):
        _parse_compositional_types(tuple, (int, str), [1, "a", 3])


def test_parse_compositional_types_unsupported_origin():
    """Test _parse_compositional_types with an unsupported origin type."""
    from compoconf.parsing import _parse_compositional_types  # pylint: disable=C0415

    # Create a custom type that's not dict, list, or tuple
    class CustomType:
        pass

    # This should return None since CustomType is not a supported origin
    result = _parse_compositional_types(CustomType, (int,), "data")
    assert result is None


def test_get_all_annotations():
    """Test _get_all_annotations function."""
    from compoconf.parsing import _get_all_annotations  # pylint: disable=C0415

    @dataclass
    class TestAnnotations:
        a: int
        b: str

    annotations = _get_all_annotations(TestAnnotations)
    assert "a" in annotations
    assert annotations["a"] is int
    assert "b" in annotations
    assert annotations["b"] is str


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
    assert asdict(cfg) == {"class_name": "", "inner": {"a": 1, "_non_strict": True}}


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

    base_dict_ref = {"class_name": "", "inner": {"a": 1, "_non_strict": True}}
    cfg = parse_config(Outer, base_dict_ref)
    assert asdict(cfg) == base_dict_ref


if __name__ == "__main__":
    test_standard_asdict_parsing()


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
