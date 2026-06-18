"""
Built-in handling for common scalar stdlib types in configs.

Supports ``pathlib.Path``, ``datetime`` / ``date`` / ``time``, ``decimal.Decimal`` and
``uuid.UUID`` symmetrically: each has a *parser* (string/value -> instance), a *serializer*
(instance -> JSON-safe value) and a JSON Schema fragment. These keep :func:`compoconf.parse_config`,
:func:`compoconf.asdict` and :func:`compoconf.to_json_schema` in sync. JSON/YAML have no native
representation for these types, so they round-trip through strings.

The :data:`_EXTENSION_TYPES` table is intentionally easy to extend with further scalar types.
"""

import datetime as _datetime
from decimal import Decimal
from pathlib import Path, PurePath
from typing import Any, Callable, Optional
from uuid import UUID


def _parse_path(value: Any):
    """Parse a filesystem path (passes existing path objects through)."""
    return value if isinstance(value, PurePath) else Path(value)


def _parse_datetime(value: Any):
    """Parse an ISO-8601 datetime string (passes existing datetimes through)."""
    return value if isinstance(value, _datetime.datetime) else _datetime.datetime.fromisoformat(value)


def _parse_date(value: Any):
    """Parse an ISO-8601 date (a datetime is narrowed to its date; strings via fromisoformat)."""
    if isinstance(value, _datetime.datetime):
        return value.date()
    return value if isinstance(value, _datetime.date) else _datetime.date.fromisoformat(value)


def _parse_time(value: Any):
    """Parse an ISO-8601 time string (passes existing times through)."""
    return value if isinstance(value, _datetime.time) else _datetime.time.fromisoformat(value)


def _parse_decimal(value: Any):
    """Parse a Decimal, going via ``str`` so floats keep their printed precision."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _parse_uuid(value: Any):
    """Parse a UUID from its string form (passes existing UUIDs through)."""
    return value if isinstance(value, UUID) else UUID(value)


# Each entry: (annotation type, instance-check type, parse fn, dump fn, JSON Schema fragment).
# ``datetime`` precedes ``date`` because it is a subclass and must match first when dumping.
_EXTENSION_TYPES: list = [
    (Path, PurePath, _parse_path, str, {"type": "string"}),
    (
        _datetime.datetime,
        _datetime.datetime,
        _parse_datetime,
        lambda v: v.isoformat(),
        {"type": "string", "format": "date-time"},
    ),
    (_datetime.date, _datetime.date, _parse_date, lambda v: v.isoformat(), {"type": "string", "format": "date"}),
    (_datetime.time, _datetime.time, _parse_time, lambda v: v.isoformat(), {"type": "string", "format": "time"}),
    (Decimal, Decimal, _parse_decimal, str, {"type": "string"}),
    (UUID, UUID, _parse_uuid, str, {"type": "string", "format": "uuid"}),
]


def extension_parser(config_class) -> Optional[Callable[[Any], Any]]:
    """Return the parse function for ``config_class`` if it is a supported extension type."""
    for ann_type, _inst, parse_fn, _dump, _schema in _EXTENSION_TYPES:
        if config_class is ann_type:
            return parse_fn
    return None


def dump_extension(obj: Any):
    """Return ``(True, json_safe_value)`` if ``obj`` is a supported extension instance, else ``(False, None)``."""
    for _ann, inst_type, _parse, dump_fn, _schema in _EXTENSION_TYPES:
        if isinstance(obj, inst_type):
            return True, dump_fn(obj)
    return False, None


def extension_schema(config_class) -> Optional[dict]:
    """Return the JSON Schema fragment for ``config_class`` if it is a supported extension type."""
    for ann_type, _inst, _parse, _dump, schema in _EXTENSION_TYPES:
        if config_class is ann_type:
            return dict(schema)
    return None
