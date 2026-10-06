"""
Parsing Tests for CompoConf.
"""

import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface
from compoconf.nonstrict_dataclass import asdict
from compoconf.parsing import dump_config, parse_config

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

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
    # a tuple dumps as a list, since JSON and YAML have a single array type
    assert dump_config((ItemConfig(3),)) == [{"class_name": "", "a": 3}]
    # arbitrary nesting of mappings and sequences
    assert dump_config({"k": [ItemConfig(4), {"j": (ItemConfig(5),)}]}) == {
        "k": [{"class_name": "", "a": 4}, {"j": [{"class_name": "", "a": 5}]}]
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


def test_dump_config_turns_sets_into_sorted_lists(reset_registry):
    """Sets have no JSON form of their own; the annotation is what makes them sets again."""

    @dataclass
    class WithSets:
        tags: set[str] = field(default_factory=set)
        ids: frozenset[int] = field(default_factory=frozenset)

    config = WithSets(tags={"c", "a", "b"}, ids=frozenset({3, 1, 2}))
    assert dump_config(config) == {"tags": ["a", "b", "c"], "ids": [1, 2, 3]}
    # asdict has to agree, or a value's dumped form depends on how it was reached
    assert asdict(config) == dump_config(config)
    # and bare sets, which dump_config also accepts
    assert dump_config({3, 1, 2}) == [1, 2, 3]
    assert dump_config(frozenset({"b", "a"})) == ["a", "b"]
    assert dump_config({"k": {2, 1}}) == {"k": [1, 2]}
    assert json.dumps(dump_config(config))


def test_set_dump_sorts_elements_after_converting_them(reset_registry):
    """It is the written form that has to be ordered, not the in-memory one."""

    class Grade(Enum):
        HIGH = "a"
        LOW = "z"
        MID = "m"

    @dataclass
    class WithEnums:
        grades: set[Grade] = field(default_factory=set)

    dumped = dump_config(WithEnums(grades={Grade.LOW, Grade.HIGH, Grade.MID}))
    assert dumped == {"grades": ["a", "m", "z"]}  # sorted by value, not by member name


def test_set_dump_of_unorderable_elements_is_still_deterministic():
    """Mutually incomparable values cannot be sorted naturally, but must still have a fixed order."""
    mixed = dump_config({1, "a", 2.5})
    assert sorted(mixed, key=repr) == mixed
    assert set(mixed) == {1, "a", 2.5}
    # repeating the dump gives the same order
    assert dump_config({1, "a", 2.5}) == mixed


def test_set_dump_is_identical_under_different_hash_seeds(tmp_path):
    """The reason for sorting: str hashing is randomized, so an unsorted dump would differ per run."""
    script = tmp_path / "dump_once.py"
    script.write_text(
        "import json\n"
        "from compoconf import dump_config\n"
        "print(json.dumps(dump_config({'alpha', 'beta', 'gamma', 'delta', 'epsilon'})))\n",
        encoding="utf-8",
    )
    outputs = set()
    for seed in ("0", "1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(SRC)}
        result = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, check=True, env=env, cwd=str(tmp_path)
        )
        outputs.add(result.stdout.strip())
    assert len(outputs) == 1, f"dump differs across hash seeds: {outputs}"
    assert outputs.pop() == '["alpha", "beta", "delta", "epsilon", "gamma"]'


def test_dump_config_turns_tuples_into_lists_keeping_their_order(reset_registry):
    """A tuple's order is meaningful, so unlike a set it is emitted as-is -- just as a list."""

    @dataclass
    class WithTuples:
        dims: tuple[int, int] = (1, 1)
        many: tuple[str, ...] = ()

    config = WithTuples(dims=(2, 3), many=("z", "a"))
    assert dump_config(config) == {"dims": [2, 3], "many": ["z", "a"]}
    assert asdict(config) == dump_config(config)
    assert dump_config((1, 2)) == [1, 2]
    assert dump_config({"k": (1, 2)}) == {"k": [1, 2]}
    # the dump is now a fixed point through a file, which it was not while tuples stayed tuples
    yaml = pytest.importorskip("yaml")
    dumped = dump_config(config)
    assert yaml.safe_load(yaml.safe_dump(dumped)) == dumped
    assert json.loads(json.dumps(dumped)) == dumped
    assert parse_config(WithTuples, dumped) == config


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
