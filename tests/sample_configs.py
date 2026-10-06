"""Shared sample config types for the round-trip and schema-agreement suites.

Not a test module. These live here rather than being duplicated per suite, and rather than becoming
fixtures, because both suites need them at *import* time to build their ``parametrize`` tables.

:func:`register_mixer` is the exception: it mutates the global registry, so it must run per test
alongside the ``reset_registry`` fixture rather than at import time.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, FrozenSet, List, Literal, Optional, Sequence, Set, Tuple, Union
from uuid import UUID

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface


class Color(Enum):
    """Sample enum: members whose values differ from their names, so by-name and by-value differ."""

    RED = "red"
    BLUE = "blue"


@dataclass
class Leaf:
    """Sample config with nothing but defaulted scalars."""

    a: int = 1
    b: str = "x"


@dataclass(frozen=True)
class Shape:
    """One annotation shape compoconf supports, with everything the suites need to exercise it.

    Both the round-trip suite and the schema-agreement suite enumerate the supported shapes, and
    they used to do so in two tables -- so adding a shape to one silently left the other blind to
    it. They share this one instead.

    Attributes:
        label: Test id.
        annotation: The annotation under test.
        examples: Inputs the round-trip suite feeds through parse -> dump -> parse -> dump. May
            include forms the JSON Schema does not describe (an enum by *name*, say), since
            parse_config is deliberately more accepting than the schema.
        accepted: Values ``to_json_schema`` must accept, and which must therefore also parse under
            ``strict_types=True`` and dump back to something the schema still accepts.
        rejected: Values ``to_json_schema`` must reject.
    """

    label: str
    annotation: Any
    examples: tuple = ()
    accepted: tuple = ()
    rejected: tuple = ()


_UUID = "12345678-1234-5678-1234-567812345678"

#: Every annotation shape the library supports, in one place.
SHAPES = [
    Shape("int", int, (7,), (0, -3, 7), ("5", 1.5, None, [], {})),
    Shape("float", float, (1.5,), (1.5, 0.0, 3), ("1.5", None, [])),
    Shape("str", str, ("s",), ("", "s"), (5, None, [])),
    Shape("bool", bool, (True,), (True, False), ("true", 1, None)),
    # both None and a present value have to survive the round trip
    Shape("optional-int", Optional[int], (None, 3), (3, None), ("3", 1.5)),
    Shape("literal", Literal["a", "b"], ("b",), ("a", "b"), ("c", 1, None)),
    # "BLUE" parses by member name, which the schema deliberately does not describe
    Shape("enum", Color, ("red", "BLUE"), ("red", "blue"), ("green", "RED", None)),
    Shape("path", Path, ("/tmp/x",), ("/tmp/x", "rel"), (5, None)),
    Shape("datetime", datetime, ("2020-01-02T03:04:05",), ("2020-01-02T03:04:05",), (5, None)),
    Shape("date", date, ("2020-01-02",), ("2020-01-02",), (5, None)),
    Shape("time", time, ("03:04:05",), ("03:04:05",), (5, None)),
    Shape("decimal", Decimal, ("1.25",), ("1.25",), (None,)),
    Shape("uuid", UUID, (_UUID,), (_UUID,), (5, None)),
    Shape(
        "dataclass",
        Leaf,
        ({"a": 2, "b": "y"},),
        ({}, {"a": 2}, {"a": 2, "b": "y"}),
        ({"a": "2"}, {"nope": 1}, None, []),
    ),
    Shape("list", list[int], ([1, 2],), ([], [1, 2]), (["1"], {}, None, 5)),
    Shape("typing-List", List[int], ([1, 2],), ([1],), (["x"],)),
    Shape("sequence", Sequence[int], ([1, 2],), ([1],), (["x"],)),
    Shape("list-of-dataclass", list[Leaf], ([{"a": 1}, {"a": 2}],), ([{"a": 1}],), ([{"nope": 1}],)),
    Shape("dict", dict[str, int], ({"k": 1},), ({}, {"k": 1}), ({"k": "1"}, [], None)),
    Shape("typing-Dict", Dict[str, int], ({"k": 1},), ({"k": 1},), ({"k": "1"},)),
    Shape("dict-of-dataclass", dict[str, Leaf], ({"k": {"a": 3}},), ({"k": {"a": 1}},), ({"k": {"nope": 1}},)),
    Shape("tuple-fixed", tuple[int, str], ([1, "a"],), ([1, "a"],), ([1], [1, "a", 2], ["1", "a"])),
    Shape("tuple-variadic", tuple[int, ...], ([1, 2, 3],), ([], [1, 2]), (["x"],)),
    Shape("typing-Tuple", Tuple[int], ([1],), ([1],), ([1, 2],)),
    Shape("tuple-of-dataclass", tuple[Leaf, Leaf], ([{"a": 1}, {"a": 2}],), ([{"a": 1}, {"a": 2}],), ([{"a": 1}],)),
    Shape("set", set[int], ([1, 2],), ([], [1, 2]), ([1, 1], ["x"], None)),
    Shape("typing-Set", Set[int], ([1, 2],), ([1],), ([1, 1],)),
    Shape("frozenset", frozenset[str], (["a", "b"],), (["a", "b"],), ([1], ["a", "a"])),
    Shape("typing-FrozenSet", FrozenSet[str], (["a"],), (["a"],), ([1],)),
    Shape("set-of-enum", set[Color], (["red", "blue"],), (["red", "blue"],), (["RED"], ["red", "red"])),
    Shape("union", Union[int, str], ("s",), (1, "s"), (None, [], 1.5)),
    Shape(
        "nested-containers", dict[str, list[Leaf]], ({"k": [{"a": 1}]},), ({"k": [{"a": 1}]},), ({"k": [{"nope": 1}]},)
    ),
    Shape("any", Any, ({"free": [1, "two"]},), (1, "s", None, [], {}), ()),
]


def register_mixer():
    """Register an interface with two implementations and return the pieces a test needs.

    Call from a fixture that also requests ``reset_registry``, so each test gets a clean registry.

    Returns:
        A namespace with ``interface``, ``attn_config`` and ``conv_config``.
    """

    @register_interface
    class Mixer(RegistrableConfigInterface):
        """The interface whose ``cfgtype`` union the tests annotate fields with."""

    @dataclass
    class AttnConfig(ConfigInterface):
        """Config of the first implementation."""

        heads: int = 8

    @register
    class Attn(Mixer):  # pylint: disable=W0612
        """First implementation."""

        config: AttnConfig

    @dataclass
    class ConvConfig(ConfigInterface):
        """Config of the second implementation, with a disjoint field set."""

        kernel: int = 3

    @register
    class Conv(Mixer):  # pylint: disable=W0612
        """Second implementation."""

        config: ConvConfig

    return SimpleNamespace(interface=Mixer, attn_config=AttnConfig, conv_config=ConvConfig)


def register_growing_mixer():
    """Register an interface with a *single* implementation, for late-registration tests.

    The point of these tests is that more implementations arrive after a plan has been cached, so
    unlike :func:`register_mixer` only the first one is registered here.

    Returns:
        A namespace with ``interface``, ``first_config`` and ``holder`` -- a dataclass whose one
        field is annotated with the interface's ``cfgtype`` union.
    """

    @register_interface
    class Mixer(RegistrableConfigInterface):
        """The interface implementations get added to during the test."""

    @dataclass
    class FirstConfig(ConfigInterface):
        """Config of the only implementation registered up front."""

        v: int = 1

    @register
    class First(Mixer):  # pylint: disable=W0612
        """The only implementation registered up front."""

        config: FirstConfig

    @dataclass
    class Holder:
        """Config with a field annotated by the interface's lazily resolved union."""

        impl: Mixer.cfgtype = None

    return SimpleNamespace(interface=Mixer, first_config=FirstConfig, holder=Holder)
