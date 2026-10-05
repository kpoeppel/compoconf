"""Tests for the package's public surface and the contract its output obeys.

Two things a release should not change by accident: what ``compoconf`` exports, and the set of value
types a dump may contain.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import pytest  # pylint: disable=E0401

# sibling helper module; mypy does not know pytest puts the tests directory on sys.path
from sample_configs import SHAPES, Color  # type: ignore[import-not-found]  # pylint: disable=E0401

import compoconf

try:
    import yaml  # type: ignore[import-untyped]  # pylint: disable=E0401
except ImportError:  # pragma: no cover - PyYAML is an optional test dependency
    yaml = None  # type: ignore[assignment]

# pylint: disable=C0115,C0116,W0212,W0621,W0613


# Every name the package promises. Adding to this list is a feature; removing from it or renaming is
# a breaking change, and this test is here to make that deliberate rather than accidental.
EXPECTED_EXPORTS = {
    "ConfigError",
    "ConfigInterface",
    "FrozenNonStrictDataclass",
    "LazyConfigUnion",
    "LiteralError",
    "MissingValue",
    "NonStrictDataclass",
    "RegistrableConfigInterface",
    "Registry",
    "asdict",
    "assert_check_literals",
    "assert_check_nonmissing",
    "clear_parse_cache",
    "dump_config",
    "from_annotations",
    "load",
    "make_dataclass_picklable",
    "parse_config",
    "parse_file",
    "partial_call",
    "register",
    "register_interface",
    "registered",
    "to_json_schema",
    "validate_literal_field",
}


def test_all_matches_the_expected_surface():
    assert set(compoconf.__all__) == EXPECTED_EXPORTS


def test_every_exported_name_is_importable():
    """``__all__`` entries that do not resolve break ``from compoconf import *`` silently."""
    missing = [name for name in compoconf.__all__ if not hasattr(compoconf, name)]
    assert not missing, f"listed in __all__ but not present: {missing}"


def test_all_has_no_duplicates():
    assert len(compoconf.__all__) == len(set(compoconf.__all__))


def test_version_is_exposed_and_well_formed():
    """``__init__.__version__`` is the single source the build reads, so it has to be parseable.

    Deliberately not compared against ``importlib.metadata.version``: that reports whatever copy is
    installed, which says nothing about the source tree and fails loudly on a stale install.
    """
    assert re.fullmatch(
        r"\d+\.\d+\.\d+(?:[.\-]?(?:a|b|rc|dev|post)\d+)?", compoconf.__version__
    ), f"not a PEP 440 release version: {compoconf.__version__!r}"


# ---------------------------------------------------------------------- the dump value contract

# JSON and YAML can represent exactly these. A dump that contains anything else cannot be written
# out, which is the whole point of dumping -- so this is the invariant the dump side has to hold,
# and the one that tuples and sets each violated in turn.
SERIALIZABLE_TYPES = (type(None), bool, int, float, str, list, dict)


def _assert_only_serializable_types(value, path="<root>"):
    assert isinstance(value, SERIALIZABLE_TYPES), f"{path} is {type(value).__name__}, which JSON/YAML cannot represent"
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), f"{path} has a non-string key {key!r} ({type(key).__name__})"
            _assert_only_serializable_types(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_only_serializable_types(item, f"{path}[{index}]")


@dataclass
class EveryKind:  # pylint: disable=R0902
    """One field per supported value kind, so a dump has to flatten all of them at once.

    Having many attributes is the point: the test is that *every* kind flattens, together.
    """

    i: int = 1
    f: float = 1.5
    s: str = "x"
    b: bool = True
    nothing: Optional[int] = None
    items: list[int] = field(default_factory=lambda: [1, 2])
    mapping: dict[str, int] = field(default_factory=lambda: {"k": 1})
    pair: tuple[int, str] = (1, "a")
    variadic: tuple[int, ...] = (1, 2)
    unique: set[int] = field(default_factory=lambda: {2, 1})
    frozen: frozenset[str] = field(default_factory=lambda: frozenset({"b", "a"}))
    color: Color = Color.RED
    where: Path = Path("/a")
    when: datetime = datetime(2020, 1, 2, 3, 4, 5)
    day: date = date(2020, 1, 2)
    clock: time = time(3, 4, 5)
    amount: Decimal = Decimal("1.5")
    ident: UUID = UUID("12345678-1234-5678-1234-567812345678")
    whatever: Any = None


def test_a_dumped_config_contains_only_json_yaml_value_types():
    dumped = compoconf.dump_config(EveryKind())
    _assert_only_serializable_types(dumped)
    assert json.dumps(dumped)
    if yaml is not None:
        assert yaml.safe_dump(dumped)


def test_asdict_obeys_the_same_contract():
    """A value must dump to the same kinds whichever entry point reached it."""
    config = EveryKind()
    assert compoconf.asdict(config) == compoconf.dump_config(config)
    _assert_only_serializable_types(compoconf.asdict(config))


@pytest.mark.parametrize("shape", SHAPES, ids=[s.label for s in SHAPES])
def test_every_supported_shape_dumps_to_serializable_types(shape):
    for data in shape.examples:
        _assert_only_serializable_types(compoconf.dump_config(compoconf.parse_config(shape.annotation, data)))


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
