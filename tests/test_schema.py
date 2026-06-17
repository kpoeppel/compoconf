"""
Tests for :func:`compoconf.to_json_schema` -- JSON Schema (draft 2020-12) export.
"""

import enum
import json
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Tuple, TypeVar

import pytest  # pylint: disable=E0401

from compoconf.compoconf import ConfigInterface, RegistrableConfigInterface, register, register_interface
from compoconf.nonstrict_dataclass import NonStrictDataclass
from compoconf.schema import to_json_schema

_DRAFT = "https://json-schema.org/draft/2020-12/schema"


class Color(enum.Enum):
    """Plain enum used for enum-field schemas."""

    RED = "red"
    GREEN = "green"


# --------------------------------------------------------------------------- #
# Scalar / leaf types                                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "typ, expected",
    [
        (int, {"type": "integer"}),
        (float, {"type": "number"}),
        (str, {"type": "string"}),
        (bool, {"type": "boolean"}),
        (None, {"type": "null"}),
        (Any, {}),
    ],
)
def test_scalar_and_special_roots(typ, expected):
    """Primitive, ``None`` and ``Any`` roots map to their JSON Schema fragments."""
    schema = to_json_schema(typ)
    assert schema["$schema"] == _DRAFT
    leaf = {k: v for k, v in schema.items() if k != "$schema"}
    assert leaf == expected


def test_literal_and_enum():
    """``Literal`` and ``Enum`` become ``enum`` schemas (enum uses member values)."""
    assert to_json_schema(Literal["a", "b"])["enum"] == ["a", "b"]
    assert to_json_schema(Color)["enum"] == ["red", "green"]


def test_unknown_type_is_unconstrained():
    """A type with no specific mapping yields an unconstrained (empty) schema."""
    schema = to_json_schema(object)
    assert set(schema) == {"$schema"}


def test_non_type_annotation_is_unconstrained():
    """A non-type, unrecognised annotation also yields an unconstrained schema."""
    schema = to_json_schema("not-a-type")  # not a class and not a known typing construct
    assert set(schema) == {"$schema"}


# --------------------------------------------------------------------------- #
# Collections                                                                  #
# --------------------------------------------------------------------------- #
def test_list_and_sequence_and_dict():
    """Lists/dicts map to array/object schemas with the right item/value schemas."""
    assert to_json_schema(list[int])["items"] == {"type": "integer"}
    assert to_json_schema(list[int])["type"] == "array"
    dct = to_json_schema(dict[str, float])
    assert dct["type"] == "object"
    assert dct["additionalProperties"] == {"type": "number"}


def test_set_is_unique_array():
    """Sets / frozensets become arrays with ``uniqueItems``."""
    for typ in (set[str], frozenset[int]):
        schema = to_json_schema(typ)
        assert schema["type"] == "array"
        assert schema["uniqueItems"] is True


def test_tuple_fixed_and_variadic_and_bare():
    """Fixed tuples use prefixItems; ``(T, ...)`` uses items; an arg-less tuple is any array."""
    fixed = to_json_schema(tuple[int, str])
    assert fixed["prefixItems"] == [{"type": "integer"}, {"type": "string"}]
    assert fixed["minItems"] == fixed["maxItems"] == 2

    variadic = to_json_schema(tuple[int, ...])
    assert variadic["items"] == {"type": "integer"}
    assert "prefixItems" not in variadic

    bare = to_json_schema(Tuple)  # typing.Tuple has origin=tuple but no args
    assert bare == {"$schema": _DRAFT, "type": "array"}


def test_dict_without_value_type_is_unconstrained_values():
    """An arg-less ``Dict`` allows any value."""
    schema = to_json_schema(Dict)  # typing.Dict has origin=dict but no args
    assert schema["additionalProperties"] == {}


def test_typevar_constraints_become_anyof():
    """A constrained ``TypeVar`` maps to an ``anyOf`` of its constraints."""
    constrained = TypeVar("constrained", int, str)
    assert to_json_schema(constrained)["anyOf"] == [{"type": "integer"}, {"type": "string"}]


# --------------------------------------------------------------------------- #
# Unions                                                                       #
# --------------------------------------------------------------------------- #
def test_optional_union():
    """``X | None`` becomes ``anyOf`` of the member and null."""
    schema = to_json_schema(Optional[int])
    assert {"type": "integer"} in schema["anyOf"]
    assert {"type": "null"} in schema["anyOf"]


# --------------------------------------------------------------------------- #
# Dataclasses                                                                  #
# --------------------------------------------------------------------------- #
@dataclass
class Inner(ConfigInterface):
    """Nested config."""

    k: int = 1


@dataclass
class Outer(ConfigInterface):
    """Config with a required field, defaults, and a nested config."""

    n: int  # required (no default)
    name: str = "x"
    inner: Optional[Inner] = None


