"""Round-trip tests: ``parse_config`` and ``dump_config``/``asdict`` must agree.

The two directions are written independently, so they drift apart silently -- a dumped config that
is not re-parseable, or not serializable at all, only fails much later at the point of writing a
file. These walk every supported annotation shape and assert the full cycle:

    data -> parse -> dump -> parse -> dump

with the two parsed values equal, the two dumps equal (so dumping is idempotent), and every dump
accepted by both ``json.dumps`` and ``yaml.safe_dump``.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Literal, Optional, Sequence, Set, Tuple, Union
from uuid import UUID

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface
from compoconf.nonstrict_dataclass import NonStrictDataclass, asdict
from compoconf.parsing import dump_config, parse_config

# pylint: disable=C0115,C0116,W0212,W0621,W0613


class Color(Enum):
    RED = "red"
    BLUE = "blue"


@dataclass
class Leaf:
    a: int = 1
    b: str = "x"


SHAPES = [
    # (label, annotation, input data)
    ("int", int, 7),
    ("float", float, 1.5),
    ("str", str, "s"),
    ("bool", bool, True),
    ("none", Optional[int], None),
    ("optional-value", Optional[int], 3),
    ("literal", Literal["a", "b"], "b"),
    ("enum-by-value", Color, "red"),
    ("enum-by-name", Color, "BLUE"),
    ("path", Path, "/tmp/x"),
    ("datetime", datetime, "2020-01-02T03:04:05"),
    ("date", date, "2020-01-02"),
    ("time", time, "03:04:05"),
    ("decimal", Decimal, "1.25"),
    ("uuid", UUID, "12345678-1234-5678-1234-567812345678"),
    ("dataclass", Leaf, {"a": 2, "b": "y"}),
    ("list", list[int], [1, 2]),
    ("typing-List", List[int], [1, 2]),
    ("sequence", Sequence[int], [1, 2]),
    ("list-of-dataclass", list[Leaf], [{"a": 1}, {"a": 2}]),
    ("dict", dict[str, int], {"k": 1}),
    ("typing-Dict", Dict[str, int], {"k": 1}),
    ("dict-of-dataclass", dict[str, Leaf], {"k": {"a": 3}}),
    ("tuple-fixed", tuple[int, str], [1, "a"]),
    ("tuple-variadic", tuple[int, ...], [1, 2, 3]),
    ("typing-Tuple", Tuple[int], [1]),
    ("tuple-of-dataclass", tuple[Leaf, Leaf], [{"a": 1}, {"a": 2}]),
    ("union", Union[int, str], "s"),
    ("nested-containers", dict[str, list[Leaf]], {"k": [{"a": 1}]}),
    ("any", Any, {"free": [1, "two"]}),
]

# Sets dump as live set/frozenset objects, which neither json nor yaml can represent, so the cycle
# cannot complete. parse_config already accepts an array for a set annotation and to_json_schema
# already declares one, so only the dump side disagrees. Marked strict so that fixing the dump turns
# these green and flags the markers for removal.
SET_SHAPES = [
    ("set", set[int], [1, 2]),
    ("typing-Set", Set[int], [1, 2]),
    ("frozenset", frozenset[str], ["a", "b"]),
    ("typing-FrozenSet", FrozenSet[str], ["a"]),
    ("set-in-dataclass", "set-field", None),
]


def _assert_serializable(dumped):
    yaml = pytest.importorskip("yaml")
    json.dumps(dumped)
    yaml.safe_dump(dumped)


def _assert_round_trips(annotation, data):
    """parse -> dump -> parse -> dump, with both halves agreeing and both dumps serializable."""
    first = parse_config(annotation, data)
    dumped = dump_config(first)
    _assert_serializable(dumped)

    second = parse_config(annotation, dumped)
    assert second == first, f"value changed across the round trip: {first!r} -> {second!r}"
    assert type(second) is type(first)  # pylint: disable=C0123

    redumped = dump_config(second)
    assert redumped == dumped, f"dumping is not idempotent: {dumped!r} -> {redumped!r}"
    _assert_serializable(redumped)


@pytest.mark.parametrize(("label", "annotation", "data"), SHAPES, ids=[s[0] for s in SHAPES])
def test_round_trip(label, annotation, data):
    _assert_round_trips(annotation, data)


@pytest.mark.parametrize(("label", "annotation", "data"), SET_SHAPES, ids=[s[0] for s in SET_SHAPES])
@pytest.mark.xfail(strict=True, reason="sets dump as live set objects; json/yaml cannot represent them")
def test_round_trip_of_sets(label, annotation, data):
    if label == "set-in-dataclass":

        @dataclass
        class WithSet:
            tags: set[str] = field(default_factory=set)

        annotation, data = WithSet, {"tags": ["a", "b"]}
    _assert_round_trips(annotation, data)


def test_sets_parse_from_an_array_even_though_they_do_not_dump_to_one():
    """The parse side of the contract already holds; this is the half that works."""
    assert parse_config(set[str], ["a", "b"]) == {"a", "b"}
    assert parse_config(frozenset[int], [1, 2]) == frozenset({1, 2})


# ---------------------------------------------------------------------- whole-config round trips
#
# The interface and its implementations are built per test rather than at import time: other test
# modules reset the registry through the ``reset_registry`` fixture, which would wipe module-level
# registrations before these tests ever run.


@pytest.fixture
def stack(reset_registry):
    """A realistic config tree: cfgtype unions, enums, extension scalars, containers."""

    @register_interface
    class Mixer(RegistrableConfigInterface):
        pass

    @dataclass
    class AttnConfig(ConfigInterface):
        heads: int = 8
        scale: float = 1.0

    @register
    class Attn(Mixer):  # pylint: disable=W0612
        config: AttnConfig

    @dataclass
    class ConvConfig(ConfigInterface):
        kernel: int = 3

    @register
    class Conv(Mixer):  # pylint: disable=W0612
        config: ConvConfig

    @dataclass
    class Block:
        mixer: Mixer.cfgtype = None
        name: str = "block"
        color: Color = Color.RED
        out: Optional[Path] = None

    @dataclass
    class Stack:
        blocks: list[Block] = field(default_factory=list)
        dims: tuple[int, int] = (1, 1)
        labels: dict[str, str] = field(default_factory=dict)
        when: Optional[datetime] = None

    return Stack


STACK_DATA = {
    "blocks": [
        {"mixer": {"class_name": "Attn", "heads": 4}, "name": "b0", "color": "blue", "out": "/tmp/a"},
        {"mixer": {"class_name": "Conv", "kernel": 5}, "name": "b1", "color": "red"},
    ],
    "dims": [2, 3],
    "labels": {"x": "1"},
    "when": "2020-01-02T03:04:05",
}


def test_whole_config_round_trips(stack):
    _assert_round_trips(stack, STACK_DATA)


def test_dumped_config_keeps_the_discriminator(stack):
    """class_name has to survive the dump, or the union cannot be resolved on the way back."""
    dumped = dump_config(parse_config(stack, STACK_DATA))
    assert [block["mixer"]["class_name"] for block in dumped["blocks"]] == ["Attn", "Conv"]


def test_round_trip_through_a_json_file(stack, tmp_path):
    from compoconf import parse_file  # pylint: disable=C0415

    path = tmp_path / "config.json"
    path.write_text(json.dumps(dump_config(parse_config(stack, STACK_DATA))), encoding="utf-8")
    assert parse_file(stack, path) == parse_config(stack, STACK_DATA)


def test_round_trip_through_a_yaml_file(stack, tmp_path):
    yaml = pytest.importorskip("yaml")
    from compoconf import parse_file  # pylint: disable=C0415

    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(dump_config(parse_config(stack, STACK_DATA))), encoding="utf-8")
    assert parse_file(stack, path) == parse_config(stack, STACK_DATA)


def test_dump_config_of_a_list_of_whole_configs(stack):
    configs = [parse_config(stack, STACK_DATA), parse_config(stack, STACK_DATA)]
    dumped = dump_config(configs)
    _assert_serializable(dumped)
    assert parse_config(list[stack], dumped) == configs


def test_non_strict_extras_round_trip():
    @dataclass(init=False)
    class Loose(NonStrictDataclass):
        known: int = 0

    parsed = parse_config(Loose, {"known": 1, "extra": "kept", "nested": {"still": "plain"}})
    dumped = asdict(parsed)
    _assert_serializable(dumped)
    assert dumped["extra"] == "kept"
    reparsed = parse_config(Loose, dumped)
    assert reparsed.known == 1
    assert reparsed.extra == "kept"
    assert asdict(reparsed) == dumped


def test_top_level_scalars_dump_like_asdict():
    """dump_config and asdict must agree, or a value's dumped form depends on where it sat."""
    values = [Color.RED, Path("/a"), datetime(2020, 1, 2), date(2020, 1, 2), time(3, 4), Decimal("1.5")]
    for value in values:
        assert dump_config(value) == asdict(value)
    # and inside a plain container, which is what dump_config is documented to take
    assert dump_config({"c": Color.RED, "p": Path("/a")}) == {"c": "red", "p": "/a"}
    assert dump_config([Color.BLUE]) == ["blue"]
    _assert_serializable(dump_config({"c": Color.RED, "p": Path("/a")}))


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
