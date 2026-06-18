"""
Tests for extension scalar types: ``pathlib.Path``, ``datetime`` / ``date`` / ``time``,
``decimal.Decimal`` and ``uuid.UUID`` -- parsing, serialization, JSON Schema, and round-trips.
"""

import datetime
import json
import pathlib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface
from compoconf.extension_types import dump_extension, extension_parser, extension_schema
from compoconf.parsing import dump_config, parse_config
from compoconf.schema import to_json_schema

_UID = "12345678-1234-5678-1234-567812345678"


# --------------------------------------------------------------------------- #
# Parsing (from string / value form)                                          #
# --------------------------------------------------------------------------- #
def test_parse_path():
    """Path parses from a string and passes existing path objects through."""
    parsed = parse_config(pathlib.Path, "a/b/c.txt")
    assert isinstance(parsed, pathlib.PurePath)
    assert str(parsed) == "a/b/c.txt"
    existing = pathlib.Path("x")
    assert parse_config(pathlib.Path, existing) is existing


def test_parse_datetime_date_time():
    """datetime/date/time parse from ISO strings."""
    assert parse_config(datetime.datetime, "2020-01-02T03:04:05") == datetime.datetime(2020, 1, 2, 3, 4, 5)
    assert parse_config(datetime.date, "2021-06-07") == datetime.date(2021, 6, 7)
    assert parse_config(datetime.time, "08:09:10") == datetime.time(8, 9, 10)


def test_parse_decimal_and_uuid():
    """Decimal and UUID parse from their string forms (Decimal keeps printed precision)."""
    assert parse_config(Decimal, "1.50") == Decimal("1.50")
    assert parse_config(Decimal, 0.1) == Decimal("0.1")  # via str(float), no binary noise
    assert parse_config(uuid.UUID, _UID) == uuid.UUID(_UID)


def test_parse_invalid_extension_raises():
    """A malformed value yields a clear ValueError."""
    with pytest.raises(ValueError, match="datetime"):
        parse_config(datetime.datetime, "not-a-date")


# --------------------------------------------------------------------------- #
# Direct parse-function branches (instance passthrough, special cases)         #
# --------------------------------------------------------------------------- #
def test_parser_passthrough_branches():
    """Each parser returns an already-correct instance unchanged."""
    now = datetime.datetime(2020, 1, 1, 2, 3)
    assert extension_parser(datetime.datetime)(now) is now
    today = datetime.date(2020, 1, 1)
    assert extension_parser(datetime.date)(today) is today
    noon = datetime.time(12)
    assert extension_parser(datetime.time)(noon) is noon
    dec = Decimal("3")
    assert extension_parser(Decimal)(dec) is dec
    uid = uuid.UUID(_UID)
    assert extension_parser(uuid.UUID)(uid) is uid


def test_date_parser_narrows_datetime():
    """Parsing a ``datetime`` into a ``date`` field narrows it to the date part."""
    result = extension_parser(datetime.date)(datetime.datetime(2020, 5, 6, 7, 8))
    assert result == datetime.date(2020, 5, 6)
    assert not isinstance(result, datetime.datetime)


def test_extension_parser_returns_none_for_other_types():
    """Non-extension types have no extension parser."""
    assert extension_parser(int) is None
    assert extension_parser(str) is None


# --------------------------------------------------------------------------- #
# Serialization (dump_extension)                                              #
# --------------------------------------------------------------------------- #
def test_dump_extension_values():
    """Each extension instance dumps to a JSON-safe form."""
    assert dump_extension(pathlib.Path("x/y")) == (True, "x/y")
    assert dump_extension(datetime.datetime(2020, 1, 2, 3, 4, 5)) == (True, "2020-01-02T03:04:05")
    assert dump_extension(datetime.date(2021, 6, 7)) == (True, "2021-06-07")
    assert dump_extension(datetime.time(8, 9, 10)) == (True, "08:09:10")
    assert dump_extension(Decimal("1.50")) == (True, "1.50")
    assert dump_extension(uuid.UUID(_UID)) == (True, _UID)


def test_dump_extension_passes_through_non_extensions():
    """A non-extension object is reported as not handled."""
    assert dump_extension(42) == (False, None)
    assert dump_extension("plain") == (False, None)


def test_datetime_dumps_before_date():
    """A datetime instance serializes as a datetime (not narrowed to date) despite subclassing."""
    handled, value = dump_extension(datetime.datetime(2020, 1, 2, 3, 4, 5))
    assert handled and "T" in value  # full datetime isoformat, not just the date


# --------------------------------------------------------------------------- #
# JSON Schema                                                                  #
# --------------------------------------------------------------------------- #
def test_extension_schema_fragments():
    """Extension types map to string schemas (with formats where applicable)."""
    assert extension_schema(pathlib.Path) == {"type": "string"}
    assert extension_schema(datetime.datetime) == {"type": "string", "format": "date-time"}
    assert extension_schema(datetime.date) == {"type": "string", "format": "date"}
    assert extension_schema(datetime.time) == {"type": "string", "format": "time"}
    assert extension_schema(Decimal) == {"type": "string"}
    assert extension_schema(uuid.UUID) == {"type": "string", "format": "uuid"}
    assert extension_schema(int) is None


def test_to_json_schema_uses_extension_fragments():
    """``to_json_schema`` emits the extension fragments for fields."""
    schema = to_json_schema(pathlib.Path)
    assert schema["type"] == "string"


# --------------------------------------------------------------------------- #
# End-to-end round-trip through a config                                       #
# --------------------------------------------------------------------------- #
@dataclass
class ExtCfg(ConfigInterface):
    """Config exercising every extension type."""

    p: pathlib.Path = pathlib.Path(".")
    dt: datetime.datetime = datetime.datetime(2020, 1, 1)
    d: datetime.date = datetime.date(2020, 1, 1)
    t: datetime.time = datetime.time(0, 0)
    dec: Decimal = Decimal("0")
    uid: Optional[uuid.UUID] = None


def test_config_roundtrip_is_json_safe_and_preserves_types():
    """A config with extension fields dumps to JSON and round-trips back to the right types."""
    orig = ExtCfg(
        p=pathlib.Path("x/y.txt"),
        dt=datetime.datetime(2020, 1, 2, 3, 4, 5),
        d=datetime.date(2021, 6, 7),
        t=datetime.time(8, 9, 10),
        dec=Decimal("1.50"),
        uid=uuid.UUID(_UID),
    )
    dumped = dump_config(orig)
    json.dumps(dumped)  # must not raise
    reparsed = parse_config(ExtCfg, dumped)
    assert reparsed == orig
    assert isinstance(reparsed.p, pathlib.PurePath)
    assert isinstance(reparsed.dec, Decimal)
    assert isinstance(reparsed.uid, uuid.UUID)
