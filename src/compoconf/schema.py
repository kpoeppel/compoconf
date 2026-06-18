"""
JSON Schema export for compoconf configuration types.

:func:`to_json_schema` converts a config class (or any supported type annotation) into a JSON
Schema (draft 2020-12) document -- useful for editor validation/autocomplete and external tooling.
The type mapping mirrors how :func:`compoconf.parse_config` interprets annotations:

- ``int`` -> ``{"type": "integer"}``, ``float`` -> ``{"type": "number"}``, ``str`` -> string,
  ``bool`` -> boolean, ``None`` -> ``{"type": "null"}``, ``Any`` -> ``{}`` (unconstrained).
- ``Literal[...]`` and ``enum.Enum`` -> ``{"enum": [...]}`` (enum members use their *values*,
  matching serialization).
- ``list``/``Sequence`` / ``set`` / ``frozenset`` / ``tuple`` / ``dict`` -> array/object schemas.
- ``Union`` (incl. ``X | None``) and ``cfgtype`` unions -> ``{"anyOf": [...]}``.
- dataclasses -> ``{"type": "object", ...}`` placed in ``$defs`` and referenced via ``$ref``
  (so shared and recursive configs are handled).
"""

from collections.abc import Sequence as AbcSequence
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, Literal, Optional, Union, get_args, get_origin, get_type_hints

from compoconf.compoconf import LazyConfigUnion, _LazyOr
from compoconf.extension_types import extension_schema
from compoconf.nonstrict_dataclass import _NonStrictDataclassBase

_DRAFT = "https://json-schema.org/draft/2020-12/schema"
_NONE_TYPE = type(None)
_PRIMITIVES = {bool: "boolean", int: "integer", float: "number", str: "string"}


class _SchemaBuilder:
    """Builds a JSON Schema, accumulating dataclass object schemas under ``$defs``."""

    def __init__(self):
        self.defs: dict = {}
        self._key_for: dict = {}  # id(dataclass) -> def key
        self._class_for_key: dict = {}  # def key -> dataclass (collision detection)

    def schema_for(self, typ) -> dict:  # pylint: disable=too-many-return-statements
        """Return the JSON Schema fragment for a single type/annotation."""
        if typ is None or typ is _NONE_TYPE:
            return {"type": "null"}
        if typ is Any:
            return {}

        ext = extension_schema(typ)
        if ext is not None:
            return ext

        origin = get_origin(typ)
        args = get_args(typ)

        if origin is Literal:
            return {"enum": list(args)}
        if origin in (Union, UnionType):
            return {"anyOf": [self.schema_for(arg) for arg in args]}

        # Lazy config unions (``Interface.cfgtype``) and TypeVar-style constraints.
        if isinstance(typ, (LazyConfigUnion, _LazyOr)):
            members = getattr(typ, "__constraints__", None) or getattr(typ, "__args__", ()) or ()
            return {"anyOf": [self.schema_for(member) for member in members]}
        if getattr(typ, "__constraints__", None):
            return {"anyOf": [self.schema_for(member) for member in typ.__constraints__]}

        collection = self._collection_schema(origin, args)
        if collection is not None:
            return collection

        if isinstance(typ, type):
            if is_dataclass(typ):
                return self._ref_for_dataclass(typ)
            if issubclass(typ, Enum):
                return {"enum": [member.value for member in typ]}
            if typ in _PRIMITIVES:
                return {"type": _PRIMITIVES[typ]}

        # Unknown / unconstrained type: permissive empty schema.
        return {}

    def _collection_schema(self, origin, args) -> Optional[dict]:  # pylint: disable=too-many-return-statements
        """Schema for list/set/frozenset/tuple/dict origins, or ``None`` if not a collection."""
        if origin in (list, AbcSequence):
            item = args[0] if args else Any
            return {"type": "array", "items": self.schema_for(item)}
        if origin in (set, frozenset):
            item = args[0] if args else Any
            return {"type": "array", "items": self.schema_for(item), "uniqueItems": True}
        if origin is tuple:
            if not args:
                return {"type": "array"}
            if len(args) == 2 and args[1] is Ellipsis:
                return {"type": "array", "items": self.schema_for(args[0])}
            prefix = [self.schema_for(arg) for arg in args]
            return {"type": "array", "prefixItems": prefix, "minItems": len(prefix), "maxItems": len(prefix)}
        if origin is dict:
            value = args[1] if len(args) == 2 else Any
            return {"type": "object", "additionalProperties": self.schema_for(value)}
        return None

    def _ref_for_dataclass(self, dataclass_type) -> dict:
        """Register ``dataclass_type``'s object schema under ``$defs`` and return a ``$ref``."""
        existing = self._key_for.get(id(dataclass_type))
        if existing is not None:
            return {"$ref": f"#/$defs/{existing}"}

        key = dataclass_type.__name__
        counter = 2
        while key in self._class_for_key and self._class_for_key[key] is not dataclass_type:
            key = f"{dataclass_type.__name__}_{counter}"
            counter += 1

        self._key_for[id(dataclass_type)] = key
        self._class_for_key[key] = dataclass_type
        self.defs[key] = {}  # placeholder so recursive references resolve
        self.defs[key] = self._object_schema(dataclass_type)
        return {"$ref": f"#/$defs/{key}"}

    def _object_schema(self, dataclass_type) -> dict:
        """Build the ``{"type": "object", ...}`` schema for a dataclass."""
        properties: dict = {}
        required: list = []
        hints = get_type_hints(dataclass_type)
        for field_info in fields(dataclass_type):
            if field_info.name in ("_extras", "_non_strict"):
                continue  # internal bookkeeping fields of (Frozen)NonStrictDataclass
            if field_info.name == "class_name":
                # ``class_name`` is always present in compoconf dumps; pin it to the registered
                # name (so unions discriminate) or allow any string for unregistered configs.
                class_name = getattr(dataclass_type, "class_name", "")
                if isinstance(class_name, str) and class_name:
                    properties["class_name"] = {"const": class_name}
                else:
                    properties["class_name"] = {"type": "string"}
                continue
            properties[field_info.name] = self.schema_for(hints.get(field_info.name, Any))
            if field_info.init and field_info.default is MISSING and field_info.default_factory is MISSING:
                required.append(field_info.name)

        schema: dict = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        schema["additionalProperties"] = issubclass(dataclass_type, _NonStrictDataclassBase)
        return schema


def to_json_schema(config_class, *, title: Optional[str] = None) -> dict:
    """
    Generate a JSON Schema (draft 2020-12) for a compoconf config class or type annotation.

    Args:
        config_class: A dataclass config type, or any annotation supported by
            :func:`compoconf.parse_config` (primitives, ``Literal``, ``Enum``, collections,
            ``Union`` / ``cfgtype``, ...).
        title: Optional ``title`` to set on the root schema.

    Returns:
        A JSON-serializable ``dict`` representing the schema. Dataclass object schemas are placed
        under ``$defs`` and referenced with ``$ref`` (so recursive/shared configs are handled).

    Example:
        schema = to_json_schema(ModelConfig)
        json.dumps(schema)  # ready for editors / validators
    """
    builder = _SchemaBuilder()
    root = builder.schema_for(config_class)
    schema: dict = {"$schema": _DRAFT}
    if title is not None:
        schema["title"] = title
    if builder.defs:
        schema["$defs"] = builder.defs
    schema.update(root)
    return schema
