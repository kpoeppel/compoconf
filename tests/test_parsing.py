"""
Parsing Tests for CompoConf.
"""

from dataclasses import MISSING, dataclass, field
from typing import Dict, FrozenSet, List, Literal, Optional, Set, Tuple, TypedDict, Union

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


def test_unset_key_parsing():
    @dataclass
    class TestClass5:
        a: int
        b: int = 3

    with pytest.raises(ValueError):
        parse_config(TestClass5, {"b": 4})


def test_unset_key_field_parsing():
    @dataclass
    class TestClass7:
        b: int = field(default=MISSING)
        a: dict[str, int] = field(default_factory=dict)
        c: int = field(default=3)

    cfg = parse_config(TestClass7, {"a": {"b": 4}, "b": 4})
    assert cfg.a == {"b": 4}
    assert cfg.b == 4

    with pytest.raises(ValueError):
        parse_config(TestClass7, {"a": {"b": 4}})

    cfg = parse_config(TestClass7, {"b": 4})
    assert cfg.b == 4

    with pytest.raises(ValueError):
        parse_config(TestClass7, {})

    with pytest.raises(ValueError):
        parse_config(TestClass7, {"a": {"b": 4}, "b": 2, "d": 3})


def test_typed_dict_parsing():
    class MyTypedDict(TypedDict):
        a: int

    assert parse_config(MyTypedDict, {"a": 3}) == {"a": 3}

    with pytest.raises(ValueError):
        parse_config(MyTypedDict, {})


def test_typed_dict_empty_parsing():
    @dataclass
    class TestClass6:
        a: int = 1

    class MyTypedDictEmpty(TypedDict):
        pass

    assert parse_config(MyTypedDictEmpty, {}) == {}
    cfg = parse_config(MyTypedDictEmpty | TestClass6, {"a": 2})
    assert isinstance(cfg, TestClass6)
    assert cfg.a == 2

    cfg = parse_config(MyTypedDictEmpty | TestClass6, {})
    assert isinstance(cfg, dict)
    assert cfg == {}


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


def test_union_parse_error_shows_details(reset_registry):
    """Test that Union parse failure shows per-option errors with class_name match first."""

    @dataclass
    class AlphaConfig(ConfigInterface):
        alpha_field: int = 1

    @dataclass
    class BetaConfig(ConfigInterface):
        beta_field: str = "b"

    # Set class_name manually (normally done by @register)
    AlphaConfig.class_name = "Alpha"
    BetaConfig.class_name = "Beta"

    ConfigUnion = Union[AlphaConfig, BetaConfig]

    # Wrong field name for Alpha — error should show AlphaConfig first (class_name match)
    with pytest.raises(ValueError, match="Tried:") as exc_info:
        parse_config(ConfigUnion, {"class_name": "Alpha", "wrong_field": 99})

    error_msg = str(exc_info.value)
    # In the "Tried:" section, AlphaConfig should appear before BetaConfig (class_name matched)
    tried_section = error_msg.split("Tried:")[1]
    assert tried_section.index("AlphaConfig") < tried_section.index("BetaConfig")
    # The actual field error is visible
    assert "wrong_field" in error_msg


def test_union_parse_error_no_class_name(reset_registry):
    """Test Union parse failure when data has no class_name."""

    @dataclass
    class Config1:
        value: int

    @dataclass
    class Config2:
        text: str

    with pytest.raises(ValueError, match="Tried:") as exc_info:
        parse_config(Union[Config1, Config2], {"invalid": "data"})

    error_msg = str(exc_info.value)
    assert "Config1" in error_msg
    assert "Config2" in error_msg


