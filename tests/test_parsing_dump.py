"""
Parsing Tests for CompoConf.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface
from compoconf.parsing import dump_config, parse_config

# pylint: disable=C0115,C0116,W0212,W0621,W0613

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


def test_dump_config_recurses_into_sequences(reset_registry):
    """A top-level list/tuple of configs must be dumped, not handed back as raw objects."""

    @dataclass
    class ItemConfig(ConfigInterface):
        a: int = 1

    assert dump_config([ItemConfig(1), ItemConfig(2)]) == [{"class_name": "", "a": 1}, {"class_name": "", "a": 2}]
    # tuples stay tuples, matching asdict
    assert dump_config((ItemConfig(3),)) == ({"class_name": "", "a": 3},)
    # arbitrary nesting of mappings and sequences
    assert dump_config({"k": [ItemConfig(4), {"j": (ItemConfig(5),)}]}) == {
        "k": [{"class_name": "", "a": 4}, {"j": ({"class_name": "", "a": 5},)}]
    }
    # the result is JSON-serializable, which it was not before
    assert json.dumps(dump_config([ItemConfig(1)]))


def test_dump_config_does_not_treat_strings_as_sequences():
    assert dump_config("hello") == "hello"
    assert dump_config(["a", "b"]) == ["a", "b"]
    assert dump_config(b"xy") == b"xy"
    assert dump_config(bytearray(b"xy")) == bytearray(b"xy")


def test_dump_config_round_trips_a_list_of_configs(reset_registry):
    @dataclass
    class Point:
        x: int = 0
        y: int = 0

    points = [Point(1, 2), Point(3, 4)]
    assert parse_config(List[Point], dump_config(points)) == points


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
