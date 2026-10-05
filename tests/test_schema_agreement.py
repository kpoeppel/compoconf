"""Check that :func:`to_json_schema` agrees with :func:`parse_config`.

The schema module documents that "the type mapping mirrors how parse_config interprets
annotations", but the two are separate implementations walking the same annotations, so nothing
stops them diverging. Tests elsewhere check the schema's *shape*; these check its *meaning* against
a real JSON Schema validator.

The direction that must hold is: **anything the schema accepts, parse_config accepts.** The reverse
is false by design -- by default parse_config coerces (``"5"`` becomes ``5`` for an ``int`` field)
while the schema describes the uncoerced form -- so it is checked under ``strict_types=True``, where
parse_config validates instead of coercing.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple, Union
from uuid import UUID

import pytest  # pylint: disable=E0401

# sibling helper module; mypy does not know pytest puts the tests directory on sys.path
from sample_configs import Color, Leaf, register_mixer  # type: ignore[import-not-found]  # pylint: disable=E0401

from compoconf.parsing import dump_config, parse_config
from compoconf.schema import to_json_schema

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema is needed to validate the emitted schemas")

# pylint: disable=C0115,C0116,W0212,W0621,W0613


# (label, annotation, values the schema should accept, values it should reject)
CASES = [
    ("int", int, [0, -3, 7], ["5", 1.5, None, [], {}]),
    ("float", float, [1.5, 0.0, 3], ["1.5", None, []]),
    ("str", str, ["", "s"], [5, None, []]),
    ("bool", bool, [True, False], ["true", 1, None]),
    ("optional-int", Optional[int], [3, None], ["3", 1.5]),
    ("literal", Literal["a", "b"], ["a", "b"], ["c", 1, None]),
    ("enum", Color, ["red", "blue"], ["green", "RED", None]),
    ("path", Path, ["/tmp/x", "rel"], [5, None]),
    ("datetime", datetime, ["2020-01-02T03:04:05"], [5, None]),
    ("date", date, ["2020-01-02"], [5, None]),
    ("time", time, ["03:04:05"], [5, None]),
    ("decimal", Decimal, ["1.25"], [None]),
    ("uuid", UUID, ["12345678-1234-5678-1234-567812345678"], [5, None]),
    ("list", list[int], [[], [1, 2]], [["1"], {}, None, 5]),
    ("typing-List", List[int], [[1]], [["x"]]),
    ("sequence", Sequence[int], [[1]], [["x"]]),
    ("set", set[int], [[], [1, 2]], [[1, 1], ["x"], None]),
    ("typing-Set", Set[int], [[1]], [[1, 1]]),
    ("dict", dict[str, int], [{}, {"k": 1}], [{"k": "1"}, [], None]),
    ("typing-Dict", Dict[str, int], [{"k": 1}], [{"k": "1"}]),
    ("tuple-fixed", tuple[int, str], [[1, "a"]], [[1], [1, "a", 2], ["1", "a"]]),
    ("tuple-variadic", tuple[int, ...], [[], [1, 2]], [["x"]]),
    ("typing-Tuple", Tuple[int], [[1]], [[1, 2]]),
    ("dataclass", Leaf, [{}, {"a": 2}, {"a": 2, "b": "y"}], [{"a": "2"}, {"nope": 1}, None, []]),
    ("list-of-dataclass", list[Leaf], [[{"a": 1}]], [[{"nope": 1}]]),
    ("dict-of-dataclass", dict[str, Leaf], [{"k": {"a": 1}}], [{"k": {"nope": 1}}]),
    ("union", Union[int, str], [1, "s"], [None, [], 1.5]),
    ("nested", dict[str, list[Leaf]], [{"k": [{"a": 1}]}], [{"k": [{"nope": 1}]}]),
    ("any", Any, [1, "s", None, [], {}], []),
]


def _validator(annotation):
    schema = to_json_schema(annotation)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


@pytest.mark.parametrize(("label", "annotation", "accepted", "rejected"), CASES, ids=[c[0] for c in CASES])
def test_schema_accepts_exactly_what_it_should(label, annotation, accepted, rejected):
    """Sanity-check the case table itself against the validator before using it below."""
    validator = _validator(annotation)
    for value in accepted:
        assert validator.is_valid(value), f"schema for {label} should accept {value!r}"
    for value in rejected:
        assert not validator.is_valid(value), f"schema for {label} should reject {value!r}"


@pytest.mark.parametrize(("label", "annotation", "accepted", "rejected"), CASES, ids=[c[0] for c in CASES])
def test_anything_the_schema_accepts_parse_config_accepts(label, annotation, accepted, rejected):
    """The schema must not promise more than the parser delivers.

    Checked with ``strict_types=True``: by default parse_config coerces, so it is *more* permissive
    than the schema, and the interesting direction is whether a schema-valid document can fail to
    parse.
    """
    for value in accepted:
        parse_config(annotation, value, strict_types=True)


# Two shapes do not survive validation of their own dump, for the same underlying reason: the dumped
# value is a Python container that JSON Schema does not consider an array.
#
#   * sets   -- dump as live set/frozenset objects, which json/yaml cannot represent at all
#   * tuples -- dump as Python tuples; json.dumps and yaml.safe_dump both write an array, but the
#               in-memory value is not one, so a validator rejects it and the dump is not a fixed
#               point through a file (a tuple comes back as a list).
#
# parse_config accepts an array for both annotations and to_json_schema declares an array for both,
# so only the dump side disagrees. Marked strict so that fixing the dump turns these green.
_DUMP_GAPS = {"set", "typing-Set", "tuple-fixed", "tuple-variadic", "typing-Tuple"}
_DUMP_CASES = [
    pytest.param(
        *case,
        id=case[0],
        marks=(
            [pytest.mark.xfail(strict=True, reason="dumped set/tuple is not a JSON array")]
            if case[0] in _DUMP_GAPS
            else []
        ),
    )
    for case in CASES
]


@pytest.mark.parametrize(("label", "annotation", "accepted", "rejected"), _DUMP_CASES)
def test_what_parse_config_accepts_dumps_back_to_something_schema_valid(label, annotation, accepted, rejected):
    """The round trip has to land inside the schema, or a dumped config fails its own validation."""
    validator = _validator(annotation)
    for value in accepted:
        dumped = dump_config(parse_config(annotation, value, strict_types=True))
        errors = list(validator.iter_errors(dumped))
        assert not errors, f"dump of {label} {value!r} -> {dumped!r} violates its own schema: {errors[0].message}"


def test_a_dumped_tuple_is_not_a_json_array():
    """Pins the gap above at the level of a single field, and that json/yaml still write it out."""

    @dataclass
    class WithTuple:
        dims: tuple[int, int] = (1, 1)

    dumped = dump_config(parse_config(WithTuple, {"dims": [2, 3]}))
    assert dumped == {"dims": (2, 3)}
    assert isinstance(dumped["dims"], tuple)
    # serializable, but not a fixed point: a tuple comes back from the file as a list
    yaml = pytest.importorskip("yaml")  # pylint: disable=W0621
    assert yaml.safe_load(yaml.safe_dump(dumped)) == {"dims": [2, 3]}
    # ... which still re-parses, so the config survives a file round trip even though the dump does not
    assert parse_config(WithTuple, yaml.safe_load(yaml.safe_dump(dumped))).dims == (2, 3)


# ---------------------------------------------------------------------- registry-backed configs


@pytest.fixture
def nested_schema(reset_registry):
    """A config tree with a cfgtype union, built per test so the registry reset cannot wipe it."""
    # not named ``mixer``: CPython evaluates ``x: ann = val`` by storing val *before* evaluating
    # ann, so a local shadowing the field name would already be None by then.
    registered = register_mixer()

    @dataclass
    class Block:
        mixer: registered.interface.cfgtype = None
        color: Color = Color.RED

    @dataclass
    class Stack:
        blocks: list[Block] = field(default_factory=list)
        dims: list[int] = field(default_factory=list)

    return Stack


def test_cfgtype_union_schema_accepts_what_parse_config_accepts(nested_schema):
    validator = _validator(nested_schema)
    data = {
        "blocks": [
            {"mixer": {"class_name": "Attn", "heads": 4}, "color": "blue"},
            {"mixer": {"class_name": "Conv", "kernel": 5}, "color": "red"},
        ],
        "dims": [2, 3],
    }
    assert validator.is_valid(data), list(validator.iter_errors(data))[0].message
    parsed = parse_config(nested_schema, data, strict_types=True)
    assert not list(validator.iter_errors(dump_config(parsed)))


def test_cfgtype_union_schema_rejects_an_unknown_class_name(nested_schema):
    validator = _validator(nested_schema)
    data = {"blocks": [{"mixer": {"class_name": "Nope"}}]}
    assert not validator.is_valid(data)
    with pytest.raises((ValueError, KeyError)):
        parse_config(nested_schema, data)


def test_cfgtype_union_schema_rejects_a_field_from_the_wrong_member(nested_schema):
    validator = _validator(nested_schema)
    data = {"blocks": [{"mixer": {"class_name": "Attn", "kernel": 5}}]}
    assert not validator.is_valid(data)
    with pytest.raises(ValueError):
        parse_config(nested_schema, data)


def test_schema_requires_the_fields_parse_config_requires():
    """A field with no default is required on both sides."""

    @dataclass
    class NeedsValue:
        must: int
        optional: str = "o"

    validator = _validator(NeedsValue)
    assert validator.is_valid({"must": 1})
    assert not validator.is_valid({"optional": "x"})
    with pytest.raises(ValueError, match="must"):
        parse_config(NeedsValue, {"optional": "x"})


# pylint: enable=C0115
# pylint: enable=C0116
# pylint: enable=W0212
# pylint: enable=W0621
# pylint: enable=W0613
