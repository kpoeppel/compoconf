"""
Tests for ``enum.Enum`` support in parsing and serialization.

Enums parse from an existing member, a member *name*, or a member *value*, and serialize back to
their value (so configs round-trip and stay JSON/YAML friendly).
"""

import enum
import json
from dataclasses import dataclass
from typing import Optional

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface
from compoconf.nonstrict_dataclass import asdict
from compoconf.parsing import dump_config, parse_config


class Color(enum.Enum):
    """A plain Enum with string values (name != value)."""

    RED = "red"
    GREEN = "green"


class Level(enum.IntEnum):
    """An IntEnum to check int-valued enums."""

    LOW = 1
    HIGH = 2


@dataclass
class Cfg(ConfigInterface):
    """Config carrying enum fields, including an optional one."""

    color: Color = Color.RED
    level: Level = Level.LOW
    maybe: Optional[Color] = None


# --------------------------------------------------------------------------- #
# Parsing                                                                      #
# --------------------------------------------------------------------------- #
def test_parse_enum_by_name():
    """A string matching a member name resolves to that member."""
    assert parse_config(Color, "RED") is Color.RED


def test_parse_enum_by_value():
    """A member value resolves to that member."""
    assert parse_config(Color, "green") is Color.GREEN


def test_parse_enum_member_passthrough():
    """An existing enum member is returned unchanged."""
    assert parse_config(Color, Color.RED) is Color.RED


def test_parse_enum_invalid_raises():
    """An unknown name/value raises ValueError listing the valid options."""
    with pytest.raises(ValueError) as exc:
        parse_config(Color, "purple")
    msg = str(exc.value)
    assert "Color" in msg
    assert "RED" in msg  # names listed
    assert "red" in msg  # values listed


def test_parse_intenum_by_value_and_name():
    """IntEnum members parse from both their int value and their name."""
    assert parse_config(Level, 2) is Level.HIGH
    assert parse_config(Level, "HIGH") is Level.HIGH


def test_parse_enum_in_dataclass_field():
    """Enum-typed dataclass fields parse (by name or value)."""
    cfg = parse_config(Cfg, {"color": "GREEN", "level": "HIGH"})
    assert cfg.color is Color.GREEN
    assert cfg.level is Level.HIGH


def test_parse_optional_enum_union():
    """An ``Enum | None`` field parses a member or stays ``None`` when omitted."""
    assert parse_config(Cfg, {"maybe": "RED"}).maybe is Color.RED
    assert parse_config(Cfg, {"color": "RED"}).maybe is None


def test_parse_enum_with_strict_types():
    """Enum parsing is unaffected by ``strict_types`` (it is not scalar coercion)."""
    assert parse_config(Color, "RED", strict_types=True) is Color.RED
    assert parse_config(Cfg, {"color": "GREEN"}, strict_types=True).color is Color.GREEN


# --------------------------------------------------------------------------- #
# Serialization                                                                #
# --------------------------------------------------------------------------- #
def test_asdict_serializes_enum_to_value():
    """``asdict`` converts enum members to their value."""
    cfg = Cfg(color=Color.GREEN, level=Level.HIGH, maybe=Color.RED)
    d = asdict(cfg)
    assert d["color"] == "green"
    assert d["level"] == 2
    assert d["maybe"] == "red"


def test_dump_config_with_enums_is_json_serializable_and_roundtrips():
    """``dump_config`` of enum fields is JSON-serializable and round-trips through the parser."""
    cfg = Cfg(color=Color.GREEN, level=Level.HIGH, maybe=Color.RED)
    dumped = dump_config(cfg)
    assert json.loads(json.dumps(dumped)) == {
        "class_name": "",
        "color": "green",
        "level": 2,
        "maybe": "red",
    }
    assert parse_config(Cfg, dumped) == cfg
