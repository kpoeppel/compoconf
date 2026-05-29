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

if __name__ == "__main__":
    test_unset_key_field_parsing()


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
