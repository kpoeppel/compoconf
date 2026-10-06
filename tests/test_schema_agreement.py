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

import pytest  # pylint: disable=E0401

# sibling helper module; mypy does not know pytest puts the tests directory on sys.path
from sample_configs import SHAPES, Color, register_mixer  # type: ignore[import-not-found]  # pylint: disable=E0401

from compoconf.parsing import dump_config, parse_config
from compoconf.schema import to_json_schema

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema is needed to validate the emitted schemas")
# pylint: disable=C0115,C0116,W0212,W0621,W0613


def _validator(annotation):
    schema = to_json_schema(annotation)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


@pytest.mark.parametrize("shape", SHAPES, ids=[s.label for s in SHAPES])
def test_schema_accepts_exactly_what_it_should(shape):
    """Sanity-check the case table itself against the validator before using it below."""
    validator = _validator(shape.annotation)
    for value in shape.accepted:
        assert validator.is_valid(value), f"schema for {shape.label} should accept {value!r}"
    for value in shape.rejected:
        assert not validator.is_valid(value), f"schema for {shape.label} should reject {value!r}"


@pytest.mark.parametrize("shape", SHAPES, ids=[s.label for s in SHAPES])
def test_anything_the_schema_accepts_parse_config_accepts(shape):
    """The schema must not promise more than the parser delivers.

    Checked with ``strict_types=True``: by default parse_config coerces, so it is *more* permissive
    than the schema, and the interesting direction is whether a schema-valid document can fail to
    parse.
    """
    for value in shape.accepted:
        parse_config(shape.annotation, value, strict_types=True)


@pytest.mark.parametrize("shape", SHAPES, ids=[s.label for s in SHAPES])
def test_what_parse_config_accepts_dumps_back_to_something_schema_valid(shape):
    """The round trip has to land inside the schema, or a dumped config fails its own validation."""
    validator = _validator(shape.annotation)
    for value in shape.accepted:
        dumped = dump_config(parse_config(shape.annotation, value, strict_types=True))
        errors = list(validator.iter_errors(dumped))
        assert not errors, f"dump of {shape.label} {value!r} -> {dumped!r} violates its own schema: {errors[0].message}"


def test_a_dumped_tuple_validates_against_its_own_schema():
    """The schema says "array" and the dump is now one, so a dumped config passes its own schema."""

    @dataclass
    class WithTuple:
        dims: tuple[int, int] = (1, 1)

    validator = _validator(WithTuple)
    dumped = dump_config(parse_config(WithTuple, {"dims": [2, 3]}))
    assert dumped == {"dims": [2, 3]}
    assert not list(validator.iter_errors(dumped))
    # and the dump is a fixed point through a file
    yaml = pytest.importorskip("yaml")
    assert yaml.safe_load(yaml.safe_dump(dumped)) == dumped
    assert parse_config(WithTuple, dumped).dims == (2, 3)


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