def test_dataclass_uses_defs_and_ref():
    """Dataclasses are placed in ``$defs`` and referenced via ``$ref``."""
    schema = to_json_schema(Outer)
    assert schema["$ref"] == "#/$defs/Outer"
    assert "Outer" in schema["$defs"]
    assert "Inner" in schema["$defs"]  # nested dataclass also defined
    outer = schema["$defs"]["Outer"]
    assert outer["type"] == "object"
    assert outer["required"] == ["n"]  # only the field without a default
    assert outer["properties"]["inner"]["anyOf"] == [{"$ref": "#/$defs/Inner"}, {"type": "null"}]


def test_unregistered_config_class_name_is_string():
    """An unregistered ConfigInterface gets a free-form ``class_name`` string property."""
    schema = to_json_schema(Inner)
    assert schema["$defs"]["Inner"]["properties"]["class_name"] == {"type": "string"}
    assert schema["$defs"]["Inner"]["additionalProperties"] is False


@dataclass
class Recur(ConfigInterface):
    """Self-referential config (module-level so the forward ref resolves)."""

    me: Optional["Recur"] = None


def test_recursive_dataclass_terminates():
    """A self-referential dataclass produces a single $def with a self $ref."""
    schema = to_json_schema(Recur)
    assert schema["$defs"]["Recur"]["properties"]["me"]["anyOf"] == [
        {"$ref": "#/$defs/Recur"},
        {"type": "null"},
    ]


def test_nonstrict_allows_additional_properties():
    """A NonStrictDataclass schema permits extra properties."""

    @dataclass(init=False)
    class Loose(NonStrictDataclass):
        """Non-strict config."""

        a: int = 0

    schema = to_json_schema(Loose)
    assert schema["$defs"]["Loose"]["additionalProperties"] is True


def test_duplicate_class_names_are_disambiguated():
    """Two distinct dataclasses sharing a ``__name__`` get distinct $def keys."""

    def _make():
        @dataclass
        class Dup(ConfigInterface):
            """Factory-made dataclass; two instances share the name 'Dup'."""

            v: int = 0

        return Dup

    dup_a = _make()
    dup_b = _make()

    @dataclass
    class Holder(ConfigInterface):
        """Holds two distinct same-named configs."""

        a: Optional[dup_a] = None
        b: Optional[dup_b] = None

    schema = to_json_schema(Holder)
    assert "Dup" in schema["$defs"]
    assert "Dup_2" in schema["$defs"]


# --------------------------------------------------------------------------- #
# Registry unions (cfgtype) + class_name discrimination                        #
# --------------------------------------------------------------------------- #
def test_cfgtype_union_and_class_name_const(reset_registry):  # pylint: disable=unused-argument
    """``Interface.cfgtype`` becomes an anyOf of registered configs, each pinning class_name."""

    @register_interface
    class ModelInterface(RegistrableConfigInterface):
        """Interface fixture."""

    @dataclass
    class MyObjConfig(ConfigInterface):
        """Registered config."""

        h: int = 8

    @register
    class MyObj(ModelInterface):  # pylint: disable=unused-variable
        """Impl."""

        config_class = MyObjConfig

    @dataclass
    class Container(ConfigInterface):
        """Holds a registry-typed field."""

        model: ModelInterface.cfgtype = None

    schema = to_json_schema(Container)
    model_schema = schema["$defs"]["Container"]["properties"]["model"]
    assert model_schema["anyOf"] == [{"$ref": "#/$defs/MyObjConfig"}]
    assert schema["$defs"]["MyObjConfig"]["properties"]["class_name"] == {"const": "MyObj"}


# --------------------------------------------------------------------------- #
# Output is real, JSON-serializable, valid schema                              #
# --------------------------------------------------------------------------- #
def test_schema_is_json_serializable():
    """The produced schema is plain JSON-serializable data."""
    assert json.loads(json.dumps(to_json_schema(Outer)))["$ref"] == "#/$defs/Outer"


def test_title_option():
    """The ``title`` argument is set on the root schema."""
    assert to_json_schema(int, title="MyInt")["title"] == "MyInt"


def test_generated_schema_is_valid_and_accepts_dumps():
    """Meta-validate against jsonschema and confirm a compoconf dump validates (if installed)."""
    jsonschema = pytest.importorskip("jsonschema")
    from compoconf.parsing import dump_config  # pylint: disable=import-outside-toplevel

    schema = to_json_schema(Outer)
    jsonschema.Draft202012Validator.check_schema(schema)
    dumped = dump_config(Outer(n=3, name="a", inner=Inner(k=2)))
    assert not list(jsonschema.Draft202012Validator(schema).iter_errors(dumped))