def test_union_parse_error_class_name_no_match(reset_registry):
    """Test error when class_name doesn't match ANY option — no option is prioritized."""

    @dataclass
    class AlphaConfig(ConfigInterface):
        alpha_field: int = 1

    @dataclass
    class BetaConfig(ConfigInterface):
        beta_field: str = "b"

    AlphaConfig.class_name = "Alpha"
    BetaConfig.class_name = "Beta"

    ConfigUnion = Union[AlphaConfig, BetaConfig]

    with pytest.raises(ValueError, match="Tried:") as exc_info:
        parse_config(ConfigUnion, {"class_name": "NoSuchClass", "x": 1})

    error_msg = str(exc_info.value)
    # Both options shown, neither prioritized
    assert "AlphaConfig" in error_msg
    assert "BetaConfig" in error_msg


def test_union_parse_error_with_pipe_syntax():
    """Test error messages with Python 3.10+ pipe union syntax."""

    @dataclass
    class Cfg1:
        a: int

    @dataclass
    class Cfg2:
        b: str

    with pytest.raises(ValueError, match="Tried:") as exc_info:
        parse_config(Cfg1 | Cfg2, {"wrong": True})

    error_msg = str(exc_info.value)
    assert "Cfg1" in error_msg
    assert "Cfg2" in error_msg


def test_union_parse_error_non_dict_data():
    """Test error when data is not a dict (no .get('class_name') available)."""

    with pytest.raises(ValueError, match="Tried:") as exc_info:
        parse_config(Union[int, float], "not_a_number")

    error_msg = str(exc_info.value)
    assert "int" in error_msg
    assert "float" in error_msg


def test_union_parse_error_nested_key_history():
    """Test that key_history propagates into the Union error."""

    @dataclass
    class Inner1:
        x: int

    @dataclass
    class Inner2:
        y: str

    @dataclass
    class Outer:
        child: Union[Inner1, Inner2]

    with pytest.raises(ValueError, match="child") as exc_info:
        parse_config(Outer, {"child": {"bad_key": True}})

    error_msg = str(exc_info.value)
    assert "Tried:" in error_msg
    assert "Inner1" in error_msg
    assert "Inner2" in error_msg


def test_union_parse_error_with_lazy_config_union(reset_registry):
    """Test error messages when parsing through a LazyConfigUnion."""
    from compoconf.compoconf import LazyConfigUnion  # pylint: disable=C0415

    @register_interface
    class MixerInterface(RegistrableConfigInterface):
        pass

    @dataclass
    class ConvConfig(ConfigInterface):
        kernel: int = 3

    @register
    class Conv(MixerInterface):  # pylint: disable=W0612
        config: ConvConfig

    @dataclass
    class AttnConfig(ConfigInterface):
        heads: int = 8

    @register
    class Attn(MixerInterface):  # pylint: disable=W0612
        config: AttnConfig

    lazy = MixerInterface.cfgtype
    assert isinstance(lazy, LazyConfigUnion)

    # Parse directly with LazyConfigUnion — wrong field
    with pytest.raises(ValueError, match="Tried:") as exc_info:
        parse_config(lazy, {"class_name": "Conv", "bad_field": 99})

    error_msg = str(exc_info.value)
    # In the "Tried:" section, ConvConfig should appear first (class_name match)
    tried_section = error_msg.split("Tried:")[1]
    assert tried_section.index("ConvConfig") < tried_section.index("AttnConfig")
    assert "bad_field" in error_msg


def test_union_parse_error_shortest_first():
    """Test that among non-class_name-matched options, shorter errors come first."""

    @dataclass
    class SmallConfig:
        a: int

    @dataclass
    class BigConfig:
        field_one: int
        field_two: str
        field_three: float

    # Neither has class_name set, so sorting falls back to error length.
    # SmallConfig has fewer fields → shorter error message about missing 'a'.
    # BigConfig has more unset fields → longer error message.
    with pytest.raises(ValueError, match="Tried:") as exc_info:
        parse_config(Union[BigConfig, SmallConfig], {"wrong": True})

    error_msg = str(exc_info.value)
    # Check ordering in the "Tried:" section (after the header which lists types in Union order)
    tried_section = error_msg.split("Tried:")[1]
    assert tried_section.index("SmallConfig") < tried_section.index("BigConfig")


if __name__ == "__main__":
    test_unset_key_field_parsing()


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
